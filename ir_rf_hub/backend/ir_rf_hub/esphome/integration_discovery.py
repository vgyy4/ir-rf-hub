"""Cache of the ESPHome devices the companion integration most recently
reported via POST /api/integration/discovered-devices.

discovery.py's own mDNS browse runs from inside the App's container,
which sits on Supervisor's isolated internal network -- whether that
actually sees real LAN multicast traffic depends on Supervisor's
Multicast plugin reaching it, which isn't guaranteed for every install.
Home Assistant Core (where the companion integration runs) has reliable
zeroconf discovery regardless, so the integration browses independently
and reports what it finds here; GET /api/devices/discover merges both
sources. See ARCHITECTURE.md's Pairing section for why host_network
isn't the fix -- it broke the App<->integration handshake instead.

Not persisted -- it's just "candidates the integration has seen
recently", refreshed on its own schedule (see the integration's
discovery.py periodic task) and expired here so a since-removed
integration doesn't leave phantom devices "discoverable" forever.
"""

from __future__ import annotations

import time

from ir_rf_hub.schemas import DiscoveredDeviceSchema

_STALE_AFTER_S = 300  # a few missed report cycles

_reported: list[DiscoveredDeviceSchema] = []
_reported_at: float = 0.0


def set_reported_devices(devices: list[DiscoveredDeviceSchema]) -> None:
    global _reported, _reported_at
    _reported = devices
    _reported_at = time.monotonic()


def get_reported_devices() -> list[DiscoveredDeviceSchema]:
    if not _reported or time.monotonic() - _reported_at > _STALE_AFTER_S:
        return []
    return list(_reported)
