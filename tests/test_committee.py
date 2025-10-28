"""Unit tests for Committee class and weighted voting system."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from meshpay.committee import Committee
from meshpay.types import Address, AuthorityState, NodeType, WeightedCertificate

if TYPE_CHECKING:
    from _pytest.fixtures import FixtureRequest


def create_authority(
    name: str,
    transaction_count: int = 0,
    error_count: int = 0,
) -> AuthorityState:
    """Create a test authority state.
    
    Args:
        name: Authority name.
        transaction_count: Number of transactions processed.
        error_count: Number of errors encountered.
        
    Returns:
        AuthorityState instance for testing.
    """
    address = Address(
        node_id=name,
        ip_address=f"10.0.0.{hash(name) % 255}",
        port=8000,
        node_type=NodeType.AUTHORITY,
    )
    return AuthorityState(
        name=name,
        address=address,
        shard_assignments=set(),
        accounts={},
        committee_members=set(),
        transaction_count=transaction_count,
        error_count=error_count,
        voting_weight=0.0,
    )


def test_committee_initialization() -> None:
    """Test Committee initialization with default threshold."""
    authorities = [
        create_authority("auth1"),
        create_authority("auth2"),
        create_authority("auth3"),
    ]
    committee = Committee(authorities)
    
    assert len(committee.authorities) == 3
    assert committee.quorum_threshold == 2 / 3


def test_committee_custom_threshold() -> None:
    """Test Committee initialization with custom threshold."""
    authorities = [create_authority("auth1")]
    committee = Committee(authorities, quorum_threshold=0.5)
    
    assert committee.quorum_threshold == 0.5


def test_compute_weights_equal_performance() -> None:
    """Test weight computation with equal performance across authorities."""
    authorities = [
        create_authority("auth1", transaction_count=10, error_count=2),
        create_authority("auth2", transaction_count=10, error_count=2),
        create_authority("auth3", transaction_count=10, error_count=2),
    ]
    committee = Committee(authorities)
    
    weights = committee.compute_weights()
    
    # All authorities should have equal weight (1/3 each)
    assert len(weights) == 3
    for weight in weights.values():
        assert pytest.approx(weight, abs=0.001) == 1.0 / 3.0
    assert pytest.approx(sum(weights.values()), abs=0.001) == 1.0


def test_compute_weights_varying_performance() -> None:
    """Test weight computation with varying performance levels."""
    authorities = [
        create_authority("auth1", transaction_count=100, error_count=0),  # Net: 100
        create_authority("auth2", transaction_count=50, error_count=0),   # Net: 50
        create_authority("auth3", transaction_count=25, error_count=5),   # Net: 20
    ]
    committee = Committee(authorities)
    
    weights = committee.compute_weights()
    
    # Total performance: 100 + 50 + 20 = 170
    assert pytest.approx(weights["auth1"], abs=0.001) == 100.0 / 170.0
    assert pytest.approx(weights["auth2"], abs=0.001) == 50.0 / 170.0
    assert pytest.approx(weights["auth3"], abs=0.001) == 20.0 / 170.0
    assert pytest.approx(sum(weights.values()), abs=0.001) == 1.0


def test_compute_weights_negative_performance() -> None:
    """Test that negative net performance is clamped to zero."""
    authorities = [
        create_authority("auth1", transaction_count=10, error_count=0),
        create_authority("auth2", transaction_count=5, error_count=20),  # Net would be -15
    ]
    committee = Committee(authorities)
    
    weights = committee.compute_weights()
    
    # auth2 should have 0 contribution (clamped)
    # Total performance: 10 + 0 = 10
    assert pytest.approx(weights["auth1"], abs=0.001) == 1.0
    assert pytest.approx(weights["auth2"], abs=0.001) == 0.0


def test_compute_weights_all_zero_performance() -> None:
    """Test equal weight fallback when all authorities have zero performance."""
    authorities = [
        create_authority("auth1", transaction_count=0, error_count=0),
        create_authority("auth2", transaction_count=5, error_count=5),
        create_authority("auth3", transaction_count=0, error_count=10),
    ]
    committee = Committee(authorities)
    
    weights = committee.compute_weights()
    
    # Should fall back to equal weights
    assert pytest.approx(weights["auth1"], abs=0.001) == 1.0 / 3.0
    assert pytest.approx(weights["auth2"], abs=0.001) == 1.0 / 3.0
    assert pytest.approx(weights["auth3"], abs=0.001) == 1.0 / 3.0


def test_get_authority_weight() -> None:
    """Test retrieving individual authority weight."""
    authorities = [
        create_authority("auth1", transaction_count=60, error_count=0),
        create_authority("auth2", transaction_count=40, error_count=0),
    ]
    committee = Committee(authorities)
    
    weight1 = committee.get_authority_weight("auth1")
    weight2 = committee.get_authority_weight("auth2")
    
    assert pytest.approx(weight1, abs=0.001) == 0.6
    assert pytest.approx(weight2, abs=0.001) == 0.4


def test_get_authority_weight_unknown() -> None:
    """Test retrieving weight for unknown authority returns zero."""
    authorities = [create_authority("auth1")]
    committee = Committee(authorities)
    
    weight = committee.get_authority_weight("unknown")
    
    assert weight == 0.0


def test_get_total_weight() -> None:
    """Test that total weight sums to 1.0."""
    authorities = [
        create_authority("auth1", transaction_count=10, error_count=0),
        create_authority("auth2", transaction_count=20, error_count=5),
        create_authority("auth3", transaction_count=30, error_count=0),
    ]
    committee = Committee(authorities)
    
    total = committee.get_total_weight()
    
    assert pytest.approx(total, abs=0.001) == 1.0


def test_has_quorum_with_sufficient_weight() -> None:
    """Test quorum check with sufficient total weight."""
    authorities = [create_authority(f"auth{i}") for i in range(5)]
    committee = Committee(authorities, quorum_threshold=2 / 3)
    
    # Simulate weights that sum to > 2/3
    signer_weights = [0.25, 0.25, 0.20]  # Total: 0.70 > 0.667
    
    assert committee.has_quorum(signer_weights) is True


def test_has_quorum_with_insufficient_weight() -> None:
    """Test quorum check with insufficient total weight."""
    authorities = [create_authority(f"auth{i}") for i in range(5)]
    committee = Committee(authorities, quorum_threshold=2 / 3)
    
    # Simulate weights that sum to < 2/3
    signer_weights = [0.25, 0.25, 0.10]  # Total: 0.60 < 0.667
    
    assert committee.has_quorum(signer_weights) is False


def test_has_quorum_exact_threshold() -> None:
    """Test quorum check with exactly the threshold weight."""
    authorities = [create_authority(f"auth{i}") for i in range(3)]
    committee = Committee(authorities, quorum_threshold=2 / 3)
    
    # Simulate weights that exactly equal 2/3
    signer_weights = [2 / 3]
    
    assert committee.has_quorum(signer_weights) is True


def test_has_quorum_by_names() -> None:
    """Test quorum check using authority names."""
    authorities = [
        create_authority("auth1", transaction_count=30, error_count=0),
        create_authority("auth2", transaction_count=30, error_count=0),
        create_authority("auth3", transaction_count=40, error_count=0),
    ]
    committee = Committee(authorities, quorum_threshold=0.5)
    committee.compute_weights()  # Weights: 0.3, 0.3, 0.4
    
    # auth2 + auth3 = 0.3 + 0.4 = 0.7 > 0.5
    assert committee.has_quorum_by_names({"auth2", "auth3"}) is True
    
    # auth1 alone = 0.3 < 0.5
    assert committee.has_quorum_by_names({"auth1"}) is False


def test_update_authority_performance() -> None:
    """Test updating performance metrics for an authority."""
    authorities = [
        create_authority("auth1", transaction_count=10, error_count=0),
        create_authority("auth2", transaction_count=10, error_count=0),
    ]
    committee = Committee(authorities)
    committee.compute_weights()
    
    # Update auth1 performance
    committee.update_authority_performance("auth1", transaction_count=50, error_count=5)
    
    # Verify state was updated
    assert authorities[0].transaction_count == 50
    assert authorities[0].error_count == 5
    assert authorities[0].voting_weight == 45.0  # 50 - 5


def test_get_committee_info() -> None:
    """Test retrieving detailed committee information."""
    authorities = [
        create_authority("auth1", transaction_count=100, error_count=10),
        create_authority("auth2", transaction_count=50, error_count=5),
    ]
    committee = Committee(authorities)
    
    info = committee.get_committee_info()
    
    assert "auth1" in info
    assert "auth2" in info
    assert info["auth1"]["transaction_count"] == 100.0
    assert info["auth1"]["error_count"] == 10.0
    assert info["auth1"]["net_performance"] == 90.0
    assert pytest.approx(info["auth1"]["normalized_weight"], abs=0.001) == 90.0 / 135.0
    assert pytest.approx(info["auth2"]["normalized_weight"], abs=0.001) == 45.0 / 135.0


def test_weighted_certificate_creation() -> None:
    """Test creating WeightedCertificate instances."""
    cert = WeightedCertificate(
        authority_name="auth1",
        authority_signature="sig123",
        weight=0.35,
        timestamp=1234567890.0,
    )
    
    assert cert.authority_name == "auth1"
    assert cert.authority_signature == "sig123"
    assert cert.weight == 0.35
    assert cert.timestamp == 1234567890.0


def test_weighted_certificates_in_quorum() -> None:
    """Test using WeightedCertificate list for quorum checking."""
    authorities = [create_authority(f"auth{i}") for i in range(5)]
    committee = Committee(authorities, quorum_threshold=2 / 3)
    
    certificates = [
        WeightedCertificate("auth1", "sig1", 0.25, 1.0),
        WeightedCertificate("auth2", "sig2", 0.25, 2.0),
        WeightedCertificate("auth3", "sig3", 0.20, 3.0),
    ]
    
    signer_weights = [cert.weight for cert in certificates]
    assert committee.has_quorum(signer_weights) is True


def test_empty_authorities_list() -> None:
    """Test Committee with empty authorities list."""
    committee = Committee([])
    
    weights = committee.compute_weights()
    
    assert len(weights) == 0
    assert committee.get_total_weight() == 0.0
    assert committee.has_quorum([]) is False


def test_single_authority() -> None:
    """Test Committee with single authority."""
    authorities = [create_authority("auth1", transaction_count=10, error_count=0)]
    committee = Committee(authorities)
    
    weights = committee.compute_weights()
    
    assert len(weights) == 1
    assert pytest.approx(weights["auth1"], abs=0.001) == 1.0
    assert committee.has_quorum([1.0]) is True


def test_weight_cache_invalidation() -> None:
    """Test that weight cache is invalidated after performance update."""
    authorities = [
        create_authority("auth1", transaction_count=10, error_count=0),
        create_authority("auth2", transaction_count=10, error_count=0),
    ]
    committee = Committee(authorities)
    
    # Initial weights
    weights1 = committee.compute_weights()
    assert pytest.approx(weights1["auth1"], abs=0.001) == 0.5
    
    # Update performance
    committee.update_authority_performance("auth1", transaction_count=30, error_count=0)
    
    # Weights should be recomputed
    weights2 = committee.compute_weights()
    assert pytest.approx(weights2["auth1"], abs=0.001) == 0.75  # 30 / (30 + 10)
    assert pytest.approx(weights2["auth2"], abs=0.001) == 0.25  # 10 / (30 + 10)

