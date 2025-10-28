"""Committee and quorum management for weighted voting system.

This module provides the Committee class that manages authority weights
and quorum calculations based on authority performance metrics.
"""

from __future__ import annotations

from typing import Dict, List, Set
from meshpay.types import AuthorityState


class Committee:
    """Manages authority weights and quorum calculations.
    
    The Committee class computes normalized weights for each authority based on
    their net performance (transaction_count - error_count) and provides methods
    to check if a given set of signers meets the weighted quorum threshold.
    """

    def __init__(
        self,
        authorities: List[AuthorityState],
        quorum_threshold: float = 2 / 3,
    ) -> None:
        """Initialize the Committee with a list of authorities.
        
        Args:
            authorities: List of AuthorityState objects representing committee members.
            quorum_threshold: Minimum weight fraction required for quorum (default: 2/3).
        """
        self.authorities = authorities
        self.quorum_threshold = quorum_threshold
        self._weight_cache: Dict[str, float] = {}

    def compute_weights(self) -> Dict[str, float]:
        """Compute normalized weights based on net performance.
        
        Weight calculation:
        1. Calculate net performance: max(tx_count - error_count, 0)
        2. Normalize so that sum of all weights = 1.0
        3. If all performances are zero, assign equal weights
        
        Returns:
            Dictionary mapping authority name to normalized weight.
        """
        weights: Dict[str, float] = {}
        
        # Calculate raw performance for each authority
        total_performance = 0.0
        for auth in self.authorities:
            net_performance = max(
                auth.transaction_count - auth.error_count,
                0
            )
            weights[auth.name] = float(net_performance)
            total_performance += net_performance
        
        # Normalize weights so they sum to 1.0
        if total_performance > 0:
            for auth_name in weights:
                weights[auth_name] = weights[auth_name] / total_performance
        else:
            # Equal weights if no transactions yet
            equal_weight = 1.0 / len(self.authorities) if self.authorities else 0.0
            for auth in self.authorities:
                weights[auth.name] = equal_weight
        
        self._weight_cache = weights
        return weights

    def get_authority_weight(self, authority_name: str) -> float:
        """Get the current weight for a specific authority.
        
        Args:
            authority_name: Name of the authority.
            
        Returns:
            Current normalized weight for the authority.
        """
        if not self._weight_cache:
            self.compute_weights()
        return self._weight_cache.get(authority_name, 0.0)

    def get_total_weight(self) -> float:
        """Return sum of all authority weights.
        
        Returns:
            Total weight (should be 1.0 after normalization).
        """
        if not self._weight_cache:
            self.compute_weights()
        return sum(self._weight_cache.values())

    def has_quorum(self, signer_weights: List[float]) -> bool:
        """Check if sum of signer weights meets threshold.
        
        Args:
            signer_weights: List of weights from signing authorities.
            
        Returns:
            True if weighted quorum is reached, False otherwise.
        """
        total_signer_weight = sum(signer_weights)
        return total_signer_weight >= self.quorum_threshold

    def has_quorum_by_names(self, signer_names: Set[str]) -> bool:
        """Check if a set of authority names meets the quorum threshold.
        
        Args:
            signer_names: Set of authority names that have signed.
            
        Returns:
            True if weighted quorum is reached, False otherwise.
        """
        if not self._weight_cache:
            self.compute_weights()
        
        signer_weights = [
            self._weight_cache.get(name, 0.0)
            for name in signer_names
        ]
        return self.has_quorum(signer_weights)

    def update_authority_performance(
        self,
        authority_name: str,
        transaction_count: int,
        error_count: int,
    ) -> None:
        """Update performance metrics for a specific authority.
        
        Args:
            authority_name: Name of the authority to update.
            transaction_count: New transaction count.
            error_count: New error count.
        """
        for auth in self.authorities:
            if auth.name == authority_name:
                auth.transaction_count = transaction_count
                auth.error_count = error_count
                auth.voting_weight = max(transaction_count - error_count, 0)
                break
        
        # Invalidate cache to force recomputation
        self._weight_cache = {}

    def get_committee_info(self) -> Dict[str, Dict[str, float]]:
        """Get detailed information about all committee members.
        
        Returns:
            Dictionary with authority name as key and performance metrics as value.
        """
        if not self._weight_cache:
            self.compute_weights()
        
        info: Dict[str, Dict[str, float]] = {}
        for auth in self.authorities:
            info[auth.name] = {
                "transaction_count": float(auth.transaction_count),
                "error_count": float(auth.error_count),
                "net_performance": float(auth.voting_weight),
                "normalized_weight": self._weight_cache.get(auth.name, 0.0),
            }
        return info


__all__ = ["Committee"]

