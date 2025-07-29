from __future__ import annotations

"""FastPay Gateway implementation for bridging clients and authorities.

This module provides a Gateway class that acts as an intermediary between clients
and authorities in the FastPay network. The gateway focuses on forwarding transfer
orders from clients to authorities without needing to receive or process responses.

Key Features:
- Forward transfer orders from clients to authorities
- Broadcast confirmation orders to authorities
- Multi-interface support (gw-eth1, gw-eth2, etc.)
- No message receiving or processing (simplified for gateway role)
- Transport-agnostic design using NetworkTransport
- Minimal state management for gateway operations
"""

import time
from typing import Dict, List, Optional, Tuple, Any
from uuid import uuid4
from dataclasses import dataclass
from mininet.log import info
from queue import Queue

from mn_wifi.baseTypes import (
    Address,
    NodeType,
    TransferOrder,
    ConfirmationOrder,
    TransactionStatus,
    GatewayState,
)
from mn_wifi.authority import WiFiAuthority
from mn_wifi.messages import (
    Message,
    MessageType,
    TransferRequestMessage,
    ConfirmationRequestMessage,
)
from mn_wifi.node import Station
from mn_wifi.transport import NetworkTransport, TransportKind
from mn_wifi.tcp import TCPTransport
from mn_wifi.udp import UDPTransport
from mn_wifi.wifiDirect import WiFiDirectTransport
from mn_wifi.clientLogger import ClientLogger
from mn_wifi.services.json import JSONable
from mn_wifi.services.shard import SHARD_NAMES

@dataclass
class AuthorityInterface:
    """Information about an authority's interface connection."""
    
    authority_address: Address
    interface_name: str  # e.g., "gw-eth1"
    gateway_ip: str      # e.g., "192.168.100.11"
    authority_ip: str    # e.g., "192.168.100.1"
    transport: NetworkTransport


class Gateway(Station):
    """Gateway node which acts as a bridge between clients and authorities.
    
    The Gateway class extends :class:`mn_wifi.node.Station` to participate in the 
    wireless network simulation while providing forwarding capabilities for FastPay
    messages. Unlike the Client class, it doesn't maintain state or receive messages,
    focusing solely on forwarding transfer orders and confirmation orders.
    
    The gateway supports multi-interface communication where each authority is
    connected via a dedicated interface (gw-eth1, gw-eth2, etc.).
    
    The gateway is designed to be lightweight and stateless, serving as a pure
    forwarding mechanism between clients and authorities.
    """

    def __init__(
        self,
        name: str,
        transport_kind: TransportKind = TransportKind.TCP,
        transport: Optional[NetworkTransport] = None,
        ip: str = "10.0.0.254/8",
        port: int = 8080,
        position: Optional[List[float]] = None,
        **station_params,
    ) -> None:
        """Create a new gateway station.

        Args:
            name: Identifier for the gateway (e.g., "gateway").
            transport_kind: Which built-in transport to create when transport is None.
            transport: Custom transport instance. When provided transport_kind is ignored.
            ip: IP address in CIDR notation (defaults to 10.0.0.254/8).
            port: TCP/UDP port for the gateway (defaults to 8080).
            position: Optional initial position [x, y, z].
            **station_params: Additional arguments forwarded to Station.
        """
        # Initialize the underlying Station
        defaults = {
            "ip": ip,
            "range": 150,  # Larger range for gateway
        }
        defaults.update(station_params)
        super().__init__(name, **defaults)  # type: ignore[arg-type]

        self.name = name
        
        # Gateway-specific address
        self.address = Address(
            node_id=name,
            ip_address=ip.split("/")[0],
            port=port,
            node_type=NodeType.GATEWAY,  
        )
        self.authorities: Dict[str, Dict[str, Any]] = {}
        # Transport initialization
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

        # Logger
        self.logger = ClientLogger(name)
        self.message_queue: Queue[Message] = Queue()
        # Gateway state - enhanced for multi-interface support
        self._authority_interfaces: Dict[str, AuthorityInterface] = {}  # auth_name -> interface_info
        self._running = False
        self.jsonable = JSONable()
        
    def start_gateway_services(self) -> bool:
        """Start the gateway services.
        
        Returns:
            True if started successfully, False otherwise.
        """
        # Connect transport if needed
        if hasattr(self.transport, "connect"):
            try:
                if not self.transport.connect():  # type: ignore[attr-defined]
                    self.logger.error("Failed to connect transport")
                    return False
            except Exception as exc:  # pragma: no cover
                self.logger.error(f"Transport connect error: {exc}")
                return False

        self._running = True
        self.logger.info(f"Gateway {self.name} started successfully")
        return True
    
    def stop_gateway_services(self) -> None:
        """Stop the gateway services."""
        self._running = False
        if hasattr(self.transport, "disconnect"):
            try:
                self.transport.disconnect()  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover
                pass
        
        # Disconnect all authority interface transports
        for auth_interface in self._authority_interfaces.values():
            if hasattr(auth_interface.transport, "disconnect"):
                try:
                    auth_interface.transport.disconnect()
                except Exception:  # pragma: no cover
                    pass
        
        self.logger.info(f"Gateway {self.name} stopped")

    def register_authority_interface(
        self,
        authority_name: str,
        authority_address: Address,
        interface_name: str,
        gateway_ip: str,
        authority_ip: str,
        transport_kind: TransportKind = TransportKind.TCP,
    ) -> None:
        """Register an authority with its specific interface information.
        
        Args:
            authority_name: Name of the authority (e.g., "auth1").
            authority_address: Authority's main address.
            interface_name: Gateway interface name (e.g., "gw-eth1").
            gateway_ip: Gateway IP on this interface (e.g., "192.168.100.11").
            authority_ip: Authority IP on this interface (e.g., "192.168.100.1").
            transport_kind: Transport type for this interface.
        """
        # Create interface-specific address for the authority
        interface_address = Address(
            node_id=authority_address.node_id,
            ip_address=authority_ip,  # Use interface-specific IP
            port=authority_address.port,
            node_type=authority_address.node_type,
        )
        
        # Create transport for this interface
        if transport_kind == TransportKind.TCP:
            transport = TCPTransport(self, interface_address)
        elif transport_kind == TransportKind.UDP:
            transport = UDPTransport(self, interface_address)
        elif transport_kind == TransportKind.WIFI_DIRECT:
            transport = WiFiDirectTransport(self, interface_address)
        else:
            raise ValueError(f"Unsupported transport kind: {transport_kind}")
        
        # Store interface information
        auth_interface = AuthorityInterface(
            authority_address=interface_address,
            interface_name=interface_name,
            gateway_ip=gateway_ip,
            authority_ip=authority_ip,
            transport=transport,
        )
        
        self._authority_interfaces[authority_name] = auth_interface
        self.logger.info(f"Registered authority {authority_name} via {interface_name} ({gateway_ip} <-> {authority_ip})")

    def register_authority(self, authority: WiFiAuthority) -> None:  # noqa: D401
        """Add/refresh *authority* entry used by the JSON API."""

        def _serialise_account(acc):  # type: ignore[ann-type]
            return {
                "address": acc.address,
                "balances": acc.balances,
                "sequence_number": acc.sequence_number,
                "last_update": acc.last_update,
            }

        accounts = {
            addr: _serialise_account(acc)
            for addr, acc in authority.state.accounts.items()
        }

        self.authorities[authority.name] = {
            "name": authority.name,
            "ip": authority.IP(),
            "address": {
                "node_id": authority.address.node_id,
                "ip_address": authority.address.ip_address,
                "port": authority.address.port,
                "node_type": authority.address.node_type.value,
            },
            "status": "online",
            "state": self.jsonable._to_jsonable(authority.state),
        }

        # Assign authority to a shard (round-robin based on index) ---------
        idx = len(self.authorities) - 1  # current index after append
        shard_name = SHARD_NAMES[idx % len(SHARD_NAMES)]
        self.authorities[authority.name]["shard"] = shard_name

    def get_transfer_order(self, body: Dict[str, Any]) -> Tuple[str, str, str, int, int, str]:
        """Get a transfer order from the body.
        
        Args:
            body: The body of the request.
        """
        sender = body.get("sender")
        recipient = body.get("recipient")
        token_address = body.get("token_address")
        amount = body.get("amount")
        sequence_number = body.get("sequence_number")
        signature = body.get("signature")

        return sender, recipient, token_address, amount, sequence_number, signature
        
    def forward_transfer(
        self,
        sender: str,
        recipient: str,
        token_address: str,
        amount: int,
        sequence_number: int = 1,
        signature: Optional[str] = None,
    ) -> bool:
        """Forward a transfer order from a client to all authorities.
        
        Args:
            sender: Sender account identifier.
            recipient: Recipient account identifier.
            token_address: Token address for the transfer.
            amount: Amount to transfer.
            sequence_number: Sequence number for the transfer.
            signature: Signature for the transfer.
        Returns:
            True if transfer was forwarded successfully, False otherwise.
        """
        # Create transfer order
        order = TransferOrder(
            order_id=uuid4(),
            sender=sender,
            recipient=recipient,
            token_address=token_address,
            amount=amount,
            sequence_number=sequence_number,
            timestamp=time.time(),
            signature=signature,  
        )
        
        request = TransferRequestMessage(transfer_order=order)
        
        message = Message(
            message_id=uuid4(),
            message_type=MessageType.TRANSFER_REQUEST,
            sender=self.address,
            recipient=None,  # Will be set per authority
            timestamp=time.time(),
            payload=request.to_payload(),
        )
        
        return self._broadcast_transfer_request(message)
    
    def _broadcast_transfer_request(self, transfer_request: Message) -> bool:
        """Broadcast a transfer request to all registered authorities via their specific interfaces.
        
        Args:
            transfer_request: Transfer request message to broadcast.
            
        Returns:
            True if at least one authority received the message, False otherwise.
        """
        self.logger.info(
            f"Forwarding transfer request to {len(self.authorities)} authorities"
        )

        successes = 0
        for auth_name, auth_data in self.authorities.items():
            # Create Address object from auth_data
            recipient_address = Address(
                node_id=auth_data["name"],
                ip_address=auth_data["ip"],
                port=auth_data["address"]["port"],
                node_type=NodeType(auth_data["address"]["node_type"]),
            )
            
            msg = Message(
                message_id=transfer_request.message_id,
                message_type=transfer_request.message_type,
                sender=transfer_request.sender,
                recipient=recipient_address,  
                timestamp=transfer_request.timestamp,
                payload=transfer_request.payload,
            )
            
            # Use the interface-specific transport with the correct interface binding
            if self.transport.send_message(msg, recipient_address):
                successes += 1
                self.logger.debug(f"Forwarded transfer to {auth_name}")
            else:
                self.logger.warning(f"Failed to forward to {auth_name}")

        if successes == 0:
            self.logger.error("Failed to forward transfer request to any authority")
            return False

        self.logger.info(f"Transfer request forwarded to {successes} / {len(self._authority_interfaces)} authorities")
        return True

    def forward_confirmation(
        self,
        transfer_order: TransferOrder,
        authority_signatures: List[str],
    ) -> bool:
        """Forward a confirmation order to all authorities via their specific interfaces.
        
        Args:
            transfer_order: The transfer order to confirm.
            authority_signatures: List of authority signatures for the confirmation.
            
        Returns:
            True if confirmation was forwarded successfully, False otherwise.
        """
        # Create confirmation order
        confirmation = ConfirmationOrder(
            order_id=uuid4(),
            transfer_order=transfer_order,
            authority_signatures=authority_signatures,
            timestamp=time.time(),
            status=TransactionStatus.CONFIRMED,
        )

        request = ConfirmationRequestMessage(confirmation_order=confirmation)

        # Send to every authority via their specific interface
        successes = 0
        for auth_name, auth_interface in self._authority_interfaces.items():
            msg = Message(
                message_id=uuid4(),
                message_type=MessageType.CONFIRMATION_REQUEST,
                sender=self.address,
                recipient=auth_interface.authority_address,  # Use interface-specific address
                timestamp=time.time(),
                payload=request.to_payload(),
            )
            
            # Use the interface-specific transport
            if auth_interface.transport.send_message(msg, auth_interface.authority_address):
                successes += 1
                self.logger.debug(f"Forwarded confirmation to {auth_name} via {auth_interface.interface_name}")
            else:
                self.logger.warning(f"Failed to forward confirmation to {auth_name} via {auth_interface.interface_name}")

        if successes == 0:
            self.logger.error("Failed to forward confirmation to any authority")
            return False

        self.logger.info(f"Confirmation forwarded to {successes} / {len(self._authority_interfaces)} authorities")
        return True

    def get_authority_count(self) -> int:
        """Get the number of registered authorities.
        
        Returns:
            Number of registered authorities.
        """
        return len(self._authority_interfaces)

    def get_authority_interfaces(self) -> Dict[str, AuthorityInterface]:
        """Get information about all registered authority interfaces.
        
        Returns:
            Dictionary mapping authority names to their interface information.
        """
        return self._authority_interfaces.copy()

    def get_authorities(self) -> List['WiFiAuthority']:
        """Get list of registered authorities for bridge updates.
        
        Returns:
            List of WiFiAuthority instances that are registered with this gateway.
        """
        authorities = []
        
        # Try to get authorities from the network if available
        for node in self.net.stations:
            if isinstance(node, WiFiAuthority):
                authorities.append(node)
        
        # If no authorities found via network, return empty list
        # The bridge will handle this gracefully
        return authorities

    def is_running(self) -> bool:
        """Check if the gateway is running.
        
        Returns:
            True if gateway is running, False otherwise.
        """
        return self._running 