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
import threading

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
        
        self.logger.info(f"Gateway {self.name} stopped")

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

    def forward_transfer(
        self,
        transfer_order: TransferOrder,
    ) -> Dict[str, Any]:
        request = TransferRequestMessage(transfer_order=transfer_order)
        
        message = Message(
            message_id=uuid4(),
            message_type=MessageType.TRANSFER_REQUEST,
            sender=self.address,
            recipient=None,
            timestamp=time.time(),
            payload=request.to_payload(),
        )
        
        # Get broadcast results
        broadcast_results = self._broadcast_transfer_request(message)
        
        # Add transfer details to the results
        broadcast_results["transfer_details"] = {
            "sender": transfer_order.sender,
            "recipient": transfer_order.recipient,
            "token_address": transfer_order.token_address,
            "amount": transfer_order.amount,
            "sequence_number": transfer_order.sequence_number,
            "order_id": str(transfer_order.order_id),
            "timestamp": transfer_order.timestamp
        }
        
        return broadcast_results
    
    def _broadcast_transfer_request(self, transfer_request: Message) -> Dict[str, Any]:
        self.logger.info(
            f"Forwarding transfer request to {len(self.authorities)} authorities"
        )

        # Default return structure
        results = {
            "success": False,
            "total_authorities": len(self.authorities),
            "successful_authorities": 0,
            "failed_authorities": 0,
            "authority_results": {},
            "timestamp": time.time()
        }
        
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
            
            # Track individual authority result
            auth_result = {
                "success": False,
                "error": None,
                "timestamp": time.time()
            }
            
            # Use the interface-specific transport with the correct interface binding
            try:
                if self.transport.send_message(msg, recipient_address):
                    auth_result["success"] = True
                    results["successful_authorities"] += 1
                    self.logger.debug(f"Forwarded transfer to {auth_name}")
                else:
                    auth_result["error"] = "Transport send failed"
                    results["failed_authorities"] += 1
                    self.logger.warning(f"Failed to forward to {auth_name}")
            except Exception as e:
                auth_result["error"] = str(e)
                results["failed_authorities"] += 1
                self.logger.error(f"Exception while forwarding to {auth_name}: {e}")
            
            results["authority_results"][auth_name] = auth_result

        # Overall success if at least one authority received the message
        results["success"] = results["successful_authorities"] > 0

        if results["successful_authorities"] == 0:
            self.logger.error("Failed to forward transfer request to any authority")
        else:
            self.logger.info(f"Transfer request forwarded to {results['successful_authorities']} / {results['total_authorities']} authorities")

        return results

    def forward_confirmation(
        self,
        confirmation_order: ConfirmationOrder,
    ) -> Dict[str, Any]:
        # Create confirmation order
        request = ConfirmationRequestMessage(confirmation_order=confirmation_order)

        # Default return structure
        results = {
            "success": False,
            "total_authorities": len(self.authorities),
            "successful_authorities": 0,
            "failed_authorities": 0,
            "authority_results": {},
            "confirmation_details": {
                "order_id": str(confirmation_order.order_id),
                "transfer_order_id": str(confirmation_order.transfer_order.order_id),
                "authority_signatures": confirmation_order.authority_signatures,
                "timestamp": confirmation_order.timestamp
            },
            "timestamp": time.time()
        }

        # Send to every authority via their specific interface
        for auth_name, auth_data in self.authorities.items():
            recipient_address = Address(
                node_id=auth_data["name"],
                ip_address=auth_data["ip"],
                port=auth_data["address"]["port"],
                node_type=NodeType(auth_data["address"]["node_type"]),
            )
            msg = Message(
                message_id=uuid4(),
                message_type=MessageType.CONFIRMATION_REQUEST,
                sender=self.address,
                recipient=recipient_address,  # Use interface-specific address
                timestamp=time.time(),
                payload=request.to_payload(),
            )
            
            # Track individual authority result
            auth_result = {
                "success": False,
                "error": None,
                "timestamp": time.time()
            }
            
            # Use the interface-specific transport
            try:
                if self.transport.send_message(msg, recipient_address):
                    auth_result["success"] = True
                    results["successful_authorities"] += 1
                else:
                    auth_result["error"] = "Transport send failed"
                    results["failed_authorities"] += 1
            except Exception as e:
                auth_result["error"] = str(e)
                results["failed_authorities"] += 1
            
            results["authority_results"][auth_name] = auth_result

        # Overall success if at least one authority received the message
        results["success"] = results["successful_authorities"] > 0

        if results["successful_authorities"] == 0:
            self.logger.error("Failed to forward confirmation to any authority")
        else:
            self.logger.info(f"Confirmation forwarded to {results['successful_authorities']} / {results['total_authorities']} authorities")

        return results