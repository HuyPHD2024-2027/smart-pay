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

from mn_wifi.baseTypes import Address, NodeType
from mn_wifi.messages import Message, MessageType


class TCPTransport:
    """TCP network interface for communication using mininet-wifi with real TCP sockets."""
    
    def __init__(self, node, address: Address) -> None:
        """Initialize TCPTransport with given address.
        
        Args:
            node: The authority node this interface belongs to
            address: Network address for this interface
        """
        self.node = node
        self.address = address
        self.is_connected = False
        self.connection_quality = 1.0
        
        # TCP server for receiving messages
        self.monitor_thread: Optional[threading.Thread] = None
        self.running = False
        
    def connect(self) -> bool:
        """Launch a TCP server **inside** the authority namespace and
        start a monitor thread that feeds authority.message_queue."""
        try:
            if not self._start_tcp_server_in_node():
                return False

            # monitor *.log and inject into queue
            self.running = True
            self.monitor_thread = threading.Thread(
                target=self._monitor_messages, daemon=True
            )
            self.monitor_thread.start()

            self.is_connected = True
            self.node.logger.info(
                f"WiFi interface connected on {self.address.ip_address}:{self.address.port}"
            )
            return True
        except Exception as exc:
            self.node.logger.error(f"TCPTransport.connect failed: {exc}")
            return False
    
    def disconnect(self) -> None:
        """Stop monitor thread; authority kills server with SIGTERM automatically
        when node stops."""
        self.running = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2.0)
        self.node.logger.info("TCPTransport disconnected")
    
    def _start_tcp_server_in_node(self) -> bool:
        """Run the tiny TCP server inside the station namespace."""
        server_script = self._create_tcp_server_script()
        if not server_script:
            return False

        # run in the node’s namespace
        self.node.cmd(f"python3 {server_script} 0.0.0.0 {self.address.port} "
                      f"{self.address.node_id} &")
        return True

    def _monitor_messages(self) -> None:
        """Tail the log file produced by the in-namespace server and push
        JSON payloads into authority.message_queue."""
        log_path = f"/tmp/{self.address.node_id}_messages.log"
        processed = 0
        while self.running:
            try:
                if not os.path.exists(log_path):
                    time.sleep(0.2)
                    continue

                with open(log_path) as fh:
                    lines = fh.readlines()

                for line in lines[processed:]:
                    ix = line.find('{')
                    if ix == -1:
                        continue
                    data = json.loads(line[ix:])
                    msg = self._parse_message(data)
                    if msg:
                        self.node.message_queue.put(msg)

                processed = len(lines)
                time.sleep(0.1)
            except Exception as exc:
                self.node.logger.error(f"Monitor error: {exc}")
                time.sleep(1)

    def _create_tcp_server_script(self) -> Optional[str]:
        """Write a tiny server that:
           - binds to 0.0.0.0:<port> (works in the namespace),
           - reads length-prefixed JSON,
           - appends JSON lines to /tmp/<node_id>_messages.log,
           - ACKs the client."""
        try:
            script = f"""#!/usr/bin/env python3
import json, socket, struct, sys, time, signal, os
LOG = f'/tmp/{{sys.argv[3]}}_messages.log'
def main(ip, port, nid):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((ip, int(port)))          # ip will be 0.0.0.0
    srv.listen(16)
    with open(LOG, 'a') as f:
        f.write(f'{{time.time()}}: server up\\n')
    while True:
        c, _ = srv.accept()
        with c:
            ln = c.recv(4, socket.MSG_WAITALL)
            if len(ln) != 4:
                continue
            size = struct.unpack('>I', ln)[0]
            raw = c.recv(size, socket.MSG_WAITALL)
            with open(LOG, 'a') as f:
                f.write(f'{{time.time()}}: '+raw.decode()+'\\n')
            ack = json.dumps({{'status':'received','node_id':nid}}).encode()
            c.sendall(struct.pack('>I', len(ack))+ack)
if __name__ == '__main__':
    if len(sys.argv) != 4:
        print('usage: server.py ip port node_id'); sys.exit(1)
    main(sys.argv[1], sys.argv[2], sys.argv[3])
"""
            import tempfile, textwrap, os
            fd, path = tempfile.mkstemp(suffix=".py")
            with os.fdopen(fd, "w") as f:
                f.write(textwrap.dedent(script))
            os.chmod(path, 0o755)
            return path
        except Exception as exc:   # pragma: no cover
            self.node.logger.error(f"Create-script failed: {exc}")
            return None
        
    def _parse_message(self, message_data: dict) -> Optional[Message]:
        """Parse message data into Message object.
        
        Args:
            message_data: Raw message data
            
        Returns:
            Parsed message or None if invalid
        """
        try:
            # check if message type is valid
            if message_data.get('message_type') not in [m.value for m in MessageType]:
                return None
            
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
            self.node.logger.debug(f"Received message: {message}")
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
            message = self.node.message_queue.get(timeout=timeout)
            self.node.logger.debug(f"Received message from {message.sender.ip_address}:{message.sender.port}")
            return message
        except Empty:
            return None
        except Exception as e:
            self.node.logger.error(f"Failed to receive message: {e}")
            return None 