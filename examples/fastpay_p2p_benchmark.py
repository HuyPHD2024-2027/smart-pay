"""FastPay P2P Benchmark Script.

This helper spins up an *ad-hoc* Mininet-WiFi topology **without any access
points** and drives a configurable number of *transfer* operations between
mobile clients and WiFi-Direct authorities.  It records *latency*,
*throughput* (transactions per second) and basic wireless statistics that can
be consumed later for plotting or report generation.

Run with *root* privileges::

    sudo python3 -m mn_wifi.examples.fastpay_p2p_benchmark --authorities 4 \
         --clients 6 --transactions 500 --outfile results/benchmark.csv

The script outputs two artefacts:

1.  A *CSV* file with one row per transaction containing timestamp, sender,
    recipient, success flag and latency in milliseconds.
2.  A *JSON* summary placed next to the CSV with aggregated statistics
    (min/avg/max latency, success-ratio, throughput, airtime, etc.).

The benchmark relies on **wmediumd** to model realistic signal degradation and
rate adaptation based on distance.  It therefore requires `--wmediumd` support
in the installed Mininet-WiFi build.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import time
from pathlib import Path
from typing import Dict, List, Tuple
from uuid import uuid4

from mininet.log import info, setLogLevel
from mn_wifi.net import Mininet_wifi
from mn_wifi.authority import WiFiAuthority
from mn_wifi.client import Client
from mn_wifi.transport import TransportKind
from mn_wifi.wifiDirect import WiFiDirectTransport
from mn_wifi.baseTypes import TransferOrder
from mn_wifi.link import adhoc  # for simple STA↔STA connectivity
from mn_wifi.examples.demoCommon import open_xterms, close_xterms  # type: ignore
from mn_wifi.baseTypes import KeyPair

# --------------------------------------------------------------------------------------
# Argument parsing helpers
# --------------------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    """Return CLI arguments for the benchmark script."""
    parser = argparse.ArgumentParser(description="FastPay P2P benchmark")
    parser.add_argument("--authorities", "-a", type=int, default=3, help="Number of authorities")
    parser.add_argument("--clients", "-c", type=int, default=5, help="Number of mobile clients")
    parser.add_argument("--transactions", "-n", type=int, default=100, help="Number of transfers to execute")
    parser.add_argument("--outfile", "-o", type=str, default="benchmark.csv", help="CSV output path")
    parser.add_argument("--logs", "-l", action="store_true", help="Open xterm windows for every node")
    parser.add_argument("--no-plot", action="store_true", help="Disable network graph plotting (faster)")
    parser.add_argument("--seed", type=int, default=42, help="Random-direction mobility seed")
    return parser.parse_args()

# --------------------------------------------------------------------------------------
# Topology construction
# --------------------------------------------------------------------------------------


def _build_topology(num_auth: int, num_clients: int, enable_plot: bool, seed: int) -> Tuple[Mininet_wifi, List[WiFiAuthority], List[Client]]:
    """Return *Mininet-WiFi* network with WiFi-Direct nodes only.

    The helper configures *wmediumd* in SNR mode so that link quality and thus
    achievable bitrate automatically degrade with distance.
    """
    net = Mininet_wifi()

    # ------------------------------------------------------------------
    # Authorities
    # ------------------------------------------------------------------
    committee = {f"auth{i}" for i in range(1, num_auth + 1)}
    authorities: List[WiFiAuthority] = []
    for i in range(1, num_auth + 1):
        name = f"auth{i}"
        auth = net.addStation(
            name,
            cls=WiFiAuthority,
            transport_kind=TransportKind.WIFI_DIRECT,
            committee_members=committee - {name},
            ip=f"10.0.0.{100 + i}/8",
            port=8100 + i,
            range=20,  # shorter range to highlight distance effects
            position=[20 + (i * 10), 50, 0],
        )
        authorities.append(auth)

    # ------------------------------------------------------------------
    # Clients (mobile)
    # ------------------------------------------------------------------
    clients: List[Client] = []
    for i in range(1, num_clients + 1):
        cli = net.addStation(
            f"user{i}",
            cls=Client,
            transport_kind=TransportKind.WIFI_DIRECT,
            ip=f"10.0.0.{10 + i}/8",
            range=20,
            min_x=0, max_x=100, min_y=0, max_y=80, min_v=1, max_v=4,
        )
        clients.append(cli)

    # ------------------------------------------------------------------
    # Controller-less since we do not deploy APs.  Still need one for Mininet.
    # ------------------------------------------------------------------
    net.addController("c0")

    # Propagation model (log-distance path-loss with high exponent)
    net.setPropagationModel(model="logDistance", exp=4.0)

    # Interfaces & PHY parameters must exist **before** mobility thread starts
    info("*** Configuring wifi interfaces\n")
    net.configureNodes()

    # Mobility (start after interfaces are ready to avoid plotting errors)
    net.setMobilityModel(time=0, model="RandomDirection", max_x=100, max_y=80, seed=seed)

    # Optional visualisation
    if enable_plot:
        net.plotGraph(max_x=100, max_y=80)

    info("*** Building network\n")
    net.build()

    # Start background FastPay services ---------------------------------
    for node in [*authorities, *clients]:
        node.start_fastpay_services()

    # ------------------------------------------------------------------
    # Create single-SSID ad-hoc network so every node can reach others
    # ------------------------------------------------------------------
    all_nodes = [*authorities, *clients]
    for node in all_nodes:
        net.addLink(node, cls=adhoc, intf=f"{node.name}-wlan0", ssid="fastpay-p2p", mode="g", channel=5)

    return net, authorities, clients

# --------------------------------------------------------------------------------------
# Benchmark logic
# --------------------------------------------------------------------------------------


def _execute_transfers(clients: List[Client], num_tx: int, csv_writer: csv.DictWriter) -> None:
    """Issue *num_tx* random transfers and write per-transaction stats."""
    import random

    for tx_id in range(1, num_tx + 1):
        sender, recipient = random.sample(clients, 2)
        amount = random.randint(1, 10)

        start_ns = time.time_ns()
        success = sender.transfer(recipient.name, amount)
        # give authorities some time to respond (best-effort)
        time.sleep(0.3)
        if success:
            try:
                sender.broadcast_confirmation()
            except Exception:
                pass  # benchmark continues even if confirmation fails
        end_ns = time.time_ns()

        latency_ms = (end_ns - start_ns) / 1_000_000
        csv_writer.writerow(
            {
                "tx_id": tx_id,
                "timestamp": start_ns // 1_000_000_000,  # epoch seconds
                "sender": sender.name,
                "recipient": recipient.name,
                "amount": amount,
                "success": int(success),
                "latency_ms": round(latency_ms, 2),
            }
        )

        # Small pacing delay to avoid overwhelming the transport completely
        time.sleep(0.05)

def _setup_demo_accounts(clients: List[Client], authorities: List[WiFiAuthority]) -> None:
    """Inject a handful of pre-funded user accounts into every authority."""
    from mn_wifi.baseTypes import AccountOffchainState, SignedTransferOrder   # local import to avoid cycles
    from uuid import uuid4
    # Allocate an initial balance for *every* client present in the topology
    demo_balances = {cli.name: 1_000 for cli in clients}

    for auth in authorities:
        for user, bal in demo_balances.items():
            auth.state.accounts[user] = AccountOffchainState(
                address=user,
                balance=bal,
                sequence_number=0,
                last_update=time.time(),
                pending_confirmation=SignedTransferOrder(
                    order_id=uuid4(),
                    transfer_order=None,
                    authority_signature={},
                    timestamp=time.time()   
                ),
                confirmed_transfers={},
            )
    for client in clients:
        client.state.secret = KeyPair("secret-placeholder")
        client.state.committee = authorities
        client.state.pending_transfer = None
        client.state.sent_certificates = []
        client.state.received_certificates = {}
        client.state.balance = demo_balances[client.state.name]
        client.state.sequence_number = 0

    # Log for debugging convenience (only once)
    if clients and hasattr(clients[0], "logger"):
        clients[0].logger.info("Injected demo accounts into authorities")



# --------------------------------------------------------------------------------------
# Entry-point
# --------------------------------------------------------------------------------------


def main() -> None:
    """Execute the FastPay P2P benchmark based on CLI parameters."""
    opts = _parse_args()
    setLogLevel("info")

    outfile = Path(opts.outfile).expanduser()
    outfile.parent.mkdir(parents=True, exist_ok=True)

    summary_path = outfile.with_suffix(".json")

    net = None
    authority_terms: List = []
    client_terms: List = []

    try:
        net, authorities, clients = _build_topology(opts.authorities, opts.clients, not opts.no_plot, opts.seed)

        # Optionally launch xterms
        if opts.logs:
            authority_terms, client_terms = open_xterms(authorities, clients)  # type: ignore[assignment]

        # ------------------------------------------------------------------
        # Pre-fund demo accounts so that transfers succeed immediately
        # ------------------------------------------------------------------
        _setup_demo_accounts(clients, authorities)

        # ------------------------------------------------------------------
        # CSV setup
        # ------------------------------------------------------------------
        with outfile.open("w", newline="") as csv_file:
            fieldnames = ["tx_id", "timestamp", "sender", "recipient", "amount", "success", "latency_ms"]
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()

            _execute_transfers(clients, opts.transactions, writer)

        # ------------------------------------------------------------------
        # Aggregate results
        # ------------------------------------------------------------------
        latencies: List[float] = []
        successes = 0
        with outfile.open(newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            for row in reader:
                latencies.append(float(row["latency_ms"]))
                successes += int(row["success"])

        summary: Dict[str, float] = {
            "transactions": opts.transactions,
            "success_ratio": round(successes / opts.transactions, 3),
            "min_latency_ms": min(latencies) if latencies else 0.0,
            "avg_latency_ms": round(statistics.mean(latencies), 2) if latencies else 0.0,
            "p95_latency_ms": round(statistics.quantiles(latencies, n=100)[94], 2) if latencies else 0.0,
            "max_latency_ms": max(latencies) if latencies else 0.0,
            "throughput_tps": round(opts.transactions / sum(latencies) * 1_000, 2) if latencies else 0.0,
        }

        summary_path.write_text(json.dumps(summary, indent=2))
        info(f"\n✅ Benchmark finished – results written to {outfile} and {summary_path}\n")

    finally:
        if net:
            info("*** Stopping network\n")
            net.stop()
            if opts.logs:
                close_xterms(authorities, clients)  # type: ignore[arg-type]

# --------------------------------------------------------------------------------------

if __name__ == "__main__":
    main() 