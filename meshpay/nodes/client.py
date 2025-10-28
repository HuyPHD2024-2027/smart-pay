from __future__ import annotations

"""MeshPay client implementation capable of using multiple network transports.

This class mirrors the previous implementation under ``mn_wifi.client`` but is
now housed under the MeshPay namespace. It communicates via a pluggable
``NetworkTransport`` and operates in the Mininet-WiFi simulation environment.
"""

import time
import threading
from queue import Queue
from typing import Dict, Optional, List
from uuid import UUID, uuid4

from meshpay.types import (
    Address,
    ClientState,
    NodeType,
    TransferOrder,
    KeyPair,
    AuthorityName,
    ConfirmationOrder,
    TransactionStatus,
    WeightedCertificate,
)
from meshpay.messages import (
    Message,
    MessageType,
    TransferRequestMessage,
    TransferResponseMessage,
    ConfirmationRequestMessage,
)
from mn_wifi.node import Station
from meshpay.transport.transport import NetworkTransport, TransportKind
from meshpay.transport.tcp import TCPTransport
from meshpay.transport.udp import UDPTransport
from meshpay.transport.wifiDirect import WiFiDirectTransport
from meshpay.logger.clientLogger import ClientLogger


class Client(Station):
    """Client node which can be added to a Mininet-WiFi topology using addStation.

    The class embeds the FastPay client logic while extending Station so that it
    participates in the wireless network simulation natively. Upon construction
    the caller may choose one of the supported transport kinds or inject an
    already configured NetworkTransport instance.
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
        """Create a new client station."""

        defaults = {
            "ip": ip,
            "range": 100,
        }
        defaults.update(station_params)
        super().__init__(name, **defaults)  # type: ignore[arg-type]

        self.name = name
        self.address = Address(
            node_id=name,
            ip_address=ip.split("/")[0],
            port=port,
            node_type=NodeType.CLIENT,
        )

        self.p2p_connections: Dict[str, Address] = {}
        self.message_queue: Queue[Message] = Queue()

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
            weighted_certificates=[],
            quorum_reached_time=None,
        )

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

        self.logger = ClientLogger(name)
        self._running = False
        self._message_handler_thread: Optional[threading.Thread] = None

    def start_fastpay_services(self) -> bool:
        """Boot-strap background processing threads and ready the transport."""
        if hasattr(self.transport, "connect"):
            try:
                if not self.transport.connect():  # type: ignore[attr-defined]
                    self.logger.error("Failed to connect transport")
                    return False
            except Exception as exc:  # pragma: no cover
                self.logger.error(f"Transport connect error: {exc}")
                return False

        self._running = True
        self._message_handler_thread = threading.Thread(
            target=self._message_handler_loop,
            daemon=True,
        )
        self._message_handler_thread.start()

        self.logger.info(f"Client {self.name} started successfully")
        return True
    
    def stop_fastpay_services(self) -> None:
        """Stop the FastPay client services."""
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
        token_address: str,
        amount: int,
    ) -> bool:
        """Broadcast a transfer order to the committee."""
        order = TransferOrder(
            order_id=uuid4(),
            sender=self.state.name,
            token_address=token_address,
            recipient=recipient,
            amount=amount,
            sequence_number=self.state.sequence_number,
            timestamp=time.time(),
            signature=self.state.secret,
        )
        request = TransferRequestMessage(transfer_order=order)
        self.state.pending_transfer = order

        message = Message(
            message_id=uuid4(),
            message_type=MessageType.TRANSFER_REQUEST,
            sender=self.state.address,
            recipient=None,
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
        for auth in self.state.committee:
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
        """Validate a transfer response received from an authority."""
        if transfer_response.transfer_order.sender != self.state.name:
            self.logger.error(f"Transfer {transfer_response.transfer_order.order_id} failed: sender mismatch")
            return False
        
        if transfer_response.transfer_order.sequence_number != self.state.sequence_number:
            self.logger.error(f"Transfer {transfer_response.transfer_order.order_id} failed: sequence number mismatch")
            return False
        return True
    
    def handle_transfer_response(
        self,
        transfer_response: TransferResponseMessage,
        authority_name: str = "unknown",
    ) -> bool:
        """Handle transfer response from authority with weighted certificate tracking.
        
        Args:
            transfer_response: Response message from authority.
            authority_name: Name of the responding authority.
            
        Returns:
            True if response was successfully processed.
        """
        try:
            if not self._validate_transfer_response(transfer_response):
                return False
            
            # Store traditional certificate for backward compatibility
            self.state.sent_certificates.append(transfer_response)
            
            # Create and store weighted certificate
            weighted_cert = WeightedCertificate(
                authority_name=authority_name,
                authority_signature=transfer_response.authority_signature or "",
                weight=transfer_response.authority_weight,
                timestamp=time.time(),
            )
            self.state.weighted_certificates.append(weighted_cert)
            
            # Compute total weight and check for quorum
            total_weight = sum(cert.weight for cert in self.state.weighted_certificates)
            
            # Get total committee weight (should be 1.0 for normalized weights)
            total_committee_weight = 1.0
            quorum_threshold = 2.0 / 3.0
            
            # Check if weighted quorum is reached
            if total_weight >= quorum_threshold and self.state.quorum_reached_time is None:
                self.state.quorum_reached_time = time.time()
                self.logger.info(
                    f"Weighted quorum reached: {total_weight:.3f} / {total_committee_weight:.3f} "
                    f"(threshold: {quorum_threshold:.3f}) with {len(self.state.weighted_certificates)} certificates"
                )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error handling transfer response: {e}")
            return False
        
    def _validate_confirmation_order(self, confirmation_order: ConfirmationOrder) -> bool:
        """Validate a confirmation order (placeholder)."""
        return True     
        
    def handle_confirmation_order(self, confirmation_order: ConfirmationOrder) -> bool:
        """Handle confirmation order from committee."""
        try:
            transfer = confirmation_order.transfer_order
            
            if transfer.recipient != self.state.name:
                return False
            
            if not self._validate_confirmation_order(confirmation_order):
                return False
            
            self.state.balance -= transfer.amount

            self.logger.info(
                f"Confirmation {transfer.order_id} applied – sender={transfer.sender}, amount={transfer.amount}"
            )
            self.logger.info(f"Confirmation order {confirmation_order.order_id} processed")
            return True
            
        except Exception as e:
            self.logger.error(f"Error handling confirmation order: {e}")
            # Note: client has no performance metrics collector yet
            return False

    def broadcast_confirmation(self) -> None:
        """Create and broadcast a ConfirmationOrder using weighted quorum.
        
        This method checks if weighted quorum (>= 2/3 total weight) has been reached
        before broadcasting the confirmation order to all committee members.
        """
        # Check weighted quorum
        total_weight = sum(cert.weight for cert in self.state.weighted_certificates)
        quorum_threshold = 2.0 / 3.0
        
        if total_weight < quorum_threshold:
            self.logger.error(
                f"Not enough weighted certificates to confirm: "
                f"total_weight={total_weight:.3f}, required={quorum_threshold:.3f}"
            )
            return
        
        # Gather both traditional signatures and weighted certificates
        transfer_signatures = [
            certificate.authority_signature 
            for certificate in self.state.sent_certificates
        ]
        
        order = self.state.pending_transfer
        if order is None:
            self.logger.error("No pending transfer to confirm")
            return
        
        # Create confirmation order with weighted certificates
        confirmation = ConfirmationOrder(
            order_id=order.order_id,
            transfer_order=order,
            authority_signatures=transfer_signatures,
            timestamp=time.time(),
            status=TransactionStatus.CONFIRMED,
            weighted_certificates=self.state.weighted_certificates.copy(),
            total_weight=total_weight,
        )

        req = ConfirmationRequestMessage(confirmation_order=confirmation)

        # Broadcast to all committee members
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

        self.logger.info(
            f"Broadcast confirmation order {order.order_id} with weighted quorum "
            f"(total_weight={total_weight:.3f})"
        )

        # Reset state for next transfer
        self.state.pending_transfer = None
        self.state.sequence_number += 1
        self.state.sent_certificates = []
        self.state.weighted_certificates = []
        self.state.quorum_reached_time = None
        self.state.balance -= order.amount

    def _process_message(self, message: Message) -> None:
        """Process incoming message."""
        try:
            if message.message_type == MessageType.TRANSFER_RESPONSE:
                request = TransferResponseMessage.from_payload(message.payload)
                self.handle_transfer_response(request)

            if message.message_type == MessageType.CONFIRMATION_REQUEST:
                request = ConfirmationRequestMessage.from_payload(message.payload)
                self.handle_confirmation_order(request.confirmation_order)
                
        except Exception as e:
            self.logger.error(f"Error processing message: {e}")

    def _message_handler_loop(self) -> None:
        """Background thread loop that polls the transport for incoming messages."""
        while self._running:
            try:
                message = self.transport.receive_message(timeout=1.0)
                if message:
                    self._process_message(message)
            except Exception as exc:  # pragma: no cover
                if hasattr(self, "logger"):
                    self.logger.error(f"Error in message handler loop: {exc}")
                time.sleep(0.2)

__all__ = ["Client"]



