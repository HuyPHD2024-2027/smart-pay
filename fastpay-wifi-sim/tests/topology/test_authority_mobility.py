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
from core.baseTypes import Account, TransferOrder, Address, NodeType
from core.messages import Message, MessageType
from uuid import uuid4

# Import CLI components (these would need to be recreated if the CLI functionality is needed)
# For now, we'll use the basic WiFiAuthority functionality


class EnhancedWiFiAuthority(WiFiAuthority):
    """Enhanced WiFi Authority with message listening and logging."""
    
    def __init__(self, name: str, committee_members: set, shard_assignments: set, 
                 ip: str, position: list, **kwargs):
        super().__init__(name, committee_members, shard_assignments, ip, position, **kwargs)
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
    
    def _handle_message(self, message: CLIMessage):
        """Handle incoming message based on type."""
        self.logger.log(f"📨 RECEIVED MESSAGE: {message.msg_type.value} from {message.sender}")
        self.logger.log(f"   Message ID: {message.msg_id}")
        self.logger.log(f"   Timestamp: {time.strftime('%H:%M:%S', time.localtime(message.timestamp))}")
        
        try:
            if message.msg_type == CLIMessageType.TRANSFER_ORDER or message.msg_type == CLIMessageType.TRANSFER_REQUEST:
                self._handle_transfer_order_message(message)
            elif message.msg_type == CLIMessageType.CONFIRMATION_ORDER or message.msg_type == CLIMessageType.CONFIRMATION_REQUEST:
                self._handle_confirmation_order_message(message)
            elif message.msg_type == CLIMessageType.SYNC_REQUEST:
                self._handle_sync_request_message(message)
            elif message.msg_type == CLIMessageType.PING or message.msg_type == CLIMessageType.PEER_DISCOVERY:
                self._handle_ping_message(message)
            else:
                self.logger.log(f"❓ UNKNOWN MESSAGE TYPE: {message.msg_type}")
                
        except Exception as e:
            self.logger.log(f"❌ ERROR handling message: {e}")
    
    def _handle_transfer_order_message(self, message: CLIMessage):
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
    
    def _handle_balance_query_message(self, message: CLIMessage):
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
    
    def _handle_ping_message(self, message: CLIMessage):
        """Handle ping message."""
        self.logger.log("🏓 PROCESSING PING")
        self.logger.log(f"   From: {message.sender}")
        
        self._send_response(message.sender, {
            "pong": True,
            "authority": self.name,
            "timestamp": time.time()
        })
    
    def _handle_confirmation_order_message(self, message: CLIMessage):
        """Handle confirmation order message."""
        self.logger.log("📋 PROCESSING CONFIRMATION ORDER")
        # Implementation for confirmation orders
        pass
    
    def _handle_sync_request_message(self, message: CLIMessage):
        """Handle sync request message."""
        self.logger.log("🔄 PROCESSING SYNC REQUEST")
        # Implementation for sync requests
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


class FastPayInteractiveTest(FastPayInteractiveCLI):
    """Interactive test for FastPay with message handling."""
    
    def __init__(self):
        super().__init__()
        self.authorities: List[EnhancedWiFiAuthority] = []
    
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
        initial_balances = {"user1": 1000, "user2": 500, "user3": 800}
        super().initialize_users(initial_balances)
    
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
            self.start_custom_cli()
            
        except KeyboardInterrupt:
            info("\n*** Test interrupted\n")
        except Exception as e:
            info(f"\n*** Test failed: {e}\n")
        finally:
            # Cleanup using inherited method
            self.cleanup()


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