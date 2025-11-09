"""Tests for the MeshPay DAG ledger utilities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from meshpay.dag import DagLedger, QuorumCertificate

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture
    from _pytest.fixtures import FixtureRequest
    from _pytest.logging import LogCaptureFixture
    from _pytest.monkeypatch import MonkeyPatch
    from pytest_mock.plugin import MockerFixture


def test_dag_ledger_frontier_updates() -> None:
    """Ensure adding a block updates the DAG frontier."""
    ledger = DagLedger(quorum_size=2)
    block = ledger.create_block(author="auth1", payload={"kind": "unit_test"})
    ledger.add_block(block)

    frontier = ledger.frontier()
    assert block.block_id in frontier
    assert ledger.genesis.block_id not in frontier


def test_dag_ledger_commits_block_with_quorum() -> None:
    """Verify that a block commits once the quorum threshold is met."""
    ledger = DagLedger(quorum_size=2)
    block = ledger.create_block(author="auth1", payload={"kind": "commit_test"})
    ledger.add_block(block)

    ledger.record_vote(block.block_id, "auth1")
    assert ledger.commit_ready_blocks() == []

    ledger.record_vote(block.block_id, "auth2")
    committed = ledger.commit_ready_blocks()

    assert committed and committed[0].block_id == block.block_id
    assert ledger.is_committed(block.block_id)


def test_dag_ledger_accepts_quorum_certificate() -> None:
    """Ensure quorum certificates populate vote records."""
    ledger = DagLedger(quorum_size=2)
    block = ledger.create_block(author="auth1", payload={"kind": "certificate_test"})
    ledger.add_block(block)

    certificate = QuorumCertificate(
        block_id=block.block_id,
        round=block.round,
        signatures={"auth1": "sig1", "auth2": "sig2"},
    )

    ledger.record_certificate(certificate)
    committed = ledger.commit_ready_blocks()

    assert committed and committed[0].block_id == block.block_id
    assert ledger.has_quorum(block.block_id)
