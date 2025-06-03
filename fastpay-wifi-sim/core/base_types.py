"""Base types and data structures for FastPay WiFi simulation."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Union
from uuid import UUID, uuid4


class NodeType(Enum):
    """Type of node in the network."""
    
    AUTHORITY = "authority"
    CLIENT = "client"


class TransactionStatus(Enum):
    """Status of a transaction."""
    
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    FINALIZED = "finalized"


@dataclass
class Address:
    """Network address for a node."""
    
    node_id: str
    ip_address: str
    port: int
    node_type: NodeType
    
    def __str__(self) -> str:
        """Return string representation of address."""
        return f"{self.node_type.value}:{self.node_id}@{self.ip_address}:{self.port}"


@dataclass
class Account:
    """Account state in the FastPay system."""
    
    address: str
    balance: int
    sequence_number: int
    last_update: float
    
    def __post_init__(self) -> None:
        """Initialize default values."""
        if self.last_update == 0:
            self.last_update = time.time()


@dataclass
class TransferOrder:
    """Transfer order from client to authority."""
    
    order_id: UUID
    sender: str
    recipient: str
    amount: int
    sequence_number: int
    timestamp: float
    signature: Optional[str] = None
    
    def __post_init__(self) -> None:
        """Initialize default values."""
        if self.order_id is None:
            self.order_id = uuid4()
        if self.timestamp == 0:
            self.timestamp = time.time()


@dataclass
class ConfirmationOrder:
    """Confirmation order between authorities."""
    
    order_id: UUID
    transfer_order: TransferOrder
    authority_signatures: Dict[str, str]
    timestamp: float
    status: TransactionStatus = TransactionStatus.PENDING
    
    def __post_init__(self) -> None:
        """Initialize default values."""
        if self.timestamp == 0:
            self.timestamp = time.time()


@dataclass
class AuthorityState:
    """State maintained by an authority node."""
    
    name: str
    shard_assignments: Set[str]
    accounts: Dict[str, Account]
    pending_transfers: Dict[UUID, TransferOrder]
    confirmed_transfers: Dict[UUID, ConfirmationOrder]
    committee_members: Set[str]
    last_sync_time: float
    
    def __post_init__(self) -> None:
        """Initialize default values."""
        if self.last_sync_time == 0:
            self.last_sync_time = time.time()


@dataclass
class NetworkMetrics:
    """Network performance metrics."""
    
    latency: float
    bandwidth: float
    packet_loss: float
    connectivity_ratio: float
    last_update: float
    
    def __post_init__(self) -> None:
        """Initialize default values."""
        if self.last_update == 0:
            self.last_update = time.time()


AuthorityName = str
ClientAddress = str
MessagePayload = Dict[str, Any] 