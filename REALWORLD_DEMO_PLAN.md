Title: Real-World BLE Mesh Offline Payments Demo Plan for Mininet-WiFi (FastPay-inspired)

Timestamp: 2025-08-08T00:00:00Z

Context
- You have a FastPay-inspired committee of authorities that reaches quorum on transfer orders inside Mininet-WiFi (mesh topology). Your research proposal focuses on an offline payment protocol using Bluetooth Low Energy (BLE) mesh among mobile devices, resilient to no-internet contexts, and you want to demonstrate a real-life path from phone → mesh → authorities → finality.
- Reference: “Interaction between virtual and real environments” in the Mininet-WiFi expert notes describes binding a physical network card to bridge real traffic into the virtual topology. See: https://github.com/ramonfontes/mn-wifi-ebook/blob/main/expert.md

Goals
- Demonstrate end-to-end transfers initiated from a mobile device and processed by the in-sim committee over a mesh, without requiring public internet.
- Provide a credible path to “real world” by bridging physical interfaces and/or BLE to the virtual network.
- Improve security, verifiability, latency, resilience, and UX claims in the proposal.

Solution Options
1) Wi‑Fi NIC Bridge + HTTP API
   - Approach: Use an external Wi‑Fi NIC in managed/AP/bridge mode to attach a real phone to a “gateway host” node in Mininet-WiFi. Run the existing mesh Internet bridge (HTTP server) inside the gateway; a simple mobile app or curl posts transfer {sender, recipient, amount}. The bridge forwards to authorities (already implemented via Client.transfer).
   - Pros: Easiest to demo; robust; uses existing examples (fastpay_mesh_internet_demo.py + MeshInternetBridge). Works on most laptops with supported NICs. Great for showing “real device in the loop”.
   - Cons: Uses Wi‑Fi not BLE; still convincing for supervisors but not BLE-specific.

2) BLE → HTTP Gateway (host side) [Chosen]
   - Approach: Run a small gateway on the host that accepts BLE notifications or, for portability, a local HTTP endpoint and forwards to the mesh bridge inside Mininet. Minimal BLE support via bleak is optional; fallback HTTP path keeps the demo reliable across OSes. File added: mn_wifi/examples/ble_gateway.py.
   - Pros: Direct storyline for “BLE mobile” while avoiding platform-specific pitfalls. Can still use Wi‑Fi NIC bridging to put the phone and gateway on same L2/L3. Clear, fast demo path with curl or a tiny mobile client.
   - Cons: Not a full BLE Mesh stack; it is a BLE-to-HTTP shim (good enough for demo/prototype).

3) In-sim BLE Mesh (btvirt) transport
   - Approach: Implement a new NetworkTransport that leverages mn_wifi.btvirt to simulate BLE links and routing. Extend client/authority to use TransportKind.BLE. Add example topologies.
   - Pros: Protocol-faithful; stronger research angle on BLE behavior.
   - Cons: Significantly more engineering (routing, GATT framing, reliability); harder to show live with phones quickly.

4) Dual-radio Phones: BLE for pairing, Wi‑Fi for data plane
   - Approach: Use BLE only for discovery/handshake; then the phone switches to Wi‑Fi (via physical NIC bridge) to send the actual transfer over the mesh HTTP bridge. BLE piece stays very small.
   - Pros: Strong “we use BLE” story while keeping reliability; simple.
   - Cons: Two radios to manage; may dilute the pure “BLE mesh” narrative.

Chosen Solution and Rationale
- Chosen: Option 2 (BLE → HTTP Gateway) combined with Option 1’s Wi‑Fi NIC bridging when demonstrating from a phone on the same LAN. This provides the fastest path to a live demo with real devices while keeping the architecture ready for deeper BLE work later.

Implementation Summary (Applied Changes)
- Added mn_wifi/examples/ble_gateway.py: a small HTTP forwarder with optional BLE scan hook, forwarding POST /transfer to the mesh bridge /transfer, which triggers Client.transfer.
- Reuse existing examples:
  - mn_wifi/examples/fastpay_mesh_internet_demo.py: spins up authorities/clients plus MeshInternetBridge.
  - mn_wifi/examples/mesh_internet_bridge.py: exposes /transfer and routes into Client.transfer.

How to Demo (Step-by-Step)
1) Start the mesh with gateway bridge inside Mininet-WiFi:
   - sudo python3 -m mn_wifi.examples.fastpay_mesh_internet_demo -a 5 -c 3 --internet -g 8080
   - Wait until it prints the bridge URL (e.g., http://10.0.0.254:8080).

2) Run the BLE gateway on the host:
   - python3 -m mn_wifi.examples.ble_gateway --bridge-url http://10.0.0.254:8080 --listen 0.0.0.0 --port 8099

3) Connect the phone to the gateway host network:
   - Follow “Interaction between virtual and real environments” guidance to bind a physical Wi‑Fi card to the Mininet-WiFi/GW host or to ensure the phone can reach the host’s 8099 HTTP port. See expert notes: https://github.com/ramonfontes/mn-wifi-ebook/blob/main/expert.md

4) From the phone (or any external machine on the LAN):
   - POST http://<gateway-host>:8099/transfer with JSON: {"sender":"user1","recipient":"user2","amount":25}
   - Observe logs in the Mininet CLI: transfer should reach authorities; use FastPay CLI (help_fastpay, balance) to verify state.

Security, Verifiability, Resilience, UX Enhancements
- Security:
  - Transport: run the gateway on a trusted host; restrict by firewall; migrate mesh bridge and gateway to HTTPS (self-signed for demo). Add HMAC signatures to /transfer body and verify in bridge before calling client.transfer.
  - Protocol: extend TransferOrder with real signatures (libsodium/NaCl or cryptography) and nonce/seq checks (already present). Store certificate bundles from authorities; verify quorum signatures before confirmation.
- Verifiability:
  - Add per-transfer audit log with hashes and timestamps at gateway and bridge. Expose /audit endpoint in bridge.
  - Deterministic JSON serialisation for signed payloads; include authority signatures in confirmation response and surface in CLI.
- Resilience (no internet):
  - Demo runs entirely without public internet. Optional NAT is only for showcasing external web UI; quorum and transfers are all in-sim mesh.
  - Add gateway queue-and-retry if the bridge is temporarily unreachable; persist unsent transfers (simple SQLite/JSON file).
- Performance and UX:
  - Add simple web UI (static HTML+JS) that hits the bridge /transfer and /authorities; or a minimal Flutter/React Native app for phones.
  - Preload users and show balances, confirmations, and quorum indicators; ensure sub-second local roundtrip for good UX.

Next Steps / TODOs
- Implement HMAC verification in mesh_internet_bridge.py for POST /transfer.
- Add HTTPS termination for bridge and gateway (self-signed certs).
- Add audit log and /audit route in mesh_internet_bridge.py.
- Optional: implement TransportKind.BLE and a basic BLE transport that reuses btvirt for in-sim experiments.
- Optional: small mobile app or PWA to initiate transfers and show balances.

Status
- success


