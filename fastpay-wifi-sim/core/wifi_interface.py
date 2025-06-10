"""WiFi Interface module for FastPay simulation with real TCP/UDP support."""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
from queue import Queue, Empty
from typing import TYPE_CHECKING, Optional
from uuid import UUID

if TYPE_CHECKING:
    from .authority import WiFiAuthority

from .base_types import Address, NodeType
from .messages import Message, MessageType


class WiFiInterface:
    """WiFi network interface for communication using mininet-wifi with real TCP sockets."""
    
    def __init__(self, node: 'WiFiAuthority', address: Address) -> None:
        """Initialize WiFi interface with given address.
        
        Args:
            node: The WiFiAuthority node this interface belongs to
            address: Network address for this interface
        """
        self.node = node
        self.address = address
        self.is_connected = False
        self.connection_quality = 1.0
        
        # TCP server for receiving messages
        self.server_socket: Optional[socket.socket] = None
        self.server_thread: Optional[threading.Thread] = None
        self.message_queue: Queue[Message] = Queue()
        self.running = False
        
        # Configure logging
        self.logger = logging.getLogger(f"WiFiInterface-{address.node_id}")
        
    def connect(self) -> bool:
        """Establish WiFi connection and start TCP server.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            # In mininet-wifi, ensure the wireless interface is up
            if hasattr(self.node, 'wintfs') and self.node.wintfs:
                intf = list(self.node.wintfs.values())[0]
                intf.ipLink('up')
            
            # Start TCP server for receiving messages
            if self._start_tcp_server():
                self.is_connected = True
                self.logger.info(f"WiFi interface connected on {self.address.ip_address}:{self.address.port}")
                return True
            
            return False
        except Exception as e:
            self.logger.error(f"Failed to connect WiFi interface: {e}")
            return False
    
    def disconnect(self) -> None:
        """Disconnect WiFi interface and stop TCP server."""
        try:
            self.running = False
            self.is_connected = False
            
            # Stop TCP server
            if self.server_socket:
                self.server_socket.close()
                self.server_socket = None
            
            # Wait for server thread to finish
            if self.server_thread and self.server_thread.is_alive():
                self.server_thread.join(timeout=2.0)
            
            # Bring down wireless interface if available
            if hasattr(self.node, 'wintfs') and self.node.wintfs:
                intf = list(self.node.wintfs.values())[0]
                intf.ipLink('down')
                
            self.logger.info("WiFi interface disconnected")
        except Exception as e:
            self.logger.error(f"Failed to disconnect WiFi interface: {e}")
    
    def _start_tcp_server(self) -> bool:
        """Start TCP server to receive messages.
        
        Returns:
            True if server started successfully
        """
        try:
            # Get the actual IP address from the mininet node for identification purposes
            actual_ip = self._get_node_ip_address()
            if actual_ip:
                self.address.ip_address = actual_ip
                self.logger.info(f"Node has IP address: {actual_ip}")
            else:
                self.logger.warning(f"Could not get node IP, using configured IP")
            
            # For mininet-wifi nodes, bind to 0.0.0.0 to listen on all interfaces
            # This avoids the "Cannot assign requested address" error
            bind_ip = '0.0.0.0'
            
            # Create and bind TCP socket
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((bind_ip, self.address.port))
            self.server_socket.listen(10)
            
            # Start server thread
            self.running = True
            self.server_thread = threading.Thread(target=self._tcp_server_loop, daemon=True)
            self.server_thread.start()
            
            self.logger.info(f"TCP server started on {bind_ip}:{self.address.port} (node IP: {self.address.ip_address})")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start TCP server: {e}")
            return False
    
    def _get_node_ip_address(self) -> Optional[str]:
        """Get the actual IP address of the mininet node.
        
        Returns:
            IP address string or None if not found
        """
        try:
            # Method 1: Try to get IP from mininet node
            if hasattr(self.node, 'IP'):
                ip = self.node.IP()
                if ip and ip != '127.0.0.1':
                    return ip
            
            # Method 2: Try to get IP from node's command execution
            if hasattr(self.node, 'cmd'):
                result = self.node.cmd('ip addr show | grep "inet " | grep -v "127.0.0.1" | awk \'{print $2}\' | cut -d/ -f1 | head -1')
                if result and result.strip():
                    return result.strip()
            
            # Method 3: Try to extract from interfaces
            if hasattr(self.node, 'intfs'):
                for intf in self.node.intfs.values():
                    if hasattr(intf, 'IP') and intf.IP():
                        ip = intf.IP()
                        if ip and ip != '127.0.0.1':
                            return ip
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting node IP address: {e}")
            return None
    
    def _tcp_server_loop(self) -> None:
        """TCP server loop to handle incoming connections."""
        while self.running and self.server_socket:
            try:
                self.server_socket.settimeout(1.0)
                client_socket, client_address = self.server_socket.accept()
                
                # Handle client in separate thread
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, client_address),
                    daemon=True
                )
                client_thread.start()
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self.logger.error(f"Error in TCP server loop: {e}")
                break
    
    def _handle_client(self, client_socket: socket.socket, client_address: tuple) -> None:
        """Handle incoming client connection.
        
        Args:
            client_socket: Client socket
            client_address: Client address tuple
        """
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
                self.message_queue.put(message)
                self.logger.debug(f"Received message from {client_address}")
                
                # Send acknowledgment (optional)
                ack_data = {"status": "received"}
                ack_json = json.dumps(ack_data)
                ack_bytes = ack_json.encode('utf-8')
                length_bytes = len(ack_bytes).to_bytes(4, byteorder='big')
                client_socket.send(length_bytes + ack_bytes)
            
        except Exception as e:
            self.logger.error(f"Error handling client {client_address}: {e}")
        finally:
            client_socket.close()
    
    def _parse_message(self, message_data: dict) -> Optional[Message]:
        """Parse message data into Message object.
        
        Args:
            message_data: Raw message data
            
        Returns:
            Parsed message or None if invalid
        """
        try:
            sender_data = message_data.get('sender', {})
            sender = Address(
                node_id=sender_data.get('node_id', ''),
                ip_address=sender_data.get('ip_address', ''),
                port=sender_data.get('port', 0),
                node_type=NodeType(sender_data.get('node_type', 'UNKNOWN'))
            )
            
            message = Message(
                message_id=UUID(message_data['message_id']),
                message_type=MessageType(message_data['message_type']),
                sender=sender,
                recipient=self.address,
                timestamp=message_data['timestamp'],
                payload=message_data['payload']
            )
            
            return message
        except Exception as e:
            self.logger.error(f"Failed to parse message: {e}")
            return None
    
    def send_message(self, message: Message, target: Address) -> bool:
        """Send message to target address using TCP.
        
        Args:
            message: Message to send
            target: Target address
            
        Returns:
            True if message sent successfully, False otherwise
        """
        if not self.is_connected:
            return False
        
        try:
            # Create client socket
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.settimeout(5.0)
            
            # Connect to target
            client_socket.connect((target.ip_address, target.port))
            
            # Serialize message
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
            
            json_data = json.dumps(message_data)
            message_bytes = json_data.encode('utf-8')
            
            # Send message length first, then message
            length_bytes = len(message_bytes).to_bytes(4, byteorder='big')
            client_socket.send(length_bytes + message_bytes)
            
            # Receive acknowledgment (optional)
            ack_length_bytes = client_socket.recv(4)
            if len(ack_length_bytes) == 4:
                ack_length = int.from_bytes(ack_length_bytes, byteorder='big')
                ack_bytes = client_socket.recv(ack_length)
                ack_data = json.loads(ack_bytes.decode('utf-8'))
                
            client_socket.close()
            self.logger.debug(f"Sent message to {target.ip_address}:{target.port}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send message to {target.ip_address}:{target.port}: {e}")
            return False
    
    def receive_message(self, timeout: float = 1.0) -> Optional[Message]:
        """Receive message from network queue.
        
        Args:
            timeout: Timeout in seconds
            
        Returns:
            Received message or None if timeout
        """
        if not self.is_connected:
            return None
        
        try:
            message = self.message_queue.get(timeout=timeout)
            return message
        except Empty:
            return None
        except Exception as e:
            self.logger.error(f"Failed to receive message: {e}")
            return None 