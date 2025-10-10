#!/usr/bin/env python3
"""Comprehensive mesh benchmark for MeshPay offline payments.

This script builds a parameterized IEEE 802.11s mesh using Mininet-WiFi,
starts MeshPay authority/client services, generates configurable load, and
emits JSON/CSV summary metrics suitable for plotting.

Run with root privileges (Mininet-WiFi requirement), for example:
    sudo python3 -m examples.fastpay_mesh_benchmark --authorities 5 --clients 10 \
        --duration 30 --rate 2 --range 60 --json results/benchmark.json \
        --csv results/benchmark.csv
"""

from __future__ import annotations

import argparse
import json
import os
import random
import threading
import time
from typing import List, Optional, Tuple
from uuid import uuid4, UUID

from mininet.log import info, setLogLevel
from mn_wifi.link import mesh
from mn_wifi.net import Mininet_wifi

from meshpay.nodes.authority import WiFiAuthority
from meshpay.nodes.client import Client
from meshpay.messages import TransferResponseMessage
from meshpay.transport import TransportKind
# Reuse helper to seed accounts on authorities
from meshpay.examples.meshpay_demo import setup_test_accounts  # type: ignore[attr-defined]
from mn_wifi.mesh_metrics import MeshMetrics
from mn_wifi.node import Station  # noqa: F401 – reserved for future topologies
from mn_wifi.services.core.config import SUPPORTED_TOKENS


class BenchClient(Client):
    """Client subclass that records metrics for each transfer."""

    def __init__(self, *args, metrics: MeshMetrics, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self._metrics = metrics
        super().__init__(*args, **kwargs)

    def transfer(self, recipient: str, token_address: str, amount: int) -> bool:  # type: ignore[override]
        tx_id = uuid4()
        # NOTE: we cannot know exact wire bytes here; approximate payload size
        approx_bytes = 180
        self._metrics.record_tx_start(tx_id, bytes_sent=approx_bytes)
        ok = super().transfer(recipient, token_address, amount)
        if not ok:
            self._metrics.record_tx_failure(tx_id)
        # Stash tx_id on pending transfer for correlation in response
        if self.state.pending_transfer is not None:
            self.state.pending_transfer.order_id = tx_id
        return ok

    def handle_transfer_response(self, transfer_response: TransferResponseMessage) -> bool:
        # Approximate response bytes; could be refined using payload size
        approx_bytes = 220
        self._metrics.record_tx_success(transfer_response.transfer_order.order_id, bytes_received=approx_bytes)
        return super().handle_transfer_response(transfer_response)


def build_mesh(
    *,
    num_authorities: int,
    num_clients: int,
    node_range: int,
    transport: TransportKind,
) -> Tuple[Mininet_wifi, List[WiFiAuthority], List[BenchClient]]:
    """Create a simple IEEE 802.11s mesh topology for benchmarking."""
    net = Mininet_wifi()

    # Authorities -----------------------------------------------------------------
    authorities: List[WiFiAuthority] = []
    committee = {f"auth{i}" for i in range(1, num_authorities + 1)}
    for i in range(1, num_authorities + 1):
        name = f"auth{i}"
        auth = net.addStation(
            name,
            cls=WiFiAuthority,
            committee_members=committee - {name},
            ip=f"10.0.0.{10 + i}/8",
            port=8000 + i,
            range=node_range,
            txpower=20,
        )
        authorities.append(auth)

    # Clients ---------------------------------------------------------------------
    metrics = MeshMetrics(run_label="benchmark")
    clients: List[BenchClient] = []
    for i in range(1, num_clients + 1):
        name = f"user{i}"
        client = net.addStation(  # type: ignore[assignment]
            name,
            cls=BenchClient,
            metrics=metrics,
            transport_kind=transport,
            ip=f"10.0.0.{20 + i}/8",
            port=9000 + i,
            range=node_range,
            txpower=15,
        )
        clients.append(client)

    # Configure nodes and mesh links ---------------------------------------------
    net.configureNodes()
    for i in range(1, num_authorities + 1):
        net.addLink(authorities[i - 1], cls=mesh, ssid="meshNet", intf=f"auth{i}-wlan0", channel=5, ht_cap="HT40+")
    for i in range(1, num_clients + 1):
        net.addLink(clients[i - 1], cls=mesh, ssid="meshNet", intf=f"user{i}-wlan0", channel=5, ht_cap="HT40+")

    # Assign committee (all authorities) to each client ---------------------------
    for client in clients:
        client.state.committee = authorities

    return net, authorities, clients


def pick_token_address() -> str:
    """Return a token address from the configured SUPPORTED_TOKENS mapping."""
    # Prefer USDC/USDT if present, else first value
    for symbol in ("USDC", "USDT"):
        if symbol in SUPPORTED_TOKENS:
            return SUPPORTED_TOKENS[symbol]["address"]
    return next(iter(SUPPORTED_TOKENS.values()))["address"]


def run_load(
    *,
    clients: List[BenchClient],
    duration_s: int,
    rate_per_client: float,
    token_address: str,
    amount: int,
) -> None:
    """Generate transfer load from each client for a fixed duration."""
    stop_at = time.time() + duration_s

    def worker(me: BenchClient) -> None:
        interval = 1.0 / max(rate_per_client, 1e-9)
        idx = int(me.name.replace("user", ""))
        rng = random.Random(idx * 1337)
        while time.time() < stop_at:
            # Choose a random recipient distinct from the sender
            candidates = [c for c in clients if c.name != me.name]
            if not candidates:
                break
            recipient = rng.choice(candidates).name
            me.transfer(recipient, token_address, amount)
            time.sleep(interval)

    threads: List[threading.Thread] = [threading.Thread(target=worker, args=(c,), daemon=True) for c in clients]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=duration_s + 5)


def write_outputs(
    metrics: MeshMetrics,
    *,
    json_path: Optional[str],
    csv_path: Optional[str],
    latencies_path: Optional[str],
    explicit_duration_s: Optional[float],
) -> None:
    """Persist metrics to optional JSON/CSV outputs and raw latencies CSV."""
    if json_path:
        os.makedirs(os.path.dirname(json_path) or ".", exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(metrics.to_json(explicit_duration_s=explicit_duration_s))
    if csv_path:
        os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
        header = ",".join(MeshMetrics.csv_header())
        row = ",".join(metrics.to_csv_row(explicit_duration_s=explicit_duration_s))
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write(header + "\n")
            f.write(row + "\n")
    if latencies_path:
        os.makedirs(os.path.dirname(latencies_path) or ".", exist_ok=True)
        with open(latencies_path, "w", encoding="utf-8") as f:
            f.write("latency_ms\n")
            for v in metrics.get_latency_samples_ms():
                f.write(f"{v:.3f}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MeshPay mesh benchmark")
    parser.add_argument("--authorities", type=int, default=5, help="number of authorities")
    parser.add_argument("--clients", type=int, default=5, help="number of clients")
    parser.add_argument("--duration", type=int, default=30, help="benchmark duration (seconds)")
    parser.add_argument("--rate", type=float, default=1.0, help="transactions per second, per client")
    parser.add_argument("--range", type=int, default=58, help="transmission range for all nodes (meters)")
    parser.add_argument("--transport", type=str, choices=["tcp", "udp", "wifi_direct"], default="tcp")
    parser.add_argument("--amount", type=int, default=1, help="transfer amount per tx")
    parser.add_argument("--json", type=str, default="results/benchmark.json", help="output JSON path")
    parser.add_argument("--csv", type=str, default="results/benchmark.csv", help="output CSV summary path")
    parser.add_argument("--latencies", type=str, default="results/latencies.csv", help="output raw latencies CSV path")
    parser.add_argument("--loglevel", type=str, default="info", help="mininet log level")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setLogLevel(args.loglevel)

    info("\n🚀 MeshPay Mesh Benchmark\n")
    info(f"   Authorities: {args.authorities}\n")
    info(f"   Clients: {args.clients}\n")
    info(f"   Duration: {args.duration}s\n")
    info(f"   Rate: {args.rate} tx/s/client\n")
    info(f"   Range: {args.range} m\n")
    info(f"   Transport: {args.transport}\n")

    transport = {
        "tcp": TransportKind.TCP,
        "udp": TransportKind.UDP,
        "wifi_direct": TransportKind.WIFI_DIRECT,
    }[args.transport]

    json_out = args.json
    csv_out = args.csv
    latencies_out = args.latencies

    net = None
    try:
        net, authorities, clients = build_mesh(
            num_authorities=args.authorities,
            num_clients=args.clients,
            node_range=args.range,
            transport=transport,
        )

        # Build network and start services
        info("*** Building mesh network\n")
        net.build()

        info("*** Starting authority services\n")
        for a in authorities:
            a.start_fastpay_services(False)

        info("*** Seeding accounts on authorities\n")
        setup_test_accounts(authorities, clients)

        info("*** Starting client services\n")
        for c in clients:
            c.start_fastpay_services()

        info("*** Stabilizing mesh\n")
        time.sleep(3)

        token_address = pick_token_address()

        # Metrics are stored on the first client's metrics instance (shared)
        metrics: MeshMetrics = clients[0]._metrics  # type: ignore[attr-defined]

        t_start = time.time()
        run_load(
            clients=clients,
            duration_s=args.duration,
            rate_per_client=args.rate,
            token_address=token_address,
            amount=args.amount,
        )
        duration_s = time.time() - t_start

        info("*** Benchmark complete – computing metrics\n")
        print(metrics.to_json(explicit_duration_s=duration_s))
        write_outputs(
            metrics,
            json_path=json_out,
            csv_path=csv_out,
            latencies_path=latencies_out,
            explicit_duration_s=duration_s,
        )

    finally:
        if net is not None:
            info("*** Stopping mesh network\n")
            try:
                net.stop()
            except Exception:  # pragma: no cover – defensive cleanup
                pass


if __name__ == "__main__":
    main()
