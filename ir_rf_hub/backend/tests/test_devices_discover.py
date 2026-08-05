"""GET /api/devices/discover merges two sources: the App's own local
mDNS browse and whatever the companion integration most recently
reported via POST /api/integration/discovered-devices. The local browse
is monkeypatched everywhere here -- it's a real zeroconf/multicast
operation that doesn't belong in a fast, deterministic unit test (and
may not even work in a sandboxed CI network namespace at all).
"""

from __future__ import annotations

import httpx
import pytest

import ir_rf_hub.api.rest.devices as devices_module
import ir_rf_hub.esphome.integration_discovery as integration_discovery
from ir_rf_hub.esphome.discovery import DiscoveredDevice
from ir_rf_hub.main import create_app
from ir_rf_hub.security import decode_pairing_code


@pytest.fixture(autouse=True)
def _reset_reported_devices():
    integration_discovery.set_reported_devices([])
    yield
    integration_discovery.set_reported_devices([])


@pytest.fixture
def _no_local_devices(monkeypatch: pytest.MonkeyPatch):
    async def fake_discover(*, timeout_s: float = 3.0) -> list[DiscoveredDevice]:
        return []

    monkeypatch.setattr(devices_module, "discover_esphome_devices", fake_discover)


@pytest.fixture
async def client():
    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        async with app.router.lifespan_context(app):
            yield c


async def _token(client: httpx.AsyncClient) -> str:
    status = (await client.get("/api/pairing-status")).json()
    return decode_pairing_code(status["code"])["token"]


async def test_discover_returns_nothing_with_no_sources(client: httpx.AsyncClient, _no_local_devices):
    resp = await client.get("/api/devices/discover")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_discover_includes_devices_reported_by_the_integration(client: httpx.AsyncClient, _no_local_devices):
    token = await _token(client)
    report = await client.post(
        "/api/integration/discovered-devices",
        headers={"Authorization": f"Bearer {token}"},
        json=[{"name": "integration-esp", "host": "10.0.0.9", "port": 6053}],
    )
    assert report.status_code == 204

    resp = await client.get("/api/devices/discover")
    assert resp.json() == [{"name": "integration-esp", "host": "10.0.0.9", "port": 6053}]


async def test_reporting_discovered_devices_requires_a_token(client: httpx.AsyncClient):
    resp = await client.post("/api/integration/discovered-devices", json=[])
    assert resp.status_code == 401


async def test_discover_excludes_devices_already_added(client: httpx.AsyncClient, _no_local_devices):
    token = await _token(client)
    await client.post(
        "/api/integration/discovered-devices",
        headers={"Authorization": f"Bearer {token}"},
        json=[{"name": "integration-esp", "host": "10.0.0.9", "port": 6053}],
    )
    await client.post("/api/devices", json={"name": "Already added", "host": "10.0.0.9", "port": 6053})

    resp = await client.get("/api/devices/discover")
    assert resp.json() == []


async def test_discover_prefers_local_result_on_host_collision(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch):
    async def fake_discover(*, timeout_s: float = 3.0) -> list[DiscoveredDevice]:
        return [DiscoveredDevice(name="fresher-local-name", host="10.0.0.9", port=6053)]

    monkeypatch.setattr(devices_module, "discover_esphome_devices", fake_discover)

    token = await _token(client)
    await client.post(
        "/api/integration/discovered-devices",
        headers={"Authorization": f"Bearer {token}"},
        json=[{"name": "stale-reported-name", "host": "10.0.0.9", "port": 6053}],
    )

    resp = await client.get("/api/devices/discover")
    assert resp.json() == [{"name": "fresher-local-name", "host": "10.0.0.9", "port": 6053}]
