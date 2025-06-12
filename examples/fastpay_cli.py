from __future__ import annotations

"""Interactive Command-Line Interface helpers for FastPay Wi-Fi simulations.

This module is **imported** by example scripts under :pymod:`mn_wifi.examples` and
implements the small REPL that operators can use to test a FastPay network
running inside *Mininet-WiFi*.

The CLI supports the following high-level commands:

1. ``ping <src> <dst>`` – ICMP reachability test between two nodes in the
   topology.
2. ``balance <user>`` or ``balances`` – Show the balance of a single user or of
   all predefined users across *all* authorities.
3. ``initiate <sender> <recipient> <amount>`` – Create a *TransferOrder* but do
   **not** broadcast it yet.
4. ``sign <order-id> <user>`` – Attach a dummy signature to the selected
   *TransferOrder*.
5. ``broadcast <order-id>`` – Send the signed *TransferOrder* to every
   authority and report whether the 2/3 + 1 quorum accepted the transfer.

The CLI was deliberately kept *stateless* regarding Mininet – it only needs
lists of authority and client nodes which are passed in by the example script.
"""

from dataclasses import asdict
import json
import time
import uuid
from typing import Dict, List, Optional, Tuple

from mn_wifi.baseTypes import Address, NodeType, TransferOrder
from mn_wifi.client import Client
from mn_wifi.messages import (
    Message,
    MessageType,
    TransferRequestMessage,
    TransferResponseMessage,
)
from mn_wifi.transport import NetworkTransport
from mn_wifi.node import Station

# --------------------------------------------------------------------------------------
# Public helpers
# --------------------------------------------------------------------------------------


class FastPayCLI:  # pylint: disable=too-many-instance-attributes
    """Small interactive shell to operate a FastPay Wi-Fi network."""

    def __init__(
        self,
        authorities: List[Station],
        clients: List[Client],
        *,
        quorum_ratio: float = 2 / 3,
    ) -> None:
        """Create the CLI helper.

        Args:
            authorities: List of authority nodes participating in the committee.
            clients: Client stations (e.g. *user1*, *user2* …).
            quorum_ratio: Fraction of authorities that must accept a transfer in
                order to reach finality.  The default replicates FastPay's
                *2/3 + 1* rule.
        """
        self.authorities = authorities
        self.clients = clients
        self.clients_map: Dict[str, Client] = {c.name: c for c in clients}
        self._pending_orders: Dict[uuid.UUID, TransferOrder] = {}
        self._quorum_weight = int(len(authorities) * quorum_ratio) + 1

        # Bring client transports up so that they can receive replies.
        for client in clients:
            if hasattr(client.transport, "connect"):
                client.transport.connect()  # type: ignore[attr-defined]

    # ---------------------------------------------------------------------
    # Low-level utilities
    # ---------------------------------------------------------------------

    def _find_node(self, name: str) -> Optional[Station]:
        """Return *any* station (authority or client) with the given *name*."""
        for node in [*self.authorities, *self.clients_map.values()]:
            if node.name == name:
                return node
        return None

    # ---------------------------------------------------------------------
    # Public command dispatchers (called by the example script)
    # ---------------------------------------------------------------------

    # 1. ------------------------------------------------------------------
    def cmd_ping(self, src: str, dst: str, *, count: int = 3) -> None:
        """Run *ping* from *src* → *dst* inside the Mininet namespace."""
        source = self._find_node(src)
        target = self._find_node(dst)
        if source is None or target is None:
            print(f"❌ Unknown source/target – src={src}, dst={dst}")
            return

        # Extract IP of *target* (strip CIDR suffix when present)
        if not target.wintfs:
            print(f"❌ Target {dst} has no wireless interfaces")
            return
        ip = list(target.wintfs.values())[0].ip.split("/")[0]

        print(f"🏓 {src} → {dst} ({ip})  count={count}")
        out = source.cmd(f"ping -c {count} -W 5 {ip} | cat")  # ensure non-interactive
        print(out)

    # 2. ------------------------------------------------------------------
    def cmd_balance(self, user: str) -> None:
        """Print *user* balance across all authorities (and highlight consistency)."""
        balances = []
        for auth in self.authorities:
            if hasattr(auth, "get_account_balance"):
                bal = auth.get_account_balance(user)
            else:
                bal = None
            balances.append(bal)

        all_equal = len(set(balances)) == 1
        symbol = "✅" if all_equal else "⚠️"
        print(f"💰 {user}: {balances[0] if all_equal else balances} {symbol}")

    # 3. ------------------------------------------------------------------
    def cmd_initiate(self, sender: str, recipient: str, amount: int) -> None:
        """Create (but *not* send) a :class:`TransferOrder`."""
        client = self.clients_map.get(sender)
        if client is None:
            print(f"❌ Unknown client '{sender}'")
            return

        order = TransferOrder(
            order_id=uuid.uuid4(),
            sender=sender,
            recipient=recipient,
            amount=amount,
            sequence_number=client.state.next_sequence(),
            timestamp=time.time(),
            signature=None,
        )
        self._pending_orders[order.order_id] = order
        print(f"📝 Initiated transfer – order_id={order.order_id}")

    # 4. ------------------------------------------------------------------
    def cmd_sign(self, order_id_str: str, user: str) -> None:
        """Attach a *dummy* signature to the pending *order_id*."""
        try:
            order_id = uuid.UUID(order_id_str)
        except ValueError:
            print("❌ order_id must be a valid UUID")
            return

        order = self._pending_orders.get(order_id)
        if order is None:
            print("❌ Unknown order_id – did you *initiate* first?")
            return
        if order.sender != user:
            print("❌ Only the *sender* can sign the order")
            return

        order.signature = f"signed-by-{user}"  # placeholder
        print(f"✒️  Order {order_id} signed by {user}")

    # 5. ------------------------------------------------------------------
    def cmd_broadcast(self, order_id_str: str) -> None:
        """Send the signed order to *all* authorities and await responses."""
        try:
            order_id = uuid.UUID(order_id_str)
        except ValueError:
            print("❌ order_id must be a valid UUID")
            return

        order = self._pending_orders.get(order_id)
        if order is None:
            print("❌ Unknown order_id – did you *initiate* first?")
            return
        if not order.signature:
            print("❌ Order is not signed – use 'sign' first")
            return

        sender_client = self.clients_map.get(order.sender)
        if sender_client is None:
            print(f"❌ Sender client '{order.sender}' not found")
            return

        success = self._broadcast_order(sender_client, order)
        if success:
            print("✅ Quorum reached – transfer **accepted**")
            # Remove from pending list once finalised
            self._pending_orders.pop(order.order_id, None)
        else:
            print("❌ Quorum NOT reached – transfer remains pending")

    # ------------------------------------------------------------------
    # Helper used by *broadcast*
    # ------------------------------------------------------------------

    def _broadcast_order(self, client: Client, order: TransferOrder) -> bool:
        """Low-level implementation of the broadcast/collect pattern."""
        req = TransferRequestMessage(transfer_order=order)
        successes = 0
        for auth in self.authorities:
            msg = Message(
                message_id=uuid.uuid4(),
                message_type=MessageType.TRANSFER_REQUEST,
                sender=client.address,
                recipient=auth.address,
                timestamp=time.time(),
                payload=req.to_payload(),
            )
            if client.transport.send_message(msg, auth.address):
                # Naïve wait for immediate response (max 3 s)
                resp = self._await_response(client, order.order_id, timeout=3.0)
                if resp and resp.success:
                    successes += 1
                    print(f"   → {auth.name}: ✅ accepted")
                else:
                    print(f"   → {auth.name}: ❌ rejected/time-out")
            else:
                print(f"   → {auth.name}: ❌ send-fail")

        print(f"🗳️  successes={successes}, quorum={self._quorum_weight}")
        return successes >= self._quorum_weight

    def _await_response(
        self, client: Client, order_id: uuid.UUID, *, timeout: float
    ) -> Optional[TransferResponseMessage]:
        """Wait (blocking) for a *TRANSFER_RESPONSE* matching *order_id*."""
        expiry = time.time() + timeout
        while time.time() < expiry:
            msg = client.transport.receive_message(timeout=0.2)
            if (
                msg
                and msg.message_type == MessageType.TRANSFER_RESPONSE
                and msg.payload.get("order_id") == str(order_id)
            ):
                return TransferResponseMessage.from_payload(msg.payload)
        return None 