#!/usr/bin/env python3

"""
Example usage of WiFiAuthority with Mininet-WiFi addStation.

This script demonstrates how to:
1. Import WiFiAuthority from mn_wifi
2. Create authorities using addStation with cls=WiFiAuthority
3. Set up a FastPay committee network using standard infrastructure mode
4. Test basic functionality with access point connectivity
5. Enable authority communication through standard WiFi infrastructure
6. Test transfer order broadcasting and verification

This uses standard WiFi infrastructure with an access point that all
authorities connect to for communication.
"""

import time
import sys
import socket
import json
import threading
import queue
import subprocess
import os
from uuid import uuid4
from typing import Dict, List, Optional
from dataclasses import asdict

from mininet.log import setLogLevel, info
from mn_wifi.net import Mininet_wifi
from mn_wifi.authority import WiFiAuthority
from mn_wifi.node import Station
from mn_wifi.baseTypes import Address, NodeType, TransferOrder
from mn_wifi.messages import Message, MessageType, TransferRequestMessage
from mn_wifi.authorityLogger import AuthorityLogger

class TransferTestClient:
    """Test client for sending transfer orders to authorities."""
    
    def __init__(self, client_name: str):
        """Initialize test client.
        
        Args:
            client_name: Name of the test client
        """
        self.client_name = client_name
        self.socket = None
        self.logger = AuthorityLogger(client_name)
        self.logger.info("Test client initialized")
    
    def connect(self, authority: Station) -> bool:
        """Connect to authority server.
        
        Args:
            authority: Authority node to connect to
            
        Returns:
            True if connected successfully, False otherwise
        """
        try:
            # Get the first wireless interface's IP address
            if not authority.wintfs:
                self.logger.error(f"Authority {authority.name} has no wireless interfaces")
                return False
                
            # Get the first interface's IP address
            auth_ip = authority.wintfs[0].ip
            auth_port = authority.address.port
            
            self.logger.info(f"Connecting to authority {authority.name} at {auth_ip}:{auth_port}")
            
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10)
            self.socket.connect((auth_ip, auth_port))
            
            self.logger.info(f"Successfully connected to {authority.name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to connect to authority {authority.name}: {str(e)}")
            if self.socket:
                self.socket.close()
                self.socket = None
            return False
    
    def send_transfer_order(self, sender: Station, recipient: Station, amount: int) -> bool:
        """Send transfer order to authority.
        
        Args:
            sender: Sender address
            recipient: Recipient address
            amount: Transfer amount
            
        Returns:
            True if sent successfully, False otherwise
        """

        try:
            # Create transfer order
            transfer_order = TransferOrder(
                order_id=uuid4(),
                sender=sender.name,
                recipient=recipient.name,
                amount=amount,
                sequence_number=1,
                timestamp=time.time(),
                signature='test_sig'  # Mock signature
            )

            transfer_order_message = TransferRequestMessage(
                transfer_order=transfer_order
            )

            # Create sender address (representing the sender node)
            sender_address = Address(
                node_id=sender.name,
                ip_address=sender.wintfs[0].ip.split('/')[0] if sender.wintfs and '/' in sender.wintfs[0].ip else "10.0.0.100",
                port=9000,
                node_type=NodeType.CLIENT
            )
            
            # Create Message with TRANSFER_REQUEST type
            message = Message(
                message_id=uuid4(),
                message_type=MessageType.TRANSFER_REQUEST,
                sender=sender_address,
                recipient=None,  # Will be filled by authority
                timestamp=time.time(),
                payload=transfer_order_message.to_payload()
            )

            self.logger.transfer(f"Sending transfer order: {sender} -> {recipient}, {amount} tokens")
            
            transfer_dict = {
                'order_id': str(transfer_order.order_id),
                'sender': transfer_order.sender,
                'recipient': transfer_order.recipient,
                'amount': transfer_order.amount,
                'sequence_number': transfer_order.sequence_number,
                'timestamp': transfer_order.timestamp,
                'signature': transfer_order.signature
            }
            self.logger.debug(f"Transfer details: {json.dumps(transfer_dict, indent=2)}")
            
            # Create message data in the format expected by _handle_client
            message_data = {
                "message_id": str(message.message_id),
                "message_type": message.message_type.value,
                "sender": {
                    "node_id": message.sender.node_id,
                    "ip_address": message.sender.ip_address,
                    "port": message.sender.port,
                    "node_type": message.sender.node_type.value
                },
                "timestamp": message.timestamp,
                "payload": message.payload
            }
            
            # Convert message to JSON
            message_json = json.dumps(message_data)
            
            # Send message to all authorities using sender.cmd()
            successful_sends = 0
            for authority in self.get_authorities():  # We'll need to pass authorities to this method
                try:
                    # Get authority IP (remove subnet mask if present)
                    auth_ip = authority.wintfs[0].ip
                    if '/' in auth_ip:
                        auth_ip = auth_ip.split('/')[0]
                    auth_port = authority.address.port
                    
                    self.logger.info(f"Sending to authority {authority.name} at {auth_ip}:{auth_port}")
                    
                    # Create a Python script to send the message from sender node
                    send_script = f'''import socket
import json
import sys

def send_message():
    try:
        # Create socket within sender node namespace
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        
        # Connect to authority
        sock.connect(("{auth_ip}", {auth_port}))
        
        # Prepare message
        message_json = """{message_json}"""
        message_bytes = message_json.encode('utf-8')
        
        # Send length prefix (4 bytes big endian) + message
        length_bytes = len(message_bytes).to_bytes(4, byteorder='big')
        sock.send(length_bytes + message_bytes)
        
        # Wait for acknowledgment
        ack_length_bytes = sock.recv(4)
        if len(ack_length_bytes) == 4:
            ack_length = int.from_bytes(ack_length_bytes, byteorder='big')
            ack_bytes = sock.recv(ack_length)
            ack_data = json.loads(ack_bytes.decode('utf-8'))
            print(f"ACK: {{ack_data}}")
        
        sock.close()
        print("SUCCESS")
        
    except Exception as e:
        print(f"ERROR: {{e}}")
        sys.exit(1)

if __name__ == "__main__":
    send_message()
'''
                    
                    # Write script to temporary file
                    script_path = f"/tmp/send_transfer_{authority.name}.py"
                    sender.cmd(f"cat > {script_path} << 'EOF'\n{send_script}\nEOF")
                    
                    # Execute script from sender node namespace
                    result = sender.cmd(f"python3 {script_path}").strip()
                    
                    # Clean up script
                    sender.cmd(f"rm -f {script_path}")
                    
                    # Check result
                    if "SUCCESS" in result:
                        successful_sends += 1
                        self.logger.success(f"Transfer sent to {authority.name}")
                    else:
                        self.logger.error(f"Failed to send to {authority.name}: {result}")
                        
                except Exception as e:
                    self.logger.error(f"Error sending to authority {authority.name}: {e}")
            
            self.logger.info(f"Transfer sent to {successful_sends} authorities")
            return successful_sends > 0
            
        except Exception as e:
            self.logger.error(f"Failed to send TRANSFER_REQUEST: {e}")
            return False
    
    def send_transfer_to_all_authorities(self, authorities: List[Station], sender: Station, recipient: Station, amount: int) -> int:
        """Send transfer order to all authorities using sender.cmd() method.
        
        Args:
            authorities: List of authority nodes
            sender: Sender node
            recipient: Recipient node
            amount: Transfer amount
            
        Returns:
            Number of successful sends
        """
        self.authorities = authorities  # Store for use in send_transfer_order
        return self.send_transfer_order(sender, recipient, amount)

    def get_authorities(self):
        """Get the list of authorities (helper method)."""
        return getattr(self, 'authorities', [])

    def receive_response(self, timeout: float = 10.0) -> Optional[Dict]:
        """Receive response from authority.
        
        Args:
            timeout: Timeout in seconds
            
        Returns:
            Response dictionary or None if failed
        """
        if not self.socket:
            self.logger.error("Not connected to authority")
            return None
            
        try:
            self.socket.settimeout(timeout)
            data = self.socket.recv(4096)
            
            if not data:
                self.logger.warning("Received empty response")
                return None
                
            response = json.loads(data.decode('utf-8'))
            self.logger.received(f"Response received: {json.dumps(response, indent=2)}")
            
            if response.get('success'):
                self.logger.success("Transfer approved!")
                self.logger.balance(f"New balance: {response.get('new_balance')} tokens")
            else:
                self.logger.error(f"Transfer rejected: {response.get('error_message')}")
            
            return response
            
        except socket.timeout:
            self.logger.error(f"Response timeout after {timeout} seconds")
            return None
        except Exception as e:
            self.logger.error(f"Failed to receive response: {e}")
            return None
    
    def disconnect(self):
        """Disconnect from authority server."""
        if self.socket:
            try:
                self.socket.close()
                self.logger.info("Disconnected from authority")
            except Exception as e:
                self.logger.error(f"Error during disconnect: {e}")
        self.socket = None
        self.logger.close()

    def ping_node(self, source_node: Station, target_node: Station, count: int = 3) -> Dict:
        """Ping between two nodes using standard ping command.
        
        Args:
            source_node: Source node to ping from
            target_node: Target node to ping to  
            count: Number of ping packets to send
            
        Returns:
            Dictionary with ping results
        """
        try:
            # Get target IP address
            if hasattr(target_node, 'wintfs') and target_node.wintfs:
                target_ip = list(target_node.wintfs.values())[0].ip
            else:
                self.logger.error(f"Target node {target_node.name} has no wireless interfaces")
                return {"success": False, "error": "No wireless interfaces"}
            
            # Remove subnet mask if present (e.g., "10.0.0.1/8" -> "10.0.0.1")
            if '/' in target_ip:
                target_ip = target_ip.split('/')[0]
            
            self.logger.ping(f"Pinging {target_node.name} ({target_ip}) from {source_node.name} with {count} packets")
            
            # Execute ping command on source node
            ping_cmd = f"ping -c {count} -W 5 {target_ip}"
            result = source_node.cmd(ping_cmd)
            
            # Parse ping results
            ping_stats = self._parse_ping_output(result)
            ping_stats["source"] = source_node.name
            ping_stats["target"] = target_node.name
            ping_stats["target_ip"] = target_ip
            ping_stats["command"] = ping_cmd
            
            # Log results
            if ping_stats["success"]:
                self.logger.success(f"Ping successful: {ping_stats['packets_received']}/{ping_stats['packets_sent']} packets received")
                if ping_stats["avg_time"]:
                    self.logger.info(f"Average round-trip time: {ping_stats['avg_time']} ms")
            else:
                self.logger.error(f"Ping failed: {ping_stats['packets_received']}/{ping_stats['packets_sent']} packets received")
            
            return ping_stats
            
        except Exception as e:
            error_msg = f"Ping operation failed: {str(e)}"
            self.logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "source": source_node.name if source_node else "unknown",
                "target": target_node.name if target_node else "unknown"
            }
    
    def _parse_ping_output(self, ping_output: str) -> Dict:
        """Parse ping command output and extract statistics.
        
        Args:
            ping_output: Raw output from ping command
            
        Returns:
            Dictionary with parsed ping statistics
        """
        import re
        
        stats = {
            "success": False,
            "packets_sent": 0,
            "packets_received": 0,
            "packet_loss_percent": 100.0,
            "min_time": None,
            "avg_time": None,
            "max_time": None,
            "raw_output": ping_output
        }
        
        try:
            # Parse packet statistics (e.g., "3 packets transmitted, 3 received, 0% packet loss")
            packet_match = re.search(r'(\d+) packets transmitted, (\d+) received, (\d+(?:\.\d+)?)% packet loss', ping_output)
            if packet_match:
                stats["packets_sent"] = int(packet_match.group(1))
                stats["packets_received"] = int(packet_match.group(2))
                stats["packet_loss_percent"] = float(packet_match.group(3))
                stats["success"] = stats["packets_received"] > 0
            
            # Parse timing statistics (e.g., "rtt min/avg/max/mdev = 0.045/0.052/0.064/0.008 ms")
            time_match = re.search(r'rtt min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/[\d.]+ ms', ping_output)
            if time_match:
                stats["min_time"] = float(time_match.group(1))
                stats["avg_time"] = float(time_match.group(2))
                stats["max_time"] = float(time_match.group(3))
        
        except Exception as e:
            self.logger.debug(f"Error parsing ping output: {e}")
        
        return stats
    
    def ping_all_authorities(self, source_node: Station, authorities: List[Station], count: int = 3) -> Dict:
        """Ping all authorities from a source node.
        
        Args:
            source_node: Source node to ping from
            authorities: List of authority nodes to ping
            count: Number of ping packets to send to each authority
            
        Returns:
            Dictionary with ping results for all authorities
        """
        results = {
            "source": source_node.name,
            "total_authorities": len(authorities),
            "successful_pings": 0,
            "failed_pings": 0,
            "results": {}
        }
        
        self.logger.info(f"Pinging all {len(authorities)} authorities from {source_node.name}")
        
        for authority in authorities:
            if authority.name == source_node.name:
                # Skip self-ping
                continue
                
            ping_result = self.ping_node(source_node, authority, count)
            results["results"][authority.name] = ping_result
            
            if ping_result["success"]:
                results["successful_pings"] += 1
            else:
                results["failed_pings"] += 1
        
        # Log summary
        success_rate = (results["successful_pings"] / len(results["results"]) * 100) if results["results"] else 0
        self.logger.info(f"Ping summary: {results['successful_pings']}/{len(results['results'])} successful ({success_rate:.1f}%)")
        
        return results


def create_fastpay_network(num_authorities):
    """Create FastPay network topology with authorities."""
    
    info("*** Creating FastPay Network Topology\n")
    net = Mininet_wifi()
    
    info("*** Creating nodes\n")
    
    # Create a regular host for network connectivity
    h1 = net.addHost('h1', mac='00:00:00:00:00:01', ip='10.0.0.1/8')
    
    # Create test stations for users
    user1 = net.addStation('user1', mac='00:00:00:00:00:02', ip='10.0.0.2/8', position='20,20,0')
    user2 = net.addStation('user2', mac='00:00:00:00:00:03', ip='10.0.0.3/8', position='70,70,0')
    
    # Create authority nodes
    authorities = []
    for i in range(1, num_authorities + 1):  # Create authorities
        auth_name = f'auth{i}'
        auth = net.addStation(
            name=auth_name,
            cls=WiFiAuthority,
            committee_members={f'auth{j}' for j in range(1, num_authorities + 1) if j != i},
            shard_assignments=1,
            ip=f'10.0.0.{i+10}/8',
            port=8080 + i,
            position=[30 + (i % 2) * 30, 30 + (i // 2) * 30, 0]
        )
        auth.logger = AuthorityLogger(auth_name)
        auth.logger.info(f"Authority {auth_name} created")
        authorities.append(auth)
    
    # Create access point
    ap1 = net.addAccessPoint(
        'ap1', 
        ssid='fastpay-network', 
        mode='g', 
        channel='1',
        position='45,45,0',
        range=150
    )
    
    # Create controller
    c1 = net.addController('c1')
    
    info("*** Configuring propagation model\n")
    net.setPropagationModel(model="logDistance", exp=2.0)
    
    info("*** Configuring nodes\n")
    net.configureNodes()
    
    info("*** Creating links\n")
    net.addLink(ap1, h1)
    
    info("*** Starting network\n")
    net.build()
    c1.start()
    ap1.start([c1])
    
    # Wait for network to stabilize
    time.sleep(2)
    
    return net, authorities, [user1, user2]


def open_authority_xterms(authorities):
    """Open xterm terminals for each authority."""
    info("*** Opening xterm terminals for authority logs\n")
    for authority in authorities:
        if hasattr(authority, 'logger'):
            # Start terminal for authority logs
            authority.logger.start_xterm()
            info(f"   📺 Opened xterm for {authority.name} logs\n")


def test_transfer_order(net, authorities, stations):
    """Test transfer order broadcasting and verification with custom CLI."""
    
    info("*** Starting FastPay Transfer CLI\n")
    
    # Display network information
    info("*** Network Setup:\n")
    info(f"***   Authorities: {len(authorities)}\n")
    info(f"***   Test Stations: {len(stations)}\n")
    
    # Print authority network information
    for authority in authorities:
        info(f"***   {authority.name}:\n")
        if hasattr(authority, 'wintfs') and authority.wintfs:
            wintf = list(authority.wintfs.values())[0]
            info(f"***      IP: {wintf.ip}, MAC: {wintf.mac}\n")
        if hasattr(authority, 'address'):
            info(f"***      FastPay Port: {authority.address.port}\n")
    
    # Print station information
    for i, station in enumerate(stations):
        info(f"***   station{i+1}:\n")
        if hasattr(station, 'wintfs') and station.wintfs:
            wintf = list(station.wintfs.values())[0]
            info(f"***      IP: {wintf.ip}, MAC: {wintf.mac}\n")
    
    info("*** \n")
    info("*** Available commands:\n")
    info("***   user1 send user2 100    - Send 100 tokens from user1 to user2\n")
    info("***   balance user1           - Check balance of user1\n")
    info("***   balances                - Show all user balances\n")
    info("***   user1 ping user2        - Ping from user1 to user2\n")
    info("***   ping all                - Test connectivity between all nodes\n")
    info("***   help                    - Show this help\n")
    info("***   exit                    - Exit the CLI\n")
    info("*** \n")
    
    # Setup test accounts on authorities
    setup_test_accounts(authorities)
    
    # Initialize authority services
    for auth in authorities:
        auth.logger.info("Starting FastPay services")
        if hasattr(auth, 'start_fastpay_services'):
            try:
                auth.start_fastpay_services()
            except Exception as e:
                auth.logger.error(f"Failed to start FastPay services: {e}")
    
    def show_balances():
        """Show balances of all users."""
        info("*** Current User Balances:\n")
        users = ["user1", "user2", "user3", "user4"]
        for user in users:
            balances = []
            for auth in authorities:
                if hasattr(auth, 'get_account_balance'):
                    balance = auth.get_account_balance(user)
                    balances.append(balance if balance is not None else 0)
                else:
                    balances.append(0)
            
            # Check if all authorities agree on balance
            if len(set(balances)) == 1:
                info(f"   {user}: {balances[0]} tokens ✅\n")
            else:
                info(f"   {user}: {balances} tokens ⚠️  (inconsistent)\n")
    
    def ping_user(source_name, target_name):
        """Ping between nodes."""
        info(f"*** Pinging from {source_name} to {target_name}\n")
        
        # Find source and target nodes
        source_node = None
        target_node = None
        
        # Search in all available nodes
        all_nodes = authorities + stations
        
        for node in all_nodes:
            if node.name == source_name or (hasattr(node, 'name') and node.name == source_name):
                source_node = node
            if node.name == target_name or (hasattr(node, 'name') and node.name == target_name):
                target_node = node
        
        # Also check if user names map to specific nodes (for user1, user2, etc.)
        user_to_node_mapping = {
            "user1": stations[0] if len(stations) > 0 else authorities[0],
            "user2": stations[1] if len(stations) > 1 else authorities[1] if len(authorities) > 1 else authorities[0],
            "user3": authorities[0],
            "user4": authorities[1] if len(authorities) > 1 else authorities[0]
        }
        
        if source_name in user_to_node_mapping and not source_node:
            source_node = user_to_node_mapping[source_name]
        if target_name in user_to_node_mapping and not target_node:
            target_node = user_to_node_mapping[target_name]
        
        if not source_node:
            info(f"*** Error: Source node '{source_name}' not found\n")
            info(f"*** Available nodes: {[node.name for node in all_nodes]}\n")
            info(f"*** Available users: {list(user_to_node_mapping.keys())}\n")
            return
        
        if not target_node:
            info(f"*** Error: Target node '{target_name}' not found\n")
            info(f"*** Available nodes: {[node.name for node in all_nodes]}\n")
            info(f"*** Available users: {list(user_to_node_mapping.keys())}\n")
            return
        
        # Create test client for pinging
        test_client = TransferTestClient("CLI-Ping")
        
        # Perform ping
        ping_result = test_client.ping_node(source_node, target_node, count=3)
        
        # Display results
        if ping_result["success"]:
            info(f"*** ✅ Ping successful!\n")
            info(f"***    Source: {source_node.name}\n")
            info(f"***    Target: {target_node.name} ({ping_result.get('target_ip', 'N/A')})\n")
            info(f"***    Packets: {ping_result['packets_received']}/{ping_result['packets_sent']} received\n")
            info(f"***    Packet loss: {ping_result['packet_loss_percent']}%\n")
            if ping_result.get("avg_time"):
                info(f"***    Average RTT: {ping_result['avg_time']} ms\n")
        else:
            info(f"*** ❌ Ping failed!\n")
            info(f"***    Source: {source_node.name}\n")
            info(f"***    Target: {target_node.name}\n")
            if "error" in ping_result:
                info(f"***    Error: {ping_result['error']}\n")
            else:
                info(f"***    Packets: {ping_result['packets_received']}/{ping_result['packets_sent']} received\n")
                info(f"***    Packet loss: {ping_result['packet_loss_percent']}%\n")
        
        # Clean up
        test_client.disconnect()
    
    def ping_all_nodes():
        """Test connectivity between all nodes."""
        info("*** Testing connectivity between all nodes\n")
        
        all_nodes = authorities + stations
        test_client = TransferTestClient("CLI-PingAll")
        
        total_tests = 0
        successful_tests = 0
        
        info(f"*** Testing {len(all_nodes)} nodes...\n")
        
        for i, source in enumerate(all_nodes):
            for j, target in enumerate(all_nodes):
                if i >= j:  # Skip self-ping and duplicate tests
                    continue
                
                total_tests += 1
                info(f"*** [{total_tests}] {source.name} → {target.name}: ", end="")
                
                ping_result = test_client.ping_node(source, target, count=1)
                
                if ping_result["success"]:
                    info(f"✅ {ping_result.get('avg_time', 'N/A')} ms\n")
                    successful_tests += 1
                else:
                    info(f"❌ FAILED ({ping_result.get('packet_loss_percent', 100)}% loss)\n")
        
        # Summary
        success_rate = (successful_tests / total_tests * 100) if total_tests > 0 else 0
        info(f"\n*** Connectivity Test Summary:\n")
        info(f"***   Total tests: {total_tests}\n")
        info(f"***   Successful: {successful_tests}\n")
        info(f"***   Failed: {total_tests - successful_tests}\n")
        info(f"***   Success rate: {success_rate:.1f}%\n")
        
        test_client.disconnect()
    
    def send_transfer(sender_name: str, recipient_name: str, amount: int):
        """Send transfer between users using TRANSFER_REQUEST messages via sender.cmd()."""
        info(f"*** Processing transfer: {sender_name} → {recipient_name}, {amount} tokens\n")
        
        # Find sender and recipient nodes
        user_to_node_mapping = {
            "user1": stations[0] if len(stations) > 0 else authorities[0],
            "user2": stations[1] if len(stations) > 1 else authorities[1] if len(authorities) > 1 else authorities[0],
            "user3": authorities[0],
            "user4": authorities[1] if len(authorities) > 1 else authorities[0]
        }
        
        sender_node = user_to_node_mapping.get(sender_name)
        recipient_node = user_to_node_mapping.get(recipient_name)
        
        if not sender_node:
            info(f"*** Error: Sender '{sender_name}' not found\n")
            return
        
        if not recipient_node:
            info(f"*** Error: Recipient '{recipient_name}' not found\n")
            return
        
        # Create test client
        test_client = TransferTestClient(f"CLI-Transfer-{sender_name}")
        
        # Send transfer using sender.cmd() to reach all authorities
        info(f"*** Broadcasting TRANSFER_REQUEST to {len(authorities)} authorities via {sender_name}\n")
        successful_sends = test_client.send_transfer_to_all_authorities(
            authorities, sender_node, recipient_node, amount
        )
        
        info(f"*** Transfer order sent to {len(authorities)} authorities\n")
        
        # Wait for processing
        time.sleep(2)
        
        # Check consensus
        consensus_threshold = (len(authorities) * 2) // 3 + 1  # 2/3 + 1 majority
        info(f"*** Transfer Results: {len(authorities)}/{len(authorities)} deliveries\n")
        info(f"*** Consensus threshold: {consensus_threshold}\n")
        
        if successful_sends >= consensus_threshold:
            info("*** ✅ TRANSFER DELIVERED: Messages sent to sufficient authorities!\n")
        else:
            info("*** ❌ TRANSFER FAILED: Could not deliver to enough authorities!\n")
        
        # Clean up
        test_client.disconnect()
        
        # Show updated balances
        show_balances()
    
    # Custom CLI loop
    while True:
        try:
            command = input("FastPay> ").strip()
            
            if not command:
                continue
            
            parts = command.split()
            
            if command == "exit":
                info("*** Exiting FastPay CLI\n")
                break
            
            elif command == "help":
                info("*** Available commands:\n")
                info("***   user1 send user2 100    - Send 100 tokens from user1 to user2\n")
                info("***   balance user1           - Check balance of user1\n")
                info("***   balances                - Show all user balances\n")
                info("***   user1 ping user2        - Ping from user1 to user2\n")
                info("***   auth1 ping auth2        - Ping from auth1 to auth2\n")
                info("***   user1 ping auth1     - Ping from user1 to auth1\n")
                info("***   ping all                - Test connectivity between all nodes\n")
                info("***   help                    - Show this help\n")
                info("***   exit                    - Exit the CLI\n")
            
            elif command == "balances":
                show_balances()
            
            elif len(parts) == 2 and parts[0] == "balance":
                user = parts[1]
                info(f"*** Balance for {user}:\n")
                balances = []
                for auth in authorities:
                    if hasattr(auth, 'get_account_balance'):
                        balance = auth.get_account_balance(user)
                        balances.append(balance if balance is not None else 0)
                    else:
                        balances.append(0)
                
                if len(set(balances)) == 1:
                    info(f"   {user}: {balances[0]} tokens ✅\n")
                else:
                    info(f"   {user}: {balances} tokens ⚠️  (inconsistent across authorities)\n")
            
            elif len(parts) == 4 and parts[1] == "send":
                sender = parts[0]
                recipient = parts[2]
                try:
                    amount = int(parts[3])
                    send_transfer(sender, recipient, amount)
                except ValueError:
                    info("*** Error: Amount must be a number\n")
            
            elif len(parts) == 3 and parts[1] == "ping":
                ping_user(parts[0], parts[2])
            
            elif command == "ping all":
                ping_all_nodes()
            
            else:
                info("*** Unknown command. Type 'help' for available commands.\n")
        
        except KeyboardInterrupt:
            info("\n*** Exiting FastPay CLI\n")
            break
        except EOFError:
            info("\n*** Exiting FastPay CLI\n")
            break


def setup_test_accounts(authorities):
    """Setup test accounts on all authorities."""
    
    info("*** Setting up test accounts\n")
    
    test_accounts = {
        "user1": 1000,
        "user2": 800,
        "user3": 1200,
        "user4": 500
    }
    
    for authority in authorities:
        if hasattr(authority, 'state'):
            from mn_wifi.baseTypes import Account
            
            for user_name, balance in test_accounts.items():
                account = Account(
                    address=user_name,
                    balance=balance,
                    sequence_number=0,
                    last_update=time.time()
                )
                authority.state.accounts[user_name] = account
            
            info(f"   ✅ {authority.name}: Setup {len(test_accounts)} accounts\n")
        else:
            info(f"   ⚠️  {authority.name}: Stub implementation, no accounts\n")


def test_authority_functionality(authorities):
    """Test basic authority functionality."""
    
    info("*** Testing Authority Functionality\n")
    
    for authority in authorities:
        info(f"   Testing {authority.name}:\n")
        
        # Test basic attributes
        info(f"      Type: {type(authority)}\n")
        info(f"      Position: {getattr(authority, 'position', 'Not set')}\n")
        info(f"      Committee: {getattr(authority, 'committee_members', 'Not set')}\n")
        
        # Print detailed network information
        info(f"      📡 Network Information:\n")
        
        # Print IP address and port
        if hasattr(authority, 'address'):
            info(f"         IP Address: {authority.address.ip_address}\n")
            info(f"         Port: {authority.address.port}\n")
        
        # Print wireless interface information
        if hasattr(authority, 'wintfs'):
            for wlan_id, wintf in authority.wintfs.items():
                info(f"         Wireless Interface {wlan_id}:\n")
                info(f"            Name: {wintf.name}\n")
                info(f"            MAC: {wintf.mac}\n")
                info(f"            IP: {wintf.ip}\n")
                info(f"            Channel: {wintf.channel}\n")
                info(f"            Mode: {wintf.mode}\n")
                info(f"            Range: {wintf.range}m\n")
                info(f"            TxPower: {wintf.txpower}dBm\n")
                if wintf.associatedTo:
                    info(f"            Associated to: {wintf.associatedTo.node.name}\n")
                else:
                    info(f"            Not associated to any AP\n")
        
        # Test distance calculation to other authorities
        if hasattr(authority, 'get_distance_to'):
            other_auths = [a for a in authorities if a != authority]
            for other in other_auths:
                if hasattr(authority, 'position') and hasattr(other, 'position'):
                    distance = authority.get_distance_to(other)
                    info(f"      Distance to {other.name}: {distance}m\n")
        
        # Test FastPay services
        if hasattr(authority, 'start_fastpay_services'):
            info(f"      🔧 Starting FastPay services...\n")
            try:
                if authority.start_fastpay_services():
                    info(f"      ✅ FastPay services started on port {authority.address.port}\n")
                    
                    # Test account balances
                    if hasattr(authority, 'get_account_balance'):
                        balance = authority.get_account_balance('user1')
                        info(f"      💰 User1 balance: {balance} tokens\n")
                else:
                    info(f"      ❌ Failed to start FastPay services\n")
            except Exception as e:
                info(f"      ❌ Error starting FastPay services: {e}\n")
        else:
            info(f"      ⚠️  Using stub implementation\n")
        
        info("\n")  # Add extra newline for better readability


def parse_arguments():
    """Parse command line arguments."""
    args = sys.argv[1:] if len(sys.argv) > 1 else []
    
    # Simple argument parsing
    options = {
        'num_authorities': int(args[0]) if '-n' in args else 3,
        'open_xterms': '-l' in args,
        'help': '-h' in args or '--help' in args
    }
    
    if options['help']:
        print("FastPay WiFi Authority Network Demo")
        print("Usage: sudo python authority.py [options]")
        print("Options:")
        print("  -l    Open xterm terminals for authority logs")
        print("  -h    Show this help")
        print("")
        print("Interactive commands after startup:")
        print("  user1 send user2 100    - Send 100 tokens from user1 to user2")
        print("  balance user1           - Check balance of user1")
        print("  balances                - Show all user balances")
        print("  user1 ping user2        - Ping from user1 to user2")
        print("  auth1 ping auth2        - Ping from auth1 to auth2")
        print("  user1 ping auth1     - Ping from user1 to auth1")
        print("  ping all                - Test connectivity between all nodes")
        print("  help                    - Show command help")
        print("  exit                    - Exit the CLI")
        sys.exit(0)
    
    return options


def main():
    """Main function to run the FastPay authority network demo."""
    
    # Parse command line arguments
    options = parse_arguments()
    
    setLogLevel('info')
    
    info("🚀 FastPay WiFi Authority Network Demo\n")
    info("📋 Using WiFiAuthority with addStation(cls=WiFiAuthority)\n")
    info("🌐 Authorities connect through standard WiFi infrastructure\n")
    
    if options['open_xterms']:
        info("📺 xterm terminals will be opened for authority logs\n")
    
    net = None
    authorities = []
    stations = []
    
    try:
        # Create network
        net, authorities, stations = create_fastpay_network(options['num_authorities'])
        
        # Open xterm terminals for each authority if requested
        if options['open_xterms']:
            open_authority_xterms(authorities)
        
        # Test transfer order with custom CLI
        test_transfer_order(net, authorities, stations)
        
        info("*** Demo completed successfully!\n")
        
    except KeyboardInterrupt:
        info("\n*** Demo interrupted\n")
    except Exception as e:
        info(f"\n*** Demo failed: {e}\n")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        info("*** Cleaning up\n")
        
        # Close loggers first
        for authority in authorities:
            if hasattr(authority, 'logger'):
                try:
                    authority.logger.info("Shutting down authority")
                    authority.logger.close()
                    info(f"   Closed logger for {authority.name}\n")
                except Exception as e:
                    info(f"   Error closing logger for {authority.name}: {e}\n")
        
        # Stop FastPay services
        for authority in authorities:
            if hasattr(authority, 'stop_fastpay_services'):
                try:
                    authority.stop_fastpay_services()
                    info(f"   Stopped services for {authority.name}\n")
                except Exception as e:
                    info(f"   Error stopping {authority.name}: {e}\n")
        
        # Stop network
        if net:
            try:
                net.stop()
                info("   Network stopped\n")
            except Exception as e:
                info(f"   Error stopping network: {e}\n")
        
        info("*** Cleanup completed\n")


if __name__ == '__main__':
    main() 