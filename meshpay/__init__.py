"""MeshPay namespace package.

This package provides a clean, future-proof structure for the offline payment
components (FastPay/MeshPay) without moving existing implementation files yet.

The modules here re-export symbols from their current locations under
``mn_wifi`` so downstream code can gradually migrate to the new, clearer API:

  - mn_wifi.meshpay.domain.types
  - mn_wifi.meshpay.nodes.{authority,client}
  - mn_wifi.meshpay.messaging.messages
  - mn_wifi.meshpay.services.{blockchain,config}
  - mn_wifi.meshpay.api.{bridge,gateway}

"""

from __future__ import annotations

# Public API re-exports adapted to the new flat layout ------------------------

# Domain types
from .types import (  # noqa: F401
    Address,
    NodeType,
    TransactionStatus,
    TransferOrder,
    SignedTransferOrder,
    ConfirmationOrder,
    TokenBalance,
    AccountOffchainState,
    AuthorityState,
    NetworkMetrics,
    ClientState,
    GatewayState,
    KeyPair,
    AuthorityName,
)

# Messaging DTOs
from .messages import (  # noqa: F401
    Message,
    MessageType,
    TransferRequestMessage,
    TransferResponseMessage,
    ConfirmationRequestMessage,
    SyncRequestMessage,
    PeerDiscoveryMessage,
)

# Transports
from .transport import NetworkTransport, TransportKind  # noqa: F401
from .transport import TCPTransport  # noqa: F401
from .transport import UDPTransport  # noqa: F401
from .transport import WiFiDirectTransport  # noqa: F401

# Nodes and HTTP API
from .nodes.authority import WiFiAuthority  # noqa: F401
from .nodes.client import Client  # noqa: F401
from .api.bridge import Bridge  # noqa: F401
from .api.gateway import Gateway  # noqa: F401

# Loggers (optional convenience)
from .logger.authorityLogger import AuthorityLogger  # noqa: F401
from .logger.clientLogger import ClientLogger  # noqa: F401
from .logger.bridgeLogger import BridgeLogger  # noqa: F401

__all__ = [
    # core
    "Address",
    "NodeType",
    "TransactionStatus",
    "TransferOrder",
    "SignedTransferOrder",
    "ConfirmationOrder",
    "TokenBalance",
    "AccountOffchainState",
    "AuthorityState",
    "NetworkMetrics",
    "ClientState",
    "GatewayState",
    "KeyPair",
    "AuthorityName",
    "Message",
    "MessageType",
    "TransferRequestMessage",
    "TransferResponseMessage",
    "ConfirmationRequestMessage",
    "SyncRequestMessage",
    "PeerDiscoveryMessage",
    # infra
    "NetworkTransport",
    "TransportKind",
    "TCPTransport",
    "UDPTransport",
    "WiFiDirectTransport",
    # app
    "WiFiAuthority",
    "Client",
    "Bridge",
    "Gateway",
    # loggers
    "AuthorityLogger",
    "ClientLogger",
    "BridgeLogger",
]


