---
_title: Offline P2P Payments Without Internet: Mesh + DAG Pattern
_version: 1.0
_status: draft
---

## Pattern Proposal: Offline Peer‑to‑Peer Payments via Mesh Routing and DAG Consensus

### Intent
Enable secure, resilient peer‑to‑peer payments without continuous internet by combining delay‑tolerant mesh routing for transaction dissemination with a DAG‑based consensus for ordering, validation, and conflict resolution upon (re)connect.

### Context
- Environments with intermittent or absent backhaul (disaster zones, remote regions, local events).
- Devices form ad‑hoc meshes (Wi‑Fi Direct, BLE, LoRa, community mesh) with high churn and asymmetric links.
- Payment integrity, double‑spend resistance, and auditability must be preserved under delay and partition.

### Problem
How can nodes exchange, validate, and ultimately finalize payments when end‑to‑end connectivity and synchronized clocks are unavailable, and topology changes frequently?

### Forces
- Unreliable connectivity; messages may be delayed, duplicated, or lost.
- Limited power, bandwidth, and storage on edge devices.
- Need for double‑spend resistance and strong integrity with minimal coordination.
- Privacy considerations for payer/payee metadata in a local mesh.
- Practical UX: fast local acknowledgment vs. eventual global finality.

### Solution (Pattern)
Layer a delay‑tolerant mesh routing protocol beneath a DAG‑based consensus ledger:
- Mesh layer provides peer discovery, store–carry–forward propagation, and opportunistic forwarding (e.g., PRoPHET/epidemic/Q‑learning assisted), with rate‑limiting and content‑addressed deduplication.
- Consensus layer models transactions as DAG vertices; each new transaction references and approves prior tips. Nodes perform local validation (signatures, balance proofs, conflict rules) offline, then reconcile upon connectivity via tip selection and conflict resolution to converge on a consistent, double‑spend‑resistant state.

### Structure
- Node: { RoutingService, LedgerService, WalletService, Gossip/Sync }
- RoutingService: neighbor discovery, link scoring, bundle queue, opportunistic forwarding.
- LedgerService: DAG storage, tip selection, validation, conflict set tracking, finality rules.
- WalletService: key management, spend policy, local acceptance thresholds, receipts.

### Participants and Responsibilities
- RoutingService: disseminate and retrieve transactions; enforce quotas; prioritize by utility/age.
- LedgerService: construct transactions referencing k tips; validate signatures and spend conditions; maintain conflict graph; compute confidence and finalize.
- Sync/Gossip: exchange DAG diffs, compact proofs, and missing dependencies upon contact.
- Policy/UX: local acceptance thresholds for "offline ok" vs. "await sync" states.

### Collaboration
1. User creates payment; WalletService constructs a transaction referencing current tips from LedgerService.
2. RoutingService gossips the transaction over mesh with store–carry–forward and dedup.
3. Peers validate locally; accepted transactions become tips until later approvals reduce tip set.
4. When peers reconnect (mesh or internet), DAG diffs reconcile; conflicts resolved per consensus rules to achieve finality.

### Option Analysis
- Option A: Pure epidemic routing + naive tip selection.
  - Pros: Simple, robust under churn. Cons: High overhead; slower convergence.
- Option B: PRoPHET‑style utility routing + weighted tip selection (trust/age/quality).
  - Pros: Efficient propagation; faster confirmation; tunable security. Cons: Requires utility estimation and reputation hygiene.
- Option C: Geo/cluster‑aware routing + shard‑like DAG partitions with cross‑shard approvals.
  - Pros: Scales in dense deployments. Cons: Added complexity and cross‑partition reconciliation.
- Option D: Deterministic opportunistic routing + stake/credential‑weighted approvals for merchants.
  - Pros: Stronger double‑spend resistance for high‑value. Cons: Onboarding/credential overhead.

### Recommendation
Adopt Option B: PRoPHET‑style opportunistic routing combined with trust/age/quality‑weighted tip selection and conflict resolution. This balances propagation efficiency, resource constraints, and rapid local confidence accrual while preserving eventual global finality.

### Consequences
- Local spends can be accepted quickly with configurable risk thresholds; hard finality achieved post‑sync.
- Improved bandwidth efficiency via utility‑guided forwarding and content addressing.
- Requires careful reputation/utility controls to resist spam and eclipse attempts.

### Implementation Notes
- Content addressing (CID) and Bloom filters for dedup/sync.
- Rate limiting, per‑peer quotas, and proof‑of‑resource stamps for anti‑spam.
- Signed transactions; optional zero‑knowledge notes for enhanced privacy.
- Compact DAG sync: tip set exchange + ancestor sketching (IBLT/minisketch).
- Tip selection: weighted random walk favoring well‑approved, recent, and reputable issuers.
- Finality: confidence threshold over approvals and conflict‑free depth; checkpointing when available.

### Known Uses
- DTN/PRoPHET in challenged networks; DAG‑ledgers such as IOTA‑like constructs adapted for offline sync.

### Related Patterns
- Delay‑Tolerant Networking, Gossip Dissemination, Eventual Consistency, Probabilistic Finality.

### Security Considerations
- Mitigate Sybil with lightweight identity and usage‑bound credentials; locality‑aware limits.
- Guard against flooding via quotas, stamps, and admission control.
- Protect metadata with hop‑wise encryption and onion routing where feasible.

### Testing Strategy
- Simulation of mobility/topology churn; fault injection for delay/loss/dup.
- Property tests for conflict resolution and tip selection invariants.
- Interop tests for DAG diff/gossip compactness.

### Operational Concerns
- Telemetry with privacy‑respecting aggregates; health of tip set, queue sizes, sync lag.
- Upgradable protocol flags with capability negotiation.

### Status
Draft. Suitable for pilot implementations on Android/Linux single‑board devices and community meshes.
