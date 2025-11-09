# DAG Consensus Implementation Quick Reference

**Quick Start Guide for Developers**

---

## Current State vs. Target State

### Current Architecture
```
Client → Broadcast TransferOrder → All Authorities
        ← Collect Signatures (2/3+1) ←
        → Broadcast ConfirmationOrder →
```

**Limitations:**
- O(n) messages per transaction
- Sequential processing
- No batching
- No DAG structure

### Target Architecture
```
Client → Submit Transaction → Authority (Block Proposer)
        ↓
    [DAG Block Creation]
        ↓
    [Reliable Broadcast] → All Authorities
        ↓
    [Availability Cert] (2/3+1 attestations)
        ↓
    [Consensus Ordering] → Leader Election → Voting
        ↓
    [Commit] → Causal Closure → Finalization
```

**Benefits:**
- O(1) amortized messages (via batching)
- Parallel block processing
- DAG structure for causal ordering
- Mesh network optimizations

---

## Core Data Structures

### DAGBlock
```python
@dataclass
class DAGBlock:
    block_id: UUID
    round: int
    proposer: AuthorityName
    transactions: List[TransferOrder]  # Batched
    parents: List[UUID]  # n-f parent references
    timestamp: float
    signature: Optional[str]
    availability_cert: Optional[AvailabilityCertificate]
    quorum_cert: Optional[QuorumCertificate]
```

### AvailabilityCertificate
```python
@dataclass
class AvailabilityCertificate:
    block_id: UUID
    attestations: List[Attestation]  # 2/3+1 required
    threshold_signature: Optional[str]
```

### QuorumCertificate
```python
@dataclass
class QuorumCertificate:
    block_id: UUID
    round: int
    votes: List[Vote]
    aggregate_weight: float  # Sum of voting weights
    threshold_weight: float  # 2/3 of total weight
```

---

## Protocol Flow (Per Round)

### Round r: Block Proposal
1. **Collect Transactions:** Authority batches pending transactions
2. **Select Parents:** Choose n-f certified blocks from previous rounds
3. **Create Block:** `DAGBlock(round=r, parents=selected_parents, transactions=batch)`
4. **Broadcast:** Reliable broadcast block metadata + data to all authorities

### Round r: Availability Certification
1. **Receive Block:** Authority receives block proposal
2. **Validate:** Check block data, signatures, no equivocation
3. **Attest:** Send attestation back to proposer
4. **Form Certificate:** Proposer collects 2/3+1 attestations → `AvailabilityCertificate`

### Round r+1: Consensus Ordering
1. **Leader Election:** `leader = hash(round, randomness) % n`
2. **Vote:** Validators vote on leader's block if certified and valid
3. **Commit:** If aggregate weight ≥ 2/3:
   - Commit leader's block
   - Commit all blocks in causal closure
   - Update `last_committed_round`

---

## Key Algorithms

### Parent Selection (n-f parents)
```python
def select_parents(dag_state: DAGState, round: int, f: int) -> List[UUID]:
    """Select n-f certified blocks from previous rounds."""
    n = len(dag_state.committee)
    certified_blocks = [b for b in dag_state.certified_blocks 
                       if dag_state.blocks[b].round < round]
    # Select n-f parents ensuring causal ordering
    return select_n_minus_f(certified_blocks, n - f)
```

### Leader Election (Deterministic)
```python
def elect_leader(round: int, randomness: bytes, n: int) -> int:
    """Elect leader deterministically from randomness."""
    seed = hash(round.to_bytes(8, 'big') + randomness)
    return int.from_bytes(seed[:8], 'big') % n
```

### DAG Commit Rule
```python
def commit_block(block_id: UUID, dag_state: DAGState) -> Set[UUID]:
    """Commit block and all blocks in causal closure."""
    committed = {block_id}
    block = dag_state.blocks[block_id]
    
    # Recursively commit all parents
    for parent_id in block.parents:
        if parent_id not in dag_state.committed_blocks:
            committed.update(commit_block(parent_id, dag_state))
    
    return committed
```

### Connectivity-Weighted Voting
```python
def compute_weight(authority: AuthorityState, metrics: NetworkMetrics) -> float:
    """Compute voting weight based on connectivity."""
    base = authority.stake
    connectivity_bonus = metrics.connectivity_ratio * 0.1
    latency_penalty = max(0, (metrics.latency - 100) / 1000) * 0.05
    weight = base * (1 + connectivity_bonus - latency_penalty)
    return min(weight, base * 1.33)  # Cap at 33% increase
```

---

## Implementation Checklist

### Phase 1: Foundation
- [ ] Create `DAGBlock` dataclass
- [ ] Create `DAGState` class
- [ ] Implement block proposal logic
- [ ] Implement parent selection
- [ ] Add block validation
- [ ] Write unit tests

### Phase 2: Availability Layer
- [ ] Implement reliable broadcast
- [ ] Add attestation collection
- [ ] Create `AvailabilityCertificate`
- [ ] Integrate with mesh transport
- [ ] Add retry logic for unreliable links
- [ ] Write integration tests

### Phase 3: Consensus Ordering
- [ ] Implement leader election
- [ ] Add voting mechanism
- [ ] Create `QuorumCertificate`
- [ ] Implement DAG commit rule
- [ ] Add causal closure computation
- [ ] Write consensus tests

### Phase 4: Mesh Optimizations
- [ ] Add network metrics collection
- [ ] Implement connectivity-weighted voting
- [ ] Add clustering support (optional)
- [ ] Implement erasure coding (optional)
- [ ] Create adaptive overlay (optional)
- [ ] Write performance tests

### Phase 5: Integration
- [ ] Update `WiFiAuthority` to use DAG
- [ ] Update `Client` for DAG interaction
- [ ] Add feature flags for migration
- [ ] Maintain backward compatibility
- [ ] Update CLI commands
- [ ] Write end-to-end tests

### Phase 6: Evaluation
- [ ] Set up benchmarking infrastructure
- [ ] Run throughput tests
- [ ] Run latency tests
- [ ] Run scalability tests
- [ ] Compare with baseline
- [ ] Document results

---

## Testing Strategy

### Unit Tests
- Block creation and validation
- Parent selection algorithm
- Leader election determinism
- Commit rule correctness
- Weight computation

### Integration Tests
- End-to-end consensus flow
- Availability certification
- Quorum formation
- Mesh network routing

### Performance Tests
- Throughput benchmarks
- Latency measurements
- Scalability tests (10, 50, 100+ authorities)
- Fault tolerance tests (Byzantine failures)
- Partition tolerance tests

### Fault Injection Tests
- Network delays
- Message loss
- Byzantine node behavior
- Partition scenarios
- Node failures

---

## Performance Targets

| Metric | Current | Target | Stretch Goal |
|--------|---------|--------|--------------|
| Throughput | ~10K TPS | 50K TPS | 100K+ TPS |
| Latency | 200ms-2s | <1s | <500ms |
| Scalability | Limited | 100+ nodes | 500+ nodes |
| Fault Tolerance | f < n/3 | f < n/3 | Same + faster recovery |

---

## Key Design Decisions

1. **Narwhal+Tusk Architecture:** Separates data dissemination from ordering, enables parallel processing
2. **n-f Parent Selection:** Ensures availability and causal ordering
3. **Deterministic Leader Election:** No extra messages, uses threshold randomness
4. **Weighted Voting:** Integrates with existing weighted voting plan, adds connectivity awareness
5. **Mesh Optimizations:** Connectivity weighting, clustering, erasure coding for mesh networks

---

## Common Pitfalls to Avoid

1. **Don't skip availability certification** - Safety depends on data availability
2. **Don't commit without quorum** - Always verify aggregate weight ≥ 2/3
3. **Don't ignore parent references** - Causal ordering is critical for safety
4. **Don't optimize prematurely** - Get correctness first, then optimize
5. **Don't break backward compatibility** - Use feature flags during migration

---

## Resources

- **Full Analysis:** `DAG_CONSENSUS_ANALYSIS_AND_IMPROVEMENT_PLAN.md`
- **Executive Summary:** `DAG_CONSENSUS_EXECUTIVE_SUMMARY.md`
- **Narwhal Paper:** "Narwhal and Tusk: A DAG-based Mempool and Efficient BFT Consensus"
- **FastPay Paper:** "FastPay: High-Performance Byzantine Fault Tolerant Settlement"
- **Sui Documentation:** docs.sui.io (Mysticeti consensus)

---

**Last Updated:** 2025-01-27  
**Status:** Ready for Implementation
