"""BLE → Mesh Gateway (host-side helper).

This helper is intended for demo/prototyping of an offline payment protocol
using Bluetooth Low Energy on mobile devices while reusing the existing
FastPay mesh inside Mininet-WiFi. It translates BLE-originated transfer
intents into HTTP calls towards the mesh Internet bridge
(`MeshInternetBridge`) running inside the simulation.

Design notes:
- Real BLE stacks differ by platform. To keep the demo portable, BLE support
  is optional via the `bleak` package. When `bleak` is not available or when
  no compatible peripheral is found, the gateway falls back to a local HTTP
  endpoint that accepts the same JSON and forwards it to the mesh bridge.
- For a live demo with actual phones, pair this gateway with a simple mobile
  app (or a BLE testing tool) that writes a JSON payload to a GATT
  characteristic exposed by the phone (central → gateway peripheral) or vice
  versa. In practice, most demos will use the HTTP fallback to keep things
  simple.

Example usage:
    $ python3 -m mn_wifi.examples.ble_gateway \
        --bridge-url http://10.0.0.254:8080 \
        --listen 0.0.0.0 --port 8099

Then on the phone (same Wi‑Fi as the gateway host, e.g., via a physical NIC
bridged into Mininet) issue:
    POST http://<gateway-host>:8099/transfer
    {"sender":"user1","recipient":"user2","amount":25}

The gateway will forward this to the mesh bridge at
`http://10.0.0.254:8080/transfer`, which triggers `Client.transfer` inside the
simulation.
"""

from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional, Tuple
import urllib.request


def _http_post_json(url: str, payload: Dict[str, Any], timeout: float = 5.0) -> Tuple[int, Dict[str, Any]]:
    """Send a JSON POST and return status code plus parsed JSON response.

    Args:
        url: Destination URL (e.g., bridge endpoint).
        payload: JSON-serialisable request body.
        timeout: Request timeout seconds.

    Returns:
        Tuple of (status_code, response_json_dict). If the response cannot be
        parsed as JSON, returns an empty dict.
    """
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.getcode(), json.loads(raw) if raw else {}
            except Exception:
                return resp.getcode(), {}
    except Exception as exc:  # pragma: no cover – network issues are expected at times
        return 599, {"success": False, "error": str(exc)}


class _ForwardingHTTPHandler(BaseHTTPRequestHandler):
    """Tiny HTTP handler that forwards /transfer calls to the mesh bridge.

    The handler expects a JSON body with fields: sender, recipient, amount.
    """

    def __init__(self, *args: Any, bridge_url: str, **kwargs: Any) -> None:
        self.bridge_url = bridge_url.rstrip("/")
        super().__init__(*args, **kwargs)

    # Utilities -----------------------------------------------------------------
    def _json(self, obj: Dict[str, Any], code: int = 200) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    # Routes --------------------------------------------------------------------
    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") == "/transfer":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length else b"{}"
                body = json.loads(raw.decode() or "{}")
            except Exception as exc:
                self._json({"success": False, "error": f"invalid_json: {exc}"}, 400)
                return

            status, resp = _http_post_json(f"{self.bridge_url}/transfer", body)
            self._json(resp or {"success": status == 200}, 200 if status == 200 else 502)
            return

        self._json({"error": "not_found"}, 404)

    def log_message(self, *_: Any) -> None:  # silence default logs
        pass


class BLEGateway:
    """Optional BLE-to-HTTP forwarder with an HTTP fallback.

    In most demos the HTTP fallback is sufficient and easier to integrate with
    a phone UI. BLE support requires the `bleak` package and a basic agreement
    about service/characteristic and payload format with the phone app.
    """

    def __init__(self, bridge_url: str, listen_host: str = "127.0.0.1", listen_port: int = 8099) -> None:
        """Create a new gateway instance.

        Args:
            bridge_url: Base URL of the mesh internet bridge.
            listen_host: Host/IP for the local HTTP fallback server.
            listen_port: TCP port for the local HTTP fallback server.
        """
        self.bridge_url = bridge_url.rstrip("/")
        self.listen_host = listen_host
        self.listen_port = listen_port
        self._httpd: Optional[HTTPServer] = None
        self._http_thread: Optional[threading.Thread] = None

    def start_http_fallback(self) -> None:
        """Start the local HTTP forwarding server in a background thread."""
        def _factory(*args: Any, **kwargs: Any) -> _ForwardingHTTPHandler:
            return _ForwardingHTTPHandler(*args, bridge_url=self.bridge_url, **kwargs)

        self._httpd = HTTPServer((self.listen_host, self.listen_port), _factory)
        self._http_thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._http_thread.start()

    def stop_http_fallback(self) -> None:
        """Stop the local HTTP server if running."""
        if self._httpd is None:
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._http_thread is not None:
            self._http_thread.join(timeout=2)
        self._httpd = None
        self._http_thread = None

    # BLE section kept minimal and optional -------------------------------------
    def start_ble_listener(self) -> None:  # pragma: no cover - optional env
        """Attempt to start a BLE listener (best-effort, optional).

        This method tries to import `bleak` and scan for notifications under a
        custom service UUID. For a predictable demo, prefer the HTTP fallback.
        """
        try:
            import asyncio
            from bleak import BleakScanner  # type: ignore
        except Exception:
            # BLE not available; rely on HTTP fallback only.
            return

        TARGET_NAME = "FastPay-Mobile"  # Suggestion: phone advertises this name

        async def _scan_loop() -> None:
            while True:
                devices = await BleakScanner.discover(timeout=5.0)
                for d in devices:
                    if (d.name or "").startswith(TARGET_NAME):
                        # In a real implementation we would connect and subscribe
                        # to a characteristic that carries the transfer JSON, then
                        # forward it to the mesh bridge using _http_post_json.
                        # Kept as a placeholder to avoid platform-specific code.
                        pass

        threading.Thread(target=lambda: asyncio.run(_scan_loop()), daemon=True).start()


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the BLE gateway."""
    parser = argparse.ArgumentParser(description="BLE → Mesh gateway (HTTP forwarder)")
    parser.add_argument("--bridge-url", "-b", type=str, default="http://10.0.0.254:8080", help="Mesh bridge base URL")
    parser.add_argument("--listen", type=str, default="0.0.0.0", help="Local HTTP listen host")
    parser.add_argument("--port", "-p", type=int, default=8099, help="Local HTTP listen port")
    return parser.parse_args()


def main() -> None:
    """Entry-point to run the gateway as a module."""
    args = parse_args()
    gw = BLEGateway(args.bridge_url, listen_host=args.listen, listen_port=args.port)
    gw.start_http_fallback()
    gw.start_ble_listener()

    print("\nBLE → Mesh Gateway running")
    print(f"- Forwarding endpoint (HTTP fallback): http://{args.listen}:{args.port}/transfer")
    print(f"- Mesh bridge target: {args.bridge_url}/transfer\n")
    print("Test:")
    payload_json = '{"sender":"user1","recipient":"user2","amount":25}'
    cmd = (
        f"curl -X POST -H 'Content-Type: application/json' -d '{payload_json}' "
        f"http://{args.listen}:{args.port}/transfer"
    )
    print(f"  {cmd}")

    try:
        threading.Event().wait()  # block forever
    except KeyboardInterrupt:
        pass
    finally:
        gw.stop_http_fallback()


if __name__ == "__main__":
    main()


