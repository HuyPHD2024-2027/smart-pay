"""Tests for MeshMetrics aggregator.

These tests validate percentile calculations, TPS/success rates, and JSON/CSV
serialization. They use deterministic timings to avoid flakiness.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from mn_wifi.mesh_metrics import MeshMetrics

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture
    from _pytest.fixtures import FixtureRequest
    from _pytest.logging import LogCaptureFixture
    from _pytest.monkeypatch import MonkeyPatch
    from pytest_mock.plugin import MockerFixture


def test_latency_percentiles_and_snapshot(monkeypatch: "MonkeyPatch") -> None:
    """Compute percentiles accurately for a small sample set."""
    # Freeze time progression by controlling time.time()
    base = 1_700_000_000.0
    now = base

    def fake_time() -> float:
        nonlocal now
        return now

    monkeypatch.setattr(time, "time", fake_time)

    m = MeshMetrics(run_label="test", start_time_s=base)

    # Record 5 transactions with known durations (ms): 10, 20, 30, 40, 50
    durations_ms = [10, 20, 30, 40, 50]
    for d in durations_ms:
        tx = uuid4()
        m.record_tx_start(tx)
        now += d / 1000.0
        m.record_tx_success(tx)

    snap = m.snapshot()

    assert snap["transactions_started"] == 5
    assert snap["transactions_succeeded"] == 5
    assert snap["transactions_failed"] == 0
    assert pytest.approx(snap["min_latency_ms"], rel=1e-3) == 10
    assert pytest.approx(snap["avg_latency_ms"], rel=1e-3) == 30
    assert pytest.approx(snap["p50_latency_ms"], rel=1e-3) == 30
    # With linear interpolation over 5 samples, p95 lies between 40 and 50
    assert pytest.approx(snap["p95_latency_ms"], rel=1e-3) == 48.0
    assert pytest.approx(snap["max_latency_ms"], rel=1e-3) == 50
    assert snap["latency_samples"] == 5


def test_tps_and_success_rate(monkeypatch: "MonkeyPatch") -> None:
    """TPS uses explicit duration; success rate handles division by zero."""
    base = 1_700_100_000.0
    m = MeshMetrics(run_label="rate", start_time_s=base)

    for _ in range(4):
        tx = uuid4()
        m.record_tx_start(tx)
        m.record_tx_success(tx)
    # One failed transaction that was started but not completed
    fail_tx = uuid4()
    m.record_tx_start(fail_tx)
    m.record_tx_failure(fail_tx)

    # Explicit duration 2 seconds → 4 successes / 2s = 2 TPS
    snap = m.snapshot(explicit_duration_s=2.0)
    assert pytest.approx(snap["throughput_tps"], rel=1e-6) == 2.0
    assert pytest.approx(snap["success_rate_pct"], rel=1e-6) == 80.0


def test_json_and_csv_export() -> None:
    """Ensure exports are well-formed and consistent."""
    m = MeshMetrics(run_label="export")
    for _ in range(3):
        tx = uuid4()
        m.record_tx_start(tx)
        m.record_tx_success(tx)

    js = m.to_json(explicit_duration_s=1.0)
    data = json.loads(js)
    assert "throughput_tps" in data

    header = MeshMetrics.csv_header()
    row = m.to_csv_row(explicit_duration_s=1.0)
    assert len(header) == len(row)
    # CSV now includes tx/rx bps fields
    assert "network_tx_bps" in header
    assert "network_rx_bps" in header
