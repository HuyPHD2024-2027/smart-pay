#!/usr/bin/env python3
"""Enhanced FastPay IEEE 802.11s Mesh Network Demo with Internet Gateway.

This enhanced demo creates a mesh network that can communicate with external 
web backends through a dedicated internet gateway, enabling real-world integration
while maintaining mesh network integrity.

Key Features:
- IEEE 802.11s mesh networking with internet connectivity
- Gateway bridge for external communication
- Real-time authority discovery via TCP
- HTTP bridge server for protocol translation
- Maintained mesh network isolation and security

Run with root privileges:
    sudo python3 -m mn_wifi.examples.fastpay_mesh_internet_demo --authorities 5 --clients 3 --internet
    sudo python3 -m mn_wifi.examples.fastpay_mesh_internet_demo --authorities 8 --clients 4 --internet --plot

Options:
    --authorities N     Number of authority nodes (default: 5)
    --clients N         Number of client nodes (default: 3)
    --internet          Enable internet gateway (default: False)
    --gateway-port P    Gateway HTTP bridge port (default: 8080)
    --mobility          Enable advanced mobility models
    --plot              Enable network visualization
    --logs              Open xterm for each node
    --mesh-id ID        Mesh network identifier (default: fastpay-mesh)
    --security          Enable mesh security (default: True)
"""

from __future__ import annotations

import argparse
import asyncio
import http.server
import json
import socket
import socketserver
import sys
import threading
import time
from typing import Dict, List, Optional, Tuple, Any, Union
from urllib.parse import urlparse, parse_qs
from uuid import uuid4, UUID
import dataclasses

from mininet.log import info, setLogLevel
from mininet.nodelib import NAT
from mininet.link import TCLink
from mn_wifi.link import wmediumd, mesh
from mn_wifi.wmediumdConnector import interference
from mn_wifi.net import Mininet_wifi
from mn_wifi.authority import WiFiAuthority
from mn_wifi.client import Client
from mn_wifi.cli_fastpay import FastPayCLI
from mn_wifi.transport import TransportKind
from mn_wifi.baseTypes import KeyPair, AccountOffchainState, SignedTransferOrder
from mn_wifi.bridge import Bridge
from mn_wifi.gateway import Gateway
from mn_wifi.examples.demoCommon import (
    open_xterms as _open_xterms,
    close_xterms as _close_xterms,
    parse_mesh_internet_args,
)
def create_mesh_network_with_internet(
    num_authorities: int = 5,
    num_clients: int = 3,
    mesh_id: str = "fastpay-mesh",
    enable_security: bool = True,
    enable_mobility: bool = True,
    enable_plot: bool = False,
    enable_internet: bool = False,
    gateway_port: int = 8080
) -> Tuple[Mininet_wifi, List[WiFiAuthority], List[Client], Optional[Bridge]]:
    """Create IEEE 802.11s mesh network topology with optional internet gateway.
    
    Args:
        num_authorities: Number of authority nodes to create
        num_clients: Number of client nodes to create
        mesh_id: Mesh network identifier
        enable_security: Enable mesh security (WPA3-SAE)
        enable_mobility: Enable mobility models
        enable_plot: Enable network visualization
        enable_internet: Enable internet gateway bridge
        gateway_port: Port for the HTTP bridge server
        
    Returns:
        Tuple of (network, authorities, clients, bridge)
    """
    info("🕸️  Creating IEEE 802.11s Mesh Network with Internet Gateway\n")
    
    # Create network without access points
    net = Mininet_wifi(link=wmediumd, wmediumd_mode=interference)

    # Create authorities as mesh points
    authorities: List[WiFiAuthority] = []
    committee = {f"auth{i}" for i in range(1, num_authorities + 1)}
    
    for i in range(1, num_authorities + 1):
        name = f"auth{i}"
        auth = net.addStation(
            name,
            cls=WiFiAuthority,  
            committee_members=committee - {name},
            ip=f"10.0.0.{10 + i}/8",
            port=8000 + i,
            position=[20 + (i * 25), 40, 0],
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
            cls=Client,  
            ip=f"10.0.0.{20 + i}/8",
            port=9000 + i,
            # position=[30 + (i * 20), 20, 0],
            range=30,
            txpower=15,
        )
        clients.append(client)
    
    # Add internet gateway if enabled
    bridge = None
    gateway = None
    if enable_internet:
        info("🌐 Adding Internet Gateway\n")
        
        # Add host node as internet gateway (replaces access point)
        gateway = net.addStation(
            'gw',
            cls=Gateway,
            ip='10.0.0.254/8',
            # position=[20, 40, 0]
        )
        
        # Add NAT for internet connectivity using the host gateway
        nat = net.addNAT(name='nat0', connect=gateway, ip='10.0.0.1/8')
        
        # Create mesh-internet bridge service, passing host so HTTP API can
        # reuse host.forward_transfer when /transfer is called.
        bridge = Bridge(gateway, net=net, port=gateway_port)
    
    # Configure mesh networking
    info("*** Configuring IEEE 802.11s mesh\n")
    
    # Set propagation model for realistic mesh behavior
    net.setPropagationModel(model="logDistance", exp=3.5)
    
    # Configure nodes
    net.configureNodes()
    
    info("*** Creating mesh links\n")
    for i in range(1, num_authorities + 1):
        net.addLink(authorities[i-1], cls=mesh, ssid='meshNet',
                    intf=f'auth{i}-wlan0', channel=5, ht_cap='HT40+')
    for i in range(1, num_clients + 1):
        net.addLink(clients[i-1], cls=mesh, ssid='meshNet',
                intf=f'user{i}-wlan0', channel=5, ht_cap='HT40+')
    net.addLink(gateway, cls=mesh, ssid='meshNet',
                intf=f'gw-wlan0', channel=5, ht_cap='HT40+')
    
    # # Add gateway connection if internet is enabled
    # if enable_internet:
    #     info("*** Configuring internet gateway connections\n")
    #     # # Connect first authority to the internet gateway host via wired link
    #     for i in range(1, num_authorities + 1):
    #         net.addLink(authorities[i-1], gateway, cls=TCLink)


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

    return net, authorities, clients, gateway, bridge


def configure_internet_access(
    net: Mininet_wifi, 
    authorities: List[WiFiAuthority], 
    gateway: Optional[Node_wifi],
    bridge: Optional[Bridge]
) -> None:
    """Configure internet access for mesh nodes via NAT gateway.
    
    Args:
        net: Mininet-wifi network instance
        authorities: List of mesh authorities
        clients: List of mesh clients
        bridge: Mesh internet bridge instance
    """
    if not bridge:
        return
        
    info("*** Configuring internet access for mesh nodes\n")
    
    # Register authorities with bridge for HTTP API access
    for auth in authorities:
        bridge.register_authority(auth)
        gateway.register_authority(auth)
    
    # The NAT routing is automatically configured by mn-wifi's addNAT method
    # which sets default routes for all stations in the network
    info("*** NAT routing configured automatically by mn-wifi\n")
    
    # Enable IP forwarding on gateway host if needed
    gateway.cmd('sysctl -w net.ipv4.ip_forward=1')
    info(f"*** IP forwarding enabled on {gateway.name}\n")
    
    # Start bridge service on gateway host
    bridge.start_bridge_server(gateway)

def main() -> None:
    """Main entry point for the enhanced mesh demo."""
    args = parse_mesh_internet_args()
    setLogLevel("info")
    
    info(f"🚀 Enhanced FastPay IEEE 802.11s Mesh Network Demo\n")
    info(f"   Authorities: {args.authorities}\n")
    info(f"   Clients: {args.clients}\n")
    info(f"   Mesh ID: {args.mesh_id}\n")
    info(f"   Internet Gateway: {'Enabled' if args.internet else 'Disabled'}\n")
    info(f"   Gateway Port: {args.gateway_port}\n")
    info(f"   Security: {'Enabled' if not args.no_security else 'Disabled'}\n")
    info(f"   Mobility: {'Enabled' if args.mobility else 'Disabled'}\n")
    
    net = None
    bridge = None
    try:
        # Create enhanced mesh network with internet gateway
        net, authorities, clients, gateway, bridge = create_mesh_network_with_internet(
            num_authorities=args.authorities,
            num_clients=args.clients,
            mesh_id=args.mesh_id,
            enable_security=not args.no_security,
            enable_mobility=args.mobility,
            enable_plot=args.plot,
            enable_internet=args.internet,
            gateway_port=args.gateway_port
        )
        
        # Build and start network
        info("*** Building enhanced mesh network\n")
        net.build()
        
        # info("*** Assigning IPs to wired interfaces for auth-gateway link\n")
        # for i, auth in enumerate(authorities, start=1):
        #     auth_ip = f"192.168.100.{i}"
        #     gw_ip = f"192.168.100.{10 + i}"  

        #     auth.setIP(auth_ip + '/24', intf=f'{auth.name}-eth1')
        #     gateway.setIP(gw_ip + '/24', intf=f'gw-eth{i}')

        # Configure internet access if enabled
        if args.internet and bridge:
            configure_internet_access(net, authorities, gateway, bridge)
        
        # Start FastPay services on all nodes
        info("*** Starting FastPay services on all nodes\n")
        for auth in authorities:
            auth.start_fastpay_services()
        
        for client in clients:
            client.start_fastpay_services()
        
        gateway.start_gateway_services()
        
        # Wait for mesh to stabilize
        info("*** Waiting for mesh network to stabilize\n")
        time.sleep(5)
        
        # Open xterms if requested
        if args.logs:
            _open_xterms(authorities, clients)
        
        # Start interactive CLI using standard FastPay CLI
        info("*** Starting Enhanced FastPay CLI\n")
        cli = FastPayCLI(net, authorities, clients, gateway)
        print("\n" + "=" * 70)
        print("🕸️  Enhanced FastPay IEEE 802.11s Mesh Network Ready!")
        if args.internet:
            print(f"🌐 Internet Gateway Bridge: http://10.0.0.254:{args.gateway_port}")
        print("=" * 70)
        print("Available commands:")
        print("  help_fastpay             - Show all FastPay commands")
        print("  help                     - Show all commands")
        if args.internet:
            print("  Test gateway bridge:")
            print(f"    curl http://10.0.0.254:{args.gateway_port}/authorities")
            print(f"    curl http://10.0.0.254:{args.gateway_port}/health")
            print(f"    curl http://10.0.0.254:{args.gateway_port}/shards")
        print("=" * 70)
        print("Type 'help' for more commands or Ctrl-D to exit.\n")
        
        cli.cmdloop()
        
    except KeyboardInterrupt:
        info("\n*** Interrupted by user\n")
    except Exception as e:
        info(f"*** Error: {e}\n")
        import traceback
        traceback.print_exc()
    finally:
        if bridge:
            bridge.stop_bridge_server()
        if net is not None:
            info("*** Stopping enhanced mesh network\n")
            net.stop()
            if args.logs:
                _close_xterms(authorities, clients)
        info("*** Enhanced mesh demo completed\n")


if __name__ == "__main__":
    main() 