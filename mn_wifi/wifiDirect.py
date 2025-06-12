"""Wi-Fi Direct transport adapter wrapping an existing WiFiInterface instance.

This file provides *WiFiDirectTransport* so that higher-level code can interact
with Wi-Fi Direct as just another `NetworkTransport`.
"""

from __future__ import annotations

from typing import Optional

from mn_wifi.baseTypes import Address
from mn_wifi.messages import Message



class WiFiDirectTransport:  # pylint: disable=too-few-public-methods
    """Expose WiFiInterface functionality through the NetworkTransport facade."""

    def __init__(self, node, address: Address) -> None:  # noqa: D401
        pass

    # ------------------------------------------------------------------
    # Delegated operations
    # ------------------------------------------------------------------

    def connect(self) -> bool:  # type: ignore[override]
        return self.iface.connect()

    def disconnect(self) -> None:  # type: ignore[override]
        self.iface.disconnect()

    def send_message(self, message: Message, target: Address) -> bool:  # type: ignore[override]
        return self.iface.send_message(message, target)

    def receive_message(self, timeout: float = 1.0) -> Optional[Message]:  # type: ignore[override]
        return self.iface.receive_message(timeout=timeout) 