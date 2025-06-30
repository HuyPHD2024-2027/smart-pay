#!/usr/bin/env python3
"""Light-weight Resillient Ejara Offline Payment System (REPOS) Wi-Fi demo using :class:`mn_wifi.authority.WiFiAuthority`.

Run with *root* privileges because *Mininet-WiFi* requires network
namespace manipulation::

    sudo python3 -m mn_wifi.examples.fastpay_demo -a 4 -l
    sudo python3 -m mn_wifi.examples.fastpay_demo -a 3 -p  # disable plotting

Options
-------
-a / --authorities N   Number of authority nodes (default *3*)
-l / --logs            Launch an *xterm* for every authority that tails its
                       dedicated log file.
-p / --plot            Disable plotting the network graph (plotting is enabled
                       by default).

The script sets up the following topology:

* one *access-point* (``ap1``) at the centre;
* *N* authorities (``auth1`` … ``authN``) implemented via
  :class:`mn_wifi.authority.WiFiAuthority`;
* two demo clients (``user1`` and ``user2``) implemented via
  :class:`mn_wifi.client.Client`.

The demo includes mobility model functionality with RandomDirection mobility
for all nodes, allowing them to move within defined boundaries. Network 
visualization is enabled by default but can be disabled with the ``-p`` flag.

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
from mn_wifi.cli_fastpay import FastPayCLI
from mn_wifi.transport import TransportKind
from mn_wifi.examples.demoCommon import parse_args as _parse_args, open_xterms as _open_xterms, close_xterms as _close_xterms
from mn_wifi.baseTypes import KeyPair
# --------------------------------------------------------------------------------------
# Network-building helpers
# --------------------------------------------------------------------------------------

def _create_network(num_auth: int, enable_plot: bool = True) -> Tuple[Mininet_wifi, List[WiFiAuthority], List[Client]]:
    """Instantiate *Mininet-WiFi* topology with *num_auth* authorities.
    
    Args:
        num_auth: Number of authority nodes to create.
        enable_plot: Whether to enable network graph plotting (default: True).
        
    Returns:
        Tuple containing the network, list of authorities, and list of clients.
    """
    net = Mininet_wifi()

    info("*** Creating Wi-Fi nodes\n")

    # Demo clients ------------------------------------------------------------------
    user1 = net.addStation(
        "user1",
        cls=Client,
        transport_kind=TransportKind.TCP,
        ip="10.0.0.2/8",
        range=10,  
        min_x=5, max_x=25, min_y=20, max_y=40, min_v=1, max_v=5,
    )
    user2 = net.addStation(
        "user2",
        cls=Client,
        transport_kind=TransportKind.TCP,
        ip="10.0.0.3/8",
        range=10,  
        min_x=50, max_x=70, min_y=20, max_y=40, min_v=1, max_v=5,
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
            range=10,  
            position=[20 + (i * 10), 50, 0],
            min_x=15 + (i * 10), max_x=25 + (i * 10), min_y=40, max_y=60, min_v=1, max_v=3,
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

    # Plotting and mobility model setup
    if enable_plot:
        info("*** Plotting network graph\n")
        net.plotGraph(max_x=100, max_y=80)  # Explicit dimensions for proper range visualization

    info("*** Setting up mobility model\n")
    net.setMobilityModel(time=0, model='RandomDirection',
                         max_x=100, max_y=80, seed=20)
    info("*** Starting network\n")
    net.build()
    c1.start()
    ap1.start([c1])

    # Give the simulation a moment to associate STAs
    time.sleep(2)

    # Start FastPay services on authorities
    for auth in authorities:
        auth.start_fastpay_services()

    # Start FastPay services on clients
    for client in clients:
        client.start_fastpay_services()

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
                    authority_signature={},
                    timestamp=time.time()   
                ),
                confirmed_transfers={},
            )
    for client in clients:
        client.state.secret = KeyPair("secret-placeholder")
        client.state.committee = authorities
        client.state.pending_transfer = None
        client.state.sent_certificates = []
        client.state.received_certificates = {}
        client.state.balance = demo_balances[client.state.name]
        client.state.sequence_number = 0

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
        net, authorities, clients = _create_network(opts.authorities, enable_plot=not opts.plot)
        if opts.logs:
            _open_xterms(authorities, clients)

        # ------------------------------------------------------------------
        # Hand over to interactive CLI
        # ------------------------------------------------------------------
        cli = FastPayCLI(net, authorities, clients)
        print("Type 'help_fastpay' for FastPay commands or 'help' for all commands. Ctrl-D or Ctrl-C to exit.\n")
        cli.cmdloop()

    finally:
        if net is not None:
            info("*** Stopping network\n")
            net.stop()
            _close_xterms(authorities, clients)
        info("*** Done\n")


if __name__ == "__main__":
    main() 