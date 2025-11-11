# MeshPay Architecture Overview and Diagrams
## Offline Payment System over Wireless Mesh Network

**Date:** January 2025  
**Version:** 1.0  
**Status:** Architecture Documentation

---

## Table of Contents

1. [System Architecture Overview](#1-system-architecture-overview)
2. [Network Topology](#2-network-topology)
3. [Protocol Flow Diagrams](#3-protocol-flow-diagrams)
4. [Node Connection and Discovery](#4-node-connection-and-discovery)
5. [Transfer Order Processing](#5-transfer-order-processing)
6. [Withdrawal Architecture Proposal](#6-withdrawal-architecture-proposal)
7. [Security Mechanisms](#7-security-mechanisms)

---

## 1. System Architecture Overview

### 1.1 High-Level Architecture

```mermaid
graph TB
    subgraph "Mesh Network Layer (IEEE 802.11s)"
        C1[Client 1]
        C2[Client 2]
        C3[Client 3]
        A1[Authority 1]
        A2[Authority 2]
        A3[Authority 3]
        A4[Authority 4]
        GW[Gateway Node]
    end
    
    subgraph "Application Layer"
        TO[Transfer Orders]
        CO[Confirmation Orders]
        DS[Discovery Service]
    end
    
    subgraph "Consensus Layer"
        BFT[Byzantine Fault Tolerance]
        QV[Quorum Voting]
        CS[Consensus State]
    end
    
    subgraph "External Systems"
        BC[Blockchain Primary Ledger]
        RTGS[RTGS System]
        API[External APIs]
    end
    
    C1 <-->|Mesh Link| A1
    C1 <-->|Mesh Link| A2
    C2 <-->|Mesh Link| A2
    C2 <-->|Mesh Link| A3
    C3 <-->|Mesh Link| A3
    C3 <-->|Mesh Link| A4
    A1 <-->|Mesh Link| A2
    A2 <-->|Mesh Link| A3
    A3 <-->|Mesh Link| A4
    GW <-->|Mesh Link| A1
    GW <-->|Internet| BC
    GW <-->|Internet| RTGS
    GW <-->|Internet| API
    
    C1 -->|Transfer Request| TO
    TO -->|Quorum Signatures| BFT
    BFT -->|Confirmation| CO
    CO -->|Broadcast| C1
    CO -->|Broadcast| C2
    
    GW -->|Settlement| BC
    GW -->|Net Settlement| RTGS
```

### 1.2 Component Stack

```mermaid
graph LR
    subgraph "Application Layer"
        APP[FastPay Application]
    end
    
    subgraph "Protocol Layer"
        MSG[Message Handler]
        TRANS[Transfer Processor]
        CONF[Confirmation Manager]
    end
    
    subgraph "Consensus Layer"
        BFT[BFT Consensus]
        VOTE[Voting Mechanism]
        CERT[Certificate Manager]
    end
    
    subgraph "Transport Layer"
        MESH[Mesh Transport]
        TCP[TCP Transport]
        UDP[UDP Transport]
        WFD[WiFi Direct]
    end
    
    subgraph "Network Layer"
        IEEE80211s[IEEE 802.11s Mesh]
        HWMP[HWMP Routing]
        PEER[Peer Discovery]
    end
    
    subgraph "Security Layer"
        AES[AES-128-CCM]
        ED25519[Ed25519 Signatures]
        SAE[WPA3-SAE]
    end
    
    APP --> MSG
    MSG --> TRANS
    MSG --> CONF
    TRANS --> BFT
    CONF --> VOTE
    BFT --> CERT
    CERT --> MESH
    CERT --> TCP
    CERT --> UDP
    CERT --> WFD
    MESH --> IEEE80211s
    IEEE80211s --> HWMP
    IEEE80211s --> PEER
    IEEE80211s --> SAE
    MSG --> ED25519
    IEEE80211s --> AES
```

---

## 2. Network Topology

### 2.1 Mesh Network Topology

```mermaid
graph TB
    subgraph "Mesh Network: fastpay-mesh"
        subgraph "Authority Cluster"
            A1[Authority 1<br/>Committee Member]
            A2[Authority 2<br/>Committee Member]
            A3[Authority 3<br/>Committee Member]
            A4[Authority 4<br/>Committee Member]
            A5[Authority 5<br/>Committee Member]
        end
        
        subgraph "Client Nodes"
            C1[Client 1<br/>Mobile User]
            C2[Client 2<br/>Mobile User]
            C3[Client 3<br/>Mobile User]
            C4[Client 4<br/>Mobile User]
        end
        
        subgraph "Gateway"
            GW[Gateway Node<br/>Internet Bridge]
        end
    end
    
    subgraph "External Infrastructure"
        BC[Blockchain<br/>Primary Ledger]
        RTGS[RTGS System]
    end
    
    A1 <-->|Mesh Link<br/>Multi-hop| A2
    A2 <-->|Mesh Link| A3
    A3 <-->|Mesh Link| A4
    A4 <-->|Mesh Link| A5
    A5 <-->|Mesh Link| A1
    A1 <-->|Mesh Link| A3
    
    C1 <-->|Mesh Link| A1
    C1 <-->|Mesh Link| A2
    C2 <-->|Mesh Link| A2
    C2 <-->|Mesh Link| A3
    C3 <-->|Mesh Link| A3
    C3 <-->|Mesh Link| A4
    C4 <-->|Mesh Link| A4
    C4 <-->|Mesh Link| A5
    
    GW <-->|Mesh Link| A1
    GW <-->|Internet| BC
    GW <-->|Internet| RTGS
    
    style A1 fill:#4CAF50
    style A2 fill:#4CAF50
    style A3 fill:#4CAF50
    style A4 fill:#4CAF50
    style A5 fill:#4CAF50
    style C1 fill:#2196F3
    style C2 fill:#2196F3
    style C3 fill:#2196F3
    style C4 fill:#2196F3
    style GW fill:#FF9800
```

### 2.2 Multi-Hop Routing Example

```mermaid
graph LR
    C[Client] -->|Hop 1| R1[Relay Node 1]
    R1 -->|Hop 2| A1[Authority 1]
    A1 -->|Hop 3| A2[Authority 2]
    A2 -->|Hop 4| A3[Authority 3]
    A3 -->|Hop 5| R2[Relay Node 2]
    R2 -->|Hop 6| C2[Recipient Client]
    
    style C fill:#2196F3
    style C2 fill:#2196F3
    style A1 fill:#4CAF50
    style A2 fill:#4CAF50
    style A3 fill:#4CAF50
    style R1 fill:#FFC107
    style R2 fill:#FFC107
```

**Key Features:**
- **Self-healing:** Automatic path recalculation on node failure
- **Load balancing:** Multiple paths to same destination
- **Range extension:** Coverage beyond single-hop limitations
- **Scalability:** Supports 1000+ nodes

---

## 3. Protocol Flow Diagrams

### 3.1 Complete Transfer Order Flow

```mermaid
sequenceDiagram
    autonumber
    participant C as Client (Payer)
    participant M as Mesh Network
    participant A1 as Authority 1
    participant A2 as Authority 2
    participant A3 as Authority 3
    participant R as Recipient Client
    
    Note over C,R: Phase 1: Peer Discovery
    C->>M: Broadcast Peer Discovery Request
    M->>A1: Forward Discovery
    M->>A2: Forward Discovery
    M->>A3: Forward Discovery
    A1-->>M: Authority Service Announcement
    A2-->>M: Authority Service Announcement
    A3-->>M: Authority Service Announcement
    M-->>C: Authority List (A1, A2, A3)
    
    Note over C,R: Phase 2: Transfer Order Creation
    C->>C: Create TransferOrder<br/>(sender, recipient, amount, seq_num)
    C->>C: Sign TransferOrder<br/>(Ed25519 signature)
    
    Note over C,R: Phase 3: Multi-Hop Transfer Request
    C->>M: TransferRequestMessage<br/>(via mesh routing)
    M->>A1: Route to Authority 1 (2 hops)
    M->>A2: Route to Authority 2 (1 hop)
    M->>A3: Route to Authority 3 (3 hops)
    
    Note over C,R: Phase 4: Authority Processing
    A1->>A1: Validate TransferOrder<br/>(balance, sequence, signature)
    A2->>A2: Validate TransferOrder
    A3->>A3: Validate TransferOrder
    
    alt Valid Transfer
        A1->>A1: Sign TransferOrder<br/>(authority signature)
        A2->>A2: Sign TransferOrder
        A3->>A3: Sign TransferOrder
    else Invalid Transfer
        A1->>M: TransferResponseMessage<br/>(success=false, error)
        A2->>M: TransferResponseMessage<br/>(success=false, error)
        A3->>M: TransferResponseMessage<br/>(success=false, error)
        M-->>C: Error Response
    end
    
    Note over C,R: Phase 5: Signed Certificate Collection
    A1->>M: TransferResponseMessage<br/>(signed certificate)
    A2->>M: TransferResponseMessage<br/>(signed certificate)
    A3->>M: TransferResponseMessage<br/>(signed certificate)
    M-->>C: Collect Signed Certificates
    
    Note over C,R: Phase 6: Quorum Check
    C->>C: Check Quorum (≥2/3 signatures)
    
    alt Quorum Achieved
        C->>C: Create ConfirmationOrder<br/>(with quorum signatures)
        C->>M: Broadcast ConfirmationOrder
        M->>A1: Forward Confirmation
        M->>A2: Forward Confirmation
        M->>A3: Forward Confirmation
        M->>R: Forward Confirmation to Recipient
        
        Note over C,R: Phase 7: State Update
        A1->>A1: Update Account State<br/>(debit sender, credit recipient)
        A2->>A2: Update Account State
        A3->>A3: Update Account State
        R->>R: Update Account State<br/>(credit received)
        
        A1-->>C: Confirmation Acknowledgment
        A2-->>C: Confirmation Acknowledgment
        A3-->>C: Confirmation Acknowledgment
        R-->>C: Confirmation Acknowledgment
    else Quorum Not Achieved
        C->>C: Retry or Abort Transfer
    end
```

### 3.2 Node Connection and Discovery Flow

```mermaid
sequenceDiagram
    autonumber
    participant N as New Node
    participant M as Mesh Network
    participant A1 as Authority 1
    participant A2 as Authority 2
    participant C1 as Client 1
    
    Note over N,C1: Phase 1: Mesh Network Join
    N->>M: Enable 802.11s Mesh Mode
    N->>M: Join Mesh Network<br/>(mesh_id="fastpay-mesh")
    M->>M: Authenticate Node<br/>(WPA3-SAE)
    M-->>N: Mesh Join Confirmation
    
    Note over N,C1: Phase 2: Service Discovery
    N->>M: Broadcast Service Discovery<br/>(PEER_DISCOVERY message)
    M->>A1: Forward Discovery Request
    M->>A2: Forward Discovery Request
    M->>C1: Forward Discovery Request
    
    A1->>M: Service Announcement<br/>(node_type=AUTHORITY,<br/>capabilities=[transfer, consensus])
    A2->>M: Service Announcement<br/>(node_type=AUTHORITY)
    C1->>M: Service Announcement<br/>(node_type=CLIENT)
    M-->>N: Service List Received
    
    Note over N,C1: Phase 3: Peer Connection
    N->>A1: Establish P2P Connection<br/>(TCP/UDP/Mesh)
    A1-->>N: Connection Acknowledgment
    N->>A2: Establish P2P Connection
    A2-->>N: Connection Acknowledgment
    
    Note over N,C1: Phase 4: State Synchronization
    N->>A1: SyncRequestMessage<br/>(last_sync_time, account_addresses)
    A1->>A1: Query Account States
    A1-->>N: SyncResponseMessage<br/>(account states, balances)
    N->>N: Update Local State
    
    Note over N,C1: Phase 5: Routing Table Update
    N->>M: Update Routing Table<br/>(HWMP path discovery)
    M->>M: Calculate Optimal Paths
    M-->>N: Routing Table Updated
    N->>N: Ready for Transactions
```

### 3.3 Authority Committee Consensus Flow

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant A1 as Authority 1<br/>(Leader)
    participant A2 as Authority 2
    participant A3 as Authority 3
    participant A4 as Authority 4
    
    Note over C,A4: Transfer Order Received
    C->>A1: TransferRequestMessage
    C->>A2: TransferRequestMessage
    C->>A3: TransferRequestMessage
    C->>A4: TransferRequestMessage
    
    Note over C,A4: Validation Phase
    par Parallel Validation
        A1->>A1: Validate TransferOrder
        A2->>A2: Validate TransferOrder
        A3->>A3: Validate TransferOrder
        A4->>A4: Validate TransferOrder
    end
    
    Note over C,A4: Gossip Phase (Authorities Exchange)
    A1->>A2: Gossip TransferOrder<br/>(for cross-validation)
    A1->>A3: Gossip TransferOrder
    A1->>A4: Gossip TransferOrder
    A2->>A3: Gossip TransferOrder
    A2->>A4: Gossip TransferOrder
    A3->>A4: Gossip TransferOrder
    
    Note over C,A4: Double-Spend Detection
    par Double-Spend Check
        A1->>A1: Check Sequence Numbers<br/>(prevent double-spend)
        A2->>A2: Check Sequence Numbers
        A3->>A3: Check Sequence Numbers
        A4->>A4: Check Sequence Numbers
    end
    
    Note over C,A4: Voting Phase
    alt Valid Transfer (Quorum ≥ 3/4)
        A1->>A1: Sign TransferOrder<br/>(authority signature)
        A2->>A2: Sign TransferOrder
        A3->>A3: Sign TransferOrder
        A4->>A4: Sign TransferOrder
        
        A1->>C: TransferResponseMessage<br/>(signed certificate)
        A2->>C: TransferResponseMessage<br/>(signed certificate)
        A3->>C: TransferResponseMessage<br/>(signed certificate)
        A4->>C: TransferResponseMessage<br/>(signed certificate)
    else Invalid Transfer or No Quorum
        A1->>C: TransferResponseMessage<br/>(success=false)
        A2->>C: TransferResponseMessage<br/>(success=false)
        A3->>C: TransferResponseMessage<br/>(success=false)
        A4->>C: TransferResponseMessage<br/>(success=false)
    end
    
    Note over C,A4: State Commitment
    C->>C: Collect Quorum Signatures<br/>(≥2/3 required)
    C->>A1: ConfirmationOrder<br/>(with quorum certificate)
    C->>A2: ConfirmationOrder
    C->>A3: ConfirmationOrder
    C->>A4: ConfirmationOrder
    
    par State Update
        A1->>A1: Commit State Change<br/>(update balances)
        A2->>A2: Commit State Change
        A3->>A3: Commit State Change
        A4->>A4: Commit State Change
    end
```

---

## 4. Node Connection and Discovery

### 4.1 Mesh Peer Discovery Architecture

```mermaid
graph TB
    subgraph "Discovery Protocol"
        SD[Service Discovery<br/>Broadcast]
        PA[Peer Announcement]
        RT[Routing Table Update]
    end
    
    subgraph "Mesh Network"
        N1[Node 1]
        N2[Node 2]
        N3[Node 3]
        N4[Node 4]
    end
    
    subgraph "Discovery Messages"
        PD[PEER_DISCOVERY]
        SA[SERVICE_ANNOUNCEMENT]
        HB[HEARTBEAT]
    end
    
    SD --> PD
    PD --> N1
    PD --> N2
    PD --> N3
    PD --> N4
    
    N1 --> PA
    N2 --> PA
    N3 --> PA
    N4 --> PA
    
    PA --> SA
    SA --> RT
    
    RT --> N1
    RT --> N2
    RT --> N3
    RT --> N4
```

### 4.2 Connection State Machine

```mermaid
stateDiagram-v2
    [*] --> Disconnected: Node Startup
    
    Disconnected --> Discovering: Enable Mesh Mode
    Discovering --> Connecting: Peers Found
    Connecting --> Authenticating: Connection Established
    Authenticating --> Syncing: Authentication Success
    Syncing --> Connected: State Synchronized
    Connected --> Ready: Routing Table Updated
    
    Ready --> Processing: Transaction Received
    Processing --> Ready: Transaction Complete
    
    Ready --> Disconnected: Connection Lost
    Syncing --> Disconnected: Sync Failed
    Authenticating --> Disconnected: Auth Failed
    Connecting --> Disconnected: Connection Failed
    
    Ready --> Reconnecting: Network Partition
    Reconnecting --> Connecting: Reconnection Success
    Reconnecting --> Disconnected: Reconnection Failed
```

---

## 5. Transfer Order Processing

### 5.1 Transfer Order Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Created: Client Creates Order
    
    Created --> Signed: Client Signs Order
    Signed --> Broadcast: Send to Authorities
    
    Broadcast --> Validating: Authorities Receive
    Validating --> Valid: Validation Success
    Validating --> Invalid: Validation Failed
    
    Valid --> Signing: Authorities Sign
    Signing --> Collected: Client Collects Signatures
    
    Collected --> QuorumCheck: Check Quorum
    QuorumCheck --> Confirmed: Quorum Achieved (≥2/3)
    QuorumCheck --> Retry: Quorum Not Met
    
    Retry --> Broadcast: Retry Transfer
    Invalid --> Rejected: Transfer Rejected
    
    Confirmed --> Finalized: State Committed
    Finalized --> [*]
    Rejected --> [*]
```

### 5.2 Transfer Order Data Flow

```mermaid
graph LR
    subgraph "Client Side"
        CO[Create Order]
        SO[Sign Order]
        BR[Broadcast Request]
    end
    
    subgraph "Mesh Network"
        MR[Mesh Routing]
        MH[Message Handler]
    end
    
    subgraph "Authority Side"
        RV[Receive & Validate]
        SV[Sign & Vote]
        SC[Send Certificate]
    end
    
    subgraph "Consensus"
        QC[Quorum Check]
        CC[Create Confirmation]
        BC[Broadcast Confirmation]
    end
    
    CO --> SO
    SO --> BR
    BR --> MR
    MR --> MH
    MH --> RV
    RV --> SV
    SV --> SC
    SC --> QC
    QC --> CC
    CC --> BC
    BC --> MR
```

---

## 6. Withdrawal Architecture Proposal

### 6.1 Withdrawal System Architecture

```mermaid
graph TB
    subgraph "Mesh Network (Offline)"
        C[Client<br/>Withdrawal Request]
        A1[Authority 1]
        A2[Authority 2]
        A3[Authority 3]
        A4[Authority 4]
        GW[Gateway Node]
    end
    
    subgraph "Withdrawal Protocol Layer"
        WR[Withdrawal Request]
        WV[Withdrawal Validation]
        WS[Withdrawal Signature]
        WC[Withdrawal Certificate]
    end
    
    subgraph "Security Layer"
        DS[Double-Spend Prevention]
        NP[Network Partition Handling]
        QV[Quorum Verification]
        TS[Timestamp Validation]
    end
    
    subgraph "External Authority Systems"
        BC[Blockchain Primary]
        RTGS[RTGS System]
        BANK[Banking System]
    end
    
    C -->|1. Withdrawal Request| WR
    WR -->|2. Broadcast| A1
    WR -->|2. Broadcast| A2
    WR -->|2. Broadcast| A3
    WR -->|2. Broadcast| A4
    
    A1 -->|3. Validate| WV
    A2 -->|3. Validate| WV
    A3 -->|3. Validate| WV
    A4 -->|3. Validate| WV
    
    WV -->|4. Check| DS
    WV -->|5. Check| NP
    WV -->|6. Verify| QV
    WV -->|7. Validate| TS
    
    DS -->|8. Sign| WS
    NP -->|8. Sign| WS
    QV -->|8. Sign| WS
    TS -->|8. Sign| WS
    
    A1 -->|9. Certificate| WC
    A2 -->|9. Certificate| WC
    A3 -->|9. Certificate| WC
    A4 -->|9. Certificate| WC
    
    WC -->|10. Submit| GW
    GW -->|11. Settlement| BC
    GW -->|11. Settlement| RTGS
    GW -->|11. Settlement| BANK
    
    BC -->|12. Confirmation| GW
    RTGS -->|12. Confirmation| GW
    BANK -->|12. Confirmation| GW
    
    GW -->|13. Finalize| C
```

### 6.2 Withdrawal Protocol Flow

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant A1 as Authority 1
    participant A2 as Authority 2
    participant A3 as Authority 3
    participant A4 as Authority 4
    participant GW as Gateway
    participant BC as Blockchain/RTGS
    
    Note over C,BC: Phase 1: Withdrawal Request
    C->>C: Create WithdrawalOrder<br/>(amount, recipient_address,<br/>token_address, sequence)
    C->>C: Sign WithdrawalOrder<br/>(Ed25519 signature)
    C->>A1: WithdrawalRequestMessage<br/>(via mesh)
    C->>A2: WithdrawalRequestMessage
    C->>A3: WithdrawalRequestMessage
    C->>A4: WithdrawalRequestMessage
    
    Note over C,BC: Phase 2: Double-Spend Prevention
    par Parallel Double-Spend Check
        A1->>A1: Check Sequence Number<br/>(prevent replay)
        A2->>A2: Check Sequence Number
        A3->>A3: Check Sequence Number
        A4->>A4: Check Sequence Number
    end
    
    par Balance Verification
        A1->>A1: Verify Mesh Balance<br/>(sufficient funds)
        A2->>A2: Verify Mesh Balance
        A3->>A3: Verify Mesh Balance
        A4->>A4: Verify Mesh Balance
    end
    
    par Network Partition Check
        A1->>A2: Heartbeat Check
        A1->>A3: Heartbeat Check
        A1->>A4: Heartbeat Check
        A2->>A3: Heartbeat Check
        A2->>A4: Heartbeat Check
        A3->>A4: Heartbeat Check
    end
    
    Note over C,BC: Phase 3: Quorum Validation
    alt Quorum Achieved (≥3/4) & No Partition
        A1->>A1: Lock Mesh Balance<br/>(prevent double-spend)
        A2->>A2: Lock Mesh Balance
        A3->>A3: Lock Mesh Balance
        A4->>A4: Lock Mesh Balance
        
        A1->>A1: Sign WithdrawalOrder<br/>(authority signature)
        A2->>A2: Sign WithdrawalOrder
        A3->>A3: Sign WithdrawalOrder
        A4->>A4: Sign WithdrawalOrder
        
        A1->>C: WithdrawalResponseMessage<br/>(signed certificate)
        A2->>C: WithdrawalResponseMessage
        A3->>C: WithdrawalResponseMessage
        A4->>C: WithdrawalResponseMessage
    else Network Partition Detected
        A1->>C: WithdrawalResponseMessage<br/>(error: partition detected)
        A2->>C: WithdrawalResponseMessage<br/>(error: partition detected)
        Note over C,BC: Client must wait for partition resolution
    else Insufficient Quorum
        A1->>C: WithdrawalResponseMessage<br/>(error: insufficient quorum)
        Note over C,BC: Retry or abort withdrawal
    end
    
    Note over C,BC: Phase 4: Certificate Collection
    C->>C: Collect Quorum Signatures<br/>(≥2/3 required)
    C->>C: Create WithdrawalCertificate<br/>(with quorum proof)
    
    Note over C,BC: Phase 5: Gateway Submission
    C->>GW: Submit WithdrawalCertificate<br/>(via mesh or direct connection)
    GW->>GW: Validate Certificate<br/>(verify quorum signatures)
    
    alt Certificate Valid
        GW->>BC: Submit Settlement Transaction<br/>(unlock escrow, transfer funds)
        BC->>BC: Validate on Primary Ledger
        BC->>BC: Execute Settlement
        BC-->>GW: Settlement Confirmation
        GW->>GW: Update Mesh State<br/>(debit locked balance)
        GW->>A1: Broadcast State Update
        GW->>A2: Broadcast State Update
        GW->>A3: Broadcast State Update
        GW->>A4: Broadcast State Update
        
        A1->>A1: Unlock & Debit Balance
        A2->>A2: Unlock & Debit Balance
        A3->>A3: Unlock & Debit Balance
        A4->>A4: Unlock & Debit Balance
        
        GW-->>C: Withdrawal Finalized<br/>(transaction hash)
    else Certificate Invalid
        GW-->>C: Withdrawal Rejected<br/>(invalid certificate)
        Note over C,BC: Unlock mesh balance
        A1->>A1: Unlock Balance
        A2->>A2: Unlock Balance
        A3->>A3: Unlock Balance
        A4->>A4: Unlock Balance
    end
```

### 6.3 Network Partition Handling

```mermaid
graph TB
    subgraph "Partition Detection"
        HB[Heartbeat Messages]
        TC[Timeout Check]
        QV[Quorum Verification]
    end
    
    subgraph "Partition Scenarios"
        P1[Partition 1<br/>A1, A2]
        P2[Partition 2<br/>A3, A4]
        P3[No Partition<br/>All Connected]
    end
    
    subgraph "Handling Strategy"
        BL[Block Withdrawals]
        SYNC[State Synchronization]
        MERGE[Partition Merge]
    end
    
    HB --> TC
    TC --> QV
    QV --> P1
    QV --> P2
    QV --> P3
    
    P1 --> BL
    P2 --> BL
    P3 --> SYNC
    
    BL --> MERGE
    MERGE --> SYNC
    SYNC --> P3
```

### 6.4 Double-Spend Prevention Mechanism

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant A1 as Authority 1
    participant A2 as Authority 2
    participant A3 as Authority 3
    
    Note over C,A3: Attempt 1: Valid Withdrawal
    C->>A1: WithdrawalOrder(seq=10, amount=100)
    C->>A2: WithdrawalOrder(seq=10, amount=100)
    C->>A3: WithdrawalOrder(seq=10, amount=100)
    
    A1->>A1: Check Sequence: 10<br/>Last: 9 ✓
    A2->>A2: Check Sequence: 10<br/>Last: 9 ✓
    A3->>A3: Check Sequence: 10<br/>Last: 9 ✓
    
    A1->>A1: Lock Balance: 100
    A2->>A2: Lock Balance: 100
    A3->>A3: Lock Balance: 100
    
    A1->>C: Signed Certificate
    A2->>C: Signed Certificate
    A3->>C: Signed Certificate
    
    Note over C,A3: Attempt 2: Double-Spend Detection
    C->>A1: WithdrawalOrder(seq=10, amount=50)<br/>DUPLICATE SEQUENCE
    C->>A2: WithdrawalOrder(seq=10, amount=50)
    
    A1->>A1: Check Sequence: 10<br/>Last: 10 ✗<br/>ALREADY PROCESSED
    A2->>A2: Check Sequence: 10<br/>Last: 10 ✗<br/>ALREADY PROCESSED
    
    A1->>C: Reject: Duplicate Sequence
    A2->>C: Reject: Duplicate Sequence
    
    Note over C,A3: Attempt 3: Sequence Gap Detection
    C->>A1: WithdrawalOrder(seq=12, amount=50)<br/>SKIPPED SEQUENCE 11
    A1->>A1: Check Sequence: 12<br/>Last: 10 ✗<br/>GAP DETECTED
    
    A1->>C: Reject: Sequence Gap<br/>(Missing seq 11)
```

### 6.5 Withdrawal State Machine

```mermaid
stateDiagram-v2
    [*] --> RequestCreated: Client Creates Request
    
    RequestCreated --> Validating: Broadcast to Authorities
    
    Validating --> BalanceChecked: Verify Balance
    Validating --> Rejected: Invalid Request
    
    BalanceChecked --> SequenceChecked: Check Sequence Number
    SequenceChecked --> PartitionChecked: Check Network Partition
    
    PartitionChecked --> QuorumChecking: Verify Quorum
    PartitionChecked --> PartitionDetected: Network Partition
    
    QuorumChecking --> Signing: Quorum Achieved (≥2/3)
    QuorumChecking --> InsufficientQuorum: Quorum Not Met
    
    Signing --> BalanceLocked: Lock Balance
    BalanceLocked --> CertificateCreated: Collect Signatures
    
    CertificateCreated --> GatewaySubmitting: Submit to Gateway
    GatewaySubmitting --> PrimaryValidating: Gateway Validates
    
    PrimaryValidating --> PrimaryExecuting: Valid Certificate
    PrimaryValidating --> PrimaryRejected: Invalid Certificate
    
    PrimaryExecuting --> SettlementConfirmed: Primary Confirms
    SettlementConfirmed --> BalanceDebited: Update Mesh State
    BalanceDebited --> Finalized: Withdrawal Complete
    
    PartitionDetected --> WaitingForMerge: Wait for Partition Resolution
    WaitingForMerge --> PartitionChecked: Partition Resolved
    
    InsufficientQuorum --> Retrying: Retry Request
    Retrying --> Validating: Retry Broadcast
    
    PrimaryRejected --> BalanceUnlocked: Unlock Balance
    Rejected --> [*]
    Finalized --> [*]
    BalanceUnlocked --> [*]
```

---

## 7. Security Mechanisms

### 7.1 Multi-Layer Security Architecture

```mermaid
graph TB
    subgraph "Application Layer Security"
        AS[Ed25519 Signatures]
        SQ[Sequence Numbers]
        TS[Timestamps]
    end
    
    subgraph "Consensus Layer Security"
        BFT[Byzantine Fault Tolerance]
        QV[Quorum Verification]
        DS[Double-Spend Prevention]
    end
    
    subgraph "Network Layer Security"
        SAE[WPA3-SAE Authentication]
        AES[AES-128-CCM Encryption]
        MK[Key Management]
    end
    
    subgraph "Partition Resilience"
        HB[Heartbeat Monitoring]
        PC[Partition Detection]
        SM[State Merging]
    end
    
    AS --> BFT
    SQ --> DS
    TS --> QV
    
    BFT --> SAE
    QV --> AES
    DS --> MK
    
    SAE --> HB
    AES --> PC
    MK --> SM
```

### 7.2 Security Properties

#### 7.2.1 Double-Spend Prevention

**Mechanisms:**
1. **Sequence Number Tracking:** Each account maintains a strictly increasing sequence number
2. **Authority Validation:** All authorities verify sequence numbers before signing
3. **Balance Locking:** Temporary balance locks during withdrawal processing
4. **Quorum Requirement:** Multiple authorities must agree (≥2/3 quorum)

**Flow:**
```
Client → Authority: TransferOrder(seq=N)
Authority: Check if seq > last_processed_seq
  ├─ Yes: Process and update last_processed_seq
  └─ No: Reject (double-spend attempt)
```

#### 7.2.2 Network Partition Handling

**Detection:**
- Heartbeat messages between authorities
- Timeout-based partition detection
- Quorum availability check

**Handling:**
- Block withdrawals during partition
- Continue processing transfers within partition (if quorum maintained)
- Merge state when partition resolves
- Conflict resolution using timestamps and sequence numbers

**Partition Scenarios:**

```mermaid
graph LR
    subgraph "Scenario 1: Majority Partition"
        A1[Auth 1]
        A2[Auth 2]
        A3[Auth 3]
        A4[Auth 4]
        A1 -.->|Partition| A3
        A2 -.->|Partition| A4
        A1 <--> A2
        A3 <--> A4
    end
    
    subgraph "Scenario 2: Split Partition"
        B1[Auth 1]
        B2[Auth 2]
        B3[Auth 3]
        B1 -.->|Partition| B2
        B1 -.->|Partition| B3
        B2 -.->|Partition| B3
    end
```

**Resolution Strategy:**
1. **Detect Partition:** Authorities detect missing heartbeats
2. **Block Withdrawals:** Prevent withdrawals until partition resolves
3. **Continue Transfers:** Allow transfers within partition if quorum maintained
4. **State Merge:** When partition resolves, merge state using conflict resolution
5. **Validate Consistency:** Ensure no double-spends occurred during partition

---

## 8. Architecture Summary

### 8.1 Key Components

| Component | Responsibility | Key Features |
|-----------|---------------|--------------|
| **Mesh Network** | Physical connectivity | IEEE 802.11s, Multi-hop routing, Self-healing |
| **Client Node** | Payment initiation | Transfer creation, Certificate collection |
| **Authority Node** | Consensus & validation | BFT voting, State management, Signature generation |
| **Gateway Node** | External bridge | Primary ledger connection, Settlement execution |
| **Transport Layer** | Message delivery | TCP/UDP/Mesh routing, Reliable delivery |
| **Security Layer** | Protection mechanisms | Encryption, Authentication, Double-spend prevention |

### 8.2 Protocol Characteristics

- **Consensus:** Byzantine Fault Tolerant (BFT) with quorum voting
- **Quorum Requirement:** ≥2/3 of authorities must agree
- **Network Type:** IEEE 802.11s Mesh (supports 1000+ nodes)
- **Security:** Multi-layer (WPA3-SAE, AES-128-CCM, Ed25519)
- **Fault Tolerance:** Handles up to 33% Byzantine nodes
- **Partition Resilience:** Detects and handles network partitions
- **Double-Spend Prevention:** Sequence numbers + balance locking

### 8.3 Withdrawal Architecture Highlights

1. **Multi-Authority Validation:** Requires quorum of authorities
2. **Double-Spend Prevention:** Sequence number tracking + balance locking
3. **Partition Handling:** Blocks withdrawals during partitions, merges state on resolution
4. **Gateway Integration:** Secure connection to primary ledger/RTGS
5. **State Consistency:** Ensures mesh state matches primary ledger after withdrawal

---

## 9. Implementation Notes

### 9.1 Message Types

- `TRANSFER_REQUEST`: Client → Authority (transfer initiation)
- `TRANSFER_RESPONSE`: Authority → Client (signed certificate)
- `CONFIRMATION_REQUEST`: Client → Authority (confirmation broadcast)
- `WITHDRAWAL_REQUEST`: Client → Authority (withdrawal initiation)
- `WITHDRAWAL_RESPONSE`: Authority → Client (withdrawal certificate)
- `SYNC_REQUEST`: Node → Authority (state synchronization)
- `PEER_DISCOVERY`: Broadcast (service discovery)
- `HEARTBEAT`: Authority ↔ Authority (partition detection)

### 9.2 State Management

- **Account State:** Balance, sequence number, pending transfers
- **Authority State:** Committee membership, account shards, signatures
- **Network State:** Routing tables, peer connections, partition status

### 9.3 Performance Characteristics

- **Transfer Latency:** <100ms (single-hop), <500ms (multi-hop)
- **Throughput:** 80k+ TPS (theoretical, mesh-dependent)
- **Scalability:** 1000+ nodes supported
- **Recovery Time:** <2.3 seconds (node failure recovery)

---

**Document Status:** Complete  
**Last Updated:** January 2025  
**Author:** Architecture Documentation Team
