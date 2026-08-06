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


async def discover_esphome_devices(*, timeout_s: float = 3.0, settle_s: float = 0.4) -> list[DiscoveredDevice]:
    """Browse for at most `timeout_s`, but return as soon as the network goes
    quiet rather than always waiting out the full window.

    Devices on a LAN answer a multicast query within a few hundred
    milliseconds, so a flat sleep spent most of its time waiting for
    responses that had already arrived -- the "Scan for devices" button (and
    the automatic scan when the Devices menu opens) felt slow for no reason.

    `settle_s` is how long a gap with no new announcements counts as quiet.
    The full `timeout_s` is still used when nothing has been found yet, so a
    slow or busy network isn't cut short.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
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
    announced = asyncio.Event()

    def _on_change(zeroconf, service_type, name, state_change) -> None:  # noqa: ANN001
        if state_change is ServiceStateChange.Added:
            pending.add(asyncio.ensure_future(_resolve(name)))
            announced.set()

    service_browser = AsyncServiceBrowser(azc.zeroconf, _SERVICE_TYPE, handlers=[_on_change])

    try:
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break

            announced.clear()
            try:
                await asyncio.wait_for(announced.wait(), timeout=min(settle_s, remaining))
                # Something new turned up -- keep listening for more.
                continue
            except TimeoutError:
                pass

            # Quiet for settle_s. Let any in-flight resolutions land before
            # deciding we're done; a device that announced but hasn't
            # resolved yet still counts as activity.
            if pending:
                await asyncio.wait(set(pending), timeout=max(0.0, deadline - loop.time()))
                pending.difference_update({t for t in pending if t.done()})

            if found and not pending:
                break
    finally:
        for task in pending:
            task.cancel()
        await service_browser.async_cancel()
        await azc.async_close()

    return list(found.values())
