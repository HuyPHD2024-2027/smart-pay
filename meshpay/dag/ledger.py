"""In-memory DAG management utilities for experimental consensus logic."""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from typing import Deque, Dict, Iterable, List, Optional, Set, Tuple
from uuid import UUID

from meshpay.dag.block import DagBlock, QuorumCertificate

LOGGER = logging.getLogger(__name__)


class DagLedger:
    """Maintain a causal DAG of proposals and track quorum progress."""

    def __init__(self, quorum_size: int) -> None:
        """Initialise the ledger with the given quorum threshold."""
        if quorum_size <= 0:
            raise ValueError("quorum_size must be positive")
        self._quorum_size = quorum_size
        self._blocks: Dict[UUID, DagBlock] = {}
        self._children: Dict[UUID, Set[UUID]] = defaultdict(set)
        self._votes: Dict[UUID, Dict[str, str]] = defaultdict(dict)
        self._committed: Set[UUID] = set()
        self._genesis = self._create_genesis_block()
        self._frontier: Set[UUID] = {self._genesis.block_id}

    @property
    def genesis(self) -> DagBlock:
        """Return the immutable genesis block."""
        return self._genesis

    @property
    def quorum_size(self) -> int:
        """Return the number of votes required to finalise a block."""
        return self._quorum_size

    def _create_genesis_block(self) -> DagBlock:
        """Create and register a genesis block for the DAG."""
        genesis = DagBlock(author="genesis", round=0, parents=tuple(), payload={"kind": "genesis"})
        self._blocks[genesis.block_id] = genesis
        self._committed.add(genesis.block_id)
        return genesis

    def get_block(self, block_id: UUID) -> Optional[DagBlock]:
        """Return the block with the provided identifier, if known."""
        return self._blocks.get(block_id)

    def frontier(self) -> Tuple[UUID, ...]:
        """Return the tuple of block identifiers currently at the DAG frontier."""
        return tuple(self._frontier)

    def create_block(self, author: str, payload: Dict[str, object], parents: Optional[Iterable[UUID]] = None) -> DagBlock:
        """Create a block referencing the provided parents (or the current frontier)."""
        parent_ids = tuple(parents) if parents is not None else self.frontier()
        block = DagBlock(author=author, round=self._next_round(parent_ids), parents=parent_ids, payload=payload)
        return block

    def _next_round(self, parent_ids: Tuple[UUID, ...]) -> int:
        """Determine the round number for a new block relative to its parents."""
        if not parent_ids:
            return 1
        return max(self._blocks[parent_id].round for parent_id in parent_ids) + 1

    def add_block(self, block: DagBlock) -> None:
        """Add a new block to the DAG, updating frontier bookkeeping."""
        if block.block_id in self._blocks:
            LOGGER.debug("Block %s already present; ignoring duplicate add", block.block_id)
            return
        for parent in block.parents:
            if parent not in self._blocks:
                raise KeyError(f"Parent block {parent} unknown; cannot attach child")
        self._blocks[block.block_id] = block
        if block.parents:
            for parent in block.parents:
                self._children[parent].add(block.block_id)
                self._frontier.discard(parent)
        self._frontier.add(block.block_id)

    def record_vote(self, block_id: UUID, voter: str, signature: str = "") -> int:
        """Record a vote for a block and return the updated vote count."""
        if block_id not in self._blocks:
            raise KeyError(f"Cannot record vote – unknown block {block_id}")
        votes = self._votes[block_id]
        votes[voter] = signature
        LOGGER.debug("Block %s now has %s votes", block_id, len(votes))
        return len(votes)

    def record_certificate(self, certificate: QuorumCertificate) -> None:
        """Populate vote records from a quorum certificate."""
        if certificate.block_id not in self._blocks:
            raise KeyError(f"Cannot apply certificate – unknown block {certificate.block_id}")
        self._votes[certificate.block_id].update(certificate.signatures)

    def has_quorum(self, block_id: UUID) -> bool:
        """Return True if the block has gathered a quorum of votes."""
        return len(self._votes[block_id]) >= self._quorum_size

    def commit_ready_blocks(self) -> List[DagBlock]:
        """Commit and return blocks whose parents are committed and have quorum votes."""
        committed_in_round: List[DagBlock] = []
        queue: Deque[UUID] = deque(sorted(self._blocks.keys(), key=lambda bid: self._blocks[bid].round))
        while queue:
            block_id = queue.popleft()
            if block_id in self._committed:
                continue
            block = self._blocks[block_id]
            if not self.has_quorum(block_id):
                continue
            if any(parent not in self._committed for parent in block.parents):
                continue
            self._committed.add(block_id)
            committed_in_round.append(block)
        return committed_in_round

    def is_committed(self, block_id: UUID) -> bool:
        """Return True if the block has been committed."""
        return block_id in self._committed

