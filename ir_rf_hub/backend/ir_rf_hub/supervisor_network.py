"""The Home Assistant host's real IPv4 gateway and subnet, from Supervisor.

Used by the static-IP tip shown after adding a device. That tip used to
assume the two values every home network *usually* has -- a gateway at
`.1` and a /24 -- which is a guess, and a wrong one on any network that
isn't laid out that way. Supervisor knows the actual answer for the
interface Home Assistant itself is on, and `hassio_api: true` in
config.yaml already grants us the token to ask.

The ESP is assumed to share Home Assistant's subnet. That's true whenever
they're on the same LAN, which is the case this tip is for; when it isn't,
the tip degrades to the old convention-based guess rather than asserting
something wrong.
"""

from __future__ import annotations

import ipaddress
import logging
import os
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

_SUPERVISOR_NETWORK_URL = "http://supervisor/network/info"


@dataclass(frozen=True)
class HostNetwork:
    """The primary interface's IPv4 configuration."""

    gateway: str
    """e.g. "192.168.1.1"."""
    subnet_mask: str
    """Dotted-quad form of the CIDR prefix, e.g. "255.255.255.0"."""
    prefix_len: int
    network: ipaddress.IPv4Network


def _parse(payload: dict) -> HostNetwork | None:
    interfaces = payload.get("data", {}).get("interfaces") or []

    # Prefer the interface Supervisor marks primary; otherwise the first
    # connected one with a usable IPv4 config.
    ordered = sorted(interfaces, key=lambda i: (not i.get("primary"), not i.get("connected")))

    for interface in ordered:
        ipv4 = interface.get("ipv4") or {}
        gateway = ipv4.get("gateway")
        # Supervisor has used both keys across versions; accept either, and
        # `address` may be a list of CIDR strings.
        raw = ipv4.get("ip_address") or ipv4.get("address")
        if isinstance(raw, list):
            raw = raw[0] if raw else None
        if not gateway or not raw:
            continue
        try:
            iface = ipaddress.ip_interface(raw)
        except ValueError:
            continue
        if iface.version != 4:
            continue
        return HostNetwork(
            gateway=str(gateway),
            subnet_mask=str(iface.netmask),
            prefix_len=iface.network.prefixlen,
            network=iface.network,
        )
    return None


async def get_host_network() -> HostNetwork | None:
    """Returns None outside Supervisor (local dev) or if the call fails --
    callers fall back to the convention-based guess."""
    supervisor_token = os.environ.get("SUPERVISOR_TOKEN")
    if not supervisor_token:
        logger.debug("SUPERVISOR_TOKEN not set -- cannot read host network config")
        return None

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                _SUPERVISOR_NETWORK_URL,
                headers={"Authorization": f"Bearer {supervisor_token}"},
            )
            response.raise_for_status()
            return _parse(response.json())
    except (httpx.HTTPError, ValueError):
        logger.warning("Failed to read network info from Supervisor", exc_info=True)
        return None
