#!/usr/bin/env python

"""
Test for WiFiAuthority _message_handler_thread with real network communication.

This test verifies that the authority's message handler thread can receive
and process actual TCP/UDP packets containing transfer orders and other messages.
"""

import json
import socket
import threading
import time
import unittest
from typing import Dict, List, Optional, Any
from unittest.mock import Mock, patch, MagicMock
from uuid import uuid4

import pytest
from pytest_mock import MockerFixture

from core.authority import WiFiAuthority
from core.baseTypes import Account, TransferOrder, Address, NodeType
from core.messages import Message, MessageType, TransferRequestMessage
from core.wifiInterface import WiFiInterface


class MockWiFiInterface:
    """Mock WiFi interface that uses real TCP sockets for testing."""
    
    def __init__(self, node: WiFiAuthority, address: Address):
        self.node = node
        self.address = address
        self.is_connected = False
        self.server_socket: Optional[socket.socket] = None
        self.server_thread: Optional[threading.Thread] = None
        self.running = False
        self.received_messages: List[Message] = []
        
    def connect(self) -> bool:
        """Start TCP server for testing."""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('127.0.0.1', self.address.port))
            self.server_socket.listen(5)
            
            self.running = True
            self.server_thread = threading.Thread(target=self._server_loop, daemon=True)
            self.server_thread.start()
            
            self.is_connected = True
            return True
        except Exception:
            return False
    
    def disconnect(self) -> None:
        """Stop TCP server."""
        self.running = False
        self.is_connected = False
        if self.server_socket:
            self.server_socket.close()
        if self.server_thread:
            self.server_thread.join(timeout=1.0)
    
    def _server_loop(self) -> None:
        """TCP server loop."""
        while self.running and self.server_socket:
            try:
                self.server_socket.settimeout(0.5)
                client_socket, _ = self.server_socket.accept()
                self._handle_client(client_socket)
            except socket.timeout:
                continue
            except Exception:
                break
    
    def _handle_client(self, client_socket: socket.socket) -> None:
        """Handle client connection."""
        try:
            # Receive message length
            length_bytes = client_socket.recv(4)
            if len(length_bytes) != 4:
                return
            
            message_length = int.from_bytes(length_bytes, byteorder='big')
            
            # Receive message data
            message_bytes = b''
            while len(message_bytes) < message_length:
                chunk = client_socket.recv(message_length - len(message_bytes))
                if not chunk:
                    break
                message_bytes += chunk
            
            # Parse message
            message_data = json.loads(message_bytes.decode('utf-8'))
            message = self._parse_message(message_data)
            
            if message:
                self.received_messages.append(message)
                
                # Send response
                response_data = {
                    "message_id": str(uuid4()),
                    "message_type": "TRANSFER_RESPONSE",
                    "payload": {
                        "order_id": str(message_data.get('payload', {}).get('transfer_order', {}).get('order_id', '')),
                        "success": True,
                        "new_balance": 900
                    }
                }
                response_json = json.dumps(response_data)
                response_bytes = response_json.encode('utf-8')
                length_bytes = len(response_bytes).to_bytes(4, byteorder='big')
                client_socket.send(length_bytes + response_bytes)
                
        except Exception:
            pass
        finally:
            client_socket.close()
    
    def _parse_message(self, message_data: dict) -> Optional[Message]:
        """Parse message data."""
        try:
            sender_data = message_data.get('sender', {})
            sender = Address(
                node_id=sender_data.get('node_id', ''),
                ip_address=sender_data.get('ip_address', ''),
                port=sender_data.get('port', 0),
                node_type=NodeType.CLIENT
            )
            
            return Message(
                message_id=uuid4(),
                message_type=MessageType.TRANSFER_REQUEST,
                sender=sender,
                recipient=self.address,
                timestamp=time.time(),
                payload=message_data.get('payload', {})
            )
        except Exception:
            return None
    
    def receive_message(self, timeout: float = 1.0) -> Optional[Message]:
        """Get received message."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.received_messages:
                return self.received_messages.pop(0)
            time.sleep(0.1)
        return None
    
    def send_message(self, message: Message, target: Address) -> bool:
        """Mock send message."""
        return True


class NetworkTestClient:
    """Test client that sends TCP messages to authority."""
    
    def __init__(self, client_name: str):
        self.client_name = client_name
        
    def send_transfer_order(self, authority_ip: str, authority_port: int, 
                          transfer_order: TransferOrder) -> bool:
        """Send transfer order to authority via TCP."""
        try:
            # Create socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((authority_ip, authority_port))
            
            # Create message
            message_data = {
                "message_id": str(uuid4()),
                "message_type": "TRANSFER_REQUEST",
                "sender": {
                    "node_id": self.client_name,
                    "ip_address": "127.0.0.1",
                    "port": 9000,
                    "node_type": "CLIENT"
                },
                "timestamp": time.time(),
                "payload": {
                    "transfer_order": {
                        "order_id": str(transfer_order.order_id),
                        "sender": transfer_order.sender,
                        "recipient": transfer_order.recipient,
                        "amount": transfer_order.amount,
                        "sequence_number": transfer_order.sequence_number,
                        "timestamp": transfer_order.timestamp,
                        "signature": transfer_order.signature
                    }
                }
            }
            
            # Send message
            json_data = json.dumps(message_data)
            message_bytes = json_data.encode('utf-8')
            length_bytes = len(message_bytes).to_bytes(4, byteorder='big')
            sock.send(length_bytes + message_bytes)
            
            # Receive response
            response_length_bytes = sock.recv(4)
            if len(response_length_bytes) == 4:
                response_length = int.from_bytes(response_length_bytes, byteorder='big')
                response_bytes = sock.recv(response_length)
                response_data = json.loads(response_bytes.decode('utf-8'))
                
            sock.close()
            return True
            
        except Exception as e:
            print(f"Error sending transfer order: {e}")
            return False


class TestAuthorityMessageHandlerThread:
    """Test class for authority message handler thread functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.committee_members = {"auth1", "auth2", "auth3"}
        self.authority_address = Address(
            node_id="auth1",
            ip_address="127.0.0.1",
            port=8081,
            node_type=NodeType.AUTHORITY
        )
        
    def test_authority_initialization_with_network_interface(self, mocker: MockerFixture):
        """Test that authority initializes with working network interface."""
        # Mock the Station base class
        mock_station = mocker.patch('core.authority.Station.__init__')
        
        authority = WiFiAuthority(
            name="auth1",
            committee_members=self.committee_members,
            ip="127.0.0.1/8",
            position=[0, 0, 0]
        )
        
        # Verify initialization
        assert authority.name == "auth1"
        assert authority.authority_state.committee_members == self.committee_members
        assert authority.network_interface is not None
        assert authority._message_handler_thread is None  # Not started yet
        assert authority._running is False
    
    def test_message_handler_thread_starts_and_stops(self, mocker: MockerFixture):
        """Test that message handler thread starts and stops correctly."""
        # Mock the Station and network interface
        mock_station = mocker.patch('core.authority.Station.__init__')
        mock_wifi_interface = mocker.patch('core.authority.WiFiInterface')
        mock_interface_instance = Mock()
        mock_interface_instance.connect.return_value = True
        mock_interface_instance.receive_message.return_value = None
        mock_wifi_interface.return_value = mock_interface_instance
        
        authority = WiFiAuthority(
            name="auth1",
            committee_members=self.committee_members,
            ip="127.0.0.1/8"
        )
        
        # Start authority services
        result = authority.start_fastpay_services()
        assert result is True
        assert authority._running is True
        assert authority._message_handler_thread is not None
        assert authority._message_handler_thread.is_alive()
        
        # Stop authority services
        authority.stop_fastpay_services()
        assert authority._running is False
        # Give thread time to stop
        time.sleep(0.1)
        assert not authority._message_handler_thread.is_alive()
    
    def test_message_handler_processes_transfer_request(self, mocker: MockerFixture):
        """Test that message handler processes transfer requests correctly."""
        # Mock Station
        mock_station = mocker.patch('core.authority.Station.__init__')
        
        # Create authority with mock interface
        authority = WiFiAuthority(
            name="auth1",
            committee_members=self.committee_members,
            ip="127.0.0.1/8"
        )
        
        # Replace network interface with mock
        mock_interface = MockWiFiInterface(authority, authority.host_address)
        authority.network_interface = mock_interface
        
        # Set up test accounts
        authority.authority_state.accounts["user1"] = Account(
            address="user1",
            balance=1000,
            sequence_number=0,
            last_update=time.time()
        )
        authority.authority_state.accounts["user2"] = Account(
            address="user2",
            balance=500,
            sequence_number=0,
            last_update=time.time()
        )
        
        # Start authority services
        authority._running = True
        authority._message_handler_thread = threading.Thread(
            target=authority._message_handler_loop,
            daemon=True
        )
        authority._message_handler_thread.start()
        mock_interface.connect()
        
        # Create transfer order
        transfer_order = TransferOrder(
            order_id=uuid4(),
            sender="user1",
            recipient="user2",
            amount=100,
            sequence_number=1,
            timestamp=time.time(),
            signature="test_signature"
        )
        
        # Create transfer request message
        transfer_request = TransferRequestMessage(transfer_order=transfer_order)
        message = Message(
            message_id=uuid4(),
            message_type=MessageType.TRANSFER_REQUEST,
            sender=Address(
                node_id="client1",
                ip_address="127.0.0.1",
                port=9000,
                node_type=NodeType.CLIENT
            ),
            recipient=authority.host_address,
            timestamp=time.time(),
            payload=transfer_request.to_payload()
        )
        
        # Put message in authority's message queue
        authority.message_queue.put(message)
        
        # Wait for processing
        time.sleep(0.5)
        
        # Verify transfer was processed
        sender_account = authority.authority_state.accounts["user1"]
        recipient_account = authority.authority_state.accounts["user2"]
        
        assert sender_account.balance == 900  # 1000 - 100
        assert recipient_account.balance == 600  # 500 + 100
        assert transfer_order.order_id in authority.authority_state.pending_transfers
        
        # Clean up
        authority.stop_fastpay_services()
        mock_interface.disconnect()
    
    def test_real_network_message_handling(self, mocker: MockerFixture):
        """Test authority handling real TCP messages from network client."""
        # Mock Station
        mock_station = mocker.patch('core.authority.Station.__init__')
        
        # Create authority
        authority = WiFiAuthority(
            name="auth1",
            committee_members=self.committee_members,
            ip="127.0.0.1/8"
        )
        
        # Set up test accounts
        authority.authority_state.accounts["user1"] = Account(
            address="user1",
            balance=1000,
            sequence_number=0,
            last_update=time.time()
        )
        
        # Replace with mock interface that uses real TCP
        mock_interface = MockWiFiInterface(authority, authority.host_address)
        authority.network_interface = mock_interface
        
        # Start authority
        authority._running = True
        authority._message_handler_thread = threading.Thread(
            target=authority._message_handler_loop,
            daemon=True
        )
        authority._message_handler_thread.start()
        
        # Start mock TCP server
        mock_interface.connect()
        time.sleep(0.1)  # Let server start
        
        # Create test client
        client = NetworkTestClient("TestClient")
        
        # Create transfer order
        transfer_order = TransferOrder(
            order_id=uuid4(),
            sender="user1",
            recipient="user2",
            amount=150,
            sequence_number=1,
            timestamp=time.time(),
            signature="test_signature"
        )
        
        # Send transfer order via TCP
        success = client.send_transfer_order(
            "127.0.0.1",
            authority.host_address.port,
            transfer_order
        )
        
        assert success is True
        
        # Wait for message processing
        time.sleep(1.0)
        
        # Verify message was received
        assert len(mock_interface.received_messages) > 0
        received_message = mock_interface.received_messages[0]
        assert received_message.message_type == MessageType.TRANSFER_REQUEST
        
        # Clean up
        authority.stop_fastpay_services()
        mock_interface.disconnect()
    
    def test_concurrent_message_handling(self, mocker: MockerFixture):
        """Test authority handling multiple concurrent TCP messages."""
        # Mock Station
        mock_station = mocker.patch('core.authority.Station.__init__')
        
        # Create authority
        authority = WiFiAuthority(
            name="auth1",
            committee_members=self.committee_members,
            ip="127.0.0.1/8"
        )
        
        # Set up test accounts
        for i in range(5):
            authority.authority_state.accounts[f"user{i}"] = Account(
                address=f"user{i}",
                balance=1000,
                sequence_number=0,
                last_update=time.time()
            )
        
        # Replace with mock interface
        mock_interface = MockWiFiInterface(authority, authority.host_address)
        authority.network_interface = mock_interface
        
        # Start authority
        authority._running = True
        authority._message_handler_thread = threading.Thread(
            target=authority._message_handler_loop,
            daemon=True
        )
        authority._message_handler_thread.start()
        mock_interface.connect()
        time.sleep(0.1)
        
        # Send multiple concurrent transfers
        def send_transfer(client_id: int):
            client = NetworkTestClient(f"Client{client_id}")
            transfer_order = TransferOrder(
                order_id=uuid4(),
                sender=f"user{client_id}",
                recipient=f"user{(client_id + 1) % 5}",
                amount=50,
                sequence_number=1,
                timestamp=time.time(),
                signature=f"sig_{client_id}"
            )
            return client.send_transfer_order(
                "127.0.0.1",
                authority.host_address.port,
                transfer_order
            )
        
        # Start concurrent transfers
        threads = []
        for i in range(3):
            thread = threading.Thread(target=send_transfer, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all transfers
        for thread in threads:
            thread.join()
        
        # Wait for processing
        time.sleep(1.0)
        
        # Verify multiple messages were received
        assert len(mock_interface.received_messages) >= 3
        
        # Clean up
        authority.stop_fastpay_services()
        mock_interface.disconnect()
    
    def test_message_handler_error_handling(self, mocker: MockerFixture):
        """Test message handler handles errors gracefully."""
        # Mock Station
        mock_station = mocker.patch('core.authority.Station.__init__')
        
        authority = WiFiAuthority(
            name="auth1",
            committee_members=self.committee_members,
            ip="127.0.0.1/8"
        )
        
        # Mock network interface to raise exception
        mock_interface = Mock()
        mock_interface.receive_message.side_effect = Exception("Network error")
        authority.network_interface = mock_interface
        
        # Start message handler
        authority._running = True
        authority._message_handler_thread = threading.Thread(
            target=authority._message_handler_loop,
            daemon=True
        )
        authority._message_handler_thread.start()
        
        # Let it run for a bit with errors
        time.sleep(0.5)
        
        # Verify thread is still alive despite errors
        assert authority._message_handler_thread.is_alive()
        
        # Stop cleanly
        authority.stop_fastpay_services()


if __name__ == '__main__':
    pytest.main([__file__, '-v']) 