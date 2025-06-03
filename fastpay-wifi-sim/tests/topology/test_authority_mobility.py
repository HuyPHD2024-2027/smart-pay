#!/usr/bin/env python

"""
FastPay WiFi Interactive Topology Test with Authority Message Handling

Interactive test that creates a network topology with user nodes and authority nodes.
Each authority listens to messages and handles them based on message type.
Separate terminals show detailed logging for each authority's message processing.
"""

import sys
import time
import threading
import socket
import queue
import subprocess
import os
from typing import Dict, List
from enum import Enum

from mininet.log import setLogLevel, info
from mn_wifi.cli import CLI
from mn_wifi.net import Mininet_wifi

# Import FastPay components
from core.authority import WiFiAuthority
from core.base_types import Account, TransferOrder, Address, NodeType
from uuid import uuid4


class MessageType(Enum):
    """Types of messages that authorities can handle."""
    TRANSFER_ORDER = "transfer_order"
    CONFIRMATION_ORDER = "confirmation_order"
    BALANCE_QUERY = "balance_query"
    PING = "ping"


class Message:
    """Message structure for communication."""
    
    def __init__(self, msg_type: MessageType, payload: dict, sender: str, timestamp: float = None):
        self.msg_type = msg_type
        self.payload = payload
        self.sender = sender
        self.timestamp = timestamp or time.time()
        self.msg_id = str(uuid4())


class AuthorityLogger:
    """Logger for authority message processing."""
    
    def __init__(self, authority_name: str, log_file: str):
        self.authority_name = authority_name
        self.log_file = log_file
        self.log_queue = queue.Queue()
        self.running = True
        self.terminal_process = None
        
    def start_terminal(self):
        """Start a separate xterm terminal for this authority's logs."""
        # Create log file
        with open(self.log_file, 'w') as f:
            f.write(f"=== {self.authority_name} Authority Log ===\n")
            f.write(f"Started at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("="*50 + "\n\n")
        
        # Start xterm terminal that tails the log file
        cmd = f"xterm -T '{self.authority_name} Authority Log' -geometry 80x30 -e 'tail -f {self.log_file}' &"
        try:
            self.terminal_process = subprocess.Popen(cmd, shell=True)
            print(f"📋 {self.authority_name} terminal opened - logging to: {self.log_file}")
        except Exception as e:
            print(f"Could not open xterm for {self.authority_name}: {e}")
            print(f"Log file available at: {self.log_file}")
            print(f"💡 You can monitor logs with: tail -f {self.log_file}")
    
    def log(self, message: str):
        """Log a message with timestamp."""
        timestamp = time.strftime('%H:%M:%S.%f')[:-3]
        log_entry = f"[{timestamp}] {self.authority_name}: {message}"
        
        # Write to file
        with open(self.log_file, 'a') as f:
            f.write(log_entry + "\n")
            f.flush()  # Force write to disk
        
        # Also print to console with authority color coding
        colors = {
            'auth1': '\033[94m',  # Blue
            'auth2': '\033[92m',  # Green  
            'auth3': '\033[93m',  # Yellow
            'auth4': '\033[95m'   # Magenta
        }
        reset_color = '\033[0m'
        
        color = colors.get(self.authority_name, '')
        print(f"{color}{log_entry}{reset_color}")
    
    def error(self, message: str):
        """Log an error message."""
        self.log(f"❌ ERROR: {message}")
    
    def info(self, message: str):
        """Log an info message."""
        self.log(f"ℹ️  INFO: {message}")
    
    def warning(self, message: str):
        """Log a warning message."""
        self.log(f"⚠️  WARNING: {message}")
    
    def debug(self, message: str):
        """Log a debug message."""
        self.log(f"🐛 DEBUG: {message}")
    
    def close(self):
        """Close the logger and terminal."""
        self.running = False
        if self.terminal_process:
            self.terminal_process.terminate()


class EnhancedWiFiAuthority(WiFiAuthority):
    """Enhanced WiFi Authority with message listening and logging."""
    
    def __init__(self, name: str, committee_members: set, shard_assignments: set, 
                 ip: str, position: list, message_broker):
        super().__init__(name, committee_members, shard_assignments, ip, position)
        self.message_broker = message_broker
        self.logger = AuthorityLogger(name, f"/tmp/{name}_log.txt")
        self.message_queue = queue.Queue()
        self.running = True
        
        # Start logging terminal
        self.logger.start_terminal()
        
        # Start message listener thread
        self.listener_thread = threading.Thread(target=self._message_listener, daemon=True)
        self.listener_thread.start()
        
        self.logger.log("Authority initialized and ready")
    
    def _message_listener(self):
        """Listen for incoming messages."""
        self.logger.log("Message listener started")
        
        while self.running:
            try:
                # Get message from broker
                message = self.message_broker.get_message_for_authority(self.name, timeout=1.0)
                if message:
                    self._handle_message(message)
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.log(f"ERROR in message listener: {e}")
    
    def _handle_message(self, message: Message):
        """Handle incoming message based on type."""
        self.logger.log(f"📨 RECEIVED MESSAGE: {message.msg_type.value} from {message.sender}")
        self.logger.log(f"   Message ID: {message.msg_id}")
        self.logger.log(f"   Timestamp: {time.strftime('%H:%M:%S', time.localtime(message.timestamp))}")
        
        try:
            if message.msg_type == MessageType.TRANSFER_ORDER:
                self._handle_transfer_order_message(message)
            elif message.msg_type == MessageType.CONFIRMATION_ORDER:
                self._handle_confirmation_order_message(message)
            elif message.msg_type == MessageType.BALANCE_QUERY:
                self._handle_balance_query_message(message)
            elif message.msg_type == MessageType.PING:
                self._handle_ping_message(message)
            else:
                self.logger.log(f"❓ UNKNOWN MESSAGE TYPE: {message.msg_type}")
                
        except Exception as e:
            self.logger.log(f"❌ ERROR handling message: {e}")
    
    def _handle_transfer_order_message(self, message: Message):
        """Handle transfer order message."""
        self.logger.log("🔄 PROCESSING TRANSFER ORDER")
        
        try:
            # Extract transfer order from payload
            payload = message.payload
            transfer_order = TransferOrder(
                order_id=payload['order_id'],
                sender=payload['sender'],
                recipient=payload['recipient'],
                amount=payload['amount'],
                sequence_number=payload['sequence_number'],
                timestamp=payload['timestamp'],
                signature=payload['signature']
            )
            
            self.logger.log(f"   Order ID: {transfer_order.order_id}")
            self.logger.log(f"   Transfer: {transfer_order.sender} -> {transfer_order.recipient}")
            self.logger.log(f"   Amount: {transfer_order.amount} tokens")
            
            # Validate transfer order
            self.logger.log("🔍 VALIDATING TRANSFER ORDER")
            if self._validate_transfer_order(transfer_order):
                self.logger.log("✅ Transfer order validation: PASSED")
                
                # Check account balance
                sender_account = self.authority_state.accounts.get(transfer_order.sender)
                if sender_account and sender_account.balance >= transfer_order.amount:
                    self.logger.log(f"💰 Balance check: PASSED (current: {sender_account.balance})")
                    
                    # Process the transfer
                    self.logger.log("⚙️  EXECUTING TRANSFER")
                    response = self.handle_transfer_order(transfer_order)
                    
                    if response.success:
                        self.logger.log(f"✅ TRANSFER SUCCESSFUL")
                        self.logger.log(f"   New sender balance: {response.new_balance}")
                        self.logger.log(f"   Authority signature: auth_sig_{self.name}_{transfer_order.order_id}")
                        
                        # Send response back
                        self._send_response(message.sender, {
                            "status": "success",
                            "new_balance": response.new_balance,
                            "authority_signature": f"auth_sig_{self.name}_{transfer_order.order_id}"
                        })
                    else:
                        self.logger.log(f"❌ TRANSFER FAILED: {response.error_message}")
                        self._send_response(message.sender, {
                            "status": "failed",
                            "error": response.error_message
                        })
                else:
                    self.logger.log("❌ Balance check: FAILED (insufficient funds)")
                    self._send_response(message.sender, {
                        "status": "failed",
                        "error": "Insufficient balance"
                    })
            else:
                self.logger.log("❌ Transfer order validation: FAILED")
                self._send_response(message.sender, {
                    "status": "failed",
                    "error": "Invalid transfer order"
                })
                
        except Exception as e:
            self.logger.log(f"❌ ERROR in transfer processing: {e}")
    
    def _handle_balance_query_message(self, message: Message):
        """Handle balance query message."""
        self.logger.log("💰 PROCESSING BALANCE QUERY")
        
        user_id = message.payload.get('user_id')
        balance = self.get_account_balance(user_id)
        
        self.logger.log(f"   User: {user_id}")
        self.logger.log(f"   Balance: {balance}")
        
        self._send_response(message.sender, {
            "user_id": user_id,
            "balance": balance
        })
    
    def _handle_ping_message(self, message: Message):
        """Handle ping message."""
        self.logger.log("🏓 PROCESSING PING")
        self.logger.log(f"   From: {message.sender}")
        
        self._send_response(message.sender, {
            "pong": True,
            "authority": self.name,
            "timestamp": time.time()
        })
    
    def _handle_confirmation_order_message(self, message: Message):
        """Handle confirmation order message."""
        self.logger.log("📋 PROCESSING CONFIRMATION ORDER")
        # Implementation for confirmation orders
        pass
    
    def _send_response(self, recipient: str, payload: dict):
        """Send response message."""
        self.logger.log(f"📤 SENDING RESPONSE to {recipient}")
        # In a real implementation, this would send via network
        # For simulation, we just log it
        self.logger.log(f"   Response: {payload}")
    
    def shutdown(self):
        """Shutdown the authority."""
        self.logger.log("🔄 SHUTTING DOWN")
        self.running = False
        self.logger.close()


class MessageBroker:
    """Message broker for routing messages between nodes."""
    
    def __init__(self):
        self.authority_queues = {}
        self.user_queues = {}
    
    def register_authority(self, authority_name: str):
        """Register an authority with the broker."""
        self.authority_queues[authority_name] = queue.Queue()
    
    def register_user(self, user_name: str):
        """Register a user with the broker."""
        self.user_queues[user_name] = queue.Queue()
    
    def send_to_authority(self, authority_name: str, message: Message):
        """Send message to specific authority."""
        if authority_name in self.authority_queues:
            self.authority_queues[authority_name].put(message)
            return True
        return False
    
    def send_to_all_authorities(self, message: Message):
        """Send message to all authorities."""
        sent_count = 0
        for authority_name in self.authority_queues:
            if self.send_to_authority(authority_name, message):
                sent_count += 1
        return sent_count
    
    def get_message_for_authority(self, authority_name: str, timeout: float = 1.0):
        """Get message for specific authority."""
        if authority_name in self.authority_queues:
            try:
                return self.authority_queues[authority_name].get(timeout=timeout)
            except queue.Empty:
                return None
        return None


class FastPayUser:
    """FastPay user node that can send transfer orders."""
    
    def __init__(self, name: str, ip: str, initial_balance: int = 1000):
        self.name = name
        self.ip = ip
        self.balance = initial_balance
        self.sequence_number = 0
        self.message_broker = None
    
    def set_message_broker(self, broker: MessageBroker):
        """Set the message broker for communication."""
        self.message_broker = broker
        broker.register_user(self.name)
    
    def create_transfer_order(self, recipient: str, amount: int) -> TransferOrder:
        """Create a transfer order."""
        self.sequence_number += 1
        return TransferOrder(
            order_id=uuid4(),
            sender=self.name,
            recipient=recipient,
            amount=amount,
            sequence_number=self.sequence_number,
            timestamp=time.time(),
            signature=f"signature_{self.name}_{recipient}_{amount}_{self.sequence_number}"
        )
    
    def send_transfer_order(self, transfer_order: TransferOrder):
        """Send transfer order to all authorities via message broker."""
        if not self.message_broker:
            print(f"Error: No message broker set for {self.name}")
            return
        
        # Create message
        message = Message(
            msg_type=MessageType.TRANSFER_ORDER,
            payload={
                'order_id': str(transfer_order.order_id),
                'sender': transfer_order.sender,
                'recipient': transfer_order.recipient,
                'amount': transfer_order.amount,
                'sequence_number': transfer_order.sequence_number,
                'timestamp': transfer_order.timestamp,
                'signature': transfer_order.signature
            },
            sender=self.name
        )
        
        # Send to all authorities
        sent_count = self.message_broker.send_to_all_authorities(message)
        print(f"\n📡 {self.name} sent transfer order to {sent_count} authorities")
        return sent_count


class FastPayInteractiveTest:
    """Interactive test for FastPay with message handling."""
    
    def __init__(self):
        self.net = None
        self.authorities: List[EnhancedWiFiAuthority] = []
        self.users: Dict[str, FastPayUser] = {}
        self.committee_members = {"auth1", "auth2", "auth3", "auth4"}
        self.user_names = ["user1", "user2", "user3"]
        self.message_broker = MessageBroker()
    
    def create_topology(self, args):
        """Create interactive network topology with users and authorities."""
        info("*** Creating FastPay Interactive Network Topology with Message Handling\n")
        self.net = Mininet_wifi()
        
        info("*** Creating nodes\n")
        
        # Create a regular host for network connectivity
        h1 = self.net.addHost('h1', mac='00:00:00:00:00:01', ip='10.0.0.1/8')
        
        # Create user nodes
        for i, user_name in enumerate(self.user_names):
            user_station = self.net.addStation(
                user_name,
                mac=f'00:00:00:00:00:{i+2:02d}',
                ip=f'10.0.0.{i+2}/8',
                position=f'{10 + i * 20},{10},0'
            )
        
        # Create authority nodes
        for i, auth_name in enumerate(self.committee_members):
            auth_station = self.net.addStation(
                auth_name,
                mac=f'00:00:00:00:00:{i+10:02d}',
                ip=f'10.0.0.{i+10}/8',
                position=f'{30 + (i % 2) * 30},{50 + (i // 2) * 30},0'
            )
        
        # Create access point
        ap1 = self.net.addAccessPoint(
            'ap1', 
            ssid='fastpay-network', 
            mode='g', 
            channel='1',
            position='45,45,0',
            range=150
        )
        
        # Create controller
        c1 = self.net.addController('c1')
        
        info("*** Configuring propagation model\n")
        self.net.setPropagationModel(model="logDistance", exp=2.0)
        
        info("*** Configuring nodes\n")
        self.net.configureNodes()
        
        info("*** Creating links\n")
        self.net.addLink(ap1, h1)
        
        if '-p' not in args:
            self.net.plotGraph(max_x=120, max_y=120)
        
        info("*** Starting network\n")
        self.net.build()
        c1.start()
        ap1.start([c1])
        
        # Initialize FastPay components
        self._initialize_users()
        self._initialize_authorities()
        
        return self.net
    
    def _initialize_users(self):
        """Initialize FastPay user nodes."""
        info("*** Initializing FastPay users\n")
        
        initial_balances = {"user1": 1000, "user2": 500, "user3": 800}
        
        for i, user_name in enumerate(self.user_names):
            user_ip = f"10.0.0.{i+2}"
            balance = initial_balances.get(user_name, 1000)
            
            user = FastPayUser(user_name, user_ip, balance)
            user.set_message_broker(self.message_broker)
            
            self.users[user_name] = user
        
        info(f"*** Initialized {len(self.users)} users\n")
    
    def _initialize_authorities(self):
        """Initialize FastPay authorities with message handling."""
        info("*** Initializing FastPay authorities with message handling\n")
        
        for i, auth_name in enumerate(self.committee_members):
            station = self.net.get(auth_name)
            if station:
                # Register authority with message broker
                self.message_broker.register_authority(auth_name)
                
                authority = EnhancedWiFiAuthority(
                    name=auth_name,
                    committee_members=self.committee_members,
                    shard_assignments={f"shard{i+1}"},
                    ip=f"10.0.0.{i+10}/8",
                    position=[30 + (i % 2) * 30, 50 + (i // 2) * 30, 0],
                    message_broker=self.message_broker
                )
                
                # Copy station attributes
                authority.wintfs = station.wintfs
                authority.cmd = station.cmd
                authority.position = station.position if hasattr(station, 'position') else [0, 0, 0]
                
                # Setup accounts for all users
                self._setup_user_accounts(authority)
                
                # Add mock signature verification
                authority._verify_signature = self._mock_verify_signature
                
                self.authorities.append(authority)
        
        info(f"*** Initialized {len(self.authorities)} authorities with message handling\n")
        info("*** Separate xterm terminals opened for each authority's logs\n")
        info("*** Authority logs also shown in console with color coding\n")
    
    def _setup_user_accounts(self, authority: EnhancedWiFiAuthority):
        """Setup user accounts on authority."""
        for user_name, user in self.users.items():
            account = Account(
                address=user_name,
                balance=user.balance,
                sequence_number=0,
                last_update=time.time()
            )
            authority.authority_state.accounts[user_name] = account
    
    def _mock_verify_signature(self, message: str, signature: str, public_key: str) -> bool:
        """Mock signature verification."""
        return True
    
    def handle_transfer_command(self, sender: str, recipient: str, amount: int):
        """Handle a transfer command using message passing."""
        info(f"\n*** Processing transfer via message system: {sender} -> {recipient} ({amount} tokens)\n")
        
        # Check if sender exists
        if sender not in self.users:
            info(f"Error: User {sender} not found\n")
            return False
        
        # Check if recipient exists  
        if recipient not in self.users:
            info(f"Error: User {recipient} not found\n")
            return False
        
        # Get sender user
        sender_user = self.users[sender]
        
        # Create and send transfer order via message broker
        transfer_order = sender_user.create_transfer_order(recipient, amount)
        sent_count = sender_user.send_transfer_order(transfer_order)
        
        if sent_count > 0:
            info(f"✅ Transfer order sent to {sent_count} authorities\n")
            info("📋 Check the xterm terminals for detailed authority message processing\n")
            
            # Wait a bit for processing
            time.sleep(2)
            
            # Update local balances (simplified)
            sender_user.balance -= amount
            self.users[recipient].balance += amount
            
            return True
        else:
            info("❌ Failed to send transfer order\n")
            return False
    
    def show_balances(self):
        """Show current balances of all users."""
        info("\n*** Current User Balances ***\n")
        for user_name, user in self.users.items():
            info(f"{user_name}: {user.balance} tokens\n")
    
    def run_interactive_test(self, args):
        """Run the interactive test with message handling."""
        try:
            # Create network topology
            self.create_topology(args)
            
            # Show initial state
            info("\n*** FastPay Interactive Network with Message Handling Ready! ***\n")
            info("*** Authority message processing shown in separate xterm terminals\n")
            info("*** Available commands:\n")
            info("***   <sender> send <recipient> <amount>  - Transfer tokens via message system\n")
            info("***   balances                           - Show user balances\n")
            info("***   ping <authority>                   - Send ping to authority\n")
            info("***   help                              - Show all commands\n")
            info("***   exit                              - Exit the test\n")
            
            self.show_balances()
            
            # Start custom CLI
            self._start_custom_cli()
            
        except KeyboardInterrupt:
            info("\n*** Test interrupted\n")
        except Exception as e:
            info(f"\n*** Test failed: {e}\n")
        finally:
            # Shutdown authorities
            for authority in self.authorities:
                authority.shutdown()
            
            if self.net:
                info("*** Stopping network\n")
                self.net.stop()
    
    def _start_custom_cli(self):
        """Start custom CLI for FastPay commands."""
        print("\nFastPay Interactive CLI with Message Handling - Type 'help' for commands")
        
        while True:
            try:
                cmd = input("fastpay> ").strip()
                
                if not cmd:
                    continue
                
                parts = cmd.split()
                
                if cmd == "exit":
                    break
                elif cmd == "help":
                    print("Available commands:")
                    print("  <sender> send <recipient> <amount>  - Transfer tokens via message system")
                    print("  balances                           - Show user balances")  
                    print("  ping <authority>                   - Send ping to authority")
                    print("  exit                              - Exit")
                elif cmd == "balances":
                    self.show_balances()
                elif len(parts) == 2 and parts[0] == "ping":
                    authority_name = parts[1]
                    self._send_ping(authority_name)
                elif len(parts) == 4 and parts[1] == "send":
                    sender = parts[0]
                    recipient = parts[2]
                    try:
                        amount = int(parts[3])
                        self.handle_transfer_command(sender, recipient, amount)
                    except ValueError:
                        print("Error: Amount must be a number")
                else:
                    print(f"Unknown command: {cmd}")
                    print("Type 'help' for available commands")
                    
            except EOFError:
                break
            except KeyboardInterrupt:
                print("\nUse 'exit' to quit")
    
    def _send_ping(self, authority_name: str):
        """Send ping message to authority."""
        if authority_name in self.committee_members:
            message = Message(
                msg_type=MessageType.PING,
                payload={"ping": True},
                sender="CLI"
            )
            if self.message_broker.send_to_authority(authority_name, message):
                print(f"🏓 Ping sent to {authority_name}")
            else:
                print(f"❌ Failed to send ping to {authority_name}")
        else:
            print(f"❌ Authority {authority_name} not found")


def main():
    """Main function to run the interactive topology test."""
    setLogLevel('info')
    
    # Parse command line arguments
    args = sys.argv[1:] if len(sys.argv) > 1 else []
    
    # Create and run test
    test = FastPayInteractiveTest()
    test.run_interactive_test(args)


if __name__ == '__main__':
    main() 