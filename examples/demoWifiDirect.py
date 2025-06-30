#!/usr/bin/env python3
"""FastPay *Wi-Fi Direct* demo leveraging :class:`WiFiAuthority` and :class:`Client`.

The topology created by this script is deliberately minimal so that the
Wi-Fi-Direct setup remains manageable:

* one authority station (``auth1``) implemented via :class:`mn_wifi.authority.WiFiAuthority`;
* one client station (``user1``) implemented via :class:`mn_wifi.client.Client`;
* a **peer-to-peer** 802.11 P2P link between the two stations created with
  :class:`mn_wifi.link.WifiDirectLink`.

Once the network is up the script hands control to the interactive *FastPay
CLI* (see ``mn_wifi/examples/fastpay_cli.py``).  Try the following commands::

    ping user1 auth1
    balance user1
    initiate user1 user1 10
    sign <order-id> user1
    broadcast <order-id>

Run as *root* because *Mininet-WiFi* requires network namespaces::

    sudo python3 -m mn_wifi.examples.demoWifiDirect
"""

from __future__ import annotations

import time
from typing import List, Tuple

from mininet.log import info, setLogLevel
from mn_wifi.net import Mininet_wifi
from mn_wifi.link import WifiDirectLink, wmediumd
from mn_wifi.wmediumdConnector import interference

from mn_wifi.authority import WiFiAuthority
from mn_wifi.client import Client
from mn_wifi.cli_fastpay import FastPayCLI
from mn_wifi.transport import TransportKind
from mn_wifi.examples.demoCommon import (
    parse_args as _parse_args,
    open_xterms as _open_xterms,
    close_xterms as _close_xterms,
)

# --------------------------------------------------------------------------------------
# Helper to perform P2P group formation
# --------------------------------------------------------------------------------------

def _p2p_pair(sta1, sta2) -> None:  # noqa: D401
    """Minimal *wpa_cli* sequence to let *sta1* and *sta2* join the same P2P group."""
    sta1.cmd(f"wpa_cli -i{sta1.params['wlan'][0]} p2p_find")
    sta2.cmd(f"wpa_cli -i{sta2.params['wlan'][0]} p2p_find")
    time.sleep(3)
    sta1_mac = sta1.wintfs[0].mac
    sta2_mac = sta2.wintfs[0].mac
    pin = sta1.cmd(
        f"wpa_cli -i{sta1.params['wlan'][0]} p2p_connect {sta2_mac} pin auth"
    ).strip()
    time.sleep(2)
    sta2.cmd(
        f"wpa_cli -i{sta2.params['wlan'][0]} p2p_connect {sta1_mac} {pin}"
    )
    # Allow a bit of time for the group to complete
    time.sleep(5)

# --------------------------------------------------------------------------------------
# Network builder
# --------------------------------------------------------------------------------------

def _create_network(num_auth: int) -> Tuple[Mininet_wifi, List[WiFiAuthority], List[Client]]:
    """Instantiate *Mininet-WiFi* topology with *num_auth* authorities (≥1) and one client."""

    net = Mininet_wifi(link=wmediumd, wmediumd_mode=interference, configWiFiDirect=True)

    # Client ----------------------------------------------------------------------
    user1 = net.addStation(
        "user1",
        cls=Client,
        transport_kind=TransportKind.WIFI_DIRECT,
        ip="10.0.0.2/8",
        position="20,10,0",
    )

    # Authorities -----------------------------------------------------------------
    authorities: List[WiFiAuthority] = []
    committee = {f"auth{i}" for i in range(1, num_auth + 1)}
    for i in range(1, num_auth + 1):
        auth = net.addStation(
            f"auth{i}",
            cls=WiFiAuthority,
            committee_members=committee - {f"auth{i}"},
            transport_kind=TransportKind.WIFI_DIRECT,
            ip=f"10.0.0.{i}/8",
            port=9000 + i,
            position=f"{10 + (i-1)*10},10,0",
        )
        authorities.append(auth)

    # Propagation model -----------------------------------------------------------
    net.setPropagationModel(model="logDistance", exp=3.5)

    info("*** Configuring nodes\n")
    net.configureNodes()

    # Wi-Fi Direct links ----------------------------------------------------------
    # Pair *auth1* with every other station (star topology) -----------------------
    auth1 = authorities[0]
    net.addLink(auth1, user1, cls=WifiDirectLink)
    for peer in authorities[1:]:
        net.addLink(auth1, peer, cls=WifiDirectLink)

    info("*** Starting network\n")
    net.build()

    info("*** Negotiating Wi-Fi Direct groups\n")
    _p2p_pair(auth1, user1)
    for peer in authorities[1:]:
        _p2p_pair(auth1, peer)

    # Start FastPay services ------------------------------------------------------
    for auth in authorities:
        auth.start_fastpay_services()

    # Demo account ---------------------------------------------------------------
    from mn_wifi.baseTypes import Account

    for auth in authorities:
        auth.state.accounts["user1"] = Account(
            address="user1",
            balance=1_000,
            sequence_number=0,
            last_update=time.time(),
        )

    return net, authorities, [user1]

# --------------------------------------------------------------------------------------
# Entry-point
# --------------------------------------------------------------------------------------

def main() -> None:
    opts = _parse_args("FastPay Wi-Fi Direct demo")
    setLogLevel("info")

    net = None
    try:
        net, authorities, clients = _create_network(opts.authorities)

        # Hand over to FastPay interactive shell -----------------------------------
        cli = FastPayCLI(net, authorities, clients)
        print("\nType 'help_fastpay' for FastPay commands or 'help' for all commands. Ctrl-D / Ctrl-C to exit.\n")
        cli.cmdloop()

    finally:
        if net is not None:
            info("*** Stopping network\n")
            net.stop()
        if opts.logs:
            _close_xterms(authorities, clients)
        info("*** Done\n")


if __name__ == "__main__":
    main()
