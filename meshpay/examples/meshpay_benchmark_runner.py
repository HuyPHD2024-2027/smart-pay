#!/usr/bin/env python3
"""MeshPay Benchmark Runner - Simplified emulation script with TPS targeting.

This script creates real Mininet-WiFi mesh networks with configurable authority
count and target throughput (TPS), automatically scaling clients and collecting
performance metrics.

Run with root privileges (Mininet-WiFi requirement):
    sudo python3 -m meshpay.examples.meshpay_benchmark_runner \
        --authorities 10 --tps 2000 --duration 60 --range 10 \
        --output results/bench_10auth_2000tps.csv

Examples:
    # Simple benchmark with 5 authorities targeting 500 TPS
    sudo python3 -m meshpay.examples.meshpay_benchmark_runner \
        --authorities 5 --tps 500 --duration 60

    # Benchmark with faulty nodes
    sudo python3 -m meshpay.examples.meshpay_benchmark_runner \
        --authorities 10 --faulty 3 --tps 150 --duration 60

    # Different transmission ranges
    sudo python3 -m meshpay.examples.meshpay_benchmark_runner \
        --authorities 10 --tps 2000 --range 20 --duration 60
"""

from __future__ import annotations

import argparse
import os
import random
import threading
import time
from typing import List, Tuple
from uuid import uuid4

from mininet.log import info, setLogLevel
from mn_wifi.link import mesh
from mn_wifi.net import Mininet_wifi

from meshpay.nodes.authority import WiFiAuthority
from meshpay.nodes.client import Client
from meshpay.messages import TransferResponseMessage
from meshpay.transport import TransportKind
from meshpay.examples.meshpay_demo import setup_test_accounts
from mn_wifi.mesh_metrics import MeshMetrics
from mn_wifi.services.core.config import SUPPORTED_TOKENS


class BenchClient(Client):
    """Client subclass that records metrics for each transfer."""

    def __init__(self, *args, metrics: MeshMetrics, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self._metrics = metrics
        self._transfer_start_times = {}
        super().__init__(*args, **kwargs)

    def transfer(self, recipient: str, token_address: str, amount: int) -> bool:  # type: ignore[override]
        tx_id = uuid4()
        approx_bytes = 180
        self._metrics.record_tx_start(tx_id, bytes_sent=approx_bytes)
        self._transfer_start_times[tx_id] = time.time()
        ok = super().transfer(recipient, token_address, amount)
        if not ok:
            self._metrics.record_tx_failure(tx_id)
            self._transfer_start_times.pop(tx_id, None)
        if self.state.pending_transfer is not None:
            self.state.pending_transfer.order_id = tx_id
        return ok

    def handle_transfer_response(
        self,
        transfer_response: TransferResponseMessage,
        authority_name: str = "unknown",
    ) -> bool:
        """Handle transfer response and track weighted quorum latency."""
        approx_bytes = 220
        tx_id = transfer_response.transfer_order.order_id
        self._metrics.record_tx_success(tx_id, bytes_received=approx_bytes)
        
        result = super().handle_transfer_response(transfer_response, authority_name)
        
        if self.state.quorum_reached_time is not None and tx_id in self._transfer_start_times:
            start_time = self._transfer_start_times[tx_id]
            quorum_latency_ms = (self.state.quorum_reached_time - start_time) * 1000.0
            self._metrics.record_quorum_latency(tx_id, quorum_latency_ms)
            del self._transfer_start_times[tx_id]
        
        if transfer_response.authority_weight > 0:
            self._metrics.record_authority_weight(authority_name, transfer_response.authority_weight)
        
        return result


def calculate_client_config(target_tps: int) -> Tuple[int, float]:
    """Calculate optimal client count and per-client transaction rate.
    
    Args:
        target_tps: Target transactions per second for the entire network
        
    Returns:
        Tuple of (num_clients, rate_per_client)
    """
    # Use enough clients to distribute load realistically
    # Minimum 5 clients, or scale up for higher TPS
    num_clients = max(5, target_tps // 2)
    rate_per_client = target_tps / num_clients
    return num_clients, rate_per_client


def build_mesh(
    *,
    num_authorities: int,
    num_clients: int,
    node_range: int,
    transport: TransportKind,
) -> Tuple[Mininet_wifi, List[WiFiAuthority], List[BenchClient]]:
    """Create IEEE 802.11s mesh topology for benchmarking.
    
    Args:
        num_authorities: Number of authority nodes
        num_clients: Number of client nodes
        node_range: Transmission range in meters
        transport: Transport protocol to use
        
    Returns:
        Tuple of (network, authorities, clients)
    """
    net = Mininet_wifi()

    # Create authorities
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

    # Create clients with shared metrics
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

    # Configure mesh networking
    net.configureNodes()
    for i in range(1, num_authorities + 1):
        net.addLink(
            authorities[i - 1],
            cls=mesh,
            ssid="meshNet",
            intf=f"auth{i}-wlan0",
            channel=5,
            ht_cap="HT40+",
        )
    for i in range(1, num_clients + 1):
        net.addLink(
            clients[i - 1],
            cls=mesh,
            ssid="meshNet",
            intf=f"user{i}-wlan0",
            channel=5,
            ht_cap="HT40+",
        )

    # Assign committee to each client
    for client in clients:
        client.state.committee = authorities

    return net, authorities, clients


def simulate_faulty_nodes(authorities: List[WiFiAuthority], num_faulty: int) -> List[WiFiAuthority]:
    """Simulate faulty nodes by stopping random authorities.
    
    Args:
        authorities: List of all authority nodes
        num_faulty: Number of authorities to make faulty
        
    Returns:
        List of faulty authorities
    """
    if num_faulty == 0:
        return []
    
    if num_faulty >= len(authorities):
        info(f"*** Warning: Cannot make {num_faulty} authorities faulty (only {len(authorities)} total)\n")
        num_faulty = max(0, len(authorities) - 1)
    
    faulty = random.sample(authorities, num_faulty)
    for auth in faulty:
        # Stop the authority service to simulate Byzantine fault
        auth.stop()
        info(f"*** Simulating fault: {auth.name} stopped\n")
    
    return faulty


def pick_token_address() -> str:
    """Return a token address from configured SUPPORTED_TOKENS."""
    for symbol in ("MUSD", "USDC", "USDT"):
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
    """Generate transfer load from each client for fixed duration.
    
    Args:
        clients: List of client nodes
        duration_s: Benchmark duration in seconds
        rate_per_client: Transactions per second per client
        token_address: Token to use for transfers
        amount: Transfer amount per transaction
    """
    stop_at = time.time() + duration_s
    stop_event = threading.Event()

    def monitor_quorum(me: BenchClient) -> None:
        """Monitor and broadcast weighted quorum confirmations."""
        quorum_threshold = 2.0 / 3.0
        while not stop_event.is_set():
            pending = me.state.pending_transfer
            if pending is None:
                time.sleep(0.05)
                continue

            total_weight = sum(cert.weight for cert in me.state.weighted_certificates)
            if total_weight >= quorum_threshold:
                me.broadcast_confirmation()
                continue

            time.sleep(0.05)

    def worker(me: BenchClient) -> None:
        """Generate transactions at specified rate."""
        interval = 1.0 / max(rate_per_client, 1e-9)
        idx = int(me.name.replace("user", ""))
        rng = random.Random(idx * 1337)
        while time.time() < stop_at:
            if me.state.pending_transfer is not None:
                time.sleep(0.05)
                continue
            candidates = [c for c in clients if c.name != me.name]
            if not candidates:
                break
            recipient = rng.choice(candidates).name
            me.transfer(recipient, token_address, amount)
            time.sleep(interval)

    # Start monitor and worker threads
    monitor_threads: List[threading.Thread] = [
        threading.Thread(target=monitor_quorum, args=(c,), daemon=True) for c in clients
    ]
    threads: List[threading.Thread] = [
        threading.Thread(target=worker, args=(c,), daemon=True) for c in clients
    ]
    
    for monitor in monitor_threads:
        monitor.start()
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=duration_s + 5)
    stop_event.set()
    for monitor in monitor_threads:
        monitor.join(timeout=5)


def output_results(
    metrics: MeshMetrics,
    output_path: str,
    authorities: int,
    faulty: int,
    range_m: int,
    voting_mode: str,
    explicit_duration_s: float,
) -> None:
    """Output benchmark results in CSV format compatible with plotting script.
    
    Args:
        metrics: Collected metrics
        output_path: Path to output CSV file
        authorities: Number of authorities
        faulty: Number of faulty authorities
        range_m: Transmission range in meters
        voting_mode: Voting mode used (weighted/normal)
        explicit_duration_s: Actual benchmark duration
    """
    # Get summary metrics
    summary_json = metrics.to_json(explicit_duration_s=explicit_duration_s)
    import json
    summary = json.loads(summary_json)
    
    actual_tps = summary.get('throughput_tps', 0.0)
    avg_latency_ms = summary.get('avg_latency_ms', 0.0)
    avg_latency_s = avg_latency_ms / 1000.0
    success_rate = summary.get('success_rate_pct', 0.0)
    
    # Create output directory if needed
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    
    # Write CSV in plotting script format
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("authorities,faulty_nodes,voting_type,transmission_range_m,throughput_tps,avg_latency_s\n")
        f.write(f"{authorities},{faulty},{voting_mode},{range_m},{actual_tps:.2f},{avg_latency_s:.3f}\n")
    
    info(f"*** Benchmark Results:\n")
    info(f"   Actual TPS: {actual_tps:.2f}\n")
    info(f"   Avg Latency: {avg_latency_s:.3f}s\n")
    info(f"   Success Rate: {success_rate:.1f}%\n")
    info(f"✓ Results saved to: {output_path}\n")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="MeshPay Benchmark Runner - Emulation with TPS targeting",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Simple benchmark with 10 authorities targeting 2000 TPS
  sudo python3 -m meshpay.examples.meshpay_benchmark_runner \\
      --authorities 10 --tps 2000 --duration 60 --range 10

  # Benchmark with faulty nodes
  sudo python3 -m meshpay.examples.meshpay_benchmark_runner \\
      --authorities 10 --faulty 3 --tps 150 --duration 60

  # Multiple runs for different TPS targets
  for tps in 500 1000 2000 3000; do
      sudo python3 -m meshpay.examples.meshpay_benchmark_runner \\
          --authorities 10 --tps $tps --output results/10auth_${tps}tps.csv
  done
        """,
    )
    parser.add_argument(
        "--authorities",
        type=int,
        default=5,
        help="number of authority nodes (default: 5)",
    )
    parser.add_argument(
        "--tps",
        type=int,
        default=100,
        help="target transactions per second for entire network (default: 100)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="benchmark duration in seconds (default: 60)",
    )
    parser.add_argument(
        "--range",
        type=int,
        default=10,
        help="transmission range for all nodes in meters (default: 10)",
    )
    parser.add_argument(
        "--faulty",
        type=int,
        default=0,
        help="number of faulty/offline authorities (default: 0)",
    )
    parser.add_argument(
        "--voting-mode",
        type=str,
        choices=["weighted", "normal"],
        default="weighted",
        help="voting mode: weighted or normal (default: weighted)",
    )
    parser.add_argument(
        "--transport",
        type=str,
        choices=["tcp", "udp", "wifi_direct"],
        default="tcp",
        help="transport protocol (default: tcp)",
    )
    parser.add_argument(
        "--amount",
        type=int,
        default=1,
        help="transfer amount per transaction (default: 1)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="results/benchmark_result.csv",
        help="output CSV file path (default: results/benchmark_result.csv)",
    )
    parser.add_argument(
        "--loglevel",
        type=str,
        default="info",
        help="mininet log level (default: info)",
    )
    return parser.parse_args()


def main() -> None:
    """Main entry point for the benchmark runner."""
    args = parse_args()
    setLogLevel(args.loglevel)

    # Calculate client configuration based on target TPS
    num_clients, rate_per_client = calculate_client_config(args.tps)

    info("\n🚀 MeshPay Benchmark Runner\n")
    info(f"   Authorities: {args.authorities}\n")
    info(f"   Target TPS: {args.tps}\n")
    info(f"   Duration: {args.duration}s\n")
    info(f"   Range: {args.range}m\n")
    info(f"   Faulty nodes: {args.faulty}\n")
    info(f"   Voting mode: {args.voting_mode}\n")
    info(f"   Calculated clients: {num_clients} ({rate_per_client:.2f} tx/s each)\n")
    info(f"   Transport: {args.transport}\n")

    transport = {
        "tcp": TransportKind.TCP,
        "udp": TransportKind.UDP,
        "wifi_direct": TransportKind.WIFI_DIRECT,
    }[args.transport]

    net = None
    try:
        # Build mesh network
        net, authorities, clients = build_mesh(
            num_authorities=args.authorities,
            num_clients=num_clients,
            node_range=args.range,
            transport=transport,
        )

        info("*** Building mesh network\n")
        net.build()

        info("*** Starting authority services\n")
        for auth in authorities:
            auth.start_fastpay_services(False)

        # Simulate faulty nodes if requested
        if args.faulty > 0:
            info(f"*** Simulating {args.faulty} faulty authorities\n")
            faulty_authorities = simulate_faulty_nodes(authorities, args.faulty)
            info(f"*** Faulty authorities: {[a.name for a in faulty_authorities]}\n")

        info("*** Seeding accounts on authorities\n")
        setup_test_accounts(authorities, clients)

        info("*** Starting client services\n")
        for client in clients:
            client.start_fastpay_services()

        info("*** Stabilizing mesh network\n")
        time.sleep(3)

        token_address = pick_token_address()
        info(f"*** Using token: {token_address}\n")

        # Get shared metrics instance
        metrics: MeshMetrics = clients[0]._metrics  # type: ignore[attr-defined]

        info(f"*** Running benchmark for {args.duration}s...\n")
        t_start = time.time()
        run_load(
            clients=clients,
            duration_s=args.duration,
            rate_per_client=rate_per_client,
            token_address=token_address,
            amount=args.amount,
        )
        duration_s = time.time() - t_start

        info("*** Benchmark complete\n")
        
        # Output results
        output_results(
            metrics=metrics,
            output_path=args.output,
            authorities=args.authorities,
            faulty=args.faulty,
            range_m=args.range,
            voting_mode=args.voting_mode,
            explicit_duration_s=duration_s,
        )

    except KeyboardInterrupt:
        info("\n*** Interrupted by user\n")
    except Exception as e:
        info(f"*** Error: {e}\n")
        import traceback
        traceback.print_exc()
    finally:
        if net is not None:
            info("*** Stopping mesh network\n")
            try:
                net.stop()
            except Exception:
                pass


if __name__ == "__main__":
    main()

