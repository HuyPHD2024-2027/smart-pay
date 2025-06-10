"""WiFi Interface module for FastPay simulation with real TCP/UDP support."""

from __future__ import annotations

import os
import tempfile
import json
import logging
import socket
import threading
import time
from queue import Queue, Empty
from typing import TYPE_CHECKING, Optional
from uuid import UUID

if TYPE_CHECKING:
    pass

from mn_wifi.base_types import Address, NodeType
from mn_wifi.messages import Message, MessageType


class WiFiInterface:
    """WiFi network interface for communication using mininet-wifi with real TCP sockets."""
    
    def __init__(self, node, address: Address) -> None:
        """Initialize WiFi interface with given address.
        
        Args:
            node: The authority node this interface belongs to
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
        
    def connect(self) -> bool:
        """Establish WiFi connection and start TCP server.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.node.logger.info(f"Connecting WiFi interface on {self.address.ip_address}:{self.address.port}")

            # Start TCP server for receiving messages
            if self._start_tcp_server():
                self.is_connected = True
                self.node.logger.info(f"WiFi interface connected on {self.address.ip_address}:{self.address.port}")
                return True
            
            return False
        except Exception as e:
            self.node.logger.error(f"Failed to connect WiFi interface: {e}")
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
                
            self.node.logger.info("WiFi interface disconnected")
        except Exception as e:
            self.node.logger.error(f"Failed to disconnect WiFi interface: {e}")
    
    def _start_tcp_server(self) -> bool:
        """Start TCP server to receive messages.
        
        Returns:
            True if server started successfully
        """
        try:
            # Create the TCP server script
            server_script = self._create_tcp_server_script()
            if not server_script:
                return False
            
            # Start the server using sendCmd
            cmd = f'python3 {server_script} {self.address.ip_address} {self.address.port} {self.address.node_id} &'
            result = self.node.cmd(cmd)

            # Get the process ID
            pid_result = self.node.cmd('echo $!')
            if pid_result and pid_result.strip():
                self.server_pid = int(pid_result.strip())
                self.node.logger.info(f"TCP server started with PID {self.server_pid} on {self.address.ip_address}:{self.address.port}")
                
            # Give the server a moment to start
            time.sleep(0.5)
            return True
            
        except Exception as e:
            self.node.logger.error(f"Failed to start TCP server with sendCmd: {e}")
            return False

    def _create_tcp_server_script(self) -> Optional[str]:
        """Create a Python script for the TCP server that runs in the node.
        
        Returns:
            Path to the script file or None if failed
        """
        try:
            # Create temporary script file
            script_content = f'''#!/usr/bin/env python3
"""
TCP Server script for WiFi Authority node.
This script runs within the mininet node's namespace.
"""

import socket
import json
import sys
import time
import signal
import os
from threading import Thread

class NodeTCPServer:
    def __init__(self, ip, port, node_id):
        self.ip = ip
        self.port = port
        self.node_id = node_id
        self.server_socket = None
        self.running = True
        self.message_log = f"/tmp/{{node_id}}_messages.log"
        
    def start(self):
        try:
            # Create and bind socket to the node's IP
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.ip, self.port))
            self.server_socket.listen(10)
            
            print(f"TCP server started on {{self.ip}}:{{self.port}} for node {{self.node_id}}")
            
            # Log server start
            with open(self.message_log, "a") as f:
                f.write(f"{{time.time()}}: Server started on {{self.ip}}:{{self.port}}\\n")
            
            while self.running:
                try:
                    self.server_socket.settimeout(1.0)
                    client_socket, client_address = self.server_socket.accept()
                    
                    # Handle client in separate thread
                    client_thread = Thread(
                        target=self.handle_client,
                        args=(client_socket, client_address),
                        daemon=True
                    )
                    client_thread.start()
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"Error in server loop: {{e}}")
                    break
                    
        except Exception as e:
            print(f"Failed to start TCP server: {{e}}")
            sys.exit(1)
    
    def handle_client(self, client_socket, client_address):
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
            
            # Parse and log message
            message_data = json.loads(message_bytes.decode('utf-8'))
            
            # Log received message
            with open(self.message_log, "a") as f:
                f.write(f"{{time.time()}}: Received from {{client_address}}: {{json.dumps(message_data)}}\\n")
            
            # Send acknowledgment
            ack_data = {{"status": "received", "node_id": self.node_id}}
            ack_json = json.dumps(ack_data)
            ack_bytes = ack_json.encode('utf-8')
            length_bytes = len(ack_bytes).to_bytes(4, byteorder='big')
            client_socket.send(length_bytes + ack_bytes)
            
        except Exception as e:
            print(f"Error handling client {{client_address}}: {{e}}")
        finally:
            client_socket.close()
    
    def stop(self):
        self.running = False
        if self.server_socket:
            self.server_socket.close()

def signal_handler(signum, frame):
    print(f"Received signal {{signum}}, shutting down server...")
    server.stop()
    sys.exit(0)

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python3 tcp_server.py <ip> <port> <node_id>")
        sys.exit(1)
    
    ip = sys.argv[1]
    port = int(sys.argv[2])
    node_id = sys.argv[3]
    
    # Set up signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Create and start server
    server = NodeTCPServer(ip, port, node_id)
    server.start()
'''
            
            # Write script to temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(script_content)
                self.server_script_path = f.name
            
            # Make script executable
            os.chmod(self.server_script_path, 0o755)
            
            return self.server_script_path
            
        except Exception as e:
            self.node.logger.error(f"Failed to create TCP server script: {e}")
            return None
    
    def get_message_log_path(self) -> str:
        """Get the path to the message log file for this node.
        
        Returns:
            Path to the message log file
        """
        return f"/tmp/{self.address.node_id}_messages.log"
    
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
                    self.node.logger.error(f"Error in TCP server loop: {e}")
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
                self.node.logger.debug(f"Received message from {client_address}")
                
                # Send acknowledgment (optional)
                ack_data = {"status": "received"}
                ack_json = json.dumps(ack_data)
                ack_bytes = ack_json.encode('utf-8')
                length_bytes = len(ack_bytes).to_bytes(4, byteorder='big')
                client_socket.send(length_bytes + ack_bytes)
            
        except Exception as e:
            self.node.logger.error(f"Error handling client {client_address}: {e}")
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
            self.node.logger.error(f"Failed to parse message: {e}")
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
            self.node.logger.debug(f"Sent message to {target.ip_address}:{target.port}")
            return True
            
        except Exception as e:
            self.node.logger.error(f"Failed to send message to {target.ip_address}:{target.port}: {e}")
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
            self.node.logger.error(f"Failed to receive message: {e}")
            return None 