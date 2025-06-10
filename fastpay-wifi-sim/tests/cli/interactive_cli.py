"""
Interactive CLI components for FastPay WiFi testing.

This module provides user interface classes and the main interactive test
framework for the FastPay WiFi simulation environment.
"""

import sys
import time
import threading
import queue
from typing import Dict, List, Optional, Set
from uuid import uuid4

from mininet.log import setLogLevel, info

from .message_handler import MessageType, Message, MessageBroker
from core.base_types import TransferOrder


class FastPayUser:
    """FastPay user node that can send transfer orders."""
    
    def __init__(self, name: str, ip: str, initial_balance: int = 1000) -> None:
        """Initialize FastPay user.
        
        Args:
            name: User identifier
            ip: IP address of the user
            initial_balance: Initial token balance
        """
        self.name = name
        self.ip = ip
        self.balance = initial_balance
        self.sequence_number = 0
        self.message_broker: Optional[MessageBroker] = None
    
    def set_message_broker(self, broker: MessageBroker) -> None:
        """Set the message broker for communication.
        
        Args:
            broker: Message broker instance
        """
        self.message_broker = broker
        broker.register_user(self.name)
    
    def create_transfer_order(self, recipient: str, amount: int) -> TransferOrder:
        """Create a transfer order.
        
        Args:
            recipient: Recipient user identifier
            amount: Amount to transfer
            
        Returns:
            Transfer order instance
        """
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
    
    def send_transfer_order(self, transfer_order: TransferOrder) -> int:
        """Send transfer order to all authorities via message broker.
        
        Args:
            transfer_order: Transfer order to send
            
        Returns:
            Number of authorities the message was sent to
        """
        if not self.message_broker:
            print(f"Error: No message broker set for {self.name}")
            return 0
        
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
            sender=self.name,
            recipient=None,
            timestamp=time.time(),
            signature=None
        )
        
        # Send to all authorities
        sent_count = self.message_broker.send_to_all_authorities(message)
        print(f"\n📡 {self.name} sent transfer order to {sent_count} authorities")
        return sent_count
    
    def send_balance_query(self) -> int:
        """Send balance query to all authorities.
        
        Returns:
            Number of authorities the query was sent to
        """
        if not self.message_broker:
            print(f"Error: No message broker set for {self.name}")
            return 0
        
        message = Message(
            msg_type=MessageType.BALANCE_QUERY,
            payload={'user_id': self.name},
            sender=self.name,
            timestamp=time.time()
        )
        
        sent_count = self.message_broker.send_to_all_authorities(message)
        print(f"\n💰 {self.name} sent balance query to {sent_count} authorities")
        return sent_count
    
    def send_ping(self, authority_name: Optional[str] = None) -> int:
        """Send ping to authorities.
        
        Args:
            authority_name: Specific authority to ping, or None for all
            
        Returns:
            Number of authorities pinged
        """
        if not self.message_broker:
            print(f"Error: No message broker set for {self.name}")
            return 0
        
        message = Message(
            msg_type=MessageType.PING,
            payload={'ping': True},
            sender=self.name,
            timestamp=time.time()
        )
        
        if authority_name:
            sent = self.message_broker.send_to_authority(authority_name, message)
            count = 1 if sent else 0
            print(f"\n🏓 {self.name} pinged {authority_name}")
        else:
            count = self.message_broker.send_to_all_authorities(message)
            print(f"\n🏓 {self.name} pinged all {count} authorities")
        
        return count


class FastPayInteractiveCLI:
    """Interactive CLI for FastPay testing with message handling."""
    
    def __init__(self) -> None:
        """Initialize the interactive CLI."""
        self.net = None
        self.authorities: List = []
        self.users: Dict[str, FastPayUser] = {}
        self.committee_members: Set[str] = {"auth1", "auth2", "auth3", "auth4"}
        self.user_names: List[str] = ["user1", "user2", "user3"]
        self.message_broker = MessageBroker()
    
    def initialize_users(self, initial_balances: Optional[Dict[str, int]] = None) -> None:
        """Initialize FastPay user nodes.
        
        Args:
            initial_balances: Optional mapping of user names to initial balances
        """
        info("*** Initializing FastPay users\n")
        
        if initial_balances is None:
            initial_balances = {"user1": 1000, "user2": 500, "user3": 800}
        
        for i, user_name in enumerate(self.user_names):
            user_ip = f"10.0.0.{i+2}"
            balance = initial_balances.get(user_name, 1000)
            
            user = FastPayUser(user_name, user_ip, balance)
            user.set_message_broker(self.message_broker)
            
            self.users[user_name] = user
        
        info(f"*** Initialized {len(self.users)} users\n")
    
    def handle_transfer_command(self, sender: str, recipient: str, amount: int) -> bool:
        """Handle a transfer command using message passing.
        
        Args:
            sender: Sender user identifier
            recipient: Recipient user identifier  
            amount: Amount to transfer
            
        Returns:
            True if transfer was initiated successfully, False otherwise
        """
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
            
            # Update local balances (simplified for testing)
            sender_user.balance -= amount
            self.users[recipient].balance += amount
            
            return True
        else:
            info("❌ Failed to send transfer order\n")
            return False
    
    def show_balances(self) -> None:
        """Show current balances of all users."""
        info("\n*** Current User Balances ***\n")
        for user_name, user in self.users.items():
            info(f"{user_name}: {user.balance} tokens\n")
    
    def send_ping(self, authority_name: str) -> None:
        """Send ping message to authority.
        
        Args:
            authority_name: Name of authority to ping
        """
        if authority_name in self.committee_members:
            message = Message(
                msg_type=MessageType.PING,
                payload={"ping": True}, 
                sender="CLI",
                recipient=authority_name,
                timestamp=time.time(),
                signature=None
            )
            if self.message_broker.send_to_authority(authority_name, message):
                print(f"🏓 Ping sent to {authority_name}")
            else:
                print(f"❌ Failed to send ping to {authority_name}")
        else:
            print(f"❌ Authority {authority_name} not found")
    
    def show_help(self) -> None:
        """Show help for available commands."""
        print("\nAvailable commands:")
        print("  <sender> send <recipient> <amount>  - Transfer tokens via message system")
        print("  balances                           - Show user balances")  
        print("  ping <authority>                   - Send ping to specific authority")
        print("  ping all                          - Send ping to all authorities")
        print("  query <user>                      - Query balance of specific user")
        print("  status                            - Show system status")
        print("  help                              - Show this help")
        print("  exit                              - Exit")
    
    def show_status(self) -> None:
        """Show system status."""
        print(f"\n📊 System Status:")
        print(f"  Authorities: {self.message_broker.get_authority_count()}")
        print(f"  Users: {self.message_broker.get_user_count()}")
        print(f"  Committee members: {', '.join(self.committee_members)}")
        print(f"  User names: {', '.join(self.user_names)}")
    
    def query_user_balance(self, user_name: str) -> None:
        """Query balance of a specific user.
        
        Args:
            user_name: Name of user to query
        """
        if user_name in self.users:
            user = self.users[user_name]
            sent_count = user.send_balance_query()
            if sent_count > 0:
                print(f"💰 Balance query sent for {user_name} to {sent_count} authorities")
            else:
                print(f"❌ Failed to send balance query for {user_name}")
        else:
            print(f"❌ User {user_name} not found")
    
    def start_custom_cli(self) -> None:
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
                    self.show_help()
                elif cmd == "balances":
                    self.show_balances()
                elif cmd == "status":
                    self.show_status()
                elif len(parts) == 2 and parts[0] == "ping":
                    if parts[1] == "all":
                        # Send ping from first user to all authorities
                        if self.users:
                            first_user = list(self.users.values())[0]
                            sent_count = first_user.send_ping()
                            print(f"🏓 Pinged all {sent_count} authorities")
                        else:
                            print("❌ No users available")
                    else:
                        authority_name = parts[1]
                        self.send_ping(authority_name)
                elif len(parts) == 2 and parts[0] == "query":
                    user_name = parts[1]
                    self.query_user_balance(user_name)
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
        
        print("\nExiting FastPay CLI...")
    
    def shutdown_authorities(self) -> None:
        """Shutdown all authorities."""
        for authority in self.authorities:
            if hasattr(authority, 'shutdown'):
                authority.shutdown()
    
    def cleanup(self) -> None:
        """Cleanup resources."""
        self.shutdown_authorities()
        if self.net:
            info("*** Stopping network\n")
            self.net.stop() 