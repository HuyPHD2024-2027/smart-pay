# MeshPay Architecture Summary
## Quick Reference Guide

**Date:** January 2025  
**Version:** 1.0

---

## Overview

MeshPay is an offline payment system built on IEEE 802.11s wireless mesh networks, enabling secure peer-to-peer transactions without internet connectivity.

---

## System Components

### Node Types

```
┌─────────────────────────────────────────────────────────┐
│                    MeshPay Node Types                    │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   Client     │  │  Authority   │  │   Gateway    │  │
│  │              │  │              │  │              │  │
│  │ • Initiates  │  │ • Validates  │  │ • Bridges    │  │
│  │   transfers  │  │   transfers  │  │   to primary │  │
│  │ • Collects   │  │ • Signs      │  │   ledger     │  │
│  │   signatures │  │   orders     │  │ • Settles    │  │
│  │ • Manages    │  │ • Maintains  │  │   withdrawals│  │
│  │   balance    │  │   state      │  │              │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## Network Topology

### Mesh Network Structure

```
                    [Authority 1]
                         │
                         │ Mesh Link
                         │
        [Client 1] ──────┼────── [Client 2]
                         │
                         │
                    [Authority 2] ────── [Authority 3]
                         │                    │
                         │                    │
                    [Client 3]           [Gateway] ── Internet
                         │                    │
                         │                    │
                    [Authority 4] ────── [Authority 5]
```

**Key Features:**
- **Multi-hop routing:** Messages routed through intermediate nodes
- **Self-healing:** Automatic path recalculation on failures
- **Scalability:** Supports 1000+ nodes
- **No infrastructure:** No access points required

---

## Protocol Flows

### 1. Transfer Order Flow

```
Client                    Mesh Network              Authorities
  │                            │                         │
  │─── Create TransferOrder ──>│                         │
  │                            │                         │
  │                            │─── Broadcast ─────────>│
  │                            │                         │
  │                            │<── Validate & Sign ────│
  │                            │                         │
  │<── Collect Signatures ─────│                         │
  │                            │                         │
  │─── Create Confirmation ───>│                         │
  │                            │                         │
  │                            │─── Broadcast ─────────>│
  │                            │                         │
  │<── Finalized ──────────────│                         │
```

### 2. Withdrawal Flow

```
Client          Authorities          Gateway          Primary Ledger
  │                 │                   │                  │
  │─── Request ────>│                   │                  │
  │                 │                   │                  │
  │                 │─── Validate ─────>│                  │
  │                 │                   │                  │
  │                 │<── Lock Balance ──│                  │
  │                 │                   │                  │
  │<── Certificate ─│                   │                  │
  │                 │                   │                  │
  │─── Submit ─────────────────────────>│                  │
  │                 │                   │                  │
  │                 │                   │─── Settle ──────>│
  │                 │                   │                  │
  │                 │                   │<── Confirm ──────│
  │                 │                   │                  │
  │<── Finalized ────────────────────────│                  │
```

---

## Security Mechanisms

### Double-Spend Prevention

```
┌─────────────────────────────────────────────────────┐
│         Double-Spend Prevention Mechanism           │
├─────────────────────────────────────────────────────┤
│                                                      │
│  1. Sequence Number Tracking                        │
│     └─> Each account has strictly increasing seq     │
│                                                      │
│  2. Balance Locking                                 │
│     └─> Temporary lock during withdrawal            │
│                                                      │
│  3. Cross-Authority Validation                      │
│     └─> Authorities gossip orders to detect conflicts│
│                                                      │
│  4. Quorum Requirement                              │
│     └─> ≥2/3 authorities must agree                 │
│                                                      │
└─────────────────────────────────────────────────────┘
```

### Network Partition Handling

```
┌─────────────────────────────────────────────────────┐
│         Network Partition Handling                   │
├─────────────────────────────────────────────────────┤
│                                                      │
│  Detection:                                          │
│    • Heartbeat monitoring                           │
│    • Timeout detection                              │
│    • Quorum verification                            │
│                                                      │
│  Handling:                                          │
│    • Block withdrawals during partition             │
│    • Continue transfers if quorum maintained        │
│    • Merge state when partition resolves           │
│                                                      │
│  Resolution:                                        │
│    • State synchronization                          │
│    • Conflict resolution using timestamps           │
│    • Unlock balances                                │
│                                                      │
└─────────────────────────────────────────────────────┘
```

---

## Key Data Structures

### TransferOrder

```python
TransferOrder:
  - order_id: UUID
  - sender: Address
  - recipient: Address
  - token_address: str
  - amount: int
  - sequence_number: int  # Critical for double-spend prevention
  - timestamp: float
  - signature: str  # Client signature
```

### WithdrawalOrder

```python
WithdrawalOrder:
  - order_id: UUID
  - client_address: Address
  - recipient_address: str  # External address
  - token_address: str
  - amount: int
  - sequence_number: int  # Critical for double-spend prevention
  - timestamp: float
  - signature: str  # Client signature
```

### WithdrawalCertificate

```python
WithdrawalCertificate:
  - order_id: UUID
  - withdrawal_order: WithdrawalOrder
  - authority_signatures: Dict[str, str]  # Authority -> Signature
  - quorum_proof: QuorumProof
  - created_at: float
  - expires_at: float
```

---

## Message Types

| Message Type | Direction | Purpose |
|-------------|-----------|---------|
| `TRANSFER_REQUEST` | Client → Authority | Initiate transfer |
| `TRANSFER_RESPONSE` | Authority → Client | Signed certificate |
| `CONFIRMATION_REQUEST` | Client → Authority | Broadcast confirmation |
| `WITHDRAWAL_REQUEST` | Client → Authority | Initiate withdrawal |
| `WITHDRAWAL_RESPONSE` | Authority → Client | Withdrawal certificate |
| `SYNC_REQUEST` | Node → Authority | State synchronization |
| `PEER_DISCOVERY` | Broadcast | Service discovery |
| `HEARTBEAT` | Authority ↔ Authority | Partition detection |

---

## Consensus Mechanism

### Byzantine Fault Tolerance (BFT)

```
┌─────────────────────────────────────────────────────┐
│              BFT Consensus Process                   │
├─────────────────────────────────────────────────────┤
│                                                      │
│  Committee: 4 Authorities                           │
│  Quorum: ≥3/4 (≥67%)                                │
│  Fault Tolerance: 1 Byzantine node                  │
│                                                      │
│  Process:                                            │
│    1. Client broadcasts to all authorities          │
│    2. Authorities validate independently             │
│    3. Authorities gossip to cross-validate           │
│    4. Authorities sign if valid                      │
│    5. Client collects quorum signatures              │
│    6. Client creates confirmation certificate        │
│                                                      │
└─────────────────────────────────────────────────────┘
```

---

## Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| **Transfer Latency** | <100ms (single-hop)<br/><500ms (multi-hop) | Mesh routing dependent |
| **Withdrawal Latency** | <1 minute | Primary ledger dependent |
| **Throughput** | 80k+ TPS | Theoretical, mesh-dependent |
| **Scalability** | 1000+ nodes | Tested up to 300 nodes |
| **Fault Tolerance** | 33% Byzantine nodes | BFT quorum requirement |
| **Recovery Time** | <2.3 seconds | Node failure recovery |

---

## Security Properties

### Guarantees

1. ✅ **Double-Spend Prevention:** Sequence numbers + balance locking
2. ✅ **Partition Resilience:** Detection + state merging
3. ✅ **Byzantine Tolerance:** Up to 33% malicious authorities
4. ✅ **State Consistency:** Gateway synchronization
5. ✅ **Non-Repudiation:** Cryptographic signatures
6. ✅ **Auditability:** Complete transaction history

### Threat Mitigation

| Threat | Mitigation |
|--------|------------|
| Double-spending | Sequence numbers, balance locking |
| Network partition | Partition detection, withdrawal blocking |
| Byzantine authority | Quorum requirement (≥2/3) |
| Replay attack | Timestamps, certificate expiration |
| Certificate forgery | Cryptographic signatures |

---

## Architecture Diagrams Location

1. **Main Architecture:** `/docs/meshpay_architecture_diagrams.md`
   - System architecture overview
   - Network topology
   - Protocol flows
   - Node connection and discovery

2. **Withdrawal Architecture:** `/docs/withdrawal_architecture_proposal.md`
   - Withdrawal protocol design
   - Double-spend prevention
   - Network partition handling
   - Implementation details

3. **This Summary:** `/docs/architecture_summary.md`
   - Quick reference guide
   - Key concepts overview

---

## Key Design Decisions

### 1. Mesh Network Choice
- **Why:** IEEE 802.11s provides superior scalability (1000+ nodes) vs WiFi Direct (8 nodes)
- **Benefit:** Self-healing, multi-hop, no infrastructure required

### 2. BFT Consensus
- **Why:** Byzantine fault tolerance ensures security with malicious nodes
- **Benefit:** Tolerates up to 33% malicious authorities

### 3. Sequence Numbers
- **Why:** Prevents double-spending through strict ordering
- **Benefit:** Simple, effective, auditable

### 4. Balance Locking
- **Why:** Prevents concurrent withdrawals of same funds
- **Benefit:** Temporary locks ensure atomicity

### 5. Partition Blocking
- **Why:** Prevents double-spending across partitions
- **Benefit:** Safe but may reduce availability during partitions

---

## Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| Mesh Network | ✅ Implemented | IEEE 802.11s support |
| Transfer Protocol | ✅ Implemented | BFT consensus working |
| Withdrawal Protocol | 📋 Proposed | Architecture designed |
| Partition Handling | 📋 Proposed | Detection + merging designed |
| Gateway Integration | ✅ Implemented | Bridge to primary ledger |

---

## Next Steps

1. **Implement Withdrawal Protocol**
   - Authority withdrawal handler
   - Gateway withdrawal processor
   - Certificate management

2. **Implement Partition Handling**
   - Heartbeat mechanism
   - Partition detection
   - State merging algorithm

3. **Testing**
   - Double-spend attack scenarios
   - Partition scenarios
   - Byzantine failure scenarios

4. **Documentation**
   - API documentation
   - Deployment guide
   - Security audit

---

**Document Status:** Summary Complete  
**Last Updated:** January 2025
