#!/usr/bin/env python3
"""Light-weight Resillient Ejara Offline Payment System (REPOS) Wi-Fi demo using :class:`mn_wifi.authority.WiFiAuthority`.

Run with *root* privileges because *Mininet-WiFi* requires network
namespace manipulation::

    sudo python3 -m mn_wifi.examples.fastpay_demo -a 4 -l

Options
-------
-a / --authorities N   Number of authority nodes (default *3*)
-l / --logs            Launch an *xterm* for every authority that tails its
                       dedicated log file.

The script sets up the following topology:

* one *access-point* (``ap1``) at the centre;
* *N* authorities (``auth1`` … ``authN``) implemented via
  :class:`mn_wifi.authority.WiFiAuthority`;
* two demo clients (``user1`` and ``user2``) implemented via
  :class:`mn_wifi.client.Client`.

Once the network is up it hands control to the interactive *FastPay CLI* (see
``mn_wifi/examples/fastpay_cli.py``).
"""

from __future__ import annotations

import time
from typing import List, Tuple

from mininet.log import info, setLogLevel
from mn_wifi.net import Mininet_wifi
from mn_wifi.authority import WiFiAuthority
from mn_wifi.client import Client
from mn_wifi.examples.fastpay_cli import FastPayCLI
from mn_wifi.transport import TransportKind
from mn_wifi.examples.demoCommon import parse_args as _parse_args, open_xterms as _open_xterms, close_xterms as _close_xterms
from mn_wifi.baseTypes import KeyPair
# --------------------------------------------------------------------------------------
# Network-building helpers
# --------------------------------------------------------------------------------------

def _create_network(num_auth: int) -> Tuple[Mininet_wifi, List[WiFiAuthority], List[Client]]:
    """Instantiate *Mininet-WiFi* topology with *num_auth* authorities."""
    net = Mininet_wifi()

    info("*** Creating Wi-Fi nodes\n")

    # Demo clients ------------------------------------------------------------------
    user1 = net.addStation(
        "user1",
        cls=Client,
        transport_kind=TransportKind.TCP,
        ip="10.0.0.2/8",
        position="10,30,0",
    )
    user2 = net.addStation(
        "user2",
        cls=Client,
        transport_kind=TransportKind.TCP,
        ip="10.0.0.3/8",
        position="60,30,0",
    )
    clients = [user1, user2]
    # Authorities -------------------------------------------------------------------
    authorities: List[WiFiAuthority] = []
    committee = {f"auth{i}" for i in range(1, num_auth + 1)}
    for i in range(1, num_auth + 1):
        name = f"auth{i}"
        auth = net.addStation(
            name,
            cls=WiFiAuthority,
            committee_members=committee - {name},
            shard_assignments=set(),
            ip=f"10.0.0.{10 + i}/8",
            port=8000 + i,
            position=[20 + (i * 10), 50, 0],
        )
        authorities.append(auth)

    # Access point & controller ------------------------------------------------------
    ap1 = net.addAccessPoint(
        "ap1", ssid="fastpay-net", mode="g", channel="1", position="35,40,0", range=120
    )
    c1 = net.addController("c1")

    # Propagation model (simple logDistance)
    net.setPropagationModel(model="logDistance", exp=3.0)

    info("*** Configuring nodes\n")
    net.configureNodes()

    # Basic wired link between AP and a dummy host (internet gateway)
    h1 = net.addHost("gw", ip="10.0.0.254/8")
    net.addLink(ap1, h1)

    info("*** Starting network\n")
    net.build()
    c1.start()
    ap1.start([c1])

    # Give the simulation a moment to associate STAs
    time.sleep(2)

    # Start FastPay services on authorities
    for auth in authorities:
        auth.start_fastpay_services()

    # Create demo accounts so that *balance* and transfers work out-of-the-box
    _setup_demo_accounts(clients, authorities)

    return net, authorities, clients


def _setup_demo_accounts(clients: List[Client], authorities: List[WiFiAuthority]) -> None:
    """Inject a handful of pre-funded user accounts into every authority."""
    from mn_wifi.baseTypes import AccountOffchainState, SignedTransferOrder   # local import to avoid cycles
    from uuid import uuid4
    demo_balances = {"user1": 1_000, "user2": 1_000}

    for auth in authorities:
        for user, bal in demo_balances.items():
            auth.state.accounts[user] = AccountOffchainState(
                address=user,
                balance=bal,
                sequence_number=0,
                last_update=time.time(),
                pending_confirmation=SignedTransferOrder(
                    order_id=uuid4(),
                    transfer_order=None,
                    authority_signatures={},
                    timestamp=time.time()
                ),
                confirmed_transfers={},
            )
    for client in clients:
        client.state.balance = 1000
        client.state.secret = KeyPair("secret-placeholder")
        client.state.sequence_number = 0
        client.state.last_update = time.time()
        client.state.pending_confirmation = None
        client.state.confirmed_transfers = {}
        
    client.logger.info("Injected demo accounts") if hasattr(client, "logger") else None


# --------------------------------------------------------------------------------------
# Argument parsing & entry-point
# --------------------------------------------------------------------------------------

def main() -> None:
    """Entry-point used by ``python -m mn_wifi.examples.fastpay_demo``."""

    opts = _parse_args()
    setLogLevel("info")

    info("🚀 Resillient Ejara Offline Payment System (REPOS) Wi-Fi demo (authorities=%d)\n" % opts.authorities)

    net = None
    try:
        net, authorities, clients = _create_network(opts.authorities)
        if opts.logs:
            _open_xterms(authorities, clients)

        # ------------------------------------------------------------------
        # Hand over to interactive CLI
        # ------------------------------------------------------------------
        cli = FastPayCLI(authorities, clients)
        print("Type 'help' for a list of commands. Ctrl-D or Ctrl-C to exit.\n")

        while True:
            try:
                line = input("FastPay> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("")
                break

            if not line:
                continue
            parts = line.split()
            cmd = parts[0]

            if cmd in ("exit", "quit"):
                break
            if cmd == "help":
                print("Available commands:")
                print("   ping <src> <dst>")
                print("   balance <user>")
                print("   infor <station>")
                print("   power")
                print("   performance <authority>")
                print("   initiate <sender> <recipient> <amount>")
                print("   sign <order-id> <sender>")
                print("   broadcast order <order-id>")
                print("   broadcast confirmation <order-id>")
                print("   quit / exit")
                continue

            # Dispatch to CLI helpers ------------------------------------------------
            try:
                if cmd == "ping" and len(parts) == 3:
                    cli.cmd_ping(parts[1], parts[2])
                elif cmd == "balance" and len(parts) == 2:
                    cli.cmd_balance(parts[1])
                elif cmd == "infor" and len(parts) == 2:
                    cli.cmd_infor(parts[1])
                elif cmd == "power" and len(parts) == 1:
                    cli.cmd_voting_power()
                elif cmd == "performance" and len(parts) == 2:
                    cli.cmd_performance(parts[1])
                elif cmd == "initiate" and len(parts) == 4:
                    cli.cmd_initiate(parts[1], parts[2], int(parts[3]))
                elif cmd == "sign" and len(parts) == 3:
                    cli.cmd_sign(parts[1], parts[2])
                elif len(parts) == 3 and parts[1] == "order":
                    cli.cmd_broadcast(parts[2])
                elif len(parts) == 3 and parts[1] == "confirmation":
                    cli.cmd_broadcast_confirmation(parts[2])
                else:
                    print("❓ Unknown / malformed command – type 'help'")
            except Exception as exc:  # pragma: no cover
                print(f"❌ Command failed: {exc}")

    finally:
        if net is not None:
            info("*** Stopping network\n")
            net.stop()
            _close_xterms(authorities, clients)
        info("*** Done\n")


if __name__ == "__main__":
    main() 