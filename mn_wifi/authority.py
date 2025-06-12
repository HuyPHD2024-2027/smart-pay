"""WiFi Authority Node implementation for FastPay simulation."""

from __future__ import annotations

import logging
import threading
import time
from queue import Queue
from typing import Any, Dict, List, Optional, Set, Protocol
from uuid import UUID, uuid4

from mn_wifi.node import Station
from mn_wifi.link import IntfWireless

from mn_wifi.baseTypes import (
    Account,
    Address,
    AuthorityState,
    ConfirmationOrder,
    NetworkMetrics,
    NodeType,
    TransactionStatus,
    TransferOrder,
)
from mn_wifi.messages import (
    ConfirmationRequestMessage,
    Message,
    MessageType,
    SyncRequestMessage,
    TransferRequestMessage,
    TransferResponseMessage,
)
from mn_wifi.client import TransportKind  # Enum shared across modules

# Dedicated transport implementations
from mn_wifi.transport import NetworkTransport, TransportKind
from mn_wifi.tcp import TCPTransport
from mn_wifi.udp import UDPTransport
from mn_wifi.wifiDirect import WiFiDirectTransport

from mn_wifi.metrics import MetricsCollector
from mn_wifi.authorityLogger import AuthorityLogger


class WiFiAuthority(Station):
    """Authority node that runs on mininet-wifi host, inheriting from Station."""
    
    def __init__(
        self,
        name: str,
        committee_members: Set[str],
        shard_assignments: Optional[Set[str]] = None,
        ip: str = '10.0.0.1/8',
        port: int = 8080,
        position: Optional[List[float]] = None,
        **params
    ) -> None:
        """Initialize WiFi Authority node.
        
        Args:
            name: Authority name
            committee_members: Set of committee member names
            shard_assignments: Optional set of shard assignments
            ip: IP address for the node
            position: Position of the node [x, y, z]
            **params: Additional parameters for Station
        """
        # Extract transport configuration parameters **before** updating default_params so that
        # we don't forward them to Station.__init__, which would not recognise them.

        transport_kind = params.pop("transport_kind", TransportKind.TCP)
        transport: Optional[NetworkTransport] = params.pop("transport", None)

        default_params = {
            'ip': ip,
            'position': position or [0, 0, 0],
            'range': 100,  # WiFi range in meters
            'txpower': 20,  # Transmission power
            'antennaGain': 5,  # Antenna gain
        }
        default_params.update(params)
        
        # Initialize the Station base class
        super().__init__(name, **default_params)
        
        # FastPay specific attributes
        self.state = AuthorityState(
            name=name,
            shard_assignments=shard_assignments or set(),
            accounts={},
            pending_transfers={},
            confirmed_transfers={},
            committee_members=committee_members,
            last_sync_time=time.time()
        )
        
        # Create address from mininet-wifi node information
        self.address = Address(
            node_id=name,
            ip_address=ip.split('/')[0],
            port=port,  
            node_type=NodeType.AUTHORITY
        )
        
        self.p2p_connections: Dict[str, Address] = {}
        self.message_queue: Queue[Message] = Queue()
        self.performance_metrics = MetricsCollector()
        
        self._running = False
        self._message_handler_thread: Optional[threading.Thread] = None
        self._sync_thread: Optional[threading.Thread] = None
        
        # Configure logging
        self.logger = AuthorityLogger(name)
        
        # ------------------------------------------------------------------
        # Transport selection (default = TCP for backward-compatibility)
        # ------------------------------------------------------------------

        if transport is not None:
            self.transport: NetworkTransport = transport
        else:
            if transport_kind == TransportKind.TCP:
                self.transport = TCPTransport(self, self.address)
            elif transport_kind == TransportKind.UDP:
                self.transport = UDPTransport(self, self.address)
            elif transport_kind == TransportKind.WIFI_DIRECT:
                self.transport = WiFiDirectTransport(self, self.address)
            else:
                raise ValueError(f"Unsupported transport kind: {transport_kind}")

    def start_fastpay_services(self) -> bool:
        """Boot-strap background processing threads and ready the chosen transport.

        The method preserves the previous external behaviour: it must be called explicitly after
        the authority instance is added to Mininet-WiFi so that the node's namespace exists.
        """

        # Connect transport (if the implementation supports/needs it)
        if hasattr(self.transport, "connect"):
            try:
                if not self.transport.connect():  # type: ignore[attr-defined]
                    self.logger.error("Failed to connect transport")
                    return False
            except Exception as exc:  # pragma: no cover
                self.logger.error(f"Transport connect error: {exc}")
                return False

        self._running = True

        # Spawn background threads -----------------------------------------------------------
        self._message_handler_thread = threading.Thread(
            target=self._message_handler_loop,
            daemon=True,
        )
        self._message_handler_thread.start()

        self._sync_thread = threading.Thread(
            target=self._sync_loop,
            daemon=True,
        )
        self._sync_thread.start()

        self.logger.info(f"Authority {self.name} started successfully")
        return True
    
    def stop_fastpay_services(self) -> None:
        """Stop the FastPay authority services."""
        self._running = False
        if hasattr(self.transport, "disconnect"):
            try:
                self.transport.disconnect()  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover
                pass
        
        if self._message_handler_thread:
            self._message_handler_thread.join(timeout=5.0)
        if self._sync_thread:
            self._sync_thread.join(timeout=5.0)
        self.logger.info(f"Authority {self.name} stopped")
    
    def get_wireless_interface(self) -> Optional[IntfWireless]:
        """Get the wireless interface for this node.
        
        Returns:
            The wireless interface or None if not available
        """
        if self.wintfs:
            return list(self.wintfs.values())[0]
        return None
    
    def set_wireless_position(self, x: float, y: float, z: float = 0) -> None:
        """Set the position of this wireless node.
        
        Args:
            x: X coordinate
            y: Y coordinate  
            z: Z coordinate (optional)
        """
        self.setPosition(f"{x},{y},{z}")
        
    def get_signal_strength_to(self, peer: 'WiFiAuthority') -> float:
        """Get signal strength to another authority.
        
        Args:
            peer: Target authority node
            
        Returns:
            Signal strength (RSSI) value
        """
        try:
            if hasattr(self, 'position') and hasattr(peer, 'position'):
                # Use inherited get_distance_to method from Node_wifi
                distance = self.get_distance_to(peer)
                intf = self.get_wireless_interface()
                if intf:
                    # Calculate RSSI based on distance and transmission power
                    # This is a simplified calculation
                    rssi = intf.txpower - (20 * self._log10(distance)) - 32.44
                    return rssi
        except Exception as e:
            self.logger.error(f"Error calculating signal strength: {e}")
        return -100  # Very weak signal
    
    def _log10(self, x: float) -> float:
        """Calculate log10 of x."""
        import math
        return math.log10(max(x, 1))  # Avoid log(0)
    
    def discover_nearby_authorities(self, range_meters: float = 100) -> List['WiFiAuthority']:
        """Discover nearby authority nodes within range.
        
        Args:
            range_meters: Discovery range in meters
            
        Returns:
            List of nearby authority nodes
        """
        nearby_authorities = []
        
        # In a real mininet-wifi simulation, you would access the network
        # to find other nodes. For now, this is a placeholder.
        # In practice, this would involve:
        # 1. Broadcasting discovery messages
        # 2. Listening for responses
        # 3. Filtering by node type and distance
        
        return nearby_authorities
    
    def send_to_peer(self, peer_address: Address, message: Message) -> bool:
        """Send message to a peer authority.
        
        Args:
            peer_address: Address of the peer authority
            message: Message to send
            
        Returns:
            True if sent successfully, False otherwise
        """
        return self.transport.send_message(message, peer_address)
    
    def handle_transfer_order(self, transfer_order: TransferOrder) -> TransferResponseMessage:
        """Handle transfer order from client.
        
        Args:
            transfer_order: Transfer order to process
            
        Returns:
            Transfer response message
        """
        try:
            # Validate transfer order
            if not self._validate_transfer_order(transfer_order):
                return TransferResponseMessage(
                    order_id=transfer_order.order_id,
                    success=False,
                    error_message="Invalid transfer order"
                )
            
            # Check if sender account exists and has sufficient balance
            sender_account = self.state.accounts.get(transfer_order.sender)
            if not sender_account:
                return TransferResponseMessage(
                    order_id=transfer_order.order_id,
                    success=False,
                    error_message="Sender account not found"
                )
            
            if sender_account.balance < transfer_order.amount:
                return TransferResponseMessage(
                    order_id=transfer_order.order_id,
                    success=False,
                    error_message="Insufficient balance"
                )
            
            # Add to pending transfers
            self.state.pending_transfers[transfer_order.order_id] = transfer_order
            
            # Update sender balance temporarily
            sender_account.balance -= transfer_order.amount
            sender_account.sequence_number += 1
            sender_account.last_update = time.time()
            
            # Create recipient account if it doesn't exist
            if transfer_order.recipient not in self.state.accounts:
                self.state.accounts[transfer_order.recipient] = Account(
                    address=transfer_order.recipient,
                    balance=0,
                    sequence_number=0,
                    last_update=time.time()
                )
            
            # Update recipient balance
            recipient_account = self.state.accounts[transfer_order.recipient]
            recipient_account.balance += transfer_order.amount
            recipient_account.last_update = time.time()
            
            self.performance_metrics.record_transaction()
            
            # Initiate committee confirmation if needed
            if len(self.state.committee_members) > 1:
                self._initiate_confirmation(transfer_order)
            
            return TransferResponseMessage(
                order_id=transfer_order.order_id,
                success=True,
                new_balance=sender_account.balance
            )
            
        except Exception as e:
            self.logger.error(f"Error handling transfer order: {e}")
            self.performance_metrics.record_error()
            return TransferResponseMessage(
                order_id=transfer_order.order_id,
                success=False,
                error_message=f"Internal error: {str(e)}"
            )
    
    def handle_confirmation_order(self, confirmation_order: ConfirmationOrder) -> bool:
        """Handle confirmation order from committee.
        
        Args:
            confirmation_order: Confirmation order to process
            
        Returns:
            True if handled successfully, False otherwise
        """
        try:
            # Store confirmation order
            self.state.confirmed_transfers[confirmation_order.order_id] = confirmation_order
            
            # Remove from pending if exists
            if confirmation_order.order_id in self.state.pending_transfers:
                del self.state.pending_transfers[confirmation_order.order_id]
            
            # Update confirmation status
            confirmation_order.status = TransactionStatus.CONFIRMED
            
            self.logger.info(f"Confirmation order {confirmation_order.order_id} processed")
            return True
            
        except Exception as e:
            self.logger.error(f"Error handling confirmation order: {e}")
            self.performance_metrics.record_error()
            return False
    
    def broadcast_to_peers(self, message: Message) -> int:
        """Broadcast message to all committee peers.
        
        Args:
            message: Message to broadcast
            
        Returns:
            Number of successful sends
        """
        successful_sends = 0
        
        for peer_name, peer_address in self.p2p_connections.items():
            if self.transport.send_message(message, peer_address):
                successful_sends += 1
            else:
                self.logger.warning(f"Failed to send message to peer {peer_name}")
        
        return successful_sends
    
    def sync_with_committee(self) -> bool:
        """Synchronize state with committee members.
        
        Returns:
            True if sync successful, False otherwise
        """
        try:
            # Create sync request
            sync_request = SyncRequestMessage(
                last_sync_time=self.state.last_sync_time,
                account_addresses=list(self.state.accounts.keys())
            )
            
            # Create message
            message = Message(
                message_id=uuid4(),
                message_type=MessageType.SYNC_REQUEST,
                sender=self.address,
                recipient=None,  # Broadcast
                timestamp=time.time(),
                payload=sync_request.to_payload()
            )
            
            # Broadcast to committee
            sent_count = self.broadcast_to_peers(message)
            
            if sent_count > 0:
                self.state.last_sync_time = time.time()
                self.performance_metrics.record_sync()
                self.logger.info(f"Sync request sent to {sent_count} peers")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error syncing with committee: {e}")
            self.performance_metrics.record_error()
            return False
    
    def add_peer_connection(self, peer_name: str, peer_address: Address) -> None:
        """Add a peer connection.
        
        Args:
            peer_name: Name of the peer
            peer_address: Address of the peer
        """
        self.p2p_connections[peer_name] = peer_address
        self.logger.info(f"Added peer connection: {peer_name}")
    
    def remove_peer_connection(self, peer_name: str) -> None:
        """Remove a peer connection.
        
        Args:
            peer_name: Name of the peer to remove
        """
        if peer_name in self.p2p_connections:
            del self.p2p_connections[peer_name]
            self.logger.info(f"Removed peer connection: {peer_name}")
    
    def get_account_balance(self, account_address: str) -> Optional[int]:
        """Get account balance.
        
        Args:
            account_address: Address of the account
            
        Returns:
            Account balance or None if account not found
        """
        account = self.state.accounts.get(account_address)
        return account.balance if account else None
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics.
        
        Returns:
            Dictionary containing performance stats
        """
        return self.performance_metrics.get_stats()
    
    def _validate_transfer_order(self, transfer_order: TransferOrder) -> bool:
        """Validate a transfer order.
        
        Args:
            transfer_order: Transfer order to validate
            
        Returns:
            True if valid, False otherwise
        """
        # Basic validation checks
        if transfer_order.amount <= 0:
            return False
        
        if transfer_order.sender == transfer_order.recipient:
            return False
        
        if not transfer_order.sender or not transfer_order.recipient:
            return False
        
        # Check sequence number
        sender_account = self.state.accounts.get(transfer_order.sender)
        if sender_account and transfer_order.sequence_number <= sender_account.sequence_number:
            return False
        
        return True
    
    def _initiate_confirmation(self, transfer_order: TransferOrder) -> None:
        """Initiate confirmation process with committee.
        
        Args:
            transfer_order: Transfer order to confirm
        """
        try:
            confirmation_order = ConfirmationOrder(
                order_id=transfer_order.order_id,
                transfer_order=transfer_order,
                authority_signatures={self.name: "signature_placeholder"},
                timestamp=time.time(),
                status=TransactionStatus.PENDING
            )
            
            confirmation_request = ConfirmationRequestMessage(
                confirmation_order=confirmation_order
            )
            
            message = Message(
                message_id=uuid4(),
                message_type=MessageType.CONFIRMATION_REQUEST,
                sender=self.address,
                recipient=None,  # Broadcast
                timestamp=time.time(),
                payload=confirmation_request.to_payload()
            )
            
            self.broadcast_to_peers(message)
            self.logger.info(f"Confirmation request initiated for order {transfer_order.order_id}")
            
        except Exception as e:
            self.logger.error(f"Error initiating confirmation: {e}")
    
    def _message_handler_loop(self) -> None:
        """Main message handling loop."""
        while self._running:
            try:
                message = self.transport.receive_message(timeout=1.0)
                if message:
                    self._process_message(message)
            except Exception as e:
                self.logger.error(f"Error in message handler loop: {e}")
                time.sleep(0.1)
    
    def _process_message(self, message: Message) -> None:
        """Process incoming message.
        
        Args:
            message: Message to process
        """
        try:
            if message.message_type == MessageType.TRANSFER_REQUEST:
                request = TransferRequestMessage.from_payload(message.payload)
                response = self.handle_transfer_order(request.transfer_order)
                
                # Send response back
                response_message = Message(
                    message_id=uuid4(),
                    message_type=MessageType.TRANSFER_RESPONSE,
                    sender=self.address,
                    recipient=message.sender,
                    timestamp=time.time(),
                    payload=response.to_payload()
                )
                self.transport.send_message(response_message, message.sender)
                
            elif message.message_type == MessageType.CONFIRMATION_REQUEST:
                request = ConfirmationRequestMessage.from_payload(message.payload)
                self.handle_confirmation_order(request.confirmation_order)
                
            elif message.message_type == MessageType.SYNC_REQUEST:
                self._handle_sync_request(message)
                
        except Exception as e:
            self.logger.error(f"Error processing message: {e}")
    
    def _handle_sync_request(self, message: Message) -> None:
        """Handle sync request from peer.
        
        Args:
            message: Sync request message
        """
        # Placeholder for handling sync requests.  Depending on the transport used, the
        # semantics remain identical – we simply rely on *self.transport* for I/O.
        pass
    
    def _sync_loop(self) -> None:
        """Periodic synchronization loop."""
        while self._running:
            try:
                # Sync with committee every 30 seconds
                time.sleep(30)
                if self._running:
                    self.sync_with_committee()
            except Exception as e:
                self.logger.error(f"Error in sync loop: {e}")
                time.sleep(5) 