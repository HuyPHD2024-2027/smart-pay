"""
Message handling infrastructure for FastPay WiFi CLI testing.

This module provides message types, message routing, and base message handling
functionality for the interactive CLI test environment.
"""

import time
import queue
from enum import Enum
from dataclasses import dataclass
from typing import Dict, Optional, Any, List
from uuid import UUID, uuid4


class MessageType(Enum):
    """Types of messages in the FastPay system."""
    
    TRANSFER_ORDER = "transfer_order"
    CONFIRMATION_ORDER = "confirmation_order"
    BALANCE_QUERY = "balance_query"
    PING = "ping"
    HEARTBEAT = "heartbeat"
    SYNC_REQUEST = "sync_request"
    
    # Legacy support for existing code
    TRANSFER_REQUEST = "transfer_order"
    CONFIRMATION_REQUEST = "confirmation_order"
    PEER_DISCOVERY = "ping"


@dataclass
class Message:
    """Represents a message in the FastPay system."""
    
    msg_type: MessageType
    payload: Dict[str, Any]
    sender: str
    timestamp: float
    msg_id: Optional[UUID] = None
    recipient: Optional[str] = None
    signature: Optional[str] = None
    
    # Legacy support for existing code  
    message_type: Optional[MessageType] = None
    message_id: Optional[UUID] = None
    
    def __post_init__(self) -> None:
        """Initialize message after creation."""
        if self.msg_id is None:
            self.msg_id = uuid4()
        
        # Legacy support
        if self.message_type is None:
            self.message_type = self.msg_type
        if self.message_id is None:
            self.message_id = self.msg_id


class MessageBroker:
    """Message broker for routing messages between authorities and users."""
    
    def __init__(self) -> None:
        """Initialize the message broker."""
        self.authority_queues: Dict[str, queue.Queue] = {}
        self.user_queues: Dict[str, queue.Queue] = {}
    
    def register_authority(self, authority_name: str) -> None:
        """Register an authority with the broker.
        
        Args:
            authority_name: Name of the authority to register
        """
        self.authority_queues[authority_name] = queue.Queue()
    
    def register_user(self, user_name: str) -> None:
        """Register a user with the broker.
        
        Args:
            user_name: Name of the user to register
        """
        self.user_queues[user_name] = queue.Queue()
    
    def send_to_authority(self, authority_name: str, message: Message) -> bool:
        """Send message to specific authority.
        
        Args:
            authority_name: Name of the target authority
            message: Message to send
            
        Returns:
            True if message was sent successfully, False otherwise
        """
        if authority_name in self.authority_queues:
            self.authority_queues[authority_name].put(message)
            return True
        return False
    
    def send_to_all_authorities(self, message: Message) -> int:
        """Send message to all authorities.
        
        Args:
            message: Message to send
            
        Returns:
            Number of authorities the message was sent to
        """
        sent_count = 0
        for authority_name in self.authority_queues:
            if self.send_to_authority(authority_name, message):
                sent_count += 1
        return sent_count
    
    def send_to_user(self, user_name: str, message: Message) -> bool:
        """Send message to specific user.
        
        Args:
            user_name: Name of the target user
            message: Message to send
            
        Returns:
            True if message was sent successfully, False otherwise
        """
        if user_name in self.user_queues:
            self.user_queues[user_name].put(message)
            return True
        return False
    
    def get_message_for_authority(self, authority_name: str, timeout: float = 1.0) -> Optional[Message]:
        """Get message for specific authority.
        
        Args:
            authority_name: Name of the authority
            timeout: Timeout for waiting for message
            
        Returns:
            Message if available, None if timeout or authority not found
        """
        if authority_name in self.authority_queues:
            try:
                return self.authority_queues[authority_name].get(timeout=timeout)
            except queue.Empty:
                return None
        return None
    
    def get_message_for_user(self, user_name: str, timeout: float = 1.0) -> Optional[Message]:
        """Get message for specific user.
        
        Args:
            user_name: Name of the user
            timeout: Timeout for waiting for message
            
        Returns:
            Message if available, None if timeout or user not found
        """
        if user_name in self.user_queues:
            try:
                return self.user_queues[user_name].get(timeout=timeout)
            except queue.Empty:
                return None
        return None
    
    def get_authority_count(self) -> int:
        """Get number of registered authorities.
        
        Returns:
            Number of registered authorities
        """
        return len(self.authority_queues)
    
    def get_user_count(self) -> int:
        """Get number of registered users.
        
        Returns:
            Number of registered users
        """
        return len(self.user_queues)


class MessageHandler:
    """Base class for handling messages in the FastPay system."""
    
    def __init__(self, name: str) -> None:
        """Initialize message handler.
        
        Args:
            name: Name of the message handler
        """
        self.name = name
        self.running = True
    
    def handle_message(self, message: Message) -> Optional[Dict[str, Any]]:
        """Handle incoming message based on type.
        
        Args:
            message: Message to handle
            
        Returns:
            Response payload if applicable, None otherwise
        """
        if message.msg_type == MessageType.TRANSFER_ORDER:
            return self.handle_transfer_order(message)
        elif message.msg_type == MessageType.CONFIRMATION_ORDER:
            return self.handle_confirmation_order(message)
        elif message.msg_type == MessageType.BALANCE_QUERY:
            return self.handle_balance_query(message)
        elif message.msg_type == MessageType.PING:
            return self.handle_ping(message)
        elif message.msg_type == MessageType.HEARTBEAT:
            return self.handle_heartbeat(message)
        elif message.msg_type == MessageType.SYNC_REQUEST:
            return self.handle_sync_request(message)
        else:
            return self.handle_unknown_message(message)
    
    def handle_transfer_order(self, message: Message) -> Optional[Dict[str, Any]]:
        """Handle transfer order message.
        
        Args:
            message: Transfer order message
            
        Returns:
            Response payload
        """
        # Override in subclasses
        return {"status": "not_implemented", "message_type": "transfer_order"}
    
    def handle_confirmation_order(self, message: Message) -> Optional[Dict[str, Any]]:
        """Handle confirmation order message.
        
        Args:
            message: Confirmation order message
            
        Returns:
            Response payload
        """
        # Override in subclasses
        return {"status": "not_implemented", "message_type": "confirmation_order"}
    
    def handle_balance_query(self, message: Message) -> Optional[Dict[str, Any]]:
        """Handle balance query message.
        
        Args:
            message: Balance query message
            
        Returns:
            Response payload
        """
        # Override in subclasses
        return {"status": "not_implemented", "message_type": "balance_query"}
    
    def handle_ping(self, message: Message) -> Optional[Dict[str, Any]]:
        """Handle ping message.
        
        Args:
            message: Ping message
            
        Returns:
            Pong response
        """
        return {
            "pong": True,
            "handler": self.name,
            "timestamp": time.time()
        }
    
    def handle_heartbeat(self, message: Message) -> Optional[Dict[str, Any]]:
        """Handle heartbeat message.
        
        Args:
            message: Heartbeat message
            
        Returns:
            Response payload
        """
        return {
            "heartbeat_ack": True,
            "handler": self.name,
            "timestamp": time.time()
        }
    
    def handle_sync_request(self, message: Message) -> Optional[Dict[str, Any]]:
        """Handle sync request message.
        
        Args:
            message: Sync request message
            
        Returns:
            Response payload
        """
        # Override in subclasses
        return {"status": "not_implemented", "message_type": "sync_request"}
    
    def handle_unknown_message(self, message: Message) -> Optional[Dict[str, Any]]:
        """Handle unknown message type.
        
        Args:
            message: Unknown message
            
        Returns:
            Error response
        """
        return {
            "status": "error",
            "error": f"Unknown message type: {message.msg_type}",
            "message_id": str(message.msg_id)
        }
    
    def stop(self) -> None:
        """Stop the message handler."""
        self.running = False 