"""Mesh Internet Bridge server.

Provides HTTP → FastPay TCP translation so external web front-ends can
interact with mesh authorities.
"""

from __future__ import annotations

import http.server
import json
import socket
import socketserver
import threading
import time
from typing import Any, Dict, Optional, List

from mininet.log import info

from mn_wifi.authority import WiFiAuthority
from mn_wifi.client import Client
import dataclasses
from uuid import UUID
from enum import Enum

__all__ = ["Bridge"]

# ---------------------------------------------------------------------------
# Basic static shard list – demo uses round-robin assignment               
# ---------------------------------------------------------------------------

SHARD_NAMES: list[str] = [
    "Alpha Shard",
    "Beta Shard",
    "Gamma Shard",
    "Delta Shard",
    "Epsilon Shard",
]


class Bridge:
    """HTTP bridge server that enables web back-ends to communicate with
    mesh authorities.
    """

    def __init__(self, gateway_host: str, port: int = 8080) -> None:
        self.port = port
        self.gateway_host = gateway_host
        self.authorities: Dict[str, Dict[str, Any]] = {}
        self.server: Optional[socketserver.TCPServer] = None
        self.server_thread: Optional[threading.Thread] = None
        self.running = False

    # ------------------------------------------------------------------
    # New – HTTP → client.transfer helper
    # ------------------------------------------------------------------

    def _transfer_via_client(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a transfer order through :pymeth:`mn_wifi.client.Client.transfer`.

        The JSON body must include ``sender``, ``recipient`` and ``amount``.
        The helper performs basic validation and returns a JSON-serialisable
        response containing ``success`` and optional ``error``.
        """

        sender = body.get("sender")
        recipient = body.get("recipient")
        amount = body.get("amount")

        # Basic sanity checks --------------------------------------------------
        if sender is None or recipient is None or amount is None:
            return {"success": False, "error": "missing_fields", "required": ["sender", "recipient", "amount"]}

        try:
            amount_int = int(amount)
        except Exception:
            return {"success": False, "error": "amount_not_int"}

        # ------------------------------------------------------------------
        # Execute the transfer using the built-in FastPay helper -------------
        # ------------------------------------------------------------------
        try:
            ok = self.gateway_host.transfer(recipient, amount_int)
            return {"success": bool(ok), "sender": sender, "recipient": recipient, "amount": amount_int}
        except Exception as exc:  # pragma: no cover – defensive guard
            return {"success": False, "error": str(exc)}

    # ---------------------------------------------------------------------
    # Registration helpers
    # ---------------------------------------------------------------------

    # Recursive JSON-safe serialiser ------------------------------------

    def _to_jsonable(self, obj: Any) -> Any:  # noqa: ANN401 – generic helper
        """Return *obj* converted into JSON-serialisable structures.

        • dataclasses → dict (recursively processed)
        • set → list (sorted for determinism when items are plain types)  
        • UUID → str  
        • list / tuple / dict processed recursively  
        • everything else returned unchanged.
        """

        if dataclasses.is_dataclass(obj):
            return {k: self._to_jsonable(v) for k, v in dataclasses.asdict(obj).items()}

        if isinstance(obj, dict):
            return {k: self._to_jsonable(v) for k, v in obj.items()}

        if isinstance(obj, (list, tuple)):
            return [self._to_jsonable(v) for v in obj]

        if isinstance(obj, set):
            # Try to return a deterministic ordering when items are simple types
            try:
                return [self._to_jsonable(v) for v in sorted(obj)]
            except Exception:
                return [self._to_jsonable(v) for v in obj]

        if isinstance(obj, UUID):
            return str(obj)

        if isinstance(obj, Enum):
            return obj.value

        return obj

    def register_authority(self, authority: WiFiAuthority) -> None:  # noqa: D401
        """Add/refresh *authority* entry used by the JSON API."""

        def _serialise_account(acc):  # type: ignore[ann-type]
            return {
                "address": acc.address,
                "balance": acc.balance,
                "sequence_number": acc.sequence_number,
                "last_update": acc.last_update,
            }

        accounts = {
            addr: _serialise_account(acc)
            for addr, acc in authority.state.accounts.items()
        }

        self.authorities[authority.name] = {
            "name": authority.name,
            "ip": authority.IP(),
            "address": {
                "node_id": authority.address.node_id,
                "ip_address": authority.address.ip_address,
                "port": authority.address.port,
                "node_type": authority.address.node_type.value,
            },
            "status": "online",
            "state": self._to_jsonable(authority.state),
        }

        # Assign authority to a shard (round-robin based on index) ---------
        idx = len(self.authorities) - 1  # current index after append
        shard_name = SHARD_NAMES[idx % len(SHARD_NAMES)]
        self.authorities[authority.name]["shard"] = shard_name

    # ------------------------------------------------------------------
    # Build shard view --------------------------------------------------
    # ------------------------------------------------------------------

    def _get_shards(self) -> list[dict]:  # JSON-ready shard list
        """Aggregate authority information into *ShardInfo* objects."""

        shards: Dict[str, dict] = {}
        for auth in self.authorities.values():
            shard = auth.get("shard", SHARD_NAMES[0])
            entry = shards.setdefault(shard, {
                "shard_id": shard,
                "account_count": 0,
                "total_transactions": 0,
                "total_stake": 0,
                "last_sync": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                "authorities": [],
            })

            entry["authorities"].append(auth)
            entry["account_count"] += len(auth.get("accounts", {}))
            entry["total_transactions"] += auth.get("state", {}).get("total_transactions", 0)
            entry["total_stake"] += auth.get("state", {}).get("total_stake", 0)

        return list(shards.values())

    # ---------------------------------------------------------------------
    # Web server
    # ---------------------------------------------------------------------

    def start(self) -> None:
        """Start the HTTP bridge (if not already running)."""
        if self.running:
            return

        info(f"🌉 Starting Mesh Internet Bridge on port {self.port}\n")

        class _Handler(http.server.BaseHTTPRequestHandler):  # noqa: D401
            def __init__(self, *args, bridge: "Bridge", **kwargs):
                self.bridge = bridge
                super().__init__(*args, **kwargs)

            # ------------- helpers -------------------------------------
            def _json(self, obj: Any, code: int = 200) -> None:  # noqa: ANN401
                payload = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(payload)

            # ------------- routing -------------------------------------
            def do_GET(self):  # noqa: N802
                if self.path == "/health":
                    self._json({
                        "status": "healthy",
                        "authorities_count": len(self.bridge.authorities),
                        "timestamp": time.time(),
                    })
                elif self.path == "/authorities":
                    self._json({
                        "authorities": list(self.bridge.authorities.values()),
                        "count": len(self.bridge.authorities),
                        "timestamp": time.time(),
                    })
                elif self.path == "/shards":
                    self._json({
                        "shards": self.bridge._get_shards(),
                        "timestamp": time.time(),
                    })
                else:
                    self._json({"error": "not found"}, 404)

            # -------- POST ---------------------------------------------
            def do_POST(self):  # noqa: N802
                path_parts = [p for p in self.path.split("/") if p]

                # New simple endpoint: POST /transfer -------------------
                if len(path_parts) == 1 and path_parts[0] == "transfer":
                    try:
                        length = int(self.headers.get("Content-Length", "0"))
                        raw = self.rfile.read(length) if length else b"{}"
                        body = json.loads(raw.decode() or "{}")
                    except Exception as exc:  # bad JSON
                        self._json({"success": False, "error": f"invalid_json: {exc}"}, 400)
                        return

                    result = self.bridge._transfer_via_client(body)
                    code = 200 if result.get("success") else 400
                    self._json(result, code)
                    return

            def log_message(self, *_):  # silence default logging
                pass

        def _factory(*args, **kwargs):  # type: ignore[ann-type]
            return _Handler(*args, bridge=self, **kwargs)

        self.server = socketserver.TCPServer(("", self.port), _factory)
        self.server.allow_reuse_address = True
        self.server_thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.server_thread.start()
        self.running = True
        info("✅ Mesh Internet Bridge started\n")

    def stop(self) -> None:
        if not self.running or self.server is None:
            return
        info("🛑 Stopping Mesh Internet Bridge\n")
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=2)
        self.running = False
        self.server = None
        self.server_thread = None

    # ------------------------------------------------------------------
    # Back-compat helper names (used by the demo script) ---------------
    # ------------------------------------------------------------------

    def start_bridge_server(self, *_args, **_kwargs):  # noqa: D401
        """Alias for :py:meth:`start` (kept for backward compatibility)."""

        self.start()

    def stop_bridge_server(self):  # noqa: D401
        """Alias for :py:meth:`stop` (kept for backward compatibility)."""

        self.stop() 