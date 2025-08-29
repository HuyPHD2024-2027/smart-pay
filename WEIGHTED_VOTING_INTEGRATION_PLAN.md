## Weighted Voting Integration Plan for Offline Mesh-Based Payments with Authorities

Timestamp: 2025-08-08T00:00:00Z

### Scope
Integrate a weighted voting mechanism into the existing offline payment protocol that uses authority committees operating over local mesh networks (BLE/Wi‑Fi), without public internet. The mechanism should preserve safety under asynchrony and partitions, achieve eventual liveness, and align incentives.

### Goals
- Safety under asynchrony and mesh partitions (no timing assumptions for security).
- Eventual liveness upon reconnection.
- Rational incentives (rewards/penalties) to deter censorship, bribery, and equivocation.
- Auditability suitable for regulated environments.
- Maintain good UX (near real-time acceptance when local quorum reachable).

### Chosen Approach (Summary)
- Hybrid weighted quorum certificates:
  - weight_i = α·stake_i + β·reputation_i(epoch) + γ·performance_i(short‑window), normalised with per‑entity caps (e.g., ≤ 33%).
  - Epoch-based re-weighting; decay for reputation and performance to prevent lock‑in.
  - Quorum threshold τ = 2/3 of total weight (configurable per epoch).
  - Safety: accept a transfer only with certificate whose aggregate signer weight ≥ τ.
  - Incentives: rewards proportional to effective weight used in certs; slashing/penalties for provable misbehavior or non‑participation.

Rationale: Balances sybil/bribery resistance (stake), long‑term trust (reputation per RepuCoin‑style ideas), and adaptivity (performance). Compatible with BRICK’s consistent broadcast and proactive security model.

### Plan (Phased)
1) Specification (docs only in this phase)
   - Define exact weight function, α/β/γ defaults (e.g., 0.5/0.3/0.2), caps, floors, and decay functions.
   - Define epoch parameters (duration or N‑transactions), membership update rules, and stake/reputation sources.
   - Define certificate validity rule (sum of signer weights ≥ τ) and conflict resolution under partitions.
   - Define incentive scheme: rewards, penalties, slashing triggers and proofs.
   - Define audit artifacts: epoch weight snapshots, hash‑chain of state updates, signed weight tables.

2) Prototype design (no code in this document; outline only)
   - Data model: add per‑authority `stake`, `reputation`, `performance_metrics`, and `effective_weight` (computed per epoch).
   - Quorum logic: replace count‑based consensus checks with weighted aggregation and threshold compare.
   - Epoch manager: recompute weights, apply decay, persist signed epoch state.
   - CLI/telemetry: expose current weights, threshold, and signer breakdown in certificates.

3) Evaluation design
   - Safety/liveness tests under asynchrony and partitions (conflict certificates cannot both reach τ).
   - Robustness: simulate bribery attempts, targeted DoS on high‑weight nodes, and collusion.
   - Performance/UX: measure latency/throughput vs equal‑weight baseline; tail latency under churn.

4) Security review
   - Threats: bribery/centralisation, sybil, DoS on top‑weight nodes, incentive manipulation, replay.
   - Mitigations: caps, membership floors, audit logs, robust statistics for performance, delayed activation of weight changes.

5) Demo storyline (for supervisors)
   - Start mesh with committee; show epoch weights and τ.
   - Trigger transfers; show weighted signer set and aggregate weight in real time.
   - Simulate a partition: show local holds (no τ) vs finalisation after reconnection.
   - Show audit endpoints (weights per epoch; certificate provenance).

### Immediate Next Steps (Actionable)
- Document: draft the protocol spec section covering weight function, quorum rule, epochs, audit, and incentives.
- Parameter selection: propose initial α/β/γ, caps, epoch length, decay constants, and τ.
- Risk log: document adversary models and mitigations; define slashing proofs.
- Experiment plan: define benchmarks and scenarios (baseline vs hybrid weights, partitions, DoS).

### Risks & Mitigations
- Centralisation/bribery: enforce caps; diversify signers; transparent audits.
- DoS on high‑weight nodes: use robust performance aggregation; avoid aggressive down‑weights on transient errors.
- Sybil: identity/stake/reputation floors; gated membership updates per epoch.
- Parameter drift: start conservatively; adjust after evaluation; document governance for changes.

### References
- BRICK: Asynchronous Payment Channels (wardens, consistent broadcast, proactive security): [arXiv:1905.11360](https://arxiv.org/pdf/1905.11360)
- RepuCoin: reputation as voting power (epoch adaptation, long‑range resistance): summary and approaches discussed here: [link](https://repository.tudelft.nl/record/uuid:907bd47c-394a-4e26-b901-de713159dcb8#:~:text=To%20cover%20this%20knowledge%20gap%2C%20we%20introduce%20a,leader%20rotation%20in%20the%20underlying%20state%20replication%20protocol.)

### Status
This document records the plan and next steps only; no code changes were made in this step.


