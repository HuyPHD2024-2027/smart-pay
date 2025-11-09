"""Definitions for DAG blocks and certificates used by MeshPay authorities."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Dict, Tuple
from uuid import UUID, uuid4

from meshpay.types import MessagePayload


@dataclass(frozen=True)
class DagBlock:
    """Immutable representation of a DAG block emitted by an authority node."""

    author: str
    round: int
    parents: Tuple[UUID, ...]
    payload: MessagePayload
    block_id: UUID = field(default_factory=uuid4)
    timestamp: float = field(default_factory=lambda: time.time())
    digest: str = field(init=False)

    def __post_init__(self) -> None:
        """Compute the canonical digest immediately after initialisation."""
        object.__setattr__(self, "digest", self._compute_digest())

    def _compute_digest(self) -> str:
        """Return a SHA-256 digest over canonical block contents."""
        canonical = {
            "author": self.author,
            "block_id": str(self.block_id),
            "parents": [str(parent) for parent in self.parents],
            "payload": self.payload,
            "round": self.round,
            "timestamp": self.timestamp,
        }
        encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def to_payload(self) -> Dict[str, object]:
        """Convert the block to a serialisable payload for wire transmission."""
        return {
            "author": self.author,
            "block_id": str(self.block_id),
            "digest": self.digest,
            "parents": [str(parent) for parent in self.parents],
            "payload": self.payload,
            "round": self.round,
            "timestamp": self.timestamp,
        }

    @staticmethod
    def from_payload(payload: Dict[str, object]) -> "DagBlock":
        """Reconstruct a block from a payload previously produced by ``to_payload``."""
        parents = tuple(UUID(parent) for parent in payload["parents"])  # type: ignore[index]
        block = DagBlock(
            author=str(payload["author"]),
            round=int(payload["round"]),
            parents=parents,
            payload=payload["payload"],  # type: ignore[arg-type]
            block_id=UUID(str(payload["block_id"])),
            timestamp=float(payload["timestamp"]),
        )
        if block.digest != payload["digest"]:
            raise ValueError("Block digest mismatch – payload integrity compromised")
        return block


@dataclass(frozen=True)
class QuorumCertificate:
    """Aggregate of committee signatures attesting to a block's availability."""

    block_id: UUID
    round: int
    signatures: Dict[str, str]

    def to_payload(self) -> Dict[str, object]:
        """Convert the certificate to a serialisable payload."""
        return {
            "block_id": str(self.block_id),
            "round": self.round,
            "signatures": self.signatures,
        }

    @staticmethod
    def from_payload(payload: Dict[str, object]) -> "QuorumCertificate":
        """Recreate a certificate from a payload dictionary."""
        return QuorumCertificate(
            block_id=UUID(str(payload["block_id"])),
            round=int(payload["round"]),
            signatures={str(k): str(v) for k, v in dict(payload["signatures"]).items()},  # type: ignore[arg-type]
        )

