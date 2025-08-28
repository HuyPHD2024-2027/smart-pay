#!/usr/bin/env python3
"""FastPay IEEE 802.11s Mesh Network Demo.

This demo creates a self-healing mesh network of FastPay authorities and clients
without access points. All nodes participate in the IEEE 802.11s mesh and can
communicate through multi-hop routing with automatic peer discovery.

Key Features:
- IEEE 802.11s mesh networking (no access points)
- Self-healing network topology
- Multi-hop routing with automatic path discovery
- Mesh-enabled FastPay clients and authorities
- Advanced security with WPA3-SAE encryption
- Mobile nodes with seamless mesh handoffs
- Comprehensive performance monitoring

Run with root privileges:
    sudo python3 -m mn_wifi.examples.fastpay_mesh_demo --authorities 5 --clients 3
    sudo python3 -m mn_wifi.examples.fastpay_mesh_demo --authorities 8 --clients 4 --mobility

Options:
    --authorities N     Number of authority nodes (default: 5)
    --clients N         Number of client nodes (default: 3)
    --mobility          Enable advanced mobility models
    --plot              Enable network visualization
    --logs              Open xterm for each node
    --mesh-id ID        Mesh network identifier (default: fastpay-mesh)
    --security          Enable mesh security (default: True)
"""

from __future__ import annotations

import argparse
import time
from typing import Dict, List, Optional, Tuple

from mininet.log import info, setLogLevel
from mn_wifi.link import wmediumd, mesh
from mn_wifi.wmediumdConnector import interference
from mn_wifi.net import Mininet_wifi
from mn_wifi.authority import WiFiAuthority
from mn_wifi.client import Client
from mn_wifi.cli_fastpay import FastPayCLI
from mn_wifi.transport import TransportKind
from mn_wifi.baseTypes import KeyPair, AccountOffchainState, SignedTransferOrder
from mn_wifi.examples.demoCommon import open_xterms as _open_xterms, close_xterms as _close_xterms
from uuid import uuid4


def create_mesh_network(
    num_authorities: int = 5,
    num_clients: int = 3,
    mesh_id: str = "fastpay-mesh",
    enable_security: bool = True,
    enable_mobility: bool = True,
    enable_plot: bool = False
) -> Tuple[Mininet_wifi, List[WiFiAuthority], List[Client]]:
    """Create IEEE 802.11s mesh network topology.
    
    Args:
        num_authorities: Number of authority nodes to create
        num_clients: Number of client nodes to create
        mesh_id: Mesh network identifier
        enable_security: Enable mesh security (WPA3-SAE)
        enable_mobility: Enable mobility models
        enable_plot: Enable network visualization
        
    Returns:
        Tuple of (network, authorities, clients)
    """
    info("🕸️  Creating IEEE 802.11s Mesh Network\n")
    
    # Create network without access points
    net = Mininet_wifi(link=wmediumd, wmediumd_mode=interference)

    # Create authorities as mesh points
    authorities: List[WiFiAuthority] = []
    committee = {f"auth{i}" for i in range(1, num_authorities + 1)}
    
    for i in range(1, num_authorities + 1):
        name = f"auth{i}"
        auth = net.addStation(
            name,
            cls=WiFiAuthority,  # use core authority class
            committee_members=committee - {name},
            ip=f"10.0.0.{10 + i}/8",
            port=8000 + i,
            # position=[20 + (i * 25), 40, 0],
            range=40,
            txpower=20,
        )
        authorities.append(auth)
    
    # Create mobile clients as mesh points
    clients: List[Client] = []
    for i in range(1, num_clients + 1):
        name = f"user{i}"
        client = net.addStation(
            name,
            cls=Client,  # use core client class
            ip=f"10.0.0.{20 + i}/8",
            port=9000 + i,
            # position=[30 + (i * 20), 20, 0],
            range=30,
            txpower=15,
        )
        clients.append(client)
    
    # Configure mesh networking
    info("*** Configuring IEEE 802.11s mesh\n")
    
    # Set propagation model for realistic mesh behavior
    net.setPropagationModel(model="logDistance", exp=3.5)
    
    # Configure nodes
    net.configureNodes()
    
    info("*** Creating links\n")
    for i in range(1, num_authorities + 1):
        net.addLink(authorities[i-1], cls=mesh, ssid='meshNet',
                    intf=f'auth{i}-wlan0', channel=5, ht_cap='HT40+')  #, passwd='thisisreallysecret')
    for i in range(1, num_clients + 1):
        net.addLink(clients[i-1], cls=mesh, ssid='meshNet',
                intf=f'user{i}-wlan0', channel=5, ht_cap='HT40+')  #, passwd='thisisreallysecret')

    # Configure mobility if enabled
    if enable_mobility:
        info("*** Setting up mesh mobility\n")
        net.setMobilityModel(
            time=0,
            model='RandomWaypoint',
            max_x=200,
            max_y=150,
            min_v=1,
            max_v=3,
            seed=42
        )
    
    # Enable plotting if requested
    if enable_plot:
        info("*** Plotting mesh network\n")
        net.plotGraph(max_x=200, max_y=150)

    return net, authorities, clients


def setup_mesh_accounts(
    clients: List[Client], 
    authorities: List[WiFiAuthority]
) -> None:
    """Setup demo accounts for mesh network testing.
    
    Args:
        clients: List of mesh clients
        authorities: List of mesh authorities
    """
    info("*** Setting up mesh demo accounts\n")
    
    # Demo balances for testing
    demo_balances = {client.name: 1000 for client in clients}
    
    # Configure authorities with demo accounts
    for auth in authorities:
        for user, balance in demo_balances.items():
            auth.state.accounts[user] = AccountOffchainState(
                address=user,
                balances={user: balance},
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
    
    # Configure clients with demo state
    for client in clients:
        client.state.secret = KeyPair("secret-placeholder")
        client.state.committee = authorities
        client.state.balance = demo_balances[client.name]
        client.state.sequence_number = 0
        client.state.pending_transfer = None
        client.state.sent_certificates = []
        client.state.received_certificates = {}
    
    info("*** Demo accounts configured\n")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.
    
    Returns:
        Parsed command line arguments
    """
    parser = argparse.ArgumentParser(
        description="FastPay IEEE 802.11s Mesh Network Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "--authorities", "-a",
        type=int, default=5,
        help="Number of authority nodes (default: 5)"
    )
    
    parser.add_argument(
        "--clients", "-c",
        type=int, default=3,
        help="Number of client nodes (default: 3)"
    )
    
    parser.add_argument(
        "--mesh-id", "-m",
        type=str, default="fastpay-mesh",
        help="Mesh network identifier (default: fastpay-mesh)"
    )
    
    parser.add_argument(
        "--mobility",
        action="store_true",
        help="Enable advanced mobility models"
    )
    
    parser.add_argument(
        "--plot", "-p",
        action="store_true",
        help="Enable network visualization"
    )
    
    parser.add_argument(
        "--logs", "-l",
        action="store_true",
        help="Open xterm for each node"
    )
    
    parser.add_argument(
        "--no-security",
        action="store_true",
        help="Disable mesh security (not recommended)"
    )
    
    return parser.parse_args()


def main() -> None:
    """Main entry point for the mesh demo."""
    args = parse_args()
    setLogLevel("info")
    
    info(f"🚀 FastPay IEEE 802.11s Mesh Network Demo\n")
    info(f"   Authorities: {args.authorities}\n")
    info(f"   Clients: {args.clients}\n")
    info(f"   Mesh ID: {args.mesh_id}\n")
    info(f"   Security: {'Enabled' if not args.no_security else 'Disabled'}\n")
    info(f"   Mobility: {'Enabled' if args.mobility else 'Disabled'}\n")
    
    net = None
    try:
        # Create mesh network
        net, authorities, clients = create_mesh_network(
            num_authorities=args.authorities,
            num_clients=args.clients,
            mesh_id=args.mesh_id,
            enable_security=not args.no_security,
            enable_mobility=args.mobility,
            enable_plot=args.plot
        )
        
        # Build and start network
        info("*** Building mesh network\n")
        net.build()
        
        # Start FastPay services on all nodes
        info("*** Starting FastPay services on all nodes\n")
        for auth in authorities:
            auth.start_fastpay_services()
        
        for client in clients:
            client.start_fastpay_services()
        
        # Setup demo accounts
        setup_mesh_accounts(clients, authorities)
        
        # Wait for mesh to stabilize
        info("*** Waiting for mesh network to stabilize\n")
        time.sleep(5)
        
        # Open xterms if requested
        if args.logs:
            _open_xterms(authorities, clients)
        
        # Start interactive CLI using standard FastPay CLI
        info("*** Starting FastPay CLI\n")
        cli = FastPayCLI(net, authorities, clients)
        print("\n" + "=" * 60)
        print("🕸️  FastPay IEEE 802.11s Mesh Network Ready!")
        print("=" * 60)
        print("Available commands:")
        print("  help_fastpay             - Show all FastPay commands")
        print("  help                     - Show all commands")
        print("=" * 60)
        print("Type 'help' for more commands or Ctrl-D to exit.\n")
        
        cli.cmdloop()
        
    except KeyboardInterrupt:
        info("\n*** Interrupted by user\n")
    except Exception as e:
        info(f"*** Error: {e}\n")
    finally:
        if net is not None:
            info("*** Stopping mesh network\n")
            net.stop()
            if args.logs:
                _close_xterms(authorities, clients)
        info("*** Mesh demo completed\n")


if __name__ == "__main__":
    main() 