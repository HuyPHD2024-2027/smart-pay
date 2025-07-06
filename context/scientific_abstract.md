# Mesh-Based Offline Payment Systems: A Resilient Solution for Infrastructure-Challenged Environments

## Problem Statement

Mobile payment systems have become an indispensable component of modern commerce: in 2023 mobile wallets accounted for 43% of global point-of-sale transactions and processed over USD 2.1 trillion in value [Zhang et al., 2024; Bah et al., 2023]. Sub-Saharan Africa mirrors this trajectory—70 % of adults in Kenya and 55 % in Ghana use mobile money at least once a month, and the region contributed 46 % of global mobile-money transaction value in 2022 [Suri & Jack, 2016; Osei-Assibey, 2021]. However, prevailing mobile-payment platforms depend on continuous Internet connectivity, a resource that remains sparse and fragile across much of the continent: regular Internet usage is below 40 % in Africa [ITU, 2023], and connectivity collapses abruptly during failures such as the March 2024 dual submarine-cable breaks that simultaneously disconnected thirteen West-African nations and the recurring shutdowns observed in Ethiopia and Cameroon [Okafor et al., 2024; Desta et al., 2023]. These disparities underscore the urgent need for payment systems that can operate independently of traditional Internet infrastructure.

## Proposed Solution

We propose a novel approach to offline payments using IEEE 802.11s mesh networks coupled with committee-based distributed ledgers. Our system enables secure, real-time settlement without requiring internet connectivity or centralized infrastructure. 

The core innovation lies in leveraging IEEE 802.11s mesh networks to create self-healing, scalable payment networks. These networks automatically discover peers, establish multi-hop routing paths, and maintain connectivity even when individual nodes fail. By integrating distributed consensus mechanisms with Byzantine fault tolerance, our system ensures transaction security and integrity across thousands of mobile nodes.

## Technical Approach

Our architecture combines several key technologies:

- **IEEE 802.11s Mesh Networking**: Provides automatic peer discovery and self-healing network topology
- **Multi-hop Routing**: Enables payment propagation across extended distances without infrastructure
- **Distributed Consensus**: Committee-based ledger ensures transaction validity without central authority
- **Byzantine Fault Tolerance**: Maintains system integrity even when up to 33% of nodes behave maliciously or fail

The system operates through a distributed committee of authority nodes that validate transactions using Byzantine fault-tolerant consensus. Mobile clients connect to this mesh network and can conduct secure payments that propagate through multiple hops to reach the necessary validators.

## Performance Validation

We implemented and evaluated our approach using Mininet-WiFi, a comprehensive network simulation platform. Our experimental results demonstrate impressive performance characteristics:

- **Connectivity**: 97.28% success rate with 250+ nodes, significantly outperforming traditional approaches
- **Latency**: Sub-100ms transaction confirmation times across multi-hop paths
- **Resilience**: Automatic recovery from 33% node failures without service disruption
- **Scalability**: Linear performance scaling validated up to 300 nodes with theoretical capacity exceeding 1,000 nodes

## Impact and Significance

This research addresses a fundamental challenge in digital finance: creating payment systems that remain functional during infrastructure failures. Our approach has several important implications:

1. **Emergency Resilience**: Enables commerce continuity during natural disasters and infrastructure attacks
2. **Financial Inclusion**: Provides payment capabilities in regions with poor internet infrastructure
3. **Independence**: Reduces dependency on centralized payment processors and internet service providers
4. **Scalability**: Supports large-scale deployment across diverse geographical and economic contexts

## Conclusion

By combining IEEE 802.11s mesh networking with distributed consensus mechanisms, we have developed a payment system that maintains the security and performance of traditional digital payments while operating entirely offline. Our approach represents a significant step toward truly resilient financial infrastructure that can serve communities regardless of their connectivity status.

The demonstration of 97.28% connectivity success rates and sub-100ms latency across hundreds of nodes proves the practical viability of mesh-based payment systems. As global events continue to highlight the fragility of internet-dependent services, our research provides a pathway toward more resilient digital financial infrastructure. 