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
from typing import Dict, Optional, Protocol, Union
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

# Type aliases for clarity -----------------------------------------------------------------------
AuthorityName = str


class TransportError(RuntimeError):
    """Raised whenever the underlying transport fails."""


class NetworkTransport(Protocol):
    """Protocol that any concrete transport must implement."""

    def send_message(self, message: Message, target: Address) -> bool:  # pragma: no cover
        """Transmit *message* to *target*.

        Implementations **must** be blocking and return *True* only when the payload has been
        handed over to the network stack without local errors.  They **should not** attempt to
        infer success on the remote side; higher-level logic in :class:`FastPayClient` is in charge
        of evaluating responses.
        """

    def receive_message(self, timeout: float = 1.0) -> Optional[Message]:  # pragma: no cover
        """Blocking receive with *timeout* seconds.
        
        The method should return a fully deserialised :class:`mn_wifi.messages.Message` instance or
        *None* when the timeout expires.  Implementations are free to raise exceptions on fatal
        conditions, but transient errors should be logged internally and converted into *None* to
        allow the caller to decide on a retry strategy.
        """


class TcpTransport:
    """A simple TCP-based transport suitable for both simulation and unit-testing.

    A dedicated server socket is created when :py:meth:`start_server` is invoked.  Incoming
    messages are decoded from the length-prefixed JSON representation defined by the existing
    server logic used by :class:`mn_wifi.wifiInterface.WiFiInterface` so that authorities can
    inter-operate out-of-the-box.
    """

    def __init__(self, bind: Address, logger: Optional[logging.Logger] = None) -> None:
        self.bind = bind
        self.logger = logger or logging.getLogger(f"TcpTransport-{bind.node_id}")
        self._server_socket: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None  # type: ignore[name-defined]
        self._running = False
        self._queue: "Queue[Message]" = Queue()

    # --------------------------------------------------------------------------------------------
    # Public API
    # --------------------------------------------------------------------------------------------

    def start_server(self) -> None:
        """Launch the background TCP server (**idempotent**)."""
        if self._running:
            return
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.bind.ip_address, self.bind.port))
        self._server_socket.listen(16)
        self._running = True
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        self.logger.info("TCP server started on %s:%d", self.bind.ip_address, self.bind.port)

    def stop_server(self) -> None:
        """Shutdown the background server."""
        self._running = False
        if self._server_socket:
            try:
                self._server_socket.close()
            except OSError:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self.logger.info("TCP server stopped")

    # NetworkTransport implementation ----------------------------------------------------------------

    def send_message(self, message: Message, target: Address) -> bool:  # type: ignore[override]
        try:
            with socket.create_connection((target.ip_address, target.port), timeout=5) as sock:
                payload = self._serialise(message)
                sock.sendall(len(payload).to_bytes(4, "big") + payload)
                # Optionally read ACK — ignore errors/timeouts.
                try:
                    ack_len = int.from_bytes(sock.recv(4, socket.MSG_WAITALL), "big")
                    sock.recv(ack_len, socket.MSG_WAITALL)
                except Exception:  # pragma: no cover
                    pass
            return True
        except Exception as exc:
            self.logger.error("send_message failed: %s", exc)
            return False

    def receive_message(self, timeout: float = 1.0) -> Optional[Message]:  # type: ignore[override]
        try:
            return self._queue.get(timeout=timeout)
        except Empty:
            return None

    # --------------------------------------------------------------------------------------------
    # Internal helpers
    # --------------------------------------------------------------------------------------------

    def _serve(self) -> None:
        while self._running and self._server_socket:
            try:
                client, _ = self._server_socket.accept()
            except OSError:
                break
            threading.Thread(target=self._handle_client, args=(client,), daemon=True).start()

    def _handle_client(self, sock: socket.socket) -> None:
        with sock:
            try:
                length_raw = sock.recv(4, socket.MSG_WAITALL)
                if len(length_raw) != 4:
                    return
                size = int.from_bytes(length_raw, "big")
                raw = sock.recv(size, socket.MSG_WAITALL)
                data = json.loads(raw.decode())
                msg = self._deserialise(data)
                if msg:
                    self._queue.put(msg)
                # ACK (optional)
                ack = json.dumps({"status": "received"}).encode()
                sock.sendall(len(ack).to_bytes(4, "big") + ack)
            except Exception as exc:  # pragma: no cover
                self.logger.debug("Client handler error: %s", exc)

    @staticmethod
    def _serialise(message: Message) -> bytes:
        return json.dumps(
            {
                "message_id": str(message.message_id),
                "message_type": message.message_type.value,
                "sender": {
                    "node_id": message.sender.node_id,
                    "ip_address": message.sender.ip_address,
                    "port": message.sender.port,
                    "node_type": message.sender.node_type.value,
                },
                "timestamp": message.timestamp,
                "payload": message.payload,
            }
        ).encode()

    def _deserialise(self, data: Dict[str, Union[str, Dict[str, str]]]) -> Optional[Message]:
        try:
            sender_raw = data.get("sender", {})  # type: ignore[arg-type]
            sender = Address(
                node_id=str(sender_raw.get("node_id", "")),
                ip_address=str(sender_raw.get("ip_address", "")),
                port=int(sender_raw.get("port", 0)),
                node_type=NodeType(sender_raw.get("node_type", NodeType.CLIENT.value)),
            )
            return Message(
                message_id=UUID(data["message_id"]),
                message_type=MessageType(data["message_type"]),
                sender=sender,
                recipient=self.bind,
                timestamp=float(data["timestamp"]),
                payload=data.get("payload", {}),  # type: ignore[arg-type]
            )
        except Exception as exc:  # pragma: no cover
            self.logger.error("Deserialisation failed: %s", exc)
            return None


class TransportKind(Enum):
    """User-friendly enumeration to select the desired transport type."""

    TCP = "tcp"
    UDP = "udp"
    WIFI_DIRECT = "wifi_direct"


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


class FastPayClient:
    """High-level client able to speak to FastPay authorities using various transports."""

    def __init__(
        self,
        state: ClientState,
        transport: NetworkTransport,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.state = state
        self.transport = transport
        self.logger = logger or logging.getLogger(f"FastPayClient-{state.name}")

    # ------------------------------------------------------------------------------------------------
    # Transfer operations
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


class UdpTransport:
    """A *very* light UDP transport.

    UDP is connection-less and does *not* guarantee delivery.  This implementation tries to
    minimise complexity by using a single socket both for sending and receiving.
    """

    def __init__(self, bind: Address, logger: Optional[logging.Logger] = None) -> None:
        self.bind = bind
        self.logger = logger or logging.getLogger(f"UdpTransport-{bind.node_id}")
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((bind.ip_address, bind.port))
        self._sock.setblocking(False)
        self._queue: "Queue[Message]" = Queue()
        threading.Thread(target=self._recv_loop, daemon=True).start()

    # NetworkTransport implementation ------------------------------------------------------------

    def send_message(self, message: Message, target: Address) -> bool:  # type: ignore[override]
        try:
            payload = json.dumps({
                "message_id": str(message.message_id),
                "message_type": message.message_type.value,
                "sender": {
                    "node_id": message.sender.node_id,
                    "ip_address": message.sender.ip_address,
                    "port": message.sender.port,
                    "node_type": message.sender.node_type.value,
                },
                "timestamp": message.timestamp,
                "payload": message.payload,
            }).encode()
            self._sock.sendto(payload, (target.ip_address, target.port))
            return True
        except Exception as exc:
            self.logger.error("send_message failed: %s", exc)
            return False

    def receive_message(self, timeout: float = 1.0) -> Optional[Message]:  # type: ignore[override]
        try:
            return self._queue.get(timeout=timeout)
        except Empty:
            return None

    # Internal -----------------------------------------------------------------------------------

    def _recv_loop(self) -> None:
        while True:
            try:
                data, _ = self._sock.recvfrom(65536)
                msg = json.loads(data.decode())
                deserialised = self._deserialise(msg)
                if deserialised:
                    self._queue.put(deserialised)
            except BlockingIOError:
                time.sleep(0.05)
            except Exception as exc:  # pragma: no cover
                self.logger.debug("UDP recv error: %s", exc)
                time.sleep(0.1)

    def _deserialise(self, data: Dict[str, Union[str, Dict[str, str]]]) -> Optional[Message]:
        try:
            sender_raw = data.get("sender", {})  # type: ignore[arg-type]
            sender = Address(
                node_id=str(sender_raw.get("node_id", "")),
                ip_address=str(sender_raw.get("ip_address", "")),
                port=int(sender_raw.get("port", 0)),
                node_type=NodeType(sender_raw.get("node_type", NodeType.CLIENT.value)),
            )
            return Message(
                message_id=UUID(data["message_id"]),
                message_type=MessageType(data["message_type"]),
                sender=sender,
                recipient=self.bind,
                timestamp=float(data["timestamp"]),
                payload=data.get("payload", {}),  # type: ignore[arg-type]
            )
        except Exception as exc:  # pragma: no cover
            self.logger.error("UDP deserialisation failed: %s", exc)
            return None


# -----------------------------------------------------------------------------------------------
# Wi-Fi Direct transport wrapper -----------------------------------------------------------------
# -----------------------------------------------------------------------------------------------

try:
    from mn_wifi.wifiInterface import WiFiInterface
except ImportError:  # pragma: no cover
    WiFiInterface = None  # type: ignore


class WiFiDirectTransport:
    """Adapter that exposes :class:`mn_wifi.wifiInterface.WiFiInterface` as a *NetworkTransport*."""

    def __init__(self, wifi_iface: "WiFiInterface") -> None:
        if WiFiInterface is None:
            raise RuntimeError("WiFiInterface module not available – cannot build WiFiDirectTransport")
        self.iface = wifi_iface

    # NetworkTransport implementation ------------------------------------------------------------

    def send_message(self, message: Message, target: Address) -> bool:  # type: ignore[override]
        return self.iface.send_message(message, target)

    def receive_message(self, timeout: float = 1.0) -> Optional[Message]:  # type: ignore[override]
        return self.iface.receive_message(timeout=timeout) 