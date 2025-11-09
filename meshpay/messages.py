"""Message types and protocols for MeshPay WiFi communication."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from meshpay.dag.block import DagBlock, QuorumCertificate
from meshpay.types import Address, ConfirmationOrder, TransferOrder


class MessageType(Enum):
    """Types of messages in the MeshPay WiFi protocol."""
    
    TRANSFER_REQUEST = "transfer_request"
    TRANSFER_RESPONSE = "transfer_response"
    CONFIRMATION_REQUEST = "confirmation_request"
    CONFIRMATION_RESPONSE = "confirmation_response"
    SYNC_REQUEST = "sync_request"
    SYNC_RESPONSE = "sync_response"
    PEER_DISCOVERY = "peer_discovery"
    HEARTBEAT = "heartbeat"
    ERROR = "error"
    DAG_BLOCK = "dag_block"
    DAG_VOTE = "dag_vote"


@dataclass
class Message:
    """Base message class for all WiFi communications."""
    
    message_id: UUID
    message_type: MessageType
    sender: Address
    recipient: Optional[Address]
    timestamp: float
    payload: Dict[str, Any]
    signature: Optional[str] = None
    
    def __post_init__(self) -> None:
        """Initialize default values."""
        if self.message_id is None:
            self.message_id = uuid4()
        if self.timestamp == 0:
            self.timestamp = time.time()
    
    def to_json(self) -> str:
        """Serialize message to JSON."""
        data = asdict(self)
        # Convert UUID to string for JSON serialization
        data['message_id'] = str(data['message_id'])
        data['message_type'] = data['message_type'].value
        return json.dumps(data)
    
    @classmethod
    def from_json(cls, json_str: str) -> "Message":
        """Deserialize message from JSON."""
        data = json.loads(json_str)
        data['message_id'] = UUID(data['message_id'])
        data['message_type'] = MessageType(data['message_type'])
        return cls(**data)


@dataclass
class TransferRequestMessage:
    """Message for requesting a transfer."""
    
    transfer_order: TransferOrder
    
    def to_payload(self) -> Dict[str, Any]:
        """Convert to message payload."""
        return {
            'transfer_order': {
                'order_id': str(self.transfer_order.order_id),
                'sender': str(self.transfer_order.sender),
                'recipient': str(self.transfer_order.recipient),
                'token_address': str(self.transfer_order.token_address),
                'amount': self.transfer_order.amount,
                'sequence_number': self.transfer_order.sequence_number,
                'timestamp': self.transfer_order.timestamp,
                'signature': self.transfer_order.signature
            }
        }
    
    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "TransferRequestMessage":
        """Create from message payload."""
        transfer_data = payload['transfer_order']

        if isinstance(transfer_data.get('order_id'), str):
            transfer_data['order_id'] = UUID(transfer_data['order_id'])
        transfer_order = TransferOrder(**transfer_data)
        return cls(
            transfer_order=transfer_order,
        )


@dataclass
class TransferResponseMessage:
    """Message for responding to a transfer request."""
    
    transfer_order: TransferOrder
    success: bool
    error_message: Optional[str] = None
    authority_signature: Optional[str] = None
    
    def to_payload(self) -> Dict[str, Any]:
        """Convert to message payload."""
        return {
            'transfer_order': asdict(self.transfer_order),
            'success': self.success,
            'error_message': self.error_message,
            'authority_signature': self.authority_signature
        }
    
    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "TransferResponseMessage":
        """Create from message payload."""
        return cls(
            transfer_order=TransferOrder(**payload['transfer_order']),
            success=payload['success'],
            error_message=payload.get('error_message'),
            authority_signature=payload.get('authority_signature')
        )


@dataclass
class ConfirmationRequestMessage:
    """Message for requesting confirmation from committee."""
    
    confirmation_order: ConfirmationOrder
    
    def to_payload(self) -> Dict[str, Any]:
        """Convert to message payload."""
        return {
            'confirmation_order': asdict(self.confirmation_order)
        }
    
    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "ConfirmationRequestMessage":
        """Create from message payload."""
        conf_data = payload['confirmation_order']

        if isinstance(conf_data.get('order_id'), str):
            conf_data['order_id'] = UUID(conf_data['order_id'])
        confirmation_order = ConfirmationOrder(**conf_data)
        return cls(
            confirmation_order=confirmation_order,
        )

@dataclass
class SyncRequestMessage:
    """Message for requesting synchronization."""
    
    last_sync_time: float
    account_addresses: List[str]
    
    def to_payload(self) -> Dict[str, Any]:
        """Convert to message payload."""
        return {
            'last_sync_time': self.last_sync_time,
            'account_addresses': self.account_addresses
        }
    
    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "SyncRequestMessage":
        """Create from message payload."""
        return cls(
            last_sync_time=payload['last_sync_time'],
            account_addresses=payload['account_addresses']
        )


@dataclass
class PeerDiscoveryMessage:
    """Message for peer discovery in WiFi network."""
    
    node_info: Address
    service_capabilities: List[str]
    network_metrics: Optional[Dict[str, float]] = None
    
    def to_payload(self) -> Dict[str, Any]:
        """Convert to message payload."""
        return {
            'node_info': asdict(self.node_info),
            'service_capabilities': self.service_capabilities,
            'network_metrics': self.network_metrics
        }
    
    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "PeerDiscoveryMessage":
        """Create from message payload."""
        node_data = payload['node_info']
        node_info = Address(**node_data)
        return cls(
            node_info=node_info,
            service_capabilities=payload['service_capabilities'],
            network_metrics=payload.get('network_metrics')
        )


@dataclass
class DagBlockMessage:
    """Message wrapper that transports DAG blocks and optional certificates."""

    block: DagBlock
    certificate: Optional[QuorumCertificate] = None

    def to_payload(self) -> Dict[str, Any]:
        """Convert the DAG block message into a serialisable payload."""
        payload: Dict[str, Any] = {"block": self.block.to_payload()}
        if self.certificate is not None:
            payload["certificate"] = self.certificate.to_payload()
        return payload

    @staticmethod
    def from_payload(payload: Dict[str, Any]) -> "DagBlockMessage":
        """Recreate a message from its payload."""
        block = DagBlock.from_payload(payload["block"])  # type: ignore[arg-type]
        certificate_payload = payload.get("certificate")
        certificate = (
            QuorumCertificate.from_payload(certificate_payload) if certificate_payload is not None else None
        )
        return DagBlockMessage(block=block, certificate=certificate)


@dataclass
class DagVoteMessage:
    """Message that carries a vote for a DAG block."""

    block_id: UUID
    voter: str
    signature: Optional[str] = None

    def to_payload(self) -> Dict[str, Any]:
        """Convert the vote into a serialisable payload."""
        return {
            "block_id": str(self.block_id),
            "voter": self.voter,
            "signature": self.signature,
        }

    @staticmethod
    def from_payload(payload: Dict[str, Any]) -> "DagVoteMessage":
        """Recreate a vote message from its payload."""
        signature = payload.get("signature")
        return DagVoteMessage(
            block_id=UUID(str(payload["block_id"])),
            voter=str(payload["voter"]),
            signature=str(signature) if signature is not None else None,
        )



