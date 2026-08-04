"""Short mDNS browse for ESPHome devices on the LAN (`_esphomelib._tcp.local.`).
This is for populating the App's "add a device" UI with candidates -- unrelated
to the App<->companion-integration pairing, which deliberately avoids
zeroconf entirely (see security.py).
"""

from __future__ import annotations

import asyncio
import ipaddress
from dataclasses import dataclass

from zeroconf import ServiceStateChange
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

_SERVICE_TYPE = "_esphomelib._tcp.local."


@dataclass
class DiscoveredDevice:
    name: str
    host: str
    port: int


async def discover_esphome_devices(*, timeout_s: float = 3.0) -> list[DiscoveredDevice]:
    found: dict[str, DiscoveredDevice] = {}
    azc = AsyncZeroconf()

    async def _resolve(name: str) -> None:
        info = AsyncServiceInfo(_SERVICE_TYPE, name)
        if await info.async_request(azc.zeroconf, 2000):
            addresses = info.parsed_scoped_addresses()
            if not addresses:
                return
            host = next((a for a in addresses if not ipaddress.ip_address(a.split("%")[0]).is_link_local), addresses[0])
            found[name] = DiscoveredDevice(
                name=info.server.rstrip(".") if info.server else name,
                host=host,
                port=info.port or 6053,
            )

    pending: set[asyncio.Task] = set()

    def _on_change(zeroconf, service_type, name, state_change) -> None:  # noqa: ANN001
        if state_change is ServiceStateChange.Added:
            pending.add(asyncio.ensure_future(_resolve(name)))

    service_browser = AsyncServiceBrowser(azc.zeroconf, _SERVICE_TYPE, handlers=[_on_change])

    try:
        await asyncio.sleep(timeout_s)
        if pending:
            await asyncio.wait(pending, timeout=2.0)
    finally:
        await service_browser.async_cancel()
        await azc.async_close()

    return list(found.values())
