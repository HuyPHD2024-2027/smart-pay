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

import json
import logging
import socket
import time
import threading
from dataclasses import dataclass, field
from enum import Enum
from queue import Queue, Empty
from typing import Dict, Optional, Protocol, Union, List
from uuid import UUID, uuid4

from mn_wifi.baseTypes import (
    Address,
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

# Type aliases for clarity -----------------------------------------------------------------------
AuthorityName = str



@dataclass
class ClientState:
    """Lightweight in-memory state for a FastPay client.

    Only the fields required for initiating basic transfers are included at this stage.  The class
    can be extended later with balance tracking, sequence numbers, certificates, and so on.
    """

    name: str
    address: Address
    sequence_number: int = 1
    pending_transfers: Dict[UUID, TransferOrder] = field(default_factory=dict)

    def next_sequence(self) -> int:
        """Return the current sequence number *and* increment internal counter."""
        seq = self.sequence_number
        self.sequence_number += 1
        return seq


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
            "position": position or [0, 0, 0],
            "range": 100,
        }
        defaults.update(station_params)
        super().__init__(name, **defaults)  # type: ignore[arg-type]

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

        self.state = ClientState(name=name, address=self.address)

        # Transport factory ------------------------------------------------------------------
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

    # ------------------------------------------------------------------------------------------------
    # Original FastPay client API (renamed methods remain intact)
    # ------------------------------------------------------------------------------------------------

    def transfer(
        self,
        recipient: str,
        amount: int,
        authorities: Dict[AuthorityName, Address],
    ) -> bool:
        """Broadcast a *transfer order* to the given *authorities*.

        The method uses a **best-effort** strategy similar to the original Rust implementation:
        a quorum is considered reached once *2/3 + 1* successful responses are collected.

        Args:
            recipient: Recipient account identifier.
            amount: Amount to transfer.
            authorities: Mapping *authority-name → Address*.

        Returns:
            *True* when a quorum acknowledged the transfer, *False* otherwise.
        """
        order = TransferOrder(
            order_id=uuid4(),
            sender=self.state.name,
            recipient=recipient,
            amount=amount,
            sequence_number=self.state.next_sequence(),
            timestamp=time.time(),
            signature="placeholder",  # TODO: cryptographic signatures
        )
        self.state.pending_transfers[order.order_id] = order

        request = TransferRequestMessage(transfer_order=order)

        message = Message(
            message_id=uuid4(),
            message_type=MessageType.TRANSFER_REQUEST,
            sender=self.state.address,
            recipient=None,  # Filled per authority below
            timestamp=time.time(),
            payload=request.to_payload(),
        )

        # Send to all authorities and collect responses ------------------------------------------------
        quorum_weight = (len(authorities) * 2) // 3 + 1
        success = 0
        for name, addr in authorities.items():
            msg = message
            msg.recipient = addr
            if not self.transport.send_message(msg, addr):
                self.logger.warning("Failed to send to authority %s", name)
                continue

            # Wait (non-blocking) for immediate response — real FastPay is async, but to keep things
            # simple we do a short blocking wait here.  A production-grade client would use an event
            # loop.
            resp = self._await_response(order.order_id, timeout=3.0)
            if resp and resp.success:
                success += 1
                self.logger.info("Authority %s accepted transfer", name)
            else:
                self.logger.warning("Authority %s rejected transfer", name)

            if success >= quorum_weight:
                self.logger.info("Quorum reached (accepted by %d authorities)", success)
                # Clean pending transfer.
                self.state.pending_transfers.pop(order.order_id, None)
                return True

        self.logger.error("Quorum *not* reached — transfer will remain pending")
        return False

    # ------------------------------------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------------------------------------

    def _await_response(self, order_id: UUID, timeout: float) -> Optional[TransferResponseMessage]:
        """Wait for a :class:`TransferResponseMessage` corresponding to *order_id*."""
        expiry = time.time() + timeout
        while time.time() < expiry:
            msg = self.transport.receive_message(timeout=0.2)
            if msg and msg.message_type == MessageType.TRANSFER_RESPONSE:
                response = TransferResponseMessage.from_payload(msg.payload)
                if response.order_id == order_id:
                    return response
        return None


