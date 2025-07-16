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

from mininet.log import info, setLogLevel
from mininet.node import NAT
from mn_wifi.link import wmediumd, mesh
from mn_wifi.wmediumdConnector import interference
from mn_wifi.net import Mininet_wifi
from mn_wifi.authority import WiFiAuthority
from mn_wifi.client import Client
from mn_wifi.cli_fastpay import FastPayCLI
from mn_wifi.transport import TransportKind
from mn_wifi.baseTypes import KeyPair, AccountOffchainState, SignedTransferOrder
from mn_wifi.examples.demoCommon import open_xterms as _open_xterms, close_xterms as _close_xterms


class MeshInternetBridge:
    """HTTP bridge server that enables web backend to communicate with mesh authorities.
    
    This bridge translates HTTP requests to FastPay TCP protocol and enables
    seamless communication between external web interfaces and the mesh network.
    """
    
    def __init__(self, port: int = 8080) -> None:
        """Initialize the mesh internet bridge.
        
        Args:
            port: HTTP server port for the bridge
        """
        self.port = port
        self.authorities: Dict[str, Dict[str, Any]] = {}
        self.server: Optional[socketserver.TCPServer] = None
        self.server_thread: Optional[threading.Thread] = None
        self.running = False
        
    def register_authority(self, authority: WiFiAuthority) -> None:
        """Register an authority with the bridge.
        
        Args:
            authority: WiFiAuthority instance to register
        """
        self.authorities[authority.name] = {
            'name': authority.name,
            'ip': authority.IP(),
            'port': authority.port,
            'position': {
                'x': float(authority.params.get('position', [0, 0, 0])[0]),
                'y': float(authority.params.get('position', [0, 0, 0])[1]),
                'z': float(authority.params.get('position', [0, 0, 0])[2])
            },
            'status': 'online',
            'committee_members': list(authority.committee_members) if hasattr(authority, 'committee_members') else []
        }
        
    def start_bridge_server(self, nat_node: Optional[NAT] = None) -> None:
        """Start the HTTP bridge server.
        
        Args:
            nat_node: NAT node to run the server on (if None, runs on host)
        """
        if self.running:
            return
            
        info(f"🌉 Starting Mesh Internet Bridge on port {self.port}\n")
        
        # Create custom HTTP handler with access to bridge instance
        class BridgeHandler(http.server.BaseHTTPRequestHandler):
            def __init__(self, *args, bridge=None, **kwargs):
                self.bridge = bridge
                super().__init__(*args, **kwargs)
                
            def log_message(self, format: str, *args) -> None:
                """Suppress default HTTP logging."""
                pass
                
            def do_GET(self) -> None:
                """Handle GET requests for discovery and status."""
                try:
                    if self.path == "/authorities":
                        self._send_authorities_list()
                    elif self.path.startswith("/authorities/"):
                        self._handle_authority_request()
                    elif self.path == "/health":
                        self._send_health_status()
                    else:
                        self._send_not_found()
                except Exception as e:
                    self._send_error(str(e))
                    
            def do_POST(self) -> None:
                """Handle POST requests for transfers and operations."""
                try:
                    if "/transfer" in self.path:
                        self._handle_transfer_request()
                    elif "/ping" in self.path:
                        self._handle_ping_request()
                    else:
                        self._send_not_found()
                except Exception as e:
                    self._send_error(str(e))
                    
            def _send_authorities_list(self) -> None:
                """Send list of discovered authorities."""
                response = {
                    'authorities': list(self.bridge.authorities.values()),
                    'count': len(self.bridge.authorities),
                    'timestamp': time.time()
                }
                self._send_json_response(response)
                
            def _handle_authority_request(self) -> None:
                """Handle individual authority requests."""
                path_parts = self.path.split('/')
                if len(path_parts) >= 3:
                    authority_name = path_parts[2]
                    if authority_name in self.bridge.authorities:
                        self._send_json_response(self.bridge.authorities[authority_name])
                    else:
                        self._send_not_found()
                else:
                    self._send_not_found()
                    
            def _handle_transfer_request(self) -> None:
                """Handle transfer requests by forwarding to mesh authorities."""
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length > 0:
                    post_data = self.rfile.read(content_length)
                    try:
                        transfer_data = json.loads(post_data.decode('utf-8'))
                        # Extract authority name from path
                        path_parts = self.path.split('/')
                        authority_name = None
                        for i, part in enumerate(path_parts):
                            if part == "authorities" and i + 1 < len(path_parts):
                                authority_name = path_parts[i + 1]
                                break
                                
                        if authority_name and authority_name in self.bridge.authorities:
                            result = self._forward_to_mesh_authority(authority_name, transfer_data)
                            self._send_json_response(result)
                        else:
                            self._send_error("Authority not found")
                    except json.JSONDecodeError:
                        self._send_error("Invalid JSON data")
                else:
                    self._send_error("No data provided")
                    
            def _handle_ping_request(self) -> None:
                """Handle ping requests to test authority connectivity."""
                path_parts = self.path.split('/')
                authority_name = None
                for i, part in enumerate(path_parts):
                    if part == "authorities" and i + 1 < len(path_parts):
                        authority_name = path_parts[i + 1]
                        break
                        
                if authority_name and authority_name in self.bridge.authorities:
                    result = self._ping_mesh_authority(authority_name)
                    self._send_json_response(result)
                else:
                    self._send_error("Authority not found")
                    
            def _forward_to_mesh_authority(self, authority_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
                """Forward request to mesh authority via TCP.
                
                Args:
                    authority_name: Name of the target authority
                    data: Request data to forward
                    
                Returns:
                    Response from the authority
                """
                authority_info = self.bridge.authorities[authority_name]
                ip = authority_info['ip']
                port = authority_info['port']
                
                try:
                    # Use FastPay TCP protocol to communicate with authority
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(5.0)  # 5 second timeout
                    sock.connect((ip, port))
                    
                    # Send data using FastPay protocol (JSON with length prefix)
                    message = json.dumps(data).encode('utf-8')
                    length_prefix = len(message).to_bytes(4, byteorder='big')
                    sock.send(length_prefix + message)
                    
                    # Receive response
                    response_length_bytes = sock.recv(4)
                    if len(response_length_bytes) == 4:
                        response_length = int.from_bytes(response_length_bytes, byteorder='big')
                        response_data = sock.recv(response_length)
                        response = json.loads(response_data.decode('utf-8'))
                        sock.close()
                        return {
                            'success': True,
                            'data': response,
                            'authority': authority_name,
                            'timestamp': time.time()
                        }
                    else:
                        sock.close()
                        return {
                            'success': False,
                            'error': 'Invalid response from authority',
                            'authority': authority_name,
                            'timestamp': time.time()
                        }
                        
                except Exception as e:
                    return {
                        'success': False,
                        'error': str(e),
                        'authority': authority_name,
                        'timestamp': time.time()
                    }
                    
            def _ping_mesh_authority(self, authority_name: str) -> Dict[str, Any]:
                """Ping mesh authority to test connectivity.
                
                Args:
                    authority_name: Name of the authority to ping
                    
                Returns:
                    Ping result
                """
                authority_info = self.bridge.authorities[authority_name]
                ip = authority_info['ip']
                port = authority_info['port']
                
                try:
                    start_time = time.time()
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(2.0)  # 2 second timeout for ping
                    sock.connect((ip, port))
                    sock.close()
                    end_time = time.time()
                    
                    return {
                        'success': True,
                        'authority': authority_name,
                        'latency_ms': round((end_time - start_time) * 1000, 2),
                        'timestamp': time.time()
                    }
                except Exception as e:
                    return {
                        'success': False,
                        'authority': authority_name,
                        'error': str(e),
                        'timestamp': time.time()
                    }
                    
            def _send_health_status(self) -> None:
                """Send bridge health status."""
                response = {
                    'status': 'healthy',
                    'bridge_port': self.bridge.port,
                    'authorities_count': len(self.bridge.authorities),
                    'timestamp': time.time()
                }
                self._send_json_response(response)
                
            def _send_json_response(self, data: Dict[str, Any]) -> None:
                """Send JSON response.
                
                Args:
                    data: Data to send as JSON
                """
                response_data = json.dumps(data).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(response_data)))
                self.send_header('Access-Control-Allow-Origin', '*')  # Enable CORS
                self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
                self.send_header('Access-Control-Allow-Headers', 'Content-Type')
                self.end_headers()
                self.wfile.write(response_data)
                
            def _send_error(self, message: str) -> None:
                """Send error response.
                
                Args:
                    message: Error message
                """
                response = {
                    'error': message,
                    'timestamp': time.time()
                }
                response_data = json.dumps(response).encode('utf-8')
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(response_data)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(response_data)
                
            def _send_not_found(self) -> None:
                """Send 404 not found response."""
                response = {
                    'error': 'Not found',
                    'timestamp': time.time()
                }
                response_data = json.dumps(response).encode('utf-8')
                self.send_response(404)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(response_data)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(response_data)
        
        # Create HTTP server with custom handler
        def handler_factory(*args, **kwargs):
            return BridgeHandler(*args, bridge=self, **kwargs)
            
        try:
            self.server = socketserver.TCPServer(("", self.port), handler_factory)
            self.server.allow_reuse_address = True
            self.running = True
            
            # Start server in separate thread
            self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.server_thread.start()
            
            info(f"✅ Mesh Internet Bridge started on port {self.port}\n")
        except Exception as e:
            info(f"❌ Failed to start bridge server: {e}\n")
            
    def stop_bridge_server(self) -> None:
        """Stop the HTTP bridge server."""
        if self.running and self.server:
            info("🛑 Stopping Mesh Internet Bridge\n")
            self.running = False
            self.server.shutdown()
            self.server.server_close()
            if self.server_thread and self.server_thread.is_alive():
                self.server_thread.join(timeout=2)
            self.server = None
            self.server_thread = None


def create_mesh_network_with_internet(
    num_authorities: int = 5,
    num_clients: int = 3,
    mesh_id: str = "fastpay-mesh",
    enable_security: bool = True,
    enable_mobility: bool = True,
    enable_plot: bool = False,
    enable_internet: bool = False,
    gateway_port: int = 8080
) -> Tuple[Mininet_wifi, List[WiFiAuthority], List[Client], Optional[MeshInternetBridge]]:
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
            cls=WiFiAuthority,  # use core authority class
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
            cls=Client,  # use core client class
            ip=f"10.0.0.{20 + i}/8",
            port=9000 + i,
            position=[30 + (i * 20), 20, 0],
            range=30,
            txpower=15,
        )
        clients.append(client)
    
    # Add internet gateway if enabled
    bridge = None
    if enable_internet:
        info("🌐 Adding Internet Gateway\n")
        
        # Add access point for internet gateway
        ap_inet = net.addAccessPoint(
            'ap-inet', 
            ssid='inet-gateway',
            position='150,50,0',
            range=100,
            ip='10.0.0.254/8'
        )
        
        # Add NAT for internet connectivity (mn-wifi native)
        nat = net.addNAT(name='nat0', connect=ap_inet, ip='10.0.0.1/8')
        
        # Create mesh-internet bridge service
        bridge = MeshInternetBridge(port=gateway_port)
    
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

    # Add gateway connection if internet is enabled
    if enable_internet and bridge:
        info("*** Configuring internet gateway connections\n")
        # Connect some authorities to the internet gateway AP
        for i in range(min(2, num_authorities)):  # Connect first 2 authorities to gateway
            net.addLink(authorities[i], ap_inet)

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
    
    # ------------------------------------------------------------------
    # Monkey-patch helper methods so CLI keeps working
    # ------------------------------------------------------------------
    import types

    def _get_mesh_peers(self):
        """Return list of mesh neighbour MAC addresses (uses `iw mpath`)."""
        if self.wintfs:
            intf = list(self.wintfs.values())[0]
            output = self.cmd(f'iw dev {intf.name} mpath dump')
            peers = []
            for line in output.split('\n'):
                if 'DEST' in line and 'NEXT_HOP' in line:
                    parts = line.split()
                    if len(parts) > 1:
                        peers.append(parts[1])
            return peers
        return []

    def _transfer_via_mesh(self, recipient: str, amount: int):  # type: ignore[override]
        """Fallback helper that just re-uses normal transfer."""
        return self.transfer(recipient, amount)

    # Attach helpers to every node ------------------------------------------------
    for node in [*authorities, *clients]:
        node.get_mesh_peers = types.MethodType(_get_mesh_peers, node)  # type: ignore[attr-defined]

    for client in clients:
        client.transfer_via_mesh = types.MethodType(_transfer_via_mesh, client)  # type: ignore[attr-defined]
    
    return net, authorities, clients, bridge


def configure_internet_access(
    net: Mininet_wifi, 
    authorities: List[WiFiAuthority], 
    clients: List[Client], 
    bridge: Optional[MeshInternetBridge]
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
    
    # Configure routing for mesh nodes to reach internet via gateway
    gateway_ip = "10.0.0.1"  # NAT gateway IP
    
    # Add default routes to all mesh nodes for internet connectivity
    for auth in authorities:
        auth.cmd(f"ip route add default via {gateway_ip}")
        bridge.register_authority(auth)
        
    for client in clients:
        client.cmd(f"ip route add default via {gateway_ip}")
    
    # Start bridge service
    bridge.start_bridge_server()


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
                balance=balance,
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
        description="Enhanced FastPay IEEE 802.11s Mesh Network Demo with Internet Gateway",
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
        "--internet", "-i",
        action="store_true",
        help="Enable internet gateway bridge"
    )
    
    parser.add_argument(
        "--gateway-port", "-g",
        type=int, default=8080,
        help="Gateway HTTP bridge port (default: 8080)"
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
    """Main entry point for the enhanced mesh demo."""
    args = parse_args()
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
        net, authorities, clients, bridge = create_mesh_network_with_internet(
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
        
        # Configure internet access if enabled
        if args.internet and bridge:
            configure_internet_access(net, authorities, clients, bridge)
        
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
        info("*** Starting Enhanced FastPay CLI\n")
        cli = FastPayCLI(net, authorities, clients)
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