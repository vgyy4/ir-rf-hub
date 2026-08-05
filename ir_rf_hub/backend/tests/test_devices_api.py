from __future__ import annotations

import httpx
import pytest

from ir_rf_hub.esphome.device_manager import device_manager
from ir_rf_hub.main import _connect_known_devices, create_app
from tests.fakes.fake_esphome_server import FakeEspHomeServer, FakeInfraredEntity


@pytest.fixture(autouse=True)
async def _reset_device_manager():
    yield
    await device_manager.disconnect_all()
    device_manager._sessions.clear()  # noqa: SLF001 -- test isolation between runs


@pytest.fixture
async def fake_device():
    server = FakeEspHomeServer(
        name="api-esp",
        infrared_entities=[
            FakeInfraredEntity(key=1, object_id="ir_rx", name="IR Receiver", capabilities=2),
        ],
    )
    async with server:
        yield server


@pytest.fixture
async def client():
    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        async with app.router.lifespan_context(app):
            yield c


async def test_create_device_connects_and_persists_entities(client: httpx.AsyncClient, fake_device: FakeEspHomeServer):
    resp = await client.post(
        "/api/devices", json={"name": "Living Room", "host": fake_device.host, "port": fake_device.port}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["connection_state"] == "idle"
    assert body["last_error"] is None
    assert len(body["entities"]) == 1
    assert body["entities"][0]["role"] == "rx"


async def test_create_device_with_unreachable_host_reports_error(client: httpx.AsyncClient):
    resp = await client.post("/api/devices", json={"name": "Nowhere", "host": "127.0.0.1", "port": 1})
    assert resp.status_code == 201
    body = resp.json()
    assert body["connection_state"] == "error"
    assert body["last_error"] is not None


async def test_list_and_delete_device(client: httpx.AsyncClient, fake_device: FakeEspHomeServer):
    created = (
        await client.post("/api/devices", json={"name": "Kitchen", "host": fake_device.host, "port": fake_device.port})
    ).json()

    listed = await client.get("/api/devices")
    assert listed.status_code == 200
    assert any(d["id"] == created["id"] for d in listed.json())

    deleted = await client.delete(f"/api/devices/{created['id']}")
    assert deleted.status_code == 204

    listed_after = await client.get("/api/devices")
    assert all(d["id"] != created["id"] for d in listed_after.json())


async def test_update_device_forces_reconnect(client: httpx.AsyncClient, fake_device: FakeEspHomeServer):
    created = (
        await client.post("/api/devices", json={"name": "Office", "host": fake_device.host, "port": fake_device.port})
    ).json()

    resp = await client.put(f"/api/devices/{created['id']}", json={"name": "Office Renamed"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Office Renamed"


async def test_startup_reconnects_devices_after_session_cache_is_lost(
    client: httpx.AsyncClient, fake_device: FakeEspHomeServer
):
    """A backend restart (routine: HA restarts, App updates) wipes
    device_manager's in-memory session cache, which is otherwise the
    *only* thing connection_state is derived from -- without eagerly
    reconnecting at startup, a perfectly reachable device would show
    "disconnected" until the user happened to fire/record/test it.
    """
    created = (
        await client.post("/api/devices", json={"name": "Bedroom", "host": fake_device.host, "port": fake_device.port})
    ).json()
    assert created["connection_state"] == "idle"

    # Simulate the session cache a fresh restart would start with.
    device_manager._sessions.clear()  # noqa: SLF001
    stale = await client.get("/api/devices")
    assert stale.json()[0]["connection_state"] == "disconnected"

    await _connect_known_devices()

    fresh = await client.get("/api/devices")
    assert fresh.json()[0]["id"] == created["id"]
    assert fresh.json()[0]["connection_state"] == "idle"


async def test_startup_reconnect_skips_unreachable_devices_without_raising(client: httpx.AsyncClient):
    resp = await client.post("/api/devices", json={"name": "Nowhere", "host": "127.0.0.1", "port": 1})
    assert resp.json()["connection_state"] == "error"

    device_manager._sessions.clear()  # noqa: SLF001

    await _connect_known_devices()  # must not raise

    after = await client.get("/api/devices")
    assert after.json()[0]["connection_state"] == "error"
