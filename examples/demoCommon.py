from __future__ import annotations

"""Common helper functions shared by FastPay demo scripts.

The module centralises CLI argument parsing and the optional management of
*xterm* windows used to tail per-node log files.  Importing demo scripts keep
their source code tidy and avoid duplication.
"""

import argparse
from typing import List

from mininet.log import info

from mn_wifi.authority import WiFiAuthority
from mn_wifi.client import Client

__all__ = [
    "parse_args",
    "open_xterms",
    "close_xterms",
]


def parse_args(description: str = "FastPay Wi-Fi demo") -> argparse.Namespace:
    """Parse common command-line options.

    Parameters
    ----------
    description:
        Short description displayed in the ``--help`` banner.

    Returns
    -------
    argparse.Namespace
        Parsed CLI options with attributes *authorities*, *logs*, and *plot*.
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "-a", "--authorities", type=int, default=3, help="number of authorities"
    )
    parser.add_argument(
        "-l",
        "--logs",
        action="store_true",
        help="open an xterm per authority and client and tail their logs",
    )
    parser.add_argument(
        "-p", "--plot",
        action="store_true",
        help="disable plotting the network graph (plotting is enabled by default)",
    )
    return parser.parse_args()


def open_xterms(authorities: List[WiFiAuthority], clients: List[Client]) -> None:
    """Spawn an *xterm* window per node so that live logs are visible.

    The function relies on each node exposing a ``logger`` attribute with
    ``start_xterm()`` and ``close_xterm()`` helpers (see *AuthorityLogger* and
    *ClientLogger*).
    """
    info("*** Opening xterms for authority and client logs\n")
    for auth in authorities:
        if hasattr(auth, "logger"):
            auth.logger.start_xterm()  # type: ignore[attr-defined]
            info(f"   → xterm for {auth.name}\n")
    for client in clients:
        if hasattr(client, "logger"):
            client.logger.start_xterm()  # type: ignore[attr-defined]
            info(f"   → xterm for {client.name}\n")


def close_xterms(authorities: List[WiFiAuthority], clients: List[Client]) -> None:
    """Close the xterm windows previously opened by :func:`open_xterms`."""
    for auth in authorities:
        if hasattr(auth, "logger"):
            auth.logger.close_xterm()  # type: ignore[attr-defined]
    for client in clients:
        if hasattr(client, "logger"):
            client.logger.close_xterm()  # type: ignore[attr-defined] 