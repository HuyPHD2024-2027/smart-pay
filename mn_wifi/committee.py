"""Committee management with weighted voting based on authority performance.

This module introduces a Python counterpart to the original *FastPay* `committee.rs` but
augments it with *dynamic* voting power derived from each authority's recent
performance and network health.  The implementation is intentionally
self-contained so it can be reused by the Wi-Fi simulation without creating
circular imports to :pymod:`mn_wifi.authority`.

Key features
------------
1. **Base voting rights** – a static integer weight assigned at boot-strap.
2. **Performance score** – calculated from the metrics exposed by
   :py:meth:`mn_wifi.authority.WiFiAuthority.get_performance_stats`.
3. **Dynamic voting power** – the normalised product of base weight and
   performance score (score_i / Σ scores).
4. **Quorum check helpers** – convenient methods to compute thresholds and to
   test whether a set of signers represents a quorum.

The scoring function is kept *pluggable* so that operators can experiment with
alternative formulas without modifying the core logic.
"""

from __future__ import annotations

import math
from typing import Callable, Dict, Iterable, Mapping

# Type aliases ---------------------------------------------------------------------------
AuthorityName = str
PerformanceStats = Mapping[str, object]  # whatever `get_performance_stats()` returns


class Committee:  # pylint: disable=too-few-public-methods
    """Committee of authorities with weighted voting."""

    # ----------------------------------------------------------------------------------
    # Construction helpers
    # ----------------------------------------------------------------------------------

    def __init__(
        self,
        base_voting_rights: Mapping[AuthorityName, int],
        *,
        scoring_fn: Callable[[PerformanceStats], float] | None = None,
    ) -> None:
        """Create a new committee instance.

        Args:
            base_voting_rights: Mapping *authority-name → integer weight* – the
                traditional FastPay value (typically *1* for each member).
            scoring_fn: Optional custom function that maps *performance stats*
                to an intermediate **score**.  When *None* the default
                implementation defined in :pyfunc:`_default_scoring_fn` is
                used.
        """

        if not base_voting_rights:
            raise ValueError("Committee must contain at least one authority")

        self._base_rights: Dict[AuthorityName, int] = dict(base_voting_rights)
        self._scores: Dict[AuthorityName, float] = {name: 0.0 for name in base_voting_rights}
        self._scoring_fn = scoring_fn or _default_scoring_fn

        # Cached derived values ----------------------------------------------------
        self._voting_power: Dict[AuthorityName, float] = {}
        self._total_power: float = 0.0
        self.recalculate_powers()  # initialise

    # ----------------------------------------------------------------------------------
    # Public interface
    # ----------------------------------------------------------------------------------

    # Update ---------------------------------------------------------------------------

    def update_performance(self, name: AuthorityName, stats: PerformanceStats) -> None:
        """Update *name* performance and recompute voting powers.

        Silently ignores unknown authorities so that callers are not forced to
        validate membership ahead of time.
        """
        if name not in self._base_rights:
            return

        self._scores[name] = max(self._scoring_fn(stats), 0.0)
        self.recalculate_powers()

    # Query ---------------------------------------------------------------------------

    def power(self, name: AuthorityName) -> float:
        """Return current voting power for *name* (0.0 … 1.0)."""
        return self._voting_power.get(name, 0.0)

    def total_power(self) -> float:
        """Return the sum of all voting powers (should be **1.0**)."""
        return self._total_power

    def quorum_threshold(self, ratio: float = 2.0 / 3.0) -> float:
        """Compute the absolute power required for a *ratio* quorum.

        The default replicates the original *2⁄3 + 1* rule but in floating
        point (e.g. *0.667*).  Callers comparing *>=* should pass a value a
        touch **less** than the mathematical border (e.g. *0.667 - 1e-6*) to
        account for rounding.
        """
        return ratio

    def has_quorum(self, signers: Iterable[AuthorityName]) -> bool:
        """Return *True* when *signers* cumulatively hold ≥ quorum power."""
        power_sum = sum(self.power(a) for a in signers)
        return power_sum >= self.quorum_threshold()

    # ----------------------------------------------------------------------------------
    # Internal helpers
    # ----------------------------------------------------------------------------------

    def recalculate_powers(self) -> None:
        """Recalculate normalised voting powers based on current scores."""
        # 1. Combine base weight with performance score ---------------------------
        combined: Dict[AuthorityName, float] = {}
        for name, base_weight in self._base_rights.items():
            score = self._scores.get(name, 0.0)
            combined[name] = float(base_weight) * score

        # 2. Normalise so that Σ power = 1.0 (fallback to equal when all zero) ----
        total = sum(combined.values())
        if math.isclose(total, 0.0):
            equal = 1.0 / len(self._base_rights)
            self._voting_power = {name: equal for name in self._base_rights}
            self._total_power = 1.0
            return

        self._voting_power = {name: val / total for name, val in combined.items()}
        self._total_power = 1.0  # by definition


# --------------------------------------------------------------------------------------
# Default scoring function
# --------------------------------------------------------------------------------------

def _default_scoring_fn(stats: PerformanceStats) -> float:  # noqa: D401 – imperative name
    """Translate *performance stats* into a positive scalar **score**.

    The heuristic mirrors the logic showcased in the CLI: successful
    transactions bump the score, whereas errors lower it.  Network connectivity
    acts as a *multiplier* so that poorly connected nodes wield less power.
    """
    tx = int(stats.get("transaction_count", 0))
    errors = int(stats.get("error_count", 0))
    net = stats.get("network_metrics", {})
    connectivity = float(net.get("connectivity_ratio", 1.0))

    base = max(tx - errors, 0)
    return float(base) * connectivity 