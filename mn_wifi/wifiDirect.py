"""Wi-Fi Direct transport adapter wrapping an existing WiFiInterface instance.

This file provides *WiFiDirectTransport* so that higher-level code can interact
with Wi-Fi Direct as just another `NetworkTransport`.
"""

from __future__ import annotations

from mn_wifi.baseTypes import Address
from mn_wifi.tcp import TCPTransport


class WiFiDirectTransport(TCPTransport):  # type: ignore[misc]
    """Transport relying on TCP sockets carried over a *Wi-Fi Direct* link.

    Inherits everything from :class:`mn_wifi.tcp.TCPTransport`.  No additional
    behaviour is required apart from the different *link layer* the packets
    traverse – Wi-Fi Direct instead of an AP–STA infrastructure network.
    """

    # The parent implementation already provides the full `NetworkTransport`
    # API (connect, disconnect, send_message, receive_message).  The subclass
    # is essentially an *alias* that callers can use to make their intention
    # explicit when building a topology with ``configWiFiDirect=True``.

    def __init__(self, node, address: Address) -> None:  # noqa: D401
        """Create a new *WiFiDirectTransport* bound to *address*.

        Parameters
        ----------
        node:
            The *mininet-wifi* station (or host) object that owns this
            transport.  All commands executed by the transport will run inside
            the network namespace of *node* via :pymeth:`mininet.node.Node.cmd`.
        address:
            The logical FastPay address (IP, port, node identifier) associated
            with *node*.
        """
        super().__init__(node, address)

    # No additional overrides – inherited methods are sufficient. 