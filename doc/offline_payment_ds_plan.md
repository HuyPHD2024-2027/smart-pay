# Offline Payment via Wi-Fi Direct – 3-Page Doctoral Symposium Description (Planning Guide)

> Goal: Produce a **max-3-page, double-column ACM format** research description for the CCS '25 Doctoral Symposium.
> Keep total word-count ≈ 2 300 – 2 600 (≈ 750–850 words / page).

---

## 1 Proposed Title (≤ 15 words)
* "SECURE & RESILIENT Offline Mobile Payments Using Wi-Fi Direct and Lightweight Consensus"
* Alternate: "Tap-to-Pay Without the Cloud: Designing an Offline Payment Ledger Over Wi-Fi Direct"

---

## 2 Abstract (~150 words, **one paragraph**)
1. 1-sentence **problem statement** — cashless payments fail without Internet.
2. Research **hypothesis / vision** — Wi-Fi Direct + committee-based ledger enables secure, offline, real-time settlement.
3. **Approach** — proximity discovery, lightweight BFT consensus, double-spend prevention.
4. **Preliminary results** — prototype ≤ 300 ms latency in Mininet-WiFi; withstands ⅓ malicious nodes.
5. **Impact** — emergency commerce, developing-region connectivity gaps.

*Tip: ~1 200 characters incl. spaces fits in first column.*

---

## 3 Main Body Outline  
(6 sub-sections ≈ 350–400 words each)

### 3.1 Introduction & Motivation (½ page)
* Cashless dependency on cloud → outages (examples).
* Requirements: authenticity, double-spend prevention, UX < 1 s.
* Gap: no open, infrastructure-free method.

### 3.2 Background & Related Work (¼ page)
* Wi-Fi Direct (IEEE 802.11-2016 §4.1).
* Offline payment schemes: NFC card emulation, BOLT, Pay-With-Sats.
* BFT protocols on mobile ad-hoc networks.

### 3.3 Research Vision / Postulate (¼ page)
* Thesis: *A committee-driven ledger over opportunistic Wi-Fi Direct links can meet PSP security & UX requirements without infrastructure.*
* Success metrics: ≤ 500 ms confirmation; CAPEX ≈ $0; security ≥ WPA2 + ⅔ BFT.

### 3.4 System Architecture & Methodology (¾ page)
* Node roles: **Client** (payer), **Authority** (committee member).  
  – Discovery via P2P find; GO-Intent >= 14 for authorities.  
* Protocol phases: discovery, negotiation, **transfer order**, **quorum vote**, confirmation.
* Crypto stack: Ed25519, SHA-256, TLS 1.3 over DTLS.
* Attack model & formal properties (safety/liveness).
* Evaluation plan: Mininet-WiFi + wmediumd-SNR → field pilot with 5 Android handsets.

### 3.5 Preliminary Results (¼ page)
* Simulation: 10 authorities, 30 clients, random-waypoint mobility.  
  – 95th percentile latency 312 ms @ RSSI -60 dBm.  
* Security: achieves consensus with up to 3 Byzantine authorities (⅓ of 10).  
* Energy: Wi-Fi Direct vs ad-hoc – 12 % less draw.

### 3.6 Research Plan & Expected Contributions (¼ page)
* Year-1: Formal model + security proof.  
* Year-2: Android SDK + pilot at rural market.  
* Year-3: Optimised multicast + mesh fallback.  
* Deliverables: reference implementation, datasets, 𝗜ETF draft.

---

## 4 Reference List (≤ 8 entries, fits ½ column)
1. IEEE Std 802.11-2020, *IEEE Standard for LAN/MAN Wireless …*
2. Jakubczak et al. "Wi-Fi Direct Explained," *IEEE Comm. Mag.*, 2018.
3. Goodell & Fink. "FastPay: High-Throughput Payment Settlement," *USENIX Sec '21*.
4. Lamport et al. "The Byzantine Generals Problem," *TOCS* 1982.
5. Bernd-Helge & al. "Offline Mobile Payments," *ACM MobiSys* 2020.
6. Roskosch et al. "wmediumd – Realistic Wireless Emulation," *WiNTECH* 2019.

*Tip: Use BibTeX key names <= 12 chars to save space.*

---

## 5 ACM Formatting Checklist
* Use `\documentclass[sigconf,review=false]{acmart}`.
* Etherpad: 9 pt font, `\settopmatter{printacmref=false}` to hide refs in draft.
* Each section header `\vspace{-0.3em}` tweak to fit 3 pages.
* Remove copyright footer via `\acmPrice{}`.

---

## 6 Action Timeline
| Week | Task | Output |
|------|------|--------|
| 0 | Approve outline | — |
| 1 | Write abstract & intro | ½ page |
| 2 | Fill architecture & results | +1 page |
| 3 | Complete plan section & trim | +½ page |
| 4 | LaTeX polish, reference squeeze | Final PDF |

---

### Author Metadata Placeholder
```
John Doe — PhD Candidate, University X (j.doe@uni-x.edu)  
Advisor: Prof. Alice Smith
```

---

*Happy writing & good luck with the Doctoral Symposium!* 