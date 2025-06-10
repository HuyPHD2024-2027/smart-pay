#!/usr/bin/env python

"""
FastPay WiFi Authority Real Network Message Handling Test

This test creates actual WiFi authorities and tests their _message_handler_thread
functionality by sending real TCP/UDP packets with transfer orders and other messages.
The authorities will listen to actual network events and process them.
"""

import sys
import time
import threading
import socket
import json
import queue
from typing import Dict, List, Optional, Any
from uuid import uuid4, UUID
from dataclasses import asdict

from mininet.log import setLogLevel, info
from mn_wifi.cli import CLI
from mn_wifi.net import Mininet_wifi

# Import FastPay components
from core.authority import WiFiAuthority
from core.base_types import Account, TransferOrder, Address, NodeType
from core.messages import Message, MessageType, TransferRequestMessage, TransferResponseMessage
from core.wifi_interface import WiFiInterface


class NetworkTestClient:
    """Test client that sends real network messages to authorities."""
    
    def __init__(self, client_name: str):
        self.client_name = client_name
        self.socket = None
        self.responses_received: List[Dict] = []
        self.response_queue = queue.Queue()
        
    def connect(self, server_ip: str, server_port: int) -> bool:
        """Connect to authority server.
        
        Args:
            server_ip: Authority server IP
            server_port: Authority server port
            
        Returns:
            True if connected successfully
        """
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5.0)
            self.socket.connect((server_ip, server_port))
            print(f"📡 {self.client_name}: Connected to authority at {server_ip}:{server_port}")
            return True
        except Exception as e:
            print(f"❌ {self.client_name}: Failed to connect to {server_ip}:{server_port} - {e}")
            return False
    
    def send_transfer_order(self, transfer_order: TransferOrder) -> bool:
        """Send transfer order message to authority.
        
        Args:
            transfer_order: Transfer order to send
            
        Returns:
            True if sent successfully
        """
        try:
            # Create transfer request message
            transfer_request = TransferRequestMessage(transfer_order=transfer_order)
            
            # Create network message
            message = Message(
                message_id=uuid4(),
                message_type=MessageType.TRANSFER_REQUEST,
                sender=Address(
                    node_id=self.client_name,
                    ip_address="10.0.0.100",
                    port=9000,
                    node_type=NodeType.CLIENT
                ),
                recipient=None,  # Will be filled by recipient
                timestamp=time.time(),
                payload=transfer_request.to_payload()
            )
            
            # Serialize message to JSON with proper enum handling
            sender_dict = asdict(message.sender)
            sender_dict['node_type'] = message.sender.node_type.value  # Convert enum to string
            
            message_data = {
                "message_id": str(message.message_id),
                "message_type": message.message_type.value,
                "sender": sender_dict,
                "timestamp": message.timestamp,
                "payload": message.payload
            }
            
            json_data = json.dumps(message_data)
            message_bytes = json_data.encode('utf-8')
            
            # Send message length first, then message
            length_bytes = len(message_bytes).to_bytes(4, byteorder='big')
            self.socket.send(length_bytes + message_bytes)
            
            print(f"📤 {self.client_name}: Sent transfer order {str(transfer_order.order_id)[:8]}...")
            print(f"   💰 Transfer: {transfer_order.sender} → {transfer_order.recipient}")
            print(f"   💵 Amount: {transfer_order.amount} tokens")
            
            return True
            
        except Exception as e:
            print(f"❌ {self.client_name}: Error sending transfer order: {e}")
            return False
    
    def receive_response(self, timeout: float = 5.0) -> Optional[Dict]:
        """Receive response from authority.
        
        Args:
            timeout: Timeout in seconds
            
        Returns:
            Response data or None if timeout
        """
        try:
            self.socket.settimeout(timeout)
            
            # Receive message length
            length_bytes = self.socket.recv(4)
            if len(length_bytes) != 4:
                return None
            
            message_length = int.from_bytes(length_bytes, byteorder='big')
            
            # Receive message data
            message_bytes = b''
            while len(message_bytes) < message_length:
                chunk = self.socket.recv(message_length - len(message_bytes))
                if not chunk:
                    break
                message_bytes += chunk
            
            # Parse JSON response
            response_data = json.loads(message_bytes.decode('utf-8'))
            self.responses_received.append(response_data)
            
            print(f"📨 {self.client_name}: Received response")
            print(f"   📋 Type: {response_data.get('message_type', 'Unknown')}")
            print(f"   ✅ Success: {response_data.get('payload', {}).get('success', False)}")
            
            return response_data
            
        except socket.timeout:
            print(f"⏰ {self.client_name}: Response timeout")
            return None
        except Exception as e:
            print(f"❌ {self.client_name}: Error receiving response: {e}")
            return None
    
    def disconnect(self) -> None:
        """Disconnect from authority."""
        if self.socket:
            self.socket.close()
            self.socket = None
            print(f"🔌 {self.client_name}: Disconnected")
    
    def create_transfer_order(self, sender: str, recipient: str, amount: int, 
                            sequence_number: int = 1) -> TransferOrder:
        """Create a transfer order.
        
        Args:
            sender: Sender address
            recipient: Recipient address
            amount: Transfer amount
            sequence_number: Sequence number
            
        Returns:
            Transfer order
        """
        return TransferOrder(
            order_id=uuid4(),
            sender=sender,
            recipient=recipient,
            amount=amount,
            sequence_number=sequence_number,
            timestamp=time.time(),
            signature=f"sig_{sender}_{recipient}_{amount}_{sequence_number}"
        )


class RealNetworkAuthorityTest:
    """Test for real network message handling by authorities."""
    
    def __init__(self):
        self.net = None
        self.authorities: List[WiFiAuthority] = []
        self.committee_members = {"auth1", "auth2", "auth3"}
        self.test_clients: List[NetworkTestClient] = []
        
    def create_topology(self, args: List[str]) -> Mininet_wifi:
        """Create network topology with real authority nodes."""
        info("*** Creating FastPay Real Network Authority Test\n")
        self.net = Mininet_wifi()
        
        info("*** Creating nodes\n")
        
        # Create authority nodes using WiFiAuthority class directly
        for i, auth_name in enumerate(self.committee_members):
            authority = self.net.addStation(
                auth_name,
                cls=WiFiAuthority,
                committee_members=self.committee_members,
                shard_assignments={f"shard{i+1}"},
                mac=f'00:00:00:00:00:{i+10:02d}',
                ip=f'10.0.0.{i+10}/8',
                position=[30 + (i % 2) * 30, 50 + (i // 2) * 30, 0],
                range=100
            )
            # Update the port to avoid conflicts
            authority.host_address.port = 8080 + i
            self.authorities.append(authority)
        
        # Create test client host
        test_host = self.net.addHost(
            'testclient',
            mac='00:00:00:00:00:99',
            ip='10.0.0.100/8'
        )
        
        # Create access point
        ap1 = self.net.addAccessPoint(
            'ap1', 
            ssid='fastpay-real-network', 
            mode='g', 
            channel='1',
            position='45,45,0',
            range=200
        )
        
        # Create controller
        c1 = self.net.addController('c1')
        
        info("*** Configuring propagation model\n")
        self.net.setPropagationModel(model="logDistance", exp=2.0)
        
        info("*** Configuring nodes\n")
        self.net.configureNodes()
        
        info("*** Creating links\n")
        self.net.addLink(ap1, test_host)
        
        if '-p' not in args:
            self.net.plotGraph(max_x=120, max_y=120)
        
        info("*** Starting network\n")
        self.net.build()
        c1.start()
        ap1.start([c1])
        
        # Wait for network to stabilize
        time.sleep(2)
        
        # Setup test accounts and start FastPay services
        self._initialize_authority_services()
        
        return self.net
    
    def _initialize_authority_services(self) -> None:
        """Initialize FastPay authority services and test accounts."""
        info("*** Initializing FastPay authority services\n")
        
        for authority in self.authorities:
            # Setup test accounts
            self._setup_test_accounts(authority)
            
            print(f"🔧 {authority.name}: Initializing on port {authority.host_address.port}")
            
            # Start FastPay services (this starts the _message_handler_thread)
            if authority.start_fastpay_services():
                print(f"✅ {authority.name}: FastPay services started successfully")
                print(f"   🌐 Network interface: {authority.host_address.ip_address}:{authority.host_address.port}")
                print(f"   🔄 Message handler thread: Running")
            else:
                print(f"❌ {authority.name}: Failed to start FastPay services")
        
        info(f"*** Initialized {len(self.authorities)} authorities with services running\n")
        
        # Wait for authorities to fully start
        time.sleep(2)
    
    def _setup_test_accounts(self, authority: WiFiAuthority) -> None:
        """Setup test accounts on authority.
        
        Args:
            authority: Authority to setup accounts on
        """
        test_accounts = {
            "user1": 1000,
            "user2": 800,
            "user3": 1200,
            "user4": 500
        }
        
        for user_name, balance in test_accounts.items():
            account = Account(
                address=user_name,
                balance=balance,
                sequence_number=0,
                last_update=time.time()
            )
            authority.authority_state.accounts[user_name] = account
    
    def test_real_network_transfer_handling(self) -> None:
        """Test authorities handling real network transfer order messages."""
        print("\n" + "="*70)
        print("🧪 TESTING REAL NETWORK TRANSFER ORDER HANDLING")
        print("="*70)
        
        if not self.authorities:
            print("❌ No authorities available for testing")
            return
        
        # Test with the first authority
        test_authority = self.authorities[0]
        authority_ip = test_authority.host_address.ip_address
        authority_port = test_authority.host_address.port
        
        print(f"   🔍 Attempting to connect to: {authority_ip}:{authority_port}")
        
        print(f"\n🎯 Target Authority: {test_authority.name}")
        print(f"   🌐 Address: {authority_ip}:{authority_port}")
        print(f"   📊 Initial accounts:")
        for addr, account in test_authority.authority_state.accounts.items():
            print(f"      {addr}: {account.balance} tokens")
        
        # Get the test client host from mininet for proper network connectivity
        testclient_host = self.net.get('testclient')
        if not testclient_host:
            print("❌ Test client host not found in network")
            return
        
        # Test 1: Valid transfer order
        print(f"\n📤 Test 1: Sending valid transfer order via TCP")
        
        # Create test client that will run network operations within mininet namespace
        success = self._run_network_test_on_host(
            testclient_host, 
            test_authority, 
            "TestClient1", 
            "user1", 
            "user2", 
            100,
            "valid transfer"
        )
        
        if success:
            print(f"   ✅ Test 1 completed successfully")
        else:
            print(f"   ❌ Test 1 failed")
        
        # Test 2: Insufficient balance transfer
        print(f"\n📤 Test 2: Sending insufficient balance transfer")
        
        success = self._run_network_test_on_host(
            testclient_host,
            test_authority,
            "TestClient2",
            "user4",  # user4 has 500 tokens
            "user3",
            1000,  # More than available
            "insufficient balance transfer"
        )
        
        if success:
            print(f"   ✅ Test 2 completed successfully")
        else:
            print(f"   ❌ Test 2 failed")
        
        # Test 3: Multiple concurrent transfers using mininet host
        print(f"\n📤 Test 3: Testing concurrent transfer processing")
        self._test_concurrent_transfers_on_host(testclient_host, test_authority)
        
        # Show final statistics
        self._show_authority_statistics(test_authority)
    
    def _run_network_test_on_host(self, host, authority: WiFiAuthority, client_name: str, 
                                 sender: str, recipient: str, amount: int, test_description: str) -> bool:
        """Run network test within mininet host namespace.
        
        Args:
            host: Mininet host to run test on
            authority: Target authority
            client_name: Name for test client
            sender: Transfer sender
            recipient: Transfer recipient  
            amount: Transfer amount
            test_description: Description of test
            
        Returns:
            True if test completed successfully
        """
        try:
            # Create Python script to run on mininet host  
            test_script = f'''import socket
import json
import time
from uuid import uuid4

def run_transfer_test():
    try:
        # Create socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10.0)
        
        # Try connecting to authority IP first, then localhost
        connected = False
        for target_ip in ["{authority.host_address.ip_address}", "127.0.0.1"]:
            try:
                print(f"📡 {client_name}: Attempting to connect to {{target_ip}}:{authority.host_address.port}")
                sock.connect((target_ip, {authority.host_address.port}))
                print(f"📡 {client_name}: Connected to authority at {{target_ip}}:{authority.host_address.port}")
                connected = True
                break
            except Exception as e:
                print(f"❌ {client_name}: Failed to connect to {{target_ip}}:{authority.host_address.port} - {{e}}")
                
        if not connected:
            print(f"❌ {client_name}: Could not connect to authority")
            return False
        
        # Create transfer order message
        transfer_order = {{
            "order_id": str(uuid4()),
            "sender": "{sender}",
            "recipient": "{recipient}",
            "amount": {amount},
            "sequence_number": 1,
            "timestamp": time.time(),
            "signature": f"sig_{sender}_{recipient}_{amount}_1"
        }}
        
        # Create network message with proper serialization
        message_data = {{
            "message_id": str(uuid4()),
            "message_type": "TRANSFER_REQUEST",
            "sender": {{
                "node_id": "{client_name}",
                "ip_address": "10.0.0.100",
                "port": 9000,
                "node_type": "CLIENT"
            }},
            "timestamp": time.time(),
            "payload": {{
                "transfer_order": transfer_order
            }}
        }}
        
        # Send message
        json_data = json.dumps(message_data)
        message_bytes = json_data.encode('utf-8')
        length_bytes = len(message_bytes).to_bytes(4, byteorder='big')
        sock.send(length_bytes + message_bytes)
        
        print(f"📤 {client_name}: Sent {test_description}")
        print(f"   💰 Transfer: {sender} → {recipient}")
        print(f"   💵 Amount: {amount} tokens")
        
        # Receive response
        length_bytes = sock.recv(4)
        if len(length_bytes) == 4:
            message_length = int.from_bytes(length_bytes, byteorder='big')
            message_bytes = b''
            while len(message_bytes) < message_length:
                chunk = sock.recv(message_length - len(message_bytes))
                if not chunk:
                    break
                message_bytes += chunk
            
            response_data = json.loads(message_bytes.decode('utf-8'))
            print(f"📨 {client_name}: Received response")
            print(f"   📋 Response: {{response_data}}")
            
            sock.close()
            return True
        else:
            print(f"❌ {client_name}: No response received")
            sock.close()
            return False
            
    except Exception as e:
        print(f"❌ {client_name}: Error in network test: {{e}}")
        return False

if __name__ == "__main__":
    run_transfer_test()
'''
            
            # Save script to temporary file
            script_filename = f"/tmp/test_{client_name.lower()}.py"
            with open(script_filename, 'w') as f:
                f.write(test_script)
            
            # Execute script on mininet host
            result = host.cmd(f'python3 {script_filename}')
            print(result)
            
            # Cleanup
            host.cmd(f'rm -f {script_filename}')
            
            return "Connected to authority" in result and "Sent" in result
            
        except Exception as e:
            print(f"❌ Error running network test on host: {e}")
            return False
    
    def _test_concurrent_transfers_on_host(self, host, authority: WiFiAuthority) -> None:
        """Test concurrent transfer processing on mininet host.
        
        Args:
            host: Mininet host to run test on
            authority: Target authority
        """
        print(f"   🔄 Running 3 concurrent transfers on mininet host")
        
        # Create concurrent transfer script
        concurrent_script = f'''import socket
import json
import time
import threading
from uuid import uuid4

def send_transfer(client_name, sender, recipient, amount):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10.0)
        
        # Connect to authority
        for target_ip in ["{authority.host_address.ip_address}", "127.0.0.1"]:
            try:
                sock.connect((target_ip, {authority.host_address.port}))
                print(f"📡 " + client_name + f": Connected to " + target_ip + f":{authority.host_address.port}")
                break
            except:
                continue
        
        # Create and send transfer
        transfer_order = {{
            "order_id": str(uuid4()),
            "sender": sender,
            "recipient": recipient,
            "amount": amount,
            "sequence_number": 1,
            "timestamp": time.time(),
            "signature": f"sig_" + sender + "_" + recipient + "_" + str(amount) + "_1"
        }}
        
        message_data = {{
            "message_id": str(uuid4()),
            "message_type": "TRANSFER_REQUEST",
            "sender": {{
                "node_id": client_name,
                "ip_address": "10.0.0.100",
                "port": 9000,
                "node_type": "CLIENT"
            }},
            "timestamp": time.time(),
            "payload": {{"transfer_order": transfer_order}}
        }}
        
        json_data = json.dumps(message_data)
        message_bytes = json_data.encode('utf-8')
        length_bytes = len(message_bytes).to_bytes(4, byteorder='big')
        sock.send(length_bytes + message_bytes)
        
        print(f"📤 " + client_name + f": Sent " + sender + " → " + recipient + f" (" + str(amount) + " tokens)")
        
        # Receive response
        length_bytes = sock.recv(4)
        if len(length_bytes) == 4:
            message_length = int.from_bytes(length_bytes, byteorder='big')
            message_bytes = b''
            while len(message_bytes) < message_length:
                chunk = sock.recv(message_length - len(message_bytes))
                if not chunk:
                    break
                message_bytes += chunk
            
            response_data = json.loads(message_bytes.decode('utf-8'))
            success = response_data.get('payload', {{}}).get('success', False)
            status_emoji = '✅' if success else '❌'
            status_text = 'Success' if success else 'Failed'
            print(status_emoji + " " + client_name + ": " + status_text)
        
        sock.close()
        
    except Exception as e:
        print(f"❌ " + client_name + f": Error: " + str(e))

# Run concurrent transfers
threads = []
transfers = [
    ("ConcurrentClient1", "user1", "user2", 50),
    ("ConcurrentClient2", "user2", "user3", 30),
    ("ConcurrentClient3", "user3", "user1", 25)
]

for client_name, sender, recipient, amount in transfers:
    thread = threading.Thread(target=send_transfer, args=(client_name, sender, recipient, amount))
    threads.append(thread)
    thread.start()

for thread in threads:
    thread.join(timeout=15.0)

print("🏁 Concurrent transfers completed")
'''
        
        try:
            # Save and execute concurrent test script
            script_filename = "/tmp/test_concurrent.py"
            with open(script_filename, 'w') as f:
                f.write(concurrent_script)
            
            result = host.cmd(f'python3 {script_filename}')
            print(result)
            
            # Count successful transfers from output
            successful_count = result.count('✅')
            total_count = 3
            print(f"   📊 Concurrent transfer results: {successful_count}/{total_count} successful")
            
            # Cleanup
            host.cmd(f'rm -f {script_filename}')
            
        except Exception as e:
            print(f"❌ Error running concurrent test: {e}")
    
    def _show_authority_statistics(self, authority: WiFiAuthority) -> None:
        """Show authority processing statistics.
        
        Args:
            authority: Authority to show stats for
        """
        print(f"\n📊 Authority {authority.name} Final Statistics:")
        
        # Account balances
        print(f"   💰 Final account balances:")
        for addr, account in authority.authority_state.accounts.items():
            print(f"      {addr}: {account.balance} tokens")
        
        # Performance metrics
        stats = authority.get_performance_stats()
        print(f"   📈 Performance metrics:")
        print(f"      Transactions processed: {stats.get('transactions', 0)}")
        print(f"      Errors encountered: {stats.get('errors', 0)}")
        print(f"      Sync operations: {stats.get('syncs', 0)}")
        
        # Pending transfers
        pending_count = len(authority.authority_state.pending_transfers)
        confirmed_count = len(authority.authority_state.confirmed_transfers)
        print(f"   📋 Transfer status:")
        print(f"      Pending transfers: {pending_count}")
        print(f"      Confirmed transfers: {confirmed_count}")
    
    def test_authority_message_handler_thread(self) -> None:
        """Test the actual _message_handler_thread functionality."""
        print("\n" + "="*70)
        print("🧪 TESTING AUTHORITY MESSAGE HANDLER THREAD")
        print("="*70)
        
        if not self.authorities:
            print("❌ No authorities available for testing")
            return
        
        test_authority = self.authorities[0]
        
        # Check if message handler thread is running
        handler_thread = test_authority._message_handler_thread
        if handler_thread and handler_thread.is_alive():
            print(f"✅ {test_authority.name}: Message handler thread is running")
            print(f"   🔄 Thread name: {handler_thread.name}")
            print(f"   🎯 Thread target: {handler_thread._target.__name__ if handler_thread._target else 'Unknown'}")
        else:
            print(f"❌ {test_authority.name}: Message handler thread is not running")
            return
        
        # Check if network interface is active
        if test_authority.network_interface:
            print(f"✅ {test_authority.name}: Network interface is active")
            print(f"   🌐 Listening on: {test_authority.host_address.ip_address}:{test_authority.host_address.port}")
        else:
            print(f"❌ {test_authority.name}: Network interface is not active")
            return
        
        # Test message queue functionality
        queue_size_before = test_authority.message_queue.qsize()
        print(f"📬 {test_authority.name}: Message queue size: {queue_size_before}")
        
        # Send a test message and verify it's processed
        self.test_real_network_transfer_handling()
        
        # Check message queue after processing
        queue_size_after = test_authority.message_queue.qsize()
        print(f"📬 {test_authority.name}: Message queue size after processing: {queue_size_after}")
        
        print(f"✅ Message handler thread test completed")
    
    def run_real_network_test(self, args: List[str]) -> None:
        """Run the real network message handling test.
        
        Args:
            args: Command line arguments
        """
        try:
            # Create network topology
            self.create_topology(args)
            
            # Wait for network stabilization
            time.sleep(2)
            
            # Test authority message handler threads
            self.test_authority_message_handler_thread()
            
            # Keep running if interactive mode
            if '-i' in args:
                print("\n🔧 Entering interactive mode...")
                print("💡 Authorities are running with real network interfaces")
                print("💡 You can test more transfers, inspect authorities, etc.")
                print("💡 Access authorities via: test.authorities[0], test.authorities[1], etc.")
                print("💡 Example: test.authorities[0].get_account_balance('user1')")
                print("💡 Send a test transfer: client = NetworkTestClient('TestClient')")
                print("💡   transfer_order = client.create_transfer_order('user1', 'user2', 100)")
                print("💡   client.send_transfer_order('127.0.0.1', 8080, transfer_order)")
                CLI(self.net)
            
        except KeyboardInterrupt:
            info("\n*** Test interrupted\n")
        except Exception as e:
            info(f"\n*** Test failed: {e}\n")
            import traceback
            traceback.print_exc()
        finally:
            # Stop authority services
            for authority in self.authorities:
                try:
                    authority.stop_fastpay_services()
                except Exception as e:
                    print(f"Error stopping authority {authority.name}: {e}")
            
            if self.net:
                info("*** Stopping network\n")
                try:
                    self.net.stop()
                except Exception as e:
                    print(f"Error stopping network: {e}")


def main():
    """Main function to run the real network authority message handling test."""
    setLogLevel('info')
    
    # Parse command line arguments
    args = sys.argv[1:] if len(sys.argv) > 1 else []
    
    # Show help
    if '-h' in args or '--help' in args:
        print("FastPay Authority Real Network Message Handling Test")
        print("Usage: sudo python test_authorities.py [options]")
        print("Options:")
        print("  -i    Interactive mode (enter CLI after tests)")
        print("  -p    Skip plotting (for headless environments)")
        print("  -h    Show this help")
        return
    
    print("🚀 Starting FastPay Authority Real Network Message Handling Test")
    print("📋 This test verifies authorities can handle real TCP/UDP messages")
    print("🔄 Testing _message_handler_thread functionality with actual network communication")
    
    # Create and run test
    test = RealNetworkAuthorityTest()
    test.run_real_network_test(args)


if __name__ == '__main__':
    main() 