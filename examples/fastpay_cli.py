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

from mn_wifi.baseTypes import (
    TransferOrder,
    ConfirmationOrder,
    TransactionStatus,
)
from mn_wifi.client import Client
from mn_wifi.messages import (
    Message,
    MessageType,
    ConfirmationRequestMessage,
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
        # Track which authorities accepted each order so that we can later
        # broadcast a ConfirmationOrder containing their signatures.
        self._order_signers: Dict[uuid.UUID, List[Station]] = {}

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
    def cmd_transfer(self, sender: str, recipient: str, amount: int) -> None:
        """Broadcast a transfer order using :pymeth:`mn_wifi.client.Client.transfer`."""

        client = self.clients_map.get(sender)
        if client is None:
            print(f"❌ Unknown client '{sender}'")
            return

        print(f"🚀 {sender} → {recipient}  amount={amount}")
        try:
            success = client.transfer(recipient, amount)
            if success:
                print("✅ Transfer request broadcast to authorities – awaiting quorum")
            else:
                print("❌ Failed to broadcast transfer request (no authority reachable)")
        except Exception as exc:  # pragma: no cover – defensive, should not occur
            print(f"❌ Transfer failed: {exc}")

    # 0. ------------------------------------------------------------------
    def cmd_infor(self, station: str) -> None:  # noqa: D401 – imperative form
        """Show JSON-formatted ``state`` of *station* **and** optional performance metrics.

        Usage within *fastpay_demo.py* interactive shell::

            FastPay> infor auth1
            FastPay> infor user2
            FastPay> infor all            # show every authority

        Passing *all*, *authorities* or ``*`` will display the information for **every**
        authority node in the committee sequentially.
        """

        # ------------------------------------------------------------------
        # Special-case: *all* / *authorities* / "*"  → iterate over committee.
        # ------------------------------------------------------------------
        if station.lower() in {"all", "authorities", "*"}:
            for auth in self.authorities:
                print("\n===", auth.name, "===")
                self.cmd_infor(auth.name)
            return

        # ------------------------------------------------------------------
        # Single station lookup (authority or client) -----------------------
        # ------------------------------------------------------------------
        node = self._find_node(station)
        if node is None:
            print(f"❌ Unknown station '{station}' – try 'ping' or 'balance' to list names")
            return

        if not hasattr(node, "state"):
            print(f"⚠️  Node '{station}' has no 'state' attribute")
            return

        try:
            state_dict = asdict(node.state)  # type: ignore[arg-type]

            full_info = {"state": state_dict}

            print(json.dumps(full_info, indent=2, default=str))

        except Exception:  # pragma: no cover – fallback when *state* is not a dataclass
            print(str(node.state))

    # ------------------------------------------------------------------
    # New command – voting power
    # ------------------------------------------------------------------

    def cmd_voting_power(self) -> None:
        """Display the *current* voting power of every authority.

        The helper derives a **relative weight** for each authority based on
        its on-chain/off-chain performance.  The reference implementation uses
        the following simplified scoring function::

            score = max(transaction_count - error_count, 0)

        The final *voting power* is the normalised score so that the sum across
        all authorities equals **1.0**.  When all scores are zero (e.g. right
        after network boot-strap) the helper falls back to an *equal weight*
        distribution.
        """

        # Gather raw statistics --------------------------------------------------
        scores: Dict[str, int] = {}
        for auth in self.authorities:
            if hasattr(auth, "get_performance_stats"):
                stats = auth.get_performance_stats()  # type: ignore[attr-defined]
                score = max(int(stats.get("transaction_count", 0)) - int(stats.get("error_count", 0)), 0)
            else:
                score = 0
            scores[auth.name] = score

        total = sum(scores.values())

        # Derive voting power (normalised) ---------------------------------------
        voting_power: Dict[str, float] = {}
        if total == 0:
            # All zeros → equal distribution
            equal = 1.0 / len(self.authorities) if self.authorities else 0.0
            voting_power = {name: equal for name in scores}
        else:
            voting_power = {name: round(score / total, 3) for name, score in scores.items()}

        # Pretty-print result ------------------------------------------------------
        print("⚖️  Current voting power (weighted by performance):")
        for name, power in voting_power.items():
            print(f"   • {name}: {power:.3f}")

    # ------------------------------------------------------------------
    # New command – single authority performance stats
    # ------------------------------------------------------------------

    def cmd_performance(self, authority: str) -> None:  # noqa: D401 – imperative form
        """Print *authority* performance metrics in JSON form.

        Usage::

            FastPay> performance auth1
        """

        # Locate authority --------------------------------------------------------
        auth_node = next((a for a in self.authorities if a.name == authority), None)
        if auth_node is None:
            print(f"❌ Unknown authority '{authority}' – try 'power' to list names")
            return

        if not hasattr(auth_node, "get_performance_stats"):
            print(f"⚠️  Authority '{authority}' does not expose performance metrics")
            return

        metrics = auth_node.get_performance_stats()  # type: ignore[attr-defined]
        print(json.dumps(metrics, indent=2, default=str))


    def cmd_broadcast_confirmation(self, sender: str) -> None:
        """Broadcast a transfer order using :pymeth:`mn_wifi.client.Client.transfer`."""
        client = self.clients_map.get(sender)
        if client is None:
            print(f"❌ Unknown client '{sender}'")
            return

        print(f"🚀 {sender} → broadcast confirmation")
        try:
            client.broadcast_confirmation()
        except Exception as exc:  # pragma: no cover – defensive, should not occur
            print(f"❌ Broadcast confirmation failed: {exc}")
