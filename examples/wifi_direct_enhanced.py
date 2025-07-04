#!/usr/bin/env python

"""Enhanced WiFi Direct Example with Connectivity Verification.

This example demonstrates WiFi Direct P2P communication with additional
debugging and connectivity verification features.
"""

import sys
import time
from typing import Optional

from mininet.log import setLogLevel, info
from mn_wifi.link import wmediumd, WifiDirectLink
from mn_wifi.cli import CLI
from mn_wifi.net import Mininet_wifi
from mn_wifi.node import Station
from mn_wifi.wmediumdConnector import interference


def check_connectivity(sta1: Station, sta2: Station) -> bool:
    """Check if two stations can communicate.
    
    Args:
        sta1: First station
        sta2: Second station
        
    Returns:
        True if stations can ping each other, False otherwise
    """
    # Get IP addresses
    sta1_ip = sta1.wintfs[list(sta1.wintfs.keys())[0]].ip.split('/')[0]
    sta2_ip = sta2.wintfs[list(sta2.wintfs.keys())[0]].ip.split('/')[0]
    
    info(f"*** Testing connectivity: {sta1.name}({sta1_ip}) -> {sta2.name}({sta2_ip})\n")
    
    # Test ping from sta1 to sta2
    result = sta1.cmd(f'ping -c 3 -W 2 {sta2_ip}')
    success = '3 received' in result or '3 packets transmitted, 3 received' in result
    
    if success:
        info("✅ Connectivity test PASSED\n")
    else:
        info("❌ Connectivity test FAILED\n")
        info(f"Ping output: {result}\n")
    
    return success


def get_signal_strength(sta1: Station, sta2: Station) -> Optional[float]:
    """Get signal strength between two stations.
    
    Args:
        sta1: First station
        sta2: Second station
        
    Returns:
        Signal strength in dBm, or None if unavailable
    """
    try:
        # Get distance between stations
        if hasattr(sta1, 'get_distance_to'):
            distance = sta1.get_distance_to(sta2)
            info(f"*** Distance between {sta1.name} and {sta2.name}: {distance:.2f}m\n")
            return distance
    except Exception as e:
        info(f"Could not get distance: {e}\n")
    return None


def bring_interfaces_up(sta1: Station, sta2: Station) -> None:
    """Manually bring up WiFi interfaces and configure them properly.
    
    Args:
        sta1: First station
        sta2: Second station
    """
    info("*** Bringing up WiFi interfaces\n")
    
    # Bring up interfaces
    sta1.cmd('ip link set sta1-wlan0 up')
    sta2.cmd('ip link set sta2-wlan0 up')
    
    # Wait a bit for interfaces to come up
    time.sleep(2)
    
    # Check interface status
    sta1_status = sta1.cmd('ip link show sta1-wlan0')
    sta2_status = sta2.cmd('ip link show sta2-wlan0')
    
    info(f"*** {sta1.name} interface status: {sta1_status.strip()}\n")
    info(f"*** {sta2.name} interface status: {sta2_status.strip()}\n")


def setup_wifi_direct_manually(sta1: Station, sta2: Station) -> bool:
    """Manually configure WiFi Direct without relying on automatic configuration.
    
    Args:
        sta1: First station
        sta2: Second station
        
    Returns:
        True if configuration successful, False otherwise
    """
    info("*** Setting up WiFi Direct manually\n")
    
    # Stop any existing wpa_supplicant processes
    sta1.cmd('killall wpa_supplicant 2>/dev/null')
    sta2.cmd('killall wpa_supplicant 2>/dev/null')
    time.sleep(1)
    
    # Create basic wpa_supplicant configuration
    wpa_config = """
ctrl_interface=/var/run/wpa_supplicant
ap_scan=1
device_name=STA
device_type=1-0050F204-1
p2p_go_intent=7
p2p_go_ht40=1
"""
    
    # Write configuration files
    sta1.cmd('echo "%s" > /tmp/sta1_wpa.conf' % wpa_config)
    sta2.cmd('echo "%s" > /tmp/sta2_wpa.conf' % wpa_config)
    
    # Start wpa_supplicant with P2P support
    info("*** Starting wpa_supplicant with P2P support\n")
    sta1.cmd('wpa_supplicant -B -i sta1-wlan0 -c /tmp/sta1_wpa.conf -Dnl80211')
    sta2.cmd('wpa_supplicant -B -i sta2-wlan0 -c /tmp/sta2_wpa.conf -Dnl80211')
    
    # Wait for wpa_supplicant to start
    time.sleep(3)
    
    # Check if wpa_supplicant is running
    wpa1_check = sta1.cmd('pgrep -f "wpa_supplicant.*sta1-wlan0"')
    wpa2_check = sta2.cmd('pgrep -f "wpa_supplicant.*sta2-wlan0"')
    
    if not wpa1_check.strip() or not wpa2_check.strip():
        info("❌ wpa_supplicant failed to start\n")
        return False
    
    info("✅ wpa_supplicant started successfully\n")
    return True


def wait_for_p2p_connection(sta1: Station, sta2: Station, timeout: int = 30) -> bool:
    """Wait for P2P connection to be established.
    
    Args:
        sta1: First station
        sta2: Second station
        timeout: Maximum time to wait in seconds
        
    Returns:
        True if connection established, False if timeout
    """
    info(f"*** Waiting for P2P connection (timeout: {timeout}s)\n")
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        # Check if P2P group is formed
        status1 = sta1.cmd('wpa_cli -ista1-wlan0 status 2>/dev/null')
        
        if 'p2p_state=GO_NEGOTIATION_COMPLETE' in status1 or 'p2p_state=ACTIVE' in status1:
            info("✅ P2P connection established\n")
            return True
            
        time.sleep(1)
    
    info("❌ P2P connection timeout\n")
    return False


def topology(args):
    """Create and test WiFi Direct network topology."""
    # Try without wmediumd first for simpler debugging
    if '-w' in args:
        net = Mininet_wifi(link=wmediumd, wmediumd_mode=interference,
                           configWiFiDirect=True)
    else:
        net = Mininet_wifi(configWiFiDirect=True)

    info("*** Creating nodes\n")
    # Use larger range to meet system requirements and closer positions
    sta1 = net.addStation('sta1', ip='10.0.0.1/8', position='10,10,0', range=120)
    sta2 = net.addStation('sta2', ip='10.0.0.2/8', position='12,12,0', range=120)

    info("*** Configuring Propagation Model\n")
    # Use free space model for better initial connectivity
    net.setPropagationModel(model="friiSpace")

    info("*** Configuring nodes\n")
    net.configureNodes()

    if '-p' not in args:
        net.plotGraph(max_x=200, max_y=200)

    # Check initial distance
    get_signal_strength(sta1, sta2)

    info("*** Starting WiFi Direct\n")
    net.addLink(sta1, intf='sta1-wlan0', cls=WifiDirectLink)
    net.addLink(sta2, intf='sta2-wlan0', cls=WifiDirectLink)

    info("*** Starting network\n")
    net.build()

    # Bring up interfaces manually
    bring_interfaces_up(sta1, sta2)

    # Setup WiFi Direct manually
    if not setup_wifi_direct_manually(sta1, sta2):
        info("❌ WiFi Direct setup failed\n")
        CLI(net)
        net.stop()
        return

    # Enhanced P2P connection process
    info("*** Starting P2P discovery\n")
    sta1.cmd('wpa_cli -ista1-wlan0 p2p_find')
    sta2.cmd('wpa_cli -ista2-wlan0 p2p_find')
    
    # Wait longer for discovery
    time.sleep(10)
    
    # Check discovered peers
    peers1 = sta1.cmd('wpa_cli -ista1-wlan0 p2p_peers')
    peers2 = sta2.cmd('wpa_cli -ista2-wlan0 p2p_peers')
    
    info(f"*** {sta1.name} discovered peers: {peers1.strip()}\n")
    info(f"*** {sta2.name} discovered peers: {peers2.strip()}\n")
    
    if not peers1.strip() and not peers2.strip():
        info("⚠️  No peers discovered - trying alternative approach\n")
        
        # Try to force connection by MAC address
        sta1_mac = sta1.wintfs[0].mac
        sta2_mac = sta2.wintfs[0].mac
        
        info(f"*** Attempting direct connection: {sta1_mac} -> {sta2_mac}\n")
        
        # Try WPS PIN method
        pin = sta1.cmd('wpa_cli -ista1-wlan0 p2p_connect %s pin auth' % sta2_mac)
        time.sleep(3)
        sta2.cmd('wpa_cli -ista2-wlan0 p2p_connect %s %s' % (sta1_mac, pin.strip()))
        
        # Wait for connection
        if wait_for_p2p_connection(sta1, sta2):
            time.sleep(5)
            check_connectivity(sta1, sta2)
        else:
            info("❌ Direct connection failed - trying adhoc mode\n")
            # Fallback to ad-hoc mode
            setup_adhoc_fallback(sta1, sta2)
    else:
        info("*** Establishing P2P connection\n")
        pin = sta1.cmd('wpa_cli -ista1-wlan0 p2p_connect %s pin auth'
                       % sta2.wintfs[0].mac)
        
        time.sleep(3)
        
        sta2.cmd('wpa_cli -ista2-wlan0 p2p_connect %s %s'
                 % (sta1.wintfs[0].mac, pin.strip()))

        # Wait for connection establishment
        if wait_for_p2p_connection(sta1, sta2):
            # Test connectivity
            time.sleep(5)  # Allow interface configuration
            check_connectivity(sta1, sta2)
        else:
            info("❌ P2P connection failed\n")

    info("*** Debugging Information\n")
    info(f"*** {sta1.name} interfaces:\n")
    info(sta1.cmd('ip addr show'))
    info(f"*** {sta2.name} interfaces:\n")
    info(sta2.cmd('ip addr show'))
    
    # Additional debugging
    info("*** wpa_supplicant status:\n")
    info(f"*** {sta1.name}: {sta1.cmd('wpa_cli -ista1-wlan0 status')}\n")
    info(f"*** {sta2.name}: {sta2.cmd('wpa_cli -ista2-wlan0 status')}\n")

    info("*** Running CLI\n")
    CLI(net)

    info("*** Stopping network\n")
    net.stop()


def setup_adhoc_fallback(sta1: Station, sta2: Station) -> None:
    """Setup ad-hoc mode as fallback when WiFi Direct fails.
    
    Args:
        sta1: First station
        sta2: Second station
    """
    info("*** Setting up ad-hoc fallback mode\n")
    
    # Stop wpa_supplicant
    sta1.cmd('killall wpa_supplicant 2>/dev/null')
    sta2.cmd('killall wpa_supplicant 2>/dev/null')
    time.sleep(1)
    
    # Configure ad-hoc mode
    sta1.cmd('iwconfig sta1-wlan0 mode ad-hoc')
    sta2.cmd('iwconfig sta2-wlan0 mode ad-hoc')
    
    # Set same ESSID and channel
    sta1.cmd('iwconfig sta1-wlan0 essid "test-adhoc" channel 6')
    sta2.cmd('iwconfig sta2-wlan0 essid "test-adhoc" channel 6')
    
    # Bring interfaces up
    sta1.cmd('ip link set sta1-wlan0 up')
    sta2.cmd('ip link set sta2-wlan0 up')
    
    time.sleep(3)
    
    # Test connectivity
    check_connectivity(sta1, sta2)


if __name__ == '__main__':
    setLogLevel('info')
    print("Usage: python wifi_direct_enhanced.py [-w] [-p]")
    print("  -w: Enable wmediumd (may cause issues)")
    print("  -p: Disable plotting")
    topology(sys.argv) 