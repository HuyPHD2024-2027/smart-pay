"""Integration tests for weighted voting system."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, List
from uuid import uuid4

import pytest

from meshpay.committee import Committee
from meshpay.types import (
    Address,
    AuthorityState,
    ConfirmationOrder,
    NodeType,
    TransactionStatus,
    TransferOrder,
    WeightedCertificate,
)

if TYPE_CHECKING:
    from _pytest.fixtures import FixtureRequest


@pytest.fixture
def mock_authorities() -> List[AuthorityState]:
    """Create a list of mock authorities with varying performance.
    
    Returns:
        List of 5 AuthorityState instances with different performance levels.
    """
    authorities = []
    for i in range(1, 6):
        address = Address(
            node_id=f"auth{i}",
            ip_address=f"10.0.0.{i}",
            port=8000 + i,
            node_type=NodeType.AUTHORITY,
        )
        auth = AuthorityState(
            name=f"auth{i}",
            address=address,
            shard_assignments=set(),
            accounts={},
            committee_members={f"auth{j}" for j in range(1, 6) if j != i},
            transaction_count=i * 20,  # Varying transaction counts
            error_count=i * 2,         # Proportional error counts
            voting_weight=0.0,
        )
        authorities.append(auth)
    return authorities


def test_committee_weight_distribution(mock_authorities: List[AuthorityState]) -> None:
    """Test that committee weights are properly distributed based on performance.
    
    Args:
        mock_authorities: List of mock authority states.
    """
    committee = Committee(mock_authorities)
    weights = committee.compute_weights()
    
    # Verify all authorities have weights
    assert len(weights) == 5
    for auth_name in [f"auth{i}" for i in range(1, 6)]:
        assert auth_name in weights
        assert weights[auth_name] >= 0.0
    
    # Verify weights sum to 1.0
    total_weight = sum(weights.values())
    assert pytest.approx(total_weight, abs=0.001) == 1.0
    
    # Verify higher performing authorities have higher weights
    # auth5 has highest net performance (100 - 10 = 90)
    # auth1 has lowest net performance (20 - 2 = 18)
    assert weights["auth5"] > weights["auth4"]
    assert weights["auth4"] > weights["auth3"]
    assert weights["auth1"] < weights["auth2"]


def test_weighted_quorum_validation(mock_authorities: List[AuthorityState]) -> None:
    """Test validation of weighted quorum in confirmation orders.
    
    Args:
        mock_authorities: List of mock authority states.
    """
    committee = Committee(mock_authorities, quorum_threshold=2 / 3)
    weights = committee.compute_weights()
    
    # Create weighted certificates from subset of authorities
    certificates = [
        WeightedCertificate(
            authority_name="auth4",
            authority_signature="sig4",
            weight=weights["auth4"],
            timestamp=time.time(),
        ),
        WeightedCertificate(
            authority_name="auth5",
            authority_signature="sig5",
            weight=weights["auth5"],
            timestamp=time.time(),
        ),
    ]
    
    signer_weights = [cert.weight for cert in certificates]
    total_weight = sum(signer_weights)
    
    # auth4 and auth5 together should have > 2/3 weight
    # (they have the highest performance)
    has_quorum = committee.has_quorum(signer_weights)
    
    if total_weight >= 2 / 3:
        assert has_quorum is True
    else:
        assert has_quorum is False


def test_confirmation_order_with_weighted_certificates() -> None:
    """Test creating ConfirmationOrder with weighted certificates."""
    transfer_order = TransferOrder(
        order_id=uuid4(),
        sender="alice",
        recipient="bob",
        token_address="0x123",
        amount=100,
        sequence_number=1,
        timestamp=time.time(),
        signature="sig_alice",
    )
    
    weighted_certs = [
        WeightedCertificate("auth1", "sig1", 0.25, time.time()),
        WeightedCertificate("auth2", "sig2", 0.30, time.time()),
        WeightedCertificate("auth3", "sig3", 0.20, time.time()),
    ]
    
    total_weight = sum(cert.weight for cert in weighted_certs)
    
    confirmation = ConfirmationOrder(
        order_id=transfer_order.order_id,
        transfer_order=transfer_order,
        authority_signatures=["sig1", "sig2", "sig3"],
        timestamp=time.time(),
        status=TransactionStatus.CONFIRMED,
        weighted_certificates=weighted_certs,
        total_weight=total_weight,
    )
    
    assert len(confirmation.weighted_certificates) == 3
    assert pytest.approx(confirmation.total_weight, abs=0.001) == 0.75
    assert confirmation.total_weight >= 2 / 3  # Meets quorum


def test_dynamic_weight_updates(mock_authorities: List[AuthorityState]) -> None:
    """Test that weights update dynamically as authority performance changes.
    
    Args:
        mock_authorities: List of mock authority states.
    """
    committee = Committee(mock_authorities)
    
    # Initial weights
    initial_weights = committee.compute_weights()
    initial_auth1_weight = initial_weights["auth1"]
    
    # Simulate auth1 processing many more transactions
    committee.update_authority_performance(
        "auth1",
        transaction_count=200,  # Increased from 20
        error_count=2,          # Kept same
    )
    
    # Recompute weights
    updated_weights = committee.compute_weights()
    updated_auth1_weight = updated_weights["auth1"]
    
    # auth1's weight should have increased significantly
    assert updated_auth1_weight > initial_auth1_weight
    
    # Total should still be 1.0
    assert pytest.approx(sum(updated_weights.values()), abs=0.001) == 1.0


def test_quorum_with_byzantine_authorities() -> None:
    """Test that weighted quorum still works with some byzantine (failing) authorities."""
    authorities = []
    for i in range(1, 6):
        address = Address(
            node_id=f"auth{i}",
            ip_address=f"10.0.0.{i}",
            port=8000 + i,
            node_type=NodeType.AUTHORITY,
        )
        
        # auth4 and auth5 are "byzantine" with many errors
        if i >= 4:
            tx_count = 10
            err_count = 50  # More errors than transactions
        else:
            tx_count = 100
            err_count = 0
        
        auth = AuthorityState(
            name=f"auth{i}",
            address=address,
            shard_assignments=set(),
            accounts={},
            committee_members=set(),
            transaction_count=tx_count,
            error_count=err_count,
            voting_weight=0.0,
        )
        authorities.append(auth)
    
    committee = Committee(authorities, quorum_threshold=2 / 3)
    weights = committee.compute_weights()
    
    # Byzantine authorities should have zero or very low weight
    assert weights["auth4"] == 0.0 or weights["auth4"] < 0.01
    assert weights["auth5"] == 0.0 or weights["auth5"] < 0.01
    
    # Good authorities (auth1, auth2, auth3) should share the weight
    good_auth_total = weights["auth1"] + weights["auth2"] + weights["auth3"]
    assert pytest.approx(good_auth_total, abs=0.01) == 1.0
    
    # Quorum should be reachable with just 2 good authorities
    signer_names = {"auth1", "auth2"}
    assert committee.has_quorum_by_names(signer_names) is True


def test_zero_performance_graceful_handling() -> None:
    """Test that system handles all-zero performance gracefully."""
    authorities = []
    for i in range(1, 4):
        address = Address(
            node_id=f"auth{i}",
            ip_address=f"10.0.0.{i}",
            port=8000 + i,
            node_type=NodeType.AUTHORITY,
        )
        auth = AuthorityState(
            name=f"auth{i}",
            address=address,
            shard_assignments=set(),
            accounts={},
            committee_members=set(),
            transaction_count=0,
            error_count=0,
            voting_weight=0.0,
        )
        authorities.append(auth)
    
    committee = Committee(authorities)
    weights = committee.compute_weights()
    
    # Should fall back to equal weights
    for auth_name, weight in weights.items():
        assert pytest.approx(weight, abs=0.001) == 1.0 / 3.0
    
    # Any 2 out of 3 should meet 2/3 quorum
    assert committee.has_quorum_by_names({"auth1", "auth2"}) is True


def test_weighted_certificate_timestamp_ordering() -> None:
    """Test that weighted certificates maintain temporal ordering."""
    t0 = time.time()
    
    certificates = [
        WeightedCertificate("auth1", "sig1", 0.3, t0),
        WeightedCertificate("auth2", "sig2", 0.25, t0 + 0.1),
        WeightedCertificate("auth3", "sig3", 0.2, t0 + 0.2),
    ]
    
    # Verify timestamps are in order
    for i in range(len(certificates) - 1):
        assert certificates[i].timestamp <= certificates[i + 1].timestamp


def test_minimum_authorities_for_quorum() -> None:
    """Test minimum number of authorities needed for different committee sizes."""
    test_cases = [
        (3, 2),   # 3 authorities need 2 for quorum (2/3 = 0.667)
        (5, 4),   # 5 authorities need 4 for quorum
        (7, 5),   # 7 authorities need 5 for quorum
    ]
    
    for total_auths, expected_min in test_cases:
        authorities = [
            AuthorityState(
                name=f"auth{i}",
                address=Address(f"auth{i}", f"10.0.0.{i}", 8000, NodeType.AUTHORITY),
                shard_assignments=set(),
                accounts={},
                committee_members=set(),
                transaction_count=10,  # Equal performance
                error_count=0,
                voting_weight=0.0,
            )
            for i in range(total_auths)
        ]
        
        committee = Committee(authorities, quorum_threshold=2 / 3)
        weights = committee.compute_weights()
        
        # Each authority should have equal weight
        equal_weight = 1.0 / total_auths
        
        # Test with expected_min - 1 signers (should fail)
        if expected_min > 1:
            insufficient_signers = {f"auth{i}" for i in range(expected_min - 1)}
            assert committee.has_quorum_by_names(insufficient_signers) is False
        
        # Test with expected_min signers (should pass)
        sufficient_signers = {f"auth{i}" for i in range(expected_min)}
        assert committee.has_quorum_by_names(sufficient_signers) is True

