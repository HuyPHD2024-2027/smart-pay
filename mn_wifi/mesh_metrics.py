"""Mesh network performance metrics for MeshPay simulations.

This module provides a lightweight, thread-safe aggregator that records
transaction start/end events and computes latency statistics (min/avg/p50/p95/
p99/max), throughput (TPS), success rate, and byte counters. It is transport-
agnostic and can be used by benchmark runners or integrated into nodes.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass
from statistics import mean
from typing import Dict, List, Optional, Tuple
from uuid import UUID


@dataclass
class SummaryStats:
    """Aggregate statistics over a set of latency samples.

    All latency values are expressed in milliseconds.
    """

    count: int
    min_ms: float
    avg_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float


class MeshMetrics:
    """Thread-safe metrics aggregator for mesh transaction benchmarking.

    Typical usage:
    - Call :meth:`record_tx_start` when issuing a transaction.
    - Call :meth:`record_tx_success` or :meth:`record_tx_failure` when it
      completes (or fails). The aggregator will compute latency from the
      recorded start time.
    - Optionally record "standalone" latency samples using
      :meth:`record_latency_sample_ms` for scenarios where start/end hooks are
      inconvenient.
    - Call :meth:`snapshot` at any time to fetch a dictionary ready for JSON
      serialization.
    """

    def __init__(self, *, run_label: str = "", start_time_s: Optional[float] = None) -> None:
        """Create a new aggregator.

        Args:
            run_label: Optional identifier included in snapshots.
            start_time_s: Optional explicit start timestamp; if omitted the
                current time is used.
        """
        self._lock = threading.Lock()
        self._run_label = run_label
        self._t0 = start_time_s if start_time_s is not None else time.time()

        # Per-transaction bookkeeping
        self._tx_start_time_s: Dict[UUID, float] = {}
        self._latency_samples_ms: List[float] = []

        # Counters
        self._started = 0
        self._succeeded = 0
        self._failed = 0
        self._bytes_sent = 0
        self._bytes_received = 0
        
        # Weighted voting metrics
        self._quorum_latencies_ms: List[float] = []
        self._authority_weights: Dict[str, List[float]] = {}  # authority_name -> list of weights over time

    # ----------------------------------------------------------------------------------
    # Recording helpers
    # ----------------------------------------------------------------------------------
    def record_tx_start(self, tx_id: UUID, *, bytes_sent: int = 0) -> None:
        """Record the start of a transaction and optional bytes sent.

        Args:
            tx_id: Stable transaction identifier.
            bytes_sent: Optional number of bytes sent when issuing the request.
        """
        now = time.time()
        with self._lock:
            self._tx_start_time_s[tx_id] = now
            self._started += 1
            self._bytes_sent += max(0, int(bytes_sent))

    def record_tx_success(self, tx_id: UUID, *, bytes_received: int = 0) -> None:
        """Record a successful completion and derive latency if possible.

        Args:
            tx_id: Transaction identifier used in :meth:`record_tx_start`.
            bytes_received: Optional number of bytes received in the response.
        """
        now = time.time()
        with self._lock:
            t0 = self._tx_start_time_s.pop(tx_id, None)
            if t0 is not None:
                latency_ms = (now - t0) * 1000.0
                self._latency_samples_ms.append(latency_ms)
            self._succeeded += 1
            self._bytes_received += max(0, int(bytes_received))

    def record_tx_failure(self, tx_id: Optional[UUID] = None) -> None:
        """Record a failed transaction.

        If ``tx_id`` was previously registered via :meth:`record_tx_start`, the
        pending timer is discarded.
        """
        with self._lock:
            if tx_id is not None:
                self._tx_start_time_s.pop(tx_id, None)
            self._failed += 1

    def record_latency_sample_ms(self, latency_ms: float) -> None:
        """Record a standalone latency measurement in milliseconds."""
        with self._lock:
            self._latency_samples_ms.append(float(latency_ms))

    def add_bytes(self, *, sent: int = 0, received: int = 0) -> None:
        """Increase byte counters without affecting transaction counters."""
        with self._lock:
            self._bytes_sent += max(0, int(sent))
            self._bytes_received += max(0, int(received))

    def record_quorum_latency(self, tx_id: UUID, latency_ms: float) -> None:
        """Record time to reach 2/3 weighted quorum for a transaction.
        
        Args:
            tx_id: Transaction identifier.
            latency_ms: Latency in milliseconds from transaction start to quorum.
        """
        with self._lock:
            self._quorum_latencies_ms.append(float(latency_ms))

    def record_authority_weight(self, authority_name: str, weight: float) -> None:
        """Record an authority's voting weight at a point in time.
        
        Args:
            authority_name: Name of the authority.
            weight: Normalized voting weight (0.0 to 1.0).
        """
        with self._lock:
            if authority_name not in self._authority_weights:
                self._authority_weights[authority_name] = []
            self._authority_weights[authority_name].append(float(weight))

    def get_average_quorum_latency(self) -> float:
        """Return average latency to reach weighted quorum.
        
        Returns:
            Average quorum latency in milliseconds, or 0.0 if no samples.
        """
        with self._lock:
            if not self._quorum_latencies_ms:
                return 0.0
            return mean(self._quorum_latencies_ms)

    def get_quorum_latency_stats(self) -> SummaryStats:
        """Get detailed statistics for quorum latency.
        
        Returns:
            SummaryStats object with quorum latency percentiles.
        """
        with self._lock:
            samples = list(self._quorum_latencies_ms)
        if not samples:
            return SummaryStats(count=0, min_ms=0.0, avg_ms=0.0, p50_ms=0.0, p95_ms=0.0, p99_ms=0.0, max_ms=0.0)
        samples.sort()
        return SummaryStats(
            count=len(samples),
            min_ms=samples[0],
            avg_ms=mean(samples),
            p50_ms=self._percentile(samples, 50),
            p95_ms=self._percentile(samples, 95),
            p99_ms=self._percentile(samples, 99),
            max_ms=samples[-1],
        )

    def get_authority_weights_summary(self) -> Dict[str, Dict[str, float]]:
        """Get summary statistics for each authority's voting weights.
        
        Returns:
            Dictionary mapping authority name to weight statistics (avg, min, max).
        """
        with self._lock:
            weights_copy = {k: list(v) for k, v in self._authority_weights.items()}
        
        summary: Dict[str, Dict[str, float]] = {}
        for auth_name, weights in weights_copy.items():
            if weights:
                summary[auth_name] = {
                    "avg_weight": mean(weights),
                    "min_weight": min(weights),
                    "max_weight": max(weights),
                    "final_weight": weights[-1],
                    "samples": float(len(weights)),
                }
            else:
                summary[auth_name] = {
                    "avg_weight": 0.0,
                    "min_weight": 0.0,
                    "max_weight": 0.0,
                    "final_weight": 0.0,
                    "samples": 0.0,
                }
        return summary

    # ----------------------------------------------------------------------------------
    # Computation and export
    # ----------------------------------------------------------------------------------
    @staticmethod
    def _percentile(sorted_values: List[float], p: float) -> float:
        if not sorted_values:
            return 0.0
        if p <= 0:
            return sorted_values[0]
        if p >= 100:
            return sorted_values[-1]
        k = (len(sorted_values) - 1) * (p / 100.0)
        f = int(k)
        c = min(f + 1, len(sorted_values) - 1)
        if f == c:
            return sorted_values[f]
        d0 = sorted_values[f] * (c - k)
        d1 = sorted_values[c] * (k - f)
        return d0 + d1

    def _latency_stats(self) -> SummaryStats:
        with self._lock:
            samples = list(self._latency_samples_ms)
        if not samples:
            return SummaryStats(count=0, min_ms=0.0, avg_ms=0.0, p50_ms=0.0, p95_ms=0.0, p99_ms=0.0, max_ms=0.0)
        samples.sort()
        return SummaryStats(
            count=len(samples),
            min_ms=samples[0],
            avg_ms=mean(samples),
            p50_ms=self._percentile(samples, 50),
            p95_ms=self._percentile(samples, 95),
            p99_ms=self._percentile(samples, 99),
            max_ms=samples[-1],
        )

    def elapsed_s(self) -> float:
        """Return seconds elapsed since aggregator start."""
        return max(0.0, time.time() - self._t0)

    def snapshot(self, *, explicit_duration_s: Optional[float] = None) -> Dict[str, float]:
        """Return a JSON-serializable snapshot of all metrics.

        Args:
            explicit_duration_s: Optional explicit *wall time* for computing TPS.
        """
        duration_s = explicit_duration_s if explicit_duration_s is not None else self.elapsed_s()
        latency = self._latency_stats()
        quorum_latency = self.get_quorum_latency_stats()
        authority_weights = self.get_authority_weights_summary()
        
        with self._lock:
            started = self._started
            succeeded = self._succeeded
            failed = self._failed
            bytes_sent = self._bytes_sent
            bytes_received = self._bytes_received
            
        throughput_tps = (succeeded / duration_s) if duration_s > 0 else 0.0
        tx_bps = (bytes_sent * 8.0 / duration_s) if duration_s > 0 else 0.0
        rx_bps = (bytes_received * 8.0 / duration_s) if duration_s > 0 else 0.0
        success_rate = (succeeded / started) * 100.0 if started > 0 else 0.0
        
        result: Dict[str, float] = {
            "run_label": self._run_label,
            "duration_s": duration_s,
            "transactions_started": float(started),
            "transactions_succeeded": float(succeeded),
            "transactions_failed": float(failed),
            "success_rate_pct": success_rate,
            "throughput_tps": throughput_tps,
            "network_tx_bps": tx_bps,
            "network_rx_bps": rx_bps,
            "min_latency_ms": latency.min_ms,
            "avg_latency_ms": latency.avg_ms,
            "p50_latency_ms": latency.p50_ms,
            "p95_latency_ms": latency.p95_ms,
            "p99_latency_ms": latency.p99_ms,
            "max_latency_ms": latency.max_ms,
            "latency_samples": float(latency.count),
            "bytes_sent": float(bytes_sent),
            "bytes_received": float(bytes_received),
            # Weighted voting metrics
            "average_quorum_latency_ms": quorum_latency.avg_ms,
            "p50_quorum_latency_ms": quorum_latency.p50_ms,
            "p95_quorum_latency_ms": quorum_latency.p95_ms,
            "p99_quorum_latency_ms": quorum_latency.p99_ms,
            "quorum_latency_samples": float(quorum_latency.count),
            "authority_weights": authority_weights,  # type: ignore[dict-item]
        }
        return result

    def to_json(self, *, explicit_duration_s: Optional[float] = None) -> str:
        """Return a JSON string with the current snapshot."""
        return json.dumps(self.snapshot(explicit_duration_s=explicit_duration_s), indent=2)

    def to_csv_row(self, *, explicit_duration_s: Optional[float] = None) -> Tuple[str, ...]:
        """Return a single CSV row with summary values."""
        snap = self.snapshot(explicit_duration_s=explicit_duration_s)
        return (
            str(snap["run_label"]),
            f"{snap['duration_s']:.3f}",
            f"{snap['transactions_started']:.0f}",
            f"{snap['transactions_succeeded']:.0f}",
            f"{snap['transactions_failed']:.0f}",
            f"{snap['success_rate_pct']:.2f}",
            f"{snap['throughput_tps']:.3f}",
            f"{snap['network_tx_bps']:.2f}",
            f"{snap['network_rx_bps']:.2f}",
            f"{snap['min_latency_ms']:.2f}",
            f"{snap['avg_latency_ms']:.2f}",
            f"{snap['p50_latency_ms']:.2f}",
            f"{snap['p95_latency_ms']:.2f}",
            f"{snap['p99_latency_ms']:.2f}",
            f"{snap['max_latency_ms']:.2f}",
            f"{snap['latency_samples']:.0f}",
            f"{snap['bytes_sent']:.0f}",
            f"{snap['bytes_received']:.0f}",
        )

    @staticmethod
    def csv_header() -> Tuple[str, ...]:
        """Return the CSV header tuple matching :meth:`to_csv_row`."""
        return (
            "run_label",
            "duration_s",
            "transactions_started",
            "transactions_succeeded",
            "transactions_failed",
            "success_rate_pct",
            "throughput_tps",
            "network_tx_bps",
            "network_rx_bps",
            "min_latency_ms",
            "avg_latency_ms",
            "p50_latency_ms",
            "p95_latency_ms",
            "p99_latency_ms",
            "max_latency_ms",
            "latency_samples",
            "bytes_sent",
            "bytes_received",
        )

    def get_latency_samples_ms(self) -> List[float]:
        """Return a copy of recorded latency samples in milliseconds.

        The returned list can be used to build ECDF/CDF plots or histograms.
        """
        with self._lock:
            return list(self._latency_samples_ms)
