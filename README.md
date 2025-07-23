# Resilient Offline Payment Mesh – Research Prototype

This repository accompanies the CCS ’25 Doctoral-Symposium proposal *“Resilient Offline Payment Networks: Self-Healing Mesh Architecture for Infrastructure-Free Commerce.”*  It contains a fully-working prototype that couples IEEE 802.11s mesh networking with a FastPay-style, pre-funded side-chain to enable sub-second retail payments during Internet outages.

---



## 1  Prerequisites

* Ubuntu 20.04 (LTS) or later with kernel ≥ 5.x
* Python 3.8+
* Root privileges (for network namespaces)
* Mininet-WiFi 2.4.0+ — install via:
  ```bash
  sudo apt-get install git
  git clone https://github.com/intrig-unicamp/mininet-wifi
  cd mininet-wifi
  sudo util/install.sh -Wlnfv
  ```
* Project dependencies:
  ```bash
  pip install -r requirements.txt
  ```

---

## 3  Quick Demo (5 min)

```bash
# Start a 5-authority / 3-user mesh with CLI
sudo python3 -m mn_wifi.examples.fastpay_mesh_demo --authorities 5 --clients 3
```
Inside the CLI you can issue FastPay commands such as:
```bash
transfer user1 user2 100
broadcast_confirmation user1
balance user1
balance user2
infor auth1
```

---

## 4  Reproduce Evaluation Figures

Run all experiments (baseline, scaling, mobility, Wi-Fi Direct baseline) and generate a summary:
```bash
cd mininet-wifi/examples
sudo ./run_evaluation.sh
```
Results appear under `evaluation_results_*/` and are summarised in the terminal.

Expected baseline (50 Authorities, 200 Users):
| Metric | Median | 95th pct. | Success |
|--------|--------|-----------|---------|
| Latency | ≈ 1200 ms | ≈ 1500 ms | ≈ 97 % |

---

## 5  Next Steps

1. Port protocol to Android devices for real-world pilots.
2. Integrate Coconut-style privacy credentials and confidential balances.
3. Support committee rotation & on-chain weight updates.
4. Measure energy consumption on battery-powered hardware.

We welcome feedback—especially on evaluation methodology, privacy extensions, and incentive design.

---

## 6  Contact

*Huy D. Q.*, PhD Candidate — [huydo21052000@gmail.com]

---

> © 2025 Huy D. Q.  Licensed under Apache 2.0.  Powered by Mininet-WiFi. 
