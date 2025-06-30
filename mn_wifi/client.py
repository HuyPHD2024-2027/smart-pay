from __future__ import annotations

"""FastPay client implementation capable of using multiple network transports (TCP, UDP, or Wi-Fi Direct).

This module provides a fully-typed, extensible client that mirrors part of the behaviour of the
original Rust `client.rs` while adapting it to a Pythonic environment running inside
`mininet-wifi`.  The client is transport-agnostic: it delegates all network operations to a
`NetworkTransport` implementation so that the same logic can be re-used with raw TCP sockets,
UDP datagrams, or the specialised `WiFiInterface` already available in the code-base for
Wi-Fi Direct communication.

Only a subset of the full FastPay protocol is currently supported (transfer initiation and
response handling).  The structure, however, is designed for easy future extension to cover the
entire API surface of the Rust client, including confirmation orders, certificate management, and
persistent balance tracking.
"""

import time
import threading
from queue import Queue
from typing import Dict, Optional, List
from uuid import UUID, uuid4

from mn_wifi.baseTypes import (
    Address,
    ClientState,
    NodeType,
    TransferOrder,
)
from mn_wifi.messages import (
    Message,
    MessageType,
    TransferRequestMessage,
    TransferResponseMessage,
)
from mn_wifi.node import Station
from mn_wifi.transport import NetworkTransport, TransportKind
from mn_wifi.tcp import TCPTransport
from mn_wifi.udp import UDPTransport
from mn_wifi.wifiDirect import WiFiDirectTransport
from mn_wifi.clientLogger import ClientLogger
from mn_wifi.baseTypes import KeyPair, AuthorityName
from mn_wifi.authority import ConfirmationOrder, ConfirmationRequestMessage, TransactionStatus

class Client(Station):
    """Client node which can be added to a *mininet-wifi* topology using *addStation*.

    The class embeds the previously standalone FastPay client logic while extending
    :class:`mn_wifi.node.Station` so that it participates in the wireless network simulation
    natively.  Upon construction the caller may choose one of the supported transport kinds or
    inject an already configured :pydata:`NetworkTransport` instance.
    """

    def __init__(
        self,
        name: str,
        transport_kind: TransportKind = TransportKind.TCP,
        transport: Optional[NetworkTransport] = None,
        ip: str = "10.0.0.100/8",
        port: int = 9000,
        position: Optional[List[float]] = None,
        **station_params,
    ) -> None:
        """Create a new client station.

        Args:
            name:          Identifier for the station (e.g., *"user1"*).
            transport_kind: Which built-in transport to create when *transport* is *None*.
            transport:     Custom transport instance.  When provided *transport_kind* is ignored.
            ip:            IP address in CIDR notation (defaults to *10.0.0.100/8*).
            port:          TCP/UDP port on which the client will listen for replies.
            position:      Optional initial position \[x, y, z].
            **station_params: Additional arguments forwarded to :class:`mn_wifi.node.Station`.
        """

        # -------------------------------------------------------------------------------------
        # Initialise the underlying Station
        # -------------------------------------------------------------------------------------
        defaults = {
            "ip": ip,
            "range": 100,
        }
        defaults.update(station_params)
        super().__init__(name, **defaults)  # type: ignore[arg-type]

        self.name = name
        # -------------------------------------------------------------------------------------
        # FastPay-specific pieces
        # -------------------------------------------------------------------------------------
        self.address = Address(
            node_id=name,
            ip_address=ip.split("/")[0],
            port=port,
            node_type=NodeType.CLIENT,
        )

        self.p2p_connections: Dict[str, Address] = {}
        self.message_queue: Queue[Message] = Queue()

        # Initialise client state with zero balance and a placeholder secret key.
        self.state = ClientState(
            name=name,
            address=self.address,
            balance=0,
            secret=KeyPair("secret-placeholder"),
            sequence_number=1,
            pending_transfer=None,
            committee=[],
            sent_certificates=[],
            received_certificates={},
        )

        # ------------------------------------------------------------------
        # Transport factory --------------------------------------------------
        # ------------------------------------------------------------------
        if transport is not None:
            self.transport = transport
        else:
            if transport_kind == TransportKind.TCP:
                self.transport = TCPTransport(self, self.address)
            elif transport_kind == TransportKind.UDP:
                self.transport = UDPTransport(self, self.address)
            elif transport_kind == TransportKind.WIFI_DIRECT:
                self.transport = WiFiDirectTransport(self, self.address)
            else:
                raise ValueError(f"Unsupported transport kind: {transport_kind}")

        # Logger -------------------------------------------------------------
        self.logger = ClientLogger(name)

        # Runtime control flag ----------------------------------------------
        self._running = False
        self._message_handler_thread: Optional[threading.Thread] = None

    def start_fastpay_services(self) -> bool:
        """Boot-strap background processing threads and ready the chosen transport.

        The method preserves the previous external behaviour: it must be called explicitly after
        the authority instance is added to Mininet-WiFi so that the node's namespace exists.
        """

        # Connect transport (if the implementation supports/needs it)
        if hasattr(self.transport, "connect"):
            try:
                if not self.transport.connect():  # type: ignore[attr-defined]
                    self.logger.error("Failed to connect transport")
                    return False
            except Exception as exc:  # pragma: no cover
                self.logger.error(f"Transport connect error: {exc}")
                return False

        self._running = True

        # Spawn background threads -----------------------------------------------------------
        self._message_handler_thread = threading.Thread(
            target=self._message_handler_loop,
            daemon=True,
        )
        self._message_handler_thread.start()

        self.logger.info(f"Client {self.name} started successfully")
        return True
    
    def stop_fastpay_services(self) -> None:
        """Stop the FastPay authority services."""
        self._running = False
        if hasattr(self.transport, "disconnect"):
            try:
                self.transport.disconnect()  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover
                pass
        
        if self._message_handler_thread:
            self._message_handler_thread.join(timeout=5.0)
        self.logger.info(f"Client {self.name} stopped")

    def transfer(
        self,
        recipient: str,
        amount: int,
    ) -> bool:
        """Broadcast a *transfer order* to the given *authorities*.

        The method uses a **best-effort** strategy similar to the original Rust implementation:
        a quorum is considered reached once *2/3 + 1* successful responses are collected.

        Args:
            recipient: Recipient account identifier.
            amount: Amount to transfer.

        Returns:
            *True* when sending the transfer request, *False* otherwise.
        """
        order = TransferOrder(
            order_id=uuid4(),
            sender=self.state.name,
            recipient=recipient,
            amount=amount,
            sequence_number=self.state.sequence_number,
            timestamp=time.time(),
            signature=self.state.secret,  # TODO: cryptographic signatures
        )
        request = TransferRequestMessage(transfer_order=order)
        # Add the transfer order to the pending transfer list
        self.state.pending_transfer = order

        message = Message(
            message_id=uuid4(),
            message_type=MessageType.TRANSFER_REQUEST,
            sender=self.state.address,
            recipient=None,  # Filled per authority below
            timestamp=time.time(),
            payload=request.to_payload(),
        )
        
        return self._broadcast_transfer_request(message)
    
    def _broadcast_transfer_request(self, transfer_request: Message) -> bool:
        """Broadcast a transfer request to all authorities."""
        self.logger.info(
            f"Broadcasting transfer request to {len(self.state.committee)} authorities"
        )

        successes = 0
        for index, auth in enumerate(self.state.committee):
            # Create a *fresh* message per authority so that we do not overwrite
            # the *recipient* field of a previously sent instance.
            msg = Message(
                message_id=uuid4(),
                message_type=transfer_request.message_type,
                sender=transfer_request.sender,
                recipient=auth.address,
                timestamp=time.time(),
                payload=transfer_request.payload,
            )

            if self.transport.send_message(msg, auth.address):
                successes += 1
            else:
                self.logger.warning(f"Failed to send to authority {auth.name}")

        if successes == 0:
            self.logger.error("Failed to send transfer request to any authority")
            return False

        self.logger.info(f"Transfer request delivered to {successes} / {len(self.state.committee)} authorities")
        return True
    
    def _validate_transfer_response(self, transfer_response: TransferResponseMessage) -> bool:
        """Validate a transfer response.
        
        Args:
            transfer_response: Transfer response to validate
            
        Returns:
            True if valid, False otherwise
        """
        if transfer_response.transfer_order.sender != self.state.name:
            self.logger.error(f"Transfer {transfer_response.transfer_order.order_id} failed: sender mismatch")
            return False
        
        if transfer_response.transfer_order.sequence_number != self.state.sequence_number:
            self.logger.error(f"Transfer {transfer_response.transfer_order.order_id} failed: sequence number mismatch")
            return False

        # TODO: check if the transfer order signature is valid
        return True
    
    def handle_transfer_response(self, transfer_response: TransferResponseMessage) -> bool:
        """Handle transfer response from authority.
        
        Args:
            transfer_response: Transfer response to process
            
        Returns:
            True if handled successfully, False otherwise
        """
        try:
            if not self._validate_transfer_response(transfer_response):
                return False
            
            self.state.sent_certificates.append(transfer_response)
            return True
            
        except Exception as e:
            self.logger.error(f"Error handling transfer response: {e}")
            return False
        
    def _validate_confirmation_order(self, confirmation_order: ConfirmationOrder) -> bool:
        """Validate a confirmation order.
        
        Args:
            confirmation_order: Confirmation order to validate
            
        Returns:
            True if valid, False otherwise
        """
        return True     
        
    def handle_confirmation_order(self, confirmation_order: ConfirmationOrder) -> bool:
        """Handle confirmation order from committee.
        
        Args:
            confirmation_order: Confirmation order to process
            
        Returns:
            True if handled successfully, False otherwise
        """
        try:
            transfer = confirmation_order.transfer_order
            
            if transfer.recipient != self.state.name:
                return False
            
            # Check if the confirmation order is valid
            if not self._validate_confirmation_order(confirmation_order):
                return False
            
            # Update balance
            self.state.balance -= transfer.amount

            self.logger.info(
                f"Confirmation {transfer.order_id} applied – sender={transfer.sender}, amount={transfer.amount}"
            )
            self.logger.info(f"Confirmation order {confirmation_order.order_id} processed")
            return True
            
        except Exception as e:
            self.logger.error(f"Error handling confirmation order: {e}")
            self.performance_metrics.record_error()
            return False

    def broadcast_confirmation(
        self,
    ) -> None:
        """Create and broadcast a ConfirmationOrder (internal helper)."""
        if len(self.state.sent_certificates) < 2/3 * len(self.state.committee) + 1:
            self.logger.error("Not enough transfer certificates to confirm")
            return
        
        transfer_signatures = [certificate.authority_signature for certificate in self.state.sent_certificates]
        order = self.state.pending_transfer
        confirmation = ConfirmationOrder(
            order_id=order.order_id,
            transfer_order=order,
            authority_signatures=transfer_signatures,
            timestamp=time.time(),
            status=TransactionStatus.CONFIRMED,
        )

        req = ConfirmationRequestMessage(confirmation_order=confirmation)

        # 1. Send to every authority so they finalise balances.
        for auth in self.state.committee:
            msg = Message(
                message_id=uuid4(),
                message_type=MessageType.CONFIRMATION_REQUEST,
                sender=self.address,
                recipient=auth.address,
                timestamp=time.time(),
                payload=req.to_payload(),
            )
            self.transport.send_message(msg, auth.address)

        # 2. Send to recipient ------------------------------------------------------------
        # TODO: send to recipient

        # 3. Update the client state
        self.state.pending_transfer = None
        self.state.sequence_number += 1
        self.state.sent_certificates = []
        self.state.balance -= order.amount

    def _process_message(self, message: Message) -> None:
        """Process incoming message.
        
        Args:
            message: Message to process
        """
        try:
            if message.message_type == MessageType.TRANSFER_RESPONSE:
                request = TransferResponseMessage.from_payload(message.payload)
                self.handle_transfer_response(request)

            if message.message_type == MessageType.CONFIRMATION_REQUEST:
                request = ConfirmationRequestMessage.from_payload(message.payload)
                self.handle_confirmation_order(request.confirmation_order)
                
            # elif message.message_type == MessageType.SYNC_REQUEST:
            #     self._handle_sync_request(message)
                
        except Exception as e:
            self.logger.error(f"Error processing message: {e}")

    def _message_handler_loop(self) -> None:
        """Background thread loop that polls the transport for incoming messages."""
        while self._running:
            try:
                message = self.transport.receive_message(timeout=1.0)
                if message:
                    self._process_message(message)
            except Exception as exc:  # pragma: no cover – robust against transport glitches
                if hasattr(self, "logger"):
                    self.logger.error(f"Error in message handler loop: {exc}")
                time.sleep(0.2)
    