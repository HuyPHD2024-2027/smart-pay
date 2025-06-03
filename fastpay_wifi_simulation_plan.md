# FastPay WiFi Simulation Plan

## 1. Project Structure Overview

```
fastpay-wifi-sim/
├── core/
│   ├── __init__.py
│   ├── authority.py          # Authority node implementation
│   ├── client.py             # Client node implementation
│   ├── committee.py          # Committee management
│   ├── messages.py           # Message types and protocols
│   └── base_types.py         # Basic data types
├── network/
│   ├── __init__.py
│   ├── topology.py           # Network topology definitions
│   ├── wireless_channel.py   # Wireless channel modeling
│   └── p2p_protocol.py       # P2P communication protocol
├── simulation/
│   ├── __init__.py
│   ├── scenarios.py          # Simulation scenarios
│   ├── metrics.py            # Performance metrics collection
│   └── visualization.py      # Real-time visualization
├── experiments/
│   ├── __init__.py
│   ├── offline_payment.py    # Offline payment experiments
│   ├── network_disruption.py # Network disruption scenarios
│   └── scalability_test.py   # Scalability experiments
├── config/
│   ├── default_config.yaml   # Default configuration
│   └── experiment_configs/   # Specific experiment configs
└── main.py                   # Main entry point
```

## 2. Core Module Implementation Plan

### 2.1 Authority Node (`core/authority.py`)
```python
# Key components to implement:
class WiFiAuthority:
    """Authority node that runs on mininet-wifi host"""
    - authority_state: FastPayAuthorityState
    - network_interface: WiFiInterface
    - p2p_connections: Dict[AuthorityName, Connection]
    - message_queue: Queue
    - performance_metrics: MetricsCollector
    
    # Methods:
    - handle_transfer_order()
    - handle_confirmation_order()
    - broadcast_to_peers()
    - sync_with_committee()
```

### 2.2 Client Node (`core/client.py`)
```python
class WiFiClient:
    """Client that performs P2P transactions"""
    - client_state: FastPayClientState
    - network_interface: WiFiInterface
    - nearby_peers: List[ClientAddress]
    - offline_transaction_queue: Queue
    
    # Methods:
    - transfer_to_peer()
    - discover_nearby_peers()
    - sync_when_online()
```

## 3. Network Module Implementation Plan

### 3.1 Topology (`network/topology.py`)
```python
class FastPayWiFiTopology:
    """Define network topology for simulation"""
    - create_authority_cluster()
    - create_client_zones()
    - setup_intermittent_connectivity()
    - configure_network_partitions()
```

### 3.2 P2P Protocol (`network/p2p_protocol.py`)
```python
class P2PProtocol:
    """Handle P2P communication between nodes"""
    - discover_peers()
    - establish_connection()
    - handle_offline_transactions()
    - sync_transaction_history()
```

## 4. Simulation Scenarios

### 4.1 Offline Payment Scenario
```python
def offline_payment_simulation():
    # 1. Create network with intermittent connectivity
    # 2. Deploy 4-8 authorities in different regions
    # 3. Create 20-50 clients in different zones
    # 4. Simulate offline P2P transactions
    # 5. Periodically restore connectivity for sync
    # 6. Measure transaction finality and consistency
```

### 4.2 Network Disruption Scenario
```python
def network_disruption_simulation():
    # 1. Setup stable network
    # 2. Start normal transactions
    # 3. Introduce network partitions
    # 4. Continue P2P transactions in isolated zones
    # 5. Restore connectivity and measure recovery
```

## 5. Implementation Steps (Simple Tracking)

### Week 1-2: Core Components
- [ ] Day 1-2: Set up project structure and dependencies
- [ ] Day 3-4: Implement `WiFiAuthority` class with basic FastPay logic
- [ ] Day 5-6: Implement `WiFiClient` class for P2P transactions
- [ ] Day 7-8: Create message types and serialization
- [ ] Day 9-10: Build committee management and voting logic

### Week 3-4: Network Integration
- [ ] Day 11-12: Create basic mininet-wifi topology
- [ ] Day 13-14: Implement P2P discovery protocol
- [ ] Day 15-16: Build offline transaction queue
- [ ] Day 17-18: Add network disruption simulation
- [ ] Day 19-20: Implement sync mechanisms

### Week 5-6: Experiments and Testing
- [ ] Day 21-22: Create offline payment experiment
- [ ] Day 23-24: Build metrics collection system
- [ ] Day 25-26: Add visualization dashboard
- [ ] Day 27-28: Run scalability tests
- [ ] Day 29-30: Performance optimization and documentation

## 6. Key Files to Create

### 6.1 `main.py` - Entry Point
```python
#!/usr/bin/env python
"""
FastPay WiFi Simulation
Main entry point for running simulations
"""
import argparse
from simulation.scenarios import run_scenario

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scenario', choices=['offline', 'disruption', 'scale'])
    parser.add_argument('--authorities', type=int, default=4)
    parser.add_argument('--clients', type=int, default=20)
    parser.add_argument('--duration', type=int, default=300)
    args = parser.parse_args()
    
    run_scenario(args)

if __name__ == '__main__':
    main()
```

### 6.2 `core/authority.py` - Authority Implementation
```python
class WiFiAuthority:
    def __init__(self, name, host, committee):
        self.name = name
        self.host = host  # mininet host
        self.committee = committee
        self.state = {}  # Account states
        self.pending_transfers = {}
        
    def start_server(self):
        """Start authority server on mininet host"""
        # Implementation here
        
    def handle_transfer_order(self, order):
        """Process transfer order from client"""
        # Implementation here
```

## 7. Configuration Example

### `config/default_config.yaml`
```yaml
simulation:
  duration: 300  # seconds
  log_level: INFO

network:
  topology: mesh
  channel: 11
  mode: g
  range: 100  # meters

authorities:
  count: 4
  shards_per_authority: 2
  
clients:
  count: 20
  initial_balance: 1000
  
transactions:
  rate: 10  # per second
  amount_range: [1, 100]
  
offline_mode:
  connectivity_pattern: intermittent
  offline_duration: [10, 60]  # seconds
  online_duration: [5, 15]  # seconds
```

## 8. Simple Tracking Checklist

### Phase 1: Setup (Week 1)
- [ ] Create project directory structure
- [ ] Set up Python virtual environment
- [ ] Install dependencies (mininet-wifi, fastpay requirements)
- [ ] Create base classes for Authority and Client

### Phase 2: Core Implementation (Week 2-3)
- [ ] Implement authority state management
- [ ] Create client transaction logic
- [ ] Build P2P communication protocol
- [ ] Add offline transaction queue

### Phase 3: Network Simulation (Week 4)
- [ ] Create mininet-wifi topology
- [ ] Implement network disruption scenarios
- [ ] Add connectivity management
- [ ] Build sync mechanisms

### Phase 4: Testing & Experiments (Week 5-6)
- [ ] Create test scenarios
- [ ] Implement metrics collection
- [ ] Run experiments
- [ ] Document results

## 9. Key Differences from Original FastPay

1. **Network Layer**: Replace TCP/IP with WiFi P2P communication
2. **Offline Support**: Add transaction queuing for offline periods
3. **Lightweight Validation**: Implement partial validation for offline transactions
4. **Sync Protocol**: Add periodic synchronization when connectivity is restored
5. **Network Awareness**: Authorities adapt to network conditions

## 10. Success Metrics

- Transaction success rate in offline mode
- Time to finality after connectivity restoration
- Network partition tolerance
- P2P discovery efficiency
- Resource usage on constrained devices 