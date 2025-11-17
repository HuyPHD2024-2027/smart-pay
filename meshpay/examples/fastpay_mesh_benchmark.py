#!/usr/bin/env python3
"""MeshPay mesh benchmark runner aligned with the enhanced demo topology."""

from __future__ import annotations

import argparse
import os
import random
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple, Literal, cast
from uuid import UUID, uuid4

from mininet.log import info, setLogLevel
from mn_wifi.link import mesh
from mn_wifi.net import Mininet_wifi

from meshpay.messages import TransferResponseMessage
from meshpay.nodes.authority import WiFiAuthority
from meshpay.nodes.client import Client
from meshpay.transport import TransportKind
from meshpay.types import AccountOffchainState, ConfirmationOrder, TransactionStatus, TransferOrder
from mn_wifi.mesh_metrics import MeshMetrics
from mn_wifi.services.core.config import SUPPORTED_TOKENS


FaultMode = Literal["crash", "byzantine"]


class BenchClient(Client):
    """Client subclass that records metrics for each transfer."""

    def __init__(self, *args: Any, metrics: MeshMetrics, **kwargs: Any) -> None:
        """Initialise benchmark client with a shared metrics collector."""
        self._metrics = metrics
        super().__init__(*args, **kwargs)

    def transfer(self, recipient: str, token_address: str, amount: int) -> bool:
        """Record transfer start metrics before delegating to the base implementation."""
        tx_id: UUID = uuid4()
        approx_bytes = 180
        self._metrics.record_tx_start(tx_id, bytes_sent=approx_bytes)
        successful = super().transfer(recipient, token_address, amount)
        if not successful:
            self._metrics.record_tx_failure(tx_id)
        if self.state.pending_transfer is not None:
            self.state.pending_transfer.order_id = tx_id
        return successful

    def handle_transfer_response(self, transfer_response: TransferResponseMessage) -> bool:
        """Record completion metrics before deferring to the base implementation."""
        approx_bytes = 220
        self._metrics.record_tx_success(
            transfer_response.transfer_order.order_id,
            bytes_received=approx_bytes,
        )
        return super().handle_transfer_response(transfer_response)


class ByzantineAuthority(WiFiAuthority):
    """Authority variant that exhibits Byzantine behaviour for benchmarks."""

    def __init__(self, *args: Any, drop_probability: float = 0.5, **kwargs: Any) -> None:
        """Initialise authority with configurable drop probability."""
        self._drop_probability = max(0.0, min(drop_probability, 1.0))
        super().__init__(*args, **kwargs)
        self._rng = random.Random(f"{self.name}-byzantine")

    def handle_transfer_order(self, transfer_order: TransferOrder) -> TransferResponseMessage:
        """Return corrupted or failed responses to emulate Byzantine behaviour."""
        if self._rng.random() < self._drop_probability:
            self.logger.warning("Byzantine authority %s dropped transfer", self.name)
            self.performance_metrics.record_error()
            return TransferResponseMessage(
                transfer_order=transfer_order,
                success=False,
                error_message="Byzantine drop",
                authority_signature=f"byz_drop_{self.name}",
            )
        response = super().handle_transfer_order(transfer_order)
        response.success = False
        response.error_message = "Byzantine corruption"
        response.authority_signature = f"byz_corrupt_{self.name}"
        return response

    def handle_confirmation_order(self, confirmation_order: ConfirmationOrder) -> bool:
        """Reject confirmation orders to simulate Byzantine disagreement."""
        self.logger.warning("Byzantine authority %s rejected confirmation", self.name)
        self.performance_metrics.record_error()
        confirmation_order.status = TransactionStatus.REJECTED
        return False

def setup_test_accounts(authorities: List[WiFiAuthority], clients: List[Client]) -> None:
    """Initialise each client account on all authorities with random balances.

    Balances are assigned per supported token to seed off-chain state so
    transfers validate immediately in demos.
    """

    info("*** Setting up test accounts\n")

    from mn_wifi.services.core.config import SUPPORTED_TOKENS
    from mn_wifi.services.blockchain_client import TokenBalance

    for authority in authorities:
        if not hasattr(authority, 'state'):
            info(f"   ⚠️  {authority.name}: No state found, skipping\n")
            continue

        for client in clients:
            balances_map = {}
            for symbol, cfg in SUPPORTED_TOKENS.items():
                token_address = cfg.get('address')
                if not token_address:
                    continue
                decimals = int(cfg.get('decimals', 18))

                meshpay_balance = round(random.uniform(100, 1000), 3)
                wallet_balance = round(random.uniform(0, 250), 3)
                total_balance = round(meshpay_balance + wallet_balance, 3)

                balances_map[token_address] = TokenBalance(
                    token_symbol=symbol,
                    token_address=token_address,
                    wallet_balance=wallet_balance,
                    meshpay_balance=meshpay_balance,
                    total_balance=total_balance,
                    decimals=decimals,
                )

            authority.state.accounts[client.name] = AccountOffchainState(
                address=client.name,
                balances=balances_map,
                sequence_number=0,
                last_update=time.time(),
                pending_confirmation=None,  # type: ignore[arg-type]
                confirmed_transfers={},
            )

        info(f"   ✅ {authority.name}: Setup {len(clients)} client accounts\n")


def create_mesh_network(
    *,
    num_authorities: int,
    num_clients: int,
    mesh_id: str,
    node_range: int,
    transport: TransportKind,
    num_faulty: int,
    fault_mode: FaultMode,
) -> Tuple[Mininet_wifi, List[WiFiAuthority], List[BenchClient], List[WiFiAuthority]]:
    """Create IEEE 802.11s mesh topology mirroring the meshpay_demo structure."""
    if num_authorities <= 0:
        raise ValueError("Number of authorities must be positive")
    if num_faulty > num_authorities:
        raise ValueError("Number of faulty authorities cannot exceed total authorities")
    if num_clients <= 0:
        raise ValueError("Number of clients must be positive")

    net = Mininet_wifi()
    metrics = MeshMetrics(run_label="benchmark")

    authorities: List[WiFiAuthority] = []
    faulty_authorities: List[WiFiAuthority] = []
    committee: Set[str] = {f"auth{i}" for i in range(1, num_authorities + 1)}

    for i in range(1, num_authorities + 1):
        name = f"auth{i}"
        authority_cls = WiFiAuthority
        station_kwargs: Dict[str, Any] = {
            "committee_members": committee - {name},
            "ip": f"10.0.0.{10 + i}/8",
            "port": 8000 + i,
            "min_x": 0,
            "max_x": 200,
            "min_y": 0,
            "max_y": 150,
            "min_v": 5,
            "max_v": 10,
            "range": node_range,
            "txpower": 20,
        }
        if i <= num_faulty:
            if fault_mode == "byzantine":
                authority_cls = ByzantineAuthority
                station_kwargs["drop_probability"] = 0.5
            faulty_flag = True
        else:
            faulty_flag = False
        authority = net.addStation(name, cls=authority_cls, **station_kwargs)
        authorities.append(authority)
        if faulty_flag:
            faulty_authorities.append(authority)

    clients: List[BenchClient] = []
    for i in range(1, num_clients + 1):
        name = f"user{i}"
        client = net.addStation(
            name,
            cls=BenchClient,
            metrics=metrics,
            transport_kind=transport,
            ip=f"10.0.0.{20 + i}/8",
            port=9000 + i,
            min_x=0,
            max_x=200,
            min_y=0,
            max_y=150,
            min_v=1,
            max_v=3,
            range=node_range,
            txpower=20,
        )
        clients.append(cast(BenchClient, client))

    net.setPropagationModel(model="logDistance", exp=3.5)
    net.configureNodes()

    for i in range(1, num_authorities + 1):
        net.addLink(
            authorities[i - 1],
            cls=mesh,
            ssid=mesh_id,
            intf=f"auth{i}-wlan0",
            channel=5,
            ht_cap="HT40+",
        )
    for i in range(1, num_clients + 1):
        net.addLink(
            clients[i - 1],
            cls=mesh,
            ssid=mesh_id,
            intf=f"user{i}-wlan0",
            channel=5,
            ht_cap="HT40+",
        )

    net.setMobilityModel(
        time=0,
        model="RandomDirection",
        max_x=200,
        max_y=150,
        min_v=1,
        max_v=3,
        seed=42,
    )

    for client in clients:
        client.state.committee = authorities

    return net, authorities, clients, faulty_authorities


def pick_token_address() -> str:
    """Return a token address from the configured SUPPORTED_TOKENS mapping."""
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
            candidates = [c for c in clients if c.name != me.name]
            if not candidates:
                break
            recipient = rng.choice(candidates).name
            me.transfer(recipient, token_address, amount)
            time.sleep(interval)

    threads: List[threading.Thread] = [
        threading.Thread(target=worker, args=(client,), daemon=True) for client in clients
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=duration_s + 5)


def write_outputs(
    metrics: MeshMetrics,
    *,
    json_path: Optional[str],
    csv_path: Optional[str],
    latencies_path: Optional[str],
    explicit_duration_s: Optional[float],
    num_authorities: int,
    num_clients: int,
    num_faulty: int,
    transmission_range_m: int,
) -> None:
    """Persist metrics to optional JSON/CSV outputs and raw latencies CSV."""
    snapshot = metrics.snapshot(explicit_duration_s=explicit_duration_s)

    if json_path:
        os.makedirs(os.path.dirname(json_path) or ".", exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as handle:
            handle.write(metrics.to_json(explicit_duration_s=explicit_duration_s))

    if csv_path:
        os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
        header = (
            "authorities,user_nodes,faulty_nodes,transmission_range_m,"
            "throughput_tps,avg_latency_s"
        )
        avg_latency_s = snapshot["avg_latency_ms"] / 1000.0
        row = (
            f"{num_authorities},{num_clients},{num_faulty},{transmission_range_m},"
            f"{snapshot['throughput_tps']:.3f},{avg_latency_s:.3f}"
        )
        with open(csv_path, "w", encoding="utf-8") as handle:
            handle.write(header + "\n")
            handle.write(row + "\n")

    if latencies_path:
        os.makedirs(os.path.dirname(latencies_path) or ".", exist_ok=True)
        with open(latencies_path, "w", encoding="utf-8") as handle:
            handle.write("latency_ms\n")
            for value in metrics.get_latency_samples_ms():
                handle.write(f"{value:.3f}\n")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the benchmark runner."""
    parser = argparse.ArgumentParser(description="MeshPay mesh benchmark")
    parser.add_argument("--authorities", type=int, default=5, help="number of authorities")
    parser.add_argument("--tps", type=int, default=100, help="target transactions per second")
    parser.add_argument(
        "--clients",
        type=int,
        default=None,
        help="explicit number of clients (overrides automatic scaling)",
    )
    parser.add_argument("--duration", type=int, default=60, help="benchmark duration (seconds)")
    parser.add_argument("--range", type=int, default=20, help="transmission range (meters)")
    parser.add_argument("--amount", type=int, default=1, help="transfer amount per transaction")
    parser.add_argument(
        "--faulty",
        type=int,
        default=0,
        help="number of faulty authority nodes",
    )
    parser.add_argument(
        "--fault-type",
        type=str,
        choices=["crash", "byzantine"],
        default="crash",
        help="fault model applied to faulty authority nodes",
    )
    parser.add_argument(
        "--voting-mode",
        type=str,
        choices=["normal"],
        default="normal",
        help="committee voting mode (normal equal weights)",
    )
    parser.add_argument(
        "--mesh-id",
        type=str,
        default="meshNet",
        help="mesh network identifier (SSID)",
    )
    parser.add_argument(
        "--transport",
        type=str,
        choices=["tcp", "udp", "wifi_direct"],
        default="tcp",
        help="transport protocol for client-authority communication",
    )
    parser.add_argument("--json", type=str, default="results/benchmark.json", help="output JSON path")
    parser.add_argument("--csv", type=str, default="results/benchmark.csv", help="output CSV path")
    parser.add_argument(
        "--latencies",
        type=str,
        default="results/latencies.csv",
        help="output raw latencies CSV path",
    )
    parser.add_argument("--loglevel", type=str, default="info", help="mininet log level")
    return parser.parse_args()


def main() -> None:
    """Entry point for the benchmark runner."""
    args = parse_args()
    setLogLevel(args.loglevel)

    target_tps = max(args.tps, 0)
    num_clients = args.clients if args.clients is not None else max(5, max(1, target_tps // 20))
    if num_clients <= 0:
        raise ValueError("Number of clients must be positive")
    rate_per_client = target_tps / num_clients if num_clients > 0 else 0.0

    num_faulty = max(0, min(args.faulty, args.authorities))
    fault_mode: FaultMode = cast(FaultMode, args.fault_type)

    info("\n🚀 MeshPay Mesh Benchmark\n")
    info(f"   Authorities: {args.authorities}\n")
    info(f"   Target TPS: {target_tps}\n")
    info(f"   Duration: {args.duration}s\n")
    info(f"   Range: {args.range} m\n")
    info(f"   Faulty nodes: {num_faulty} ({fault_mode})\n")
    info(f"   Voting mode: {args.voting_mode}\n")
    info(f"   Calculated clients: {num_clients} ({rate_per_client:.2f} tx/s each)\n")
    info(f"   Transport: {args.transport}\n")

    transport = {
        "tcp": TransportKind.TCP,
        "udp": TransportKind.UDP,
        "wifi_direct": TransportKind.WIFI_DIRECT,
    }[args.transport]

    json_out = args.json
    csv_out = args.csv
    latencies_out = args.latencies

    net: Optional[Mininet_wifi] = None
    try:
        net, authorities, clients, faulty_authorities = create_mesh_network(
            num_authorities=args.authorities,
            num_clients=num_clients,
            mesh_id=args.mesh_id,
            node_range=args.range,
            transport=transport,
            num_faulty=num_faulty,
            fault_mode=fault_mode,
        )

        info("*** Building mesh network\n")
        net.build()

        info("*** Starting authority services\n")
        for authority in authorities:
            if fault_mode == "crash" and authority in faulty_authorities:
                info(f"   Skipping start for faulty authority {authority.name} (crash mode)\n")
                continue
            authority.start_fastpay_services(False)

        healthy_authorities = (
            [auth for auth in authorities if auth not in faulty_authorities] if fault_mode == "crash" else authorities
        )

        info("*** Seeding accounts on authorities\n")
        setup_test_accounts(healthy_authorities, clients)

        info("*** Starting client services\n")
        for client in clients:
            client.start_fastpay_services()

        info("*** Stabilizing mesh\n")
        time.sleep(3)

        token_address = pick_token_address()
        metrics: MeshMetrics = clients[0]._metrics  # type: ignore[attr-defined]

        info("*** Running benchmark workload\n")
        t_start = time.time()
        run_load(
            clients=clients,
            duration_s=args.duration,
            rate_per_client=rate_per_client,
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
            num_authorities=args.authorities,
            num_clients=num_clients,
            num_faulty=num_faulty,
            transmission_range_m=args.range,
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

