"""Tests for WiFi Authority Node implementation."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch, Mock
from uuid import uuid4

import pytest

from core.authority import MetricsCollector, WiFiAuthority, WiFiInterface
from core.baseTypes import (
    Account,
    Address,
    ConfirmationOrder,
    NetworkMetrics,
    NodeType,
    TransactionStatus,
    TransferOrder,
)
from core.messages import Message, MessageType, TransferRequestMessage

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture
    from _pytest.fixtures import FixtureRequest
    from _pytest.logging import LogCaptureFixture
    from _pytest.monkeypatch import MonkeyPatch
    from pytest_mock.plugin import MockerFixture


class TestWiFiInterface:
    """Test cases for WiFiInterface class."""
    
    @pytest.fixture
    def mock_authority(self) -> Mock:
        """Create a mock authority node."""
        mock_auth = Mock()
        mock_auth.wintfs = {0: Mock()}
        mock_auth.cmd = Mock(return_value="Success")
        return mock_auth
    
    def test_init(self, mock_authority: Mock) -> None:
        """Test WiFiInterface initialization."""
        address = Address(
            node_id="test_node",
            ip_address="192.168.1.1",
            port=8080,
            node_type=NodeType.AUTHORITY
        )
        
        wifi_interface = WiFiInterface(mock_authority, address)
        
        assert wifi_interface.node == mock_authority
        assert wifi_interface.address == address
        assert wifi_interface.is_connected is False
        assert wifi_interface.connection_quality == 1.0
    
    def test_connect_success(self, mock_authority: Mock) -> None:
        """Test successful WiFi connection."""
        address = Address(
            node_id="test_node",
            ip_address="192.168.1.1",
            port=8080,
            node_type=NodeType.AUTHORITY
        )
        
        mock_intf = Mock()
        mock_authority.wintfs = {0: mock_intf}
        
        wifi_interface = WiFiInterface(mock_authority, address)
        
        result = wifi_interface.connect()
        
        assert result is True
        assert wifi_interface.is_connected is True
        mock_intf.ipLink.assert_called_once_with('up')
    
    def test_connect_failure_no_interfaces(self, mock_authority: Mock) -> None:
        """Test WiFi connection failure when no interfaces available."""
        address = Address(
            node_id="test_node",
            ip_address="192.168.1.1",
            port=8080,
            node_type=NodeType.AUTHORITY
        )
        
        mock_authority.wintfs = {}  # No interfaces
        
        wifi_interface = WiFiInterface(mock_authority, address)
        
        result = wifi_interface.connect()
        
        assert result is False
        assert wifi_interface.is_connected is False
    
    def test_disconnect(self, mock_authority: Mock) -> None:
        """Test WiFi disconnection."""
        address = Address(
            node_id="test_node",
            ip_address="192.168.1.1",
            port=8080,
            node_type=NodeType.AUTHORITY
        )
        
        mock_intf = Mock()
        mock_authority.wintfs = {0: mock_intf}
        
        wifi_interface = WiFiInterface(mock_authority, address)
        wifi_interface.is_connected = True
        
        wifi_interface.disconnect()
        
        assert wifi_interface.is_connected is False
        mock_intf.ipLink.assert_called_once_with('down')


class TestMetricsCollector:
    """Test cases for MetricsCollector class."""
    
    def test_init(self) -> None:
        """Test MetricsCollector initialization."""
        collector = MetricsCollector()
        
        assert collector.transaction_count == 0
        assert collector.error_count == 0
        assert collector.sync_count == 0
        assert isinstance(collector.network_metrics, NetworkMetrics)
    
    def test_record_transaction(self) -> None:
        """Test recording transactions."""
        collector = MetricsCollector()
        
        collector.record_transaction()
        collector.record_transaction()
        
        assert collector.transaction_count == 2
    
    def test_record_error(self) -> None:
        """Test recording errors."""
        collector = MetricsCollector()
        
        collector.record_error()
        collector.record_error()
        collector.record_error()
        
        assert collector.error_count == 3
    
    def test_record_sync(self) -> None:
        """Test recording synchronizations."""
        collector = MetricsCollector()
        
        collector.record_sync()
        
        assert collector.sync_count == 1
    
    def test_update_network_metrics(self) -> None:
        """Test updating network metrics."""
        collector = MetricsCollector()
        new_metrics = NetworkMetrics(
            latency=10.5,
            bandwidth=100.0,
            packet_loss=0.1,
            connectivity_ratio=0.9,
            last_update=time.time()
        )
        
        collector.update_network_metrics(new_metrics)
        
        assert collector.network_metrics == new_metrics
    
    def test_get_stats(self) -> None:
        """Test getting performance statistics."""
        collector = MetricsCollector()
        collector.record_transaction()
        collector.record_error()
        collector.record_sync()
        
        stats = collector.get_stats()
        
        expected_stats = {
            'transaction_count': 1,
            'error_count': 1,
            'sync_count': 1,
            'network_metrics': {
                'latency': 0.0,
                'bandwidth': 0.0,
                'packet_loss': 0.0,
                'connectivity_ratio': 0.0,
            }
        }
        
        assert stats == expected_stats


class TestWiFiAuthority:
    """Test cases for WiFiAuthority class."""
    
    @pytest.fixture
    def committee_members(self) -> set[str]:
        """Create test committee members."""
        return {"authority1", "authority2", "authority3"}
    
    @pytest.fixture
    def wifi_authority(self, committee_members: set[str]) -> WiFiAuthority:
        """Create test WiFiAuthority instance."""
        with patch('core.authority.Station.__init__') as mock_init:
            mock_init.return_value = None
            authority = WiFiAuthority(
                name="authority1",
                committee_members=committee_members,
                shard_assignments={"shard1", "shard2"},
                ip="10.0.0.1/8",
                position=[10.0, 20.0, 0.0]
            )
            
            # Mock required attributes that would normally be set by Station.__init__
            authority.wintfs = {0: Mock()}
            authority.name = "authority1"
            authority.position = [10.0, 20.0, 0.0]
            
            return authority
    
    def test_init(self, wifi_authority: WiFiAuthority, committee_members: set[str]) -> None:
        """Test WiFiAuthority initialization."""
        assert wifi_authority.name == "authority1"
        assert wifi_authority.host_address.node_id == "authority1"
        assert wifi_authority.host_address.ip_address == "10.0.0.1"
        assert wifi_authority.host_address.port == 8080
        assert wifi_authority.authority_state.name == "authority1"
        assert wifi_authority.authority_state.shard_assignments == {"shard1", "shard2"}
        assert wifi_authority.authority_state.committee_members == committee_members
        assert len(wifi_authority.authority_state.accounts) == 0
        assert len(wifi_authority.authority_state.pending_transfers) == 0
        assert len(wifi_authority.authority_state.confirmed_transfers) == 0
        assert wifi_authority._running is False
    
    @patch('core.authority.WiFiInterface.connect')
    def test_start_success(self, mock_connect: MagicMock, wifi_authority: WiFiAuthority) -> None:
        """Test successful authority start."""
        mock_connect.return_value = True
        
        result = wifi_authority.start_fastpay_services()
        
        assert result is True
        assert wifi_authority._running is True
        assert wifi_authority._message_handler_thread is not None
        assert wifi_authority._sync_thread is not None
        
        # Clean up
        wifi_authority.stop_fastpay_services()
    
    @patch('core.authority.WiFiInterface.connect')
    def test_start_failure(self, mock_connect: MagicMock, wifi_authority: WiFiAuthority) -> None:
        """Test authority start failure."""
        mock_connect.return_value = False
        
        result = wifi_authority.start_fastpay_services()
        
        assert result is False
        assert wifi_authority._running is False
    
    def test_stop(self, wifi_authority: WiFiAuthority) -> None:
        """Test authority stop."""
        wifi_authority._running = True
        
        wifi_authority.stop_fastpay_services()
        
        assert wifi_authority._running is False
    
    def test_get_wireless_interface(self, wifi_authority: WiFiAuthority) -> None:
        """Test getting wireless interface."""
        mock_intf = Mock()
        wifi_authority.wintfs = {0: mock_intf}
        
        result = wifi_authority.get_wireless_interface()
        
        assert result == mock_intf
    
    def test_get_wireless_interface_no_interfaces(self, wifi_authority: WiFiAuthority) -> None:
        """Test getting wireless interface when none available."""
        wifi_authority.wintfs = {}
        
        result = wifi_authority.get_wireless_interface()
        
        assert result is None
    
    def test_set_wireless_position(self, wifi_authority: WiFiAuthority) -> None:
        """Test setting wireless position."""
        with patch.object(wifi_authority, 'setPosition') as mock_set_pos:
            wifi_authority.set_wireless_position(10.0, 20.0, 5.0)
            
            mock_set_pos.assert_called_once_with("10.0,20.0,5.0")
    
    def test_get_signal_strength_to(self, wifi_authority: WiFiAuthority) -> None:
        """Test getting signal strength to peer."""
        # Create a mock peer
        peer = Mock()
        peer.position = [20.0, 30.0, 0.0]
        
        # Mock the get_distance_to method
        with patch.object(wifi_authority, 'get_distance_to', return_value=10.0):
            mock_intf = Mock()
            mock_intf.txpower = 20
            wifi_authority.wintfs = {0: mock_intf}
            
            rssi = wifi_authority.get_signal_strength_to(peer)
            
            # Should calculate RSSI based on distance and power
            assert isinstance(rssi, float)
            assert rssi < 0  # RSSI values are typically negative
    
    def test_discover_nearby_authorities(self, wifi_authority: WiFiAuthority) -> None:
        """Test discovering nearby authorities."""
        result = wifi_authority.discover_nearby_authorities(100.0)
        
        # Currently returns empty list as it's a placeholder
        assert isinstance(result, list)
        assert len(result) == 0
    
    def test_send_to_peer(self, wifi_authority: WiFiAuthority) -> None:
        """Test sending message to peer."""
        peer_address = Address(
            node_id="authority2",
            ip_address="10.0.0.2",
            port=8080,
            node_type=NodeType.AUTHORITY
        )
        
        message = Message(
            message_id=uuid4(),
            message_type=MessageType.HEARTBEAT,
            sender=wifi_authority.host_address,
            recipient=peer_address,
            timestamp=time.time(),
            payload={}
        )
        
        with patch.object(wifi_authority.network_interface, 'send_message', return_value=True) as mock_send:
            result = wifi_authority.send_to_peer(peer_address, message)
            
            assert result is True
            mock_send.assert_called_once_with(message, peer_address)
    
    def test_handle_transfer_order_success(self, wifi_authority: WiFiAuthority) -> None:
        """Test successful transfer order handling."""
        # Setup sender account
        sender_account = Account(
            address="sender123",
            balance=1000,
            sequence_number=0,
            last_update=time.time()
        )
        wifi_authority.authority_state.accounts["sender123"] = sender_account
        
        transfer_order = TransferOrder(
            order_id=uuid4(),
            sender="sender123",
            recipient="recipient456",
            amount=100,
            sequence_number=1,
            timestamp=time.time()
        )
        
        response = wifi_authority.handle_transfer_order(transfer_order)
        
        assert response.success is True
        assert response.order_id == transfer_order.order_id
        assert response.new_balance == 900
        assert sender_account.balance == 900
        assert sender_account.sequence_number == 1
        
        # Check recipient account was created
        recipient_account = wifi_authority.authority_state.accounts["recipient456"]
        assert recipient_account.balance == 100
        
        # Check pending transfer was recorded
        assert transfer_order.order_id in wifi_authority.authority_state.pending_transfers
    
    def test_handle_transfer_order_insufficient_balance(self, wifi_authority: WiFiAuthority) -> None:
        """Test transfer order with insufficient balance."""
        # Setup sender account with low balance
        sender_account = Account(
            address="sender123",
            balance=50,
            sequence_number=0,
            last_update=time.time()
        )
        wifi_authority.authority_state.accounts["sender123"] = sender_account
        
        transfer_order = TransferOrder(
            order_id=uuid4(),
            sender="sender123",
            recipient="recipient456",
            amount=100,
            sequence_number=1,
            timestamp=time.time()
        )
        
        response = wifi_authority.handle_transfer_order(transfer_order)
        
        assert response.success is False
        assert response.error_message == "Insufficient balance"
        assert sender_account.balance == 50  # Unchanged
    
    def test_handle_transfer_order_sender_not_found(self, wifi_authority: WiFiAuthority) -> None:
        """Test transfer order with nonexistent sender."""
        transfer_order = TransferOrder(
            order_id=uuid4(),
            sender="nonexistent",
            recipient="recipient456",
            amount=100,
            sequence_number=1,
            timestamp=time.time()
        )
        
        response = wifi_authority.handle_transfer_order(transfer_order)
        
        assert response.success is False
        assert response.error_message == "Sender account not found"
    
    def test_handle_transfer_order_invalid_order(self, wifi_authority: WiFiAuthority) -> None:
        """Test transfer order validation."""
        # Invalid transfer order (negative amount)
        transfer_order = TransferOrder(
            order_id=uuid4(),
            sender="sender123",
            recipient="recipient456",
            amount=-100,
            sequence_number=1,
            timestamp=time.time()
        )
        
        response = wifi_authority.handle_transfer_order(transfer_order)
        
        assert response.success is False
        assert response.error_message == "Invalid transfer order"
    
    def test_handle_confirmation_order(self, wifi_authority: WiFiAuthority) -> None:
        """Test confirmation order handling."""
        transfer_order = TransferOrder(
            order_id=uuid4(),
            sender="sender123",
            recipient="recipient456",
            amount=100,
            sequence_number=1,
            timestamp=time.time()
        )
        
        confirmation_order = ConfirmationOrder(
            order_id=transfer_order.order_id,
            transfer_order=transfer_order,
            authority_signatures={"authority1": "sig1", "authority2": "sig2"},
            timestamp=time.time()
        )
        
        # Add to pending first
        wifi_authority.authority_state.pending_transfers[transfer_order.order_id] = transfer_order
        
        result = wifi_authority.handle_confirmation_order(confirmation_order)
        
        assert result is True
        assert confirmation_order.status == TransactionStatus.CONFIRMED
        assert confirmation_order.order_id in wifi_authority.authority_state.confirmed_transfers
        assert transfer_order.order_id not in wifi_authority.authority_state.pending_transfers
    
    def test_add_peer_connection(self, wifi_authority: WiFiAuthority) -> None:
        """Test adding peer connection."""
        peer_address = Address(
            node_id="authority2",
            ip_address="192.168.1.11",
            port=8080,
            node_type=NodeType.AUTHORITY
        )
        
        wifi_authority.add_peer_connection("authority2", peer_address)
        
        assert "authority2" in wifi_authority.p2p_connections
        assert wifi_authority.p2p_connections["authority2"] == peer_address
    
    def test_remove_peer_connection(self, wifi_authority: WiFiAuthority) -> None:
        """Test removing peer connection."""
        peer_address = Address(
            node_id="authority2",
            ip_address="192.168.1.11",
            port=8080,
            node_type=NodeType.AUTHORITY
        )
        
        wifi_authority.add_peer_connection("authority2", peer_address)
        wifi_authority.remove_peer_connection("authority2")
        
        assert "authority2" not in wifi_authority.p2p_connections
    
    def test_get_account_balance(self, wifi_authority: WiFiAuthority) -> None:
        """Test getting account balance."""
        account = Account(
            address="test_account",
            balance=500,
            sequence_number=0,
            last_update=time.time()
        )
        wifi_authority.authority_state.accounts["test_account"] = account
        
        balance = wifi_authority.get_account_balance("test_account")
        assert balance == 500
        
        # Test nonexistent account
        balance = wifi_authority.get_account_balance("nonexistent")
        assert balance is None
    
    def test_get_performance_stats(self, wifi_authority: WiFiAuthority) -> None:
        """Test getting performance statistics."""
        wifi_authority.performance_metrics.record_transaction()
        wifi_authority.performance_metrics.record_error()
        
        stats = wifi_authority.get_performance_stats()
        
        assert stats['transaction_count'] == 1
        assert stats['error_count'] == 1
        assert 'network_metrics' in stats
    
    def test_validate_transfer_order(self, wifi_authority: WiFiAuthority) -> None:
        """Test transfer order validation."""
        # Valid transfer order
        valid_order = TransferOrder(
            order_id=uuid4(),
            sender="sender123",
            recipient="recipient456",
            amount=100,
            sequence_number=1,
            timestamp=time.time()
        )
        assert wifi_authority._validate_transfer_order(valid_order) is True
        
        # Invalid: negative amount
        invalid_order = TransferOrder(
            order_id=uuid4(),
            sender="sender123",
            recipient="recipient456",
            amount=-100,
            sequence_number=1,
            timestamp=time.time()
        )
        assert wifi_authority._validate_transfer_order(invalid_order) is False
        
        # Invalid: same sender and recipient
        invalid_order2 = TransferOrder(
            order_id=uuid4(),
            sender="sender123",
            recipient="sender123",
            amount=100,
            sequence_number=1,
            timestamp=time.time()
        )
        assert wifi_authority._validate_transfer_order(invalid_order2) is False
        
        # Invalid: empty sender
        invalid_order3 = TransferOrder(
            order_id=uuid4(),
            sender="",
            recipient="recipient456",
            amount=100,
            sequence_number=1,
            timestamp=time.time()
        )
        assert wifi_authority._validate_transfer_order(invalid_order3) is False
    
    @patch('core.authority.WiFiAuthority.broadcast_to_peers')
    def test_sync_with_committee(self, mock_broadcast: MagicMock, wifi_authority: WiFiAuthority) -> None:
        """Test synchronization with committee."""
        mock_broadcast.return_value = 2  # Successful sends to 2 peers
        
        result = wifi_authority.sync_with_committee()
        
        assert result is True
        assert mock_broadcast.call_count == 1
        
        # Test failure case
        mock_broadcast.return_value = 0  # No successful sends
        result = wifi_authority.sync_with_committee()
        assert result is False
    
    @patch('core.authority.WiFiInterface.send_message')
    def test_broadcast_to_peers(self, mock_send: MagicMock, wifi_authority: WiFiAuthority) -> None:
        """Test broadcasting to peers."""
        # Add some peer connections
        peer1_address = Address(
            node_id="authority2",
            ip_address="192.168.1.11",
            port=8080,
            node_type=NodeType.AUTHORITY
        )
        peer2_address = Address(
            node_id="authority3",
            ip_address="192.168.1.12",
            port=8080,
            node_type=NodeType.AUTHORITY
        )
        
        wifi_authority.add_peer_connection("authority2", peer1_address)
        wifi_authority.add_peer_connection("authority3", peer2_address)
        
        # Mock successful sends
        mock_send.return_value = True
        
        message = Message(
            message_id=uuid4(),
            message_type=MessageType.HEARTBEAT,
            sender=wifi_authority.host_address,
            recipient=None,
            timestamp=time.time(),
            payload={}
        )
        
        result = wifi_authority.broadcast_to_peers(message)
        
        assert result == 2
        assert mock_send.call_count == 2 