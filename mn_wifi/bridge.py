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
from urllib.parse import urlparse, parse_qs
from uuid import UUID

from mininet.log import info
from mn_wifi.node import Node_wifi
from mn_wifi.authority import WiFiAuthority
from mn_wifi.client import Client
from mn_wifi.gateway import Gateway
import dataclasses
from enum import Enum
from mn_wifi.services.core.config import settings
from mn_wifi.bridgeLogger import BridgeLogger
from mn_wifi.services.json import JSONable
from mn_wifi.services.shard import SHARD_NAMES
from mn_wifi.baseTypes import TransferOrder, ConfirmationOrder, TransactionStatus

__all__ = ["Bridge"]



class Bridge:
    """HTTP bridge server that enables web back-ends to communicate with
    mesh authorities.
    """

    def __init__(self, gateway: Gateway, net=None, port: int = 8080) -> None:
        """Initialize the Bridge server.
        
        Args:
            gateway: The gateway host node for mesh network communication
            net: Mininet-wifi network instance for accessing all nodes
            port: The port number for the HTTP bridge server (default: 8080)
            update_interval: Interval in seconds for authority updates (default: 30)
        """
        self.port = port
        self.logger = BridgeLogger(name="bridge")
        self.gateway: Optional[Gateway] = gateway
        self.net = net  # Store the network instance
        self.authorities: Dict[str, Dict[str, Any]] = {}
        self.server: Optional[socketserver.TCPServer] = None
        self.server_thread: Optional[threading.Thread] = None
        self.update_thread: Optional[threading.Thread] = None
        self.update_interval = settings.blockchain_sync_interval 
        self.running = False
        self.jsonable = JSONable()

    def get_authorities_from_network(self) -> List[WiFiAuthority]:
        """Get all authority nodes from the network.
        
        Returns:
            List of WiFiAuthority instances
        """
        if not self.net:
            return []
        
        authorities = []
        for node in self.net.stations:
            if isinstance(node, WiFiAuthority):
                authorities.append(node)
        return authorities

    def _confirm_via_gateway(self, body: Dict[str, Any]) -> Dict[str, Any]:
        # Default return structure
        default_response = {
            "success": False,
            "error": None,
            "transfer_details": {
                "sender": None,
                "recipient": None,
                "token_address": None,
                "amount": None,
                "sequence_number": None,
                "order_id": None,
                "timestamp": None
            },
            "authority_processing": {
                "total_authorities": 0,
                "successful_authorities": 0,
                "failed_authorities": 0,
                "success_rate": 0.0,
                "authority_results": {}
            },
            "timestamp": time.time()
        }

        # Extract and validate required fields
        transfer_payload = body.get("transfer_order")
        authority_signatures = body.get("authority_signatures")
        
        transfer_order = TransferOrder(
            order_id=transfer_payload["order_id"],
            sender=transfer_payload["sender"],
            recipient=transfer_payload["recipient"],
            token_address=transfer_payload["token_address"],
            amount=transfer_payload["amount"],
            sequence_number=transfer_payload["sequence_number"],
            timestamp=transfer_payload["timestamp"],
            signature=transfer_payload["signature"]
        )
        
        confirmation_order = ConfirmationOrder(
            order_id=body.get("order_id", None),
            transfer_order=transfer_order,
            authority_signatures=authority_signatures,
            timestamp=body.get("timestamp", time.time()),
            status=TransactionStatus.PENDING
        )

        # Basic sanity checks
        if transfer_order is None or authority_signatures is None:
            default_response["error"] = "missing_fields"
            default_response["required"] = ["transfer_order", "authority_signatures"]
            return default_response

        # Execute the transfer using the gateway
        try:
            authorities = self.get_authorities_from_network()
            for auth in authorities:
                if not auth._validate_confirmation_order(confirmation_order):
                    default_response["error"] = "invalid_confirmation_order"
                    return default_response

            # Use gateway's forward_confirmation method to get detailed results
            gateway_results = self.gateway.forward_confirmation(
                confirmation_order
            )
            
            # Update default response with gateway results
            default_response["success"] = gateway_results.get("success", False)
            default_response["transfer_details"] = gateway_results.get("transfer_details", {})
            
            # Calculate success rate
            total_auths = gateway_results.get("total_authorities", 0)
            successful_auths = gateway_results.get("successful_authorities", 0)
            success_rate = (successful_auths / total_auths * 100) if total_auths > 0 else 0.0
            
            # Update authority processing details
            default_response["authority_processing"] = {
                "total_authorities": total_auths,
                "successful_authorities": successful_auths,
                "failed_authorities": gateway_results.get("failed_authorities", 0),
                "success_rate": round(success_rate, 2),
                "authority_results": gateway_results.get("authority_results", {})
            }
            default_response["timestamp"] = gateway_results.get("timestamp", time.time())
            
            return default_response
        except Exception as exc:  # pragma: no cover – defensive guard
            default_response["error"] = str(exc)
            return default_response

    def _transfer_via_gateway(self, body: Dict[str, Any]) -> Dict[str, Any]:
       # Default return structure
        default_response = {
            "success": False,
            "error": None,
            "transfer_details": {
                "sender": None,
                "recipient": None,
                "token_address": None,
                "amount": None,
                "sequence_number": None,
                "order_id": None,
                "timestamp": None
            },
            "authority_processing": {
                "total_authorities": 0,
                "successful_authorities": 0,
                "failed_authorities": 0,
                "success_rate": 0.0,
                "authority_results": {}
            },
            "timestamp": time.time()
        }

        payload = body.get("transfer_order")
        transfer_order = TransferOrder(
            order_id=payload["order_id"],
            sender=payload["sender"],
            recipient=payload["recipient"],
            token_address=payload["token_address"],
            amount=payload["amount"],
            sequence_number=payload["sequence_number"],
            timestamp=payload["timestamp"],
            signature=payload["signature"]
        )
        # Basic sanity checks
        if transfer_order.sender is None or transfer_order.recipient is None or transfer_order.token_address is None or transfer_order.amount is None:
            default_response["error"] = "missing_fields"
            default_response["required"] = ["transfer_order"]
            return default_response

        
        # Execute the transfer using the gateway
        try:
            authorities = self.get_authorities_from_network()
            for auth in authorities:
                if not auth._validate_transfer_order(transfer_order):
                    default_response["error"] = "invalid_transfer_order"
                    return default_response

            # Use gateway's forward_transfer method to get detailed results
            gateway_results = self.gateway.forward_transfer(
                transfer_order
            )
            
            # Update default response with gateway results
            default_response["success"] = gateway_results.get("success", False)
            default_response["transfer_details"] = gateway_results.get("transfer_details", {})
            
            # Calculate success rate
            total_auths = gateway_results.get("total_authorities", 0)
            successful_auths = gateway_results.get("successful_authorities", 0)
            success_rate = (successful_auths / total_auths * 100) if total_auths > 0 else 0.0
            
            # Update authority processing details
            default_response["authority_processing"] = {
                "total_authorities": total_auths,
                "successful_authorities": successful_auths,
                "failed_authorities": gateway_results.get("failed_authorities", 0),
                "success_rate": round(success_rate, 2),
                "authority_results": gateway_results.get("authority_results", {})
            }
            default_response["timestamp"] = gateway_results.get("timestamp", time.time())
            
            return default_response
        except Exception as exc:  # pragma: no cover – defensive guard
            default_response["error"] = str(exc)
            return default_response

    # ---------------------------------------------------------------------
    # Registration helpers
    # ---------------------------------------------------------------------
    def register_authority(self, authority: WiFiAuthority) -> None:  # noqa: D401
        """Add/refresh *authority* entry used by the JSON API."""

        def _serialise_account(acc):  # type: ignore[ann-type]
            return {
                "address": acc.address,
                "balances": acc.balances,
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
            "state": self.jsonable._to_jsonable(authority.state),
        }

        # Assign authority to a shard (round-robin based on index) ---------
        idx = len(self.authorities) - 1  # current index after append
        shard_name = SHARD_NAMES[idx % len(SHARD_NAMES)]
        self.authorities[authority.name]["shard"] = shard_name

    def update_authority_info(self, authority: WiFiAuthority) -> None:
        """Update existing authority information without changing shard assignment.
        
        Args:
            authority: Authority to update
        """
        if authority.name not in self.authorities:
            # If authority doesn't exist, register it normally
            self.register_authority(authority)
            return
            
        # Update existing authority info while preserving shard assignment
        shard_name = self.authorities[authority.name].get("shard", SHARD_NAMES[0])
        
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
            "state": self.jsonable._to_jsonable(authority.state),
            "shard": shard_name,  # Preserve existing shard assignment
        }

    def _start_authority_update_thread(self) -> None:
        """Start background thread for periodic authority updates."""
        if self.update_thread and self.update_thread.is_alive():
            return
            
        self.update_thread = threading.Thread(
            target=self._authority_update_loop,
            daemon=True,
            name="BridgeAuthorityUpdate"
        )
        self.update_thread.start()
        info(f"🔄 Authority update thread started (interval: {self.update_interval}s)\n")

    def _authority_update_loop(self) -> None:
        """Background loop for periodic authority updates."""
        while self.running:
            try:
                if not self.running:
                    break
                    
                # Update all registered authorities using network
                updated_count = 0
                authorities = self.get_authorities_from_network()
                for auth in authorities:
                    self.update_authority_info(auth)
                    updated_count += 1
                
                if updated_count > 0:
                    info(f"🔄 Updated {updated_count} authorities\n")
                    
            except Exception as e:
                info(f"❌ Error in authority update loop: {e}\n")
                time.sleep(5)  # Wait before retrying

    def trigger_authority_update(self) -> int:
        """Manually trigger authority update and return number of updated authorities.
        
        Returns:
            Number of authorities that were updated
        """
        if not self.running:
            info("❌ Bridge not running, cannot update authorities\n")
            return 0
            
        try:
            updated_count = 0
            authorities = self.get_authorities_from_network()
            for auth in authorities:
                self.update_authority_info(auth)
                updated_count += 1
            
            if updated_count > 0:
                info(f"🔄 Manually updated {updated_count} authorities\n")
            else:
                info("ℹ️ No authorities found to update\n")
                
            return updated_count
            
        except Exception as e:
            info(f"❌ Error in manual authority update: {e}\n")
            return 0

    def getAccount(self, address: str) -> Dict[str, Any]:
        """Get account information for a specific address.
        
        Args:
            address: The account address to look up
            
        Returns:
            AccountInfo dictionary with balances and registration status
        """
        try:
            # Initialize default account info structure
            account_info = {}
            
            # Search for account in all authorities
            found_account = False
            for auth_info in self.authorities.values():
                if "state" in auth_info and "accounts" in auth_info["state"]:
                    accounts = auth_info["state"]["accounts"]
                    if address in accounts:
                        account_data = accounts[address]
                        found_account = True
                        
                        # Update registration status
                        account_info["is_registered"] = True
                        account_info["registration_time"] = account_data.get("last_update", 0)
                        account_info["last_redeemed_sequence"] = account_data.get("sequence_number", 0)
                        account_info["balances"] = account_data.get("balances", {})
                        account_info["sequence_number"] = account_data.get("sequence_number", 0)
                        # Only need to find the account once
                        break
            
            # If account not found in authorities, return default structure
            if not found_account:
                info(f"ℹ️ Account {address} not found in any authority\n")

            return account_info
            
        except Exception as e:
            info(f"❌ Error getting account {address}: {e}\n")
            return {
                "address": address,
                "error": str(e),
                "balances": {},
                "sequence_number": 0,
                "is_registered": False,
                "registration_time": 0,
                "last_redeemed_sequence": 0
            }

    def get_metrics(self) -> Dict[str, Any]:
        """Get metrics for the bridge."""
        return {
            "online_authorities": len(self.authorities),
            "total_authorities": len(self.authorities),
            "network_latency": 1500,
            "total_transactions": 0,
            "successful_transactions": 0,
            "average_confirmation_time": 0,
            "total_stake": 0,
        }

    # ------------------------------------------------------------------
    # Build shard view --------------------------------------------------
    # ------------------------------------------------------------------

    def _get_shards(self) -> list[dict]:  # JSON-ready shard list
        """Aggregate authority information into *ShardInfo* objects."""

        shards: Dict[str, dict] = {}
        for auth in self.authorities.values():
            # TODO: Add shard assignment logic (currently all authorities are in the same shard)
            entry = shards.setdefault(SHARD_NAMES[0], {
                "shard_id": SHARD_NAMES[0],
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
            
            # Start authority update thread
            self._start_authority_update_thread()

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
                    self._json(list(self.bridge.authorities.values()))
                elif self.path == "/network/metrics":
                    self._json(self.bridge.get_metrics())
                elif self.path == "/authorities":
                    self._json(list(self.bridge.authorities.values()))
                elif self.path == "/shards":
                    self.bridge.trigger_authority_update()
                    self._json(self.bridge._get_shards())
                elif self.path.startswith("/accounts/"):
                    address = self.path.split("/accounts/")[1]
                    if address:
                        self.bridge.trigger_authority_update()
                        account_info = self.bridge.getAccount(address)
                        self._json(account_info)
                    else:
                        self._json({"error": "Address parameter required"}, 400)
                else:
                    self._json({"error": "not found"}, 404)

            # -------- POST ---------------------------------------------
            def do_POST(self):  # noqa: N802
                if self.path == "/transfer":
                    try:
                        length = int(self.headers.get("Content-Length", "0"))
                        raw = self.rfile.read(length) if length else b"{}"
                        body = json.loads(raw.decode() or "{}")
                    except Exception as exc:  # bad JSON
                        self._json({"success": False, "error": f"invalid_json: {exc}"}, 400)
                        return
                    result = self.bridge._transfer_via_gateway(body)
                    code = 200 if result.get("success") else 400
                    self._json(result, code)

                elif self.path == "/confirm":
                    try:
                        length = int(self.headers.get("Content-Length", "0"))
                        raw = self.rfile.read(length) if length else b"{}"
                        body = json.loads(raw.decode() or "{}")
                    except Exception as exc:  # bad JSON
                        self._json({"success": False, "error": f"invalid_json: {exc}"}, 400)
                        return
                    result = self.bridge._confirm_via_gateway(body)
                    code = 200 if result.get("success") else 400
                    self._json(result, code)

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
        
        # Stop authority update thread
        if self.update_thread:
            self.update_thread.join(timeout=2)
        
        self.running = False
        self.server = None
        self.server_thread = None
        self.update_thread = None

    # ------------------------------------------------------------------
    # Back-compat helper names (used by the demo script) ---------------
    # ------------------------------------------------------------------

    def start_bridge_server(self, *_args, **_kwargs):  # noqa: D401
        """Alias for :py:meth:`start` (kept for backward compatibility)."""

        self.start()

    def stop_bridge_server(self):  # noqa: D401
        """Alias for :py:meth:`stop` (kept for backward compatibility)."""

        self.stop() 