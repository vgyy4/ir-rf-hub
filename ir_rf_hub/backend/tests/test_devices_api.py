from __future__ import annotations

import httpx
import pytest

import ir_rf_hub.api.rest.devices as devices_module
from ir_rf_hub.esphome.connection import (
    DeviceEncryptionKeyInvalidError,
    DeviceRequiresEncryptionError,
    DeviceUnexpectedEncryptionError,
)
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


async def test_create_device_rejects_duplicate_name_case_insensitively(
    client: httpx.AsyncClient, fake_device: FakeEspHomeServer
):
    await client.post("/api/devices", json={"name": "Living Room", "host": fake_device.host, "port": fake_device.port})
    resp = await client.post("/api/devices", json={"name": "living room", "host": "10.0.0.55", "port": 6053})
    assert resp.status_code == 409
    # rejected before ever being saved
    assert len((await client.get("/api/devices")).json()) == 1


async def test_create_device_rejects_duplicate_host(client: httpx.AsyncClient, fake_device: FakeEspHomeServer):
    await client.post("/api/devices", json={"name": "First", "host": fake_device.host, "port": fake_device.port})
    resp = await client.post(
        "/api/devices", json={"name": "Second", "host": fake_device.host, "port": fake_device.port}
    )
    assert resp.status_code == 409
    assert len((await client.get("/api/devices")).json()) == 1


async def test_update_device_rejects_renaming_to_a_duplicate(
    client: httpx.AsyncClient, fake_device: FakeEspHomeServer
):
    await client.post("/api/devices", json={"name": "Kitchen", "host": fake_device.host, "port": fake_device.port})
    other = (
        await client.post("/api/devices", json={"name": "Bathroom", "host": "10.0.0.77", "port": 6053})
    ).json()

    resp = await client.put(f"/api/devices/{other['id']}", json={"name": "kitchen"})
    assert resp.status_code == 409

    # renaming to its own current name (unchanged) must still be allowed
    resp2 = await client.put(f"/api/devices/{other['id']}", json={"name": "Bathroom"})
    assert resp2.status_code == 200


async def test_update_device_rejects_duplicate_host(client: httpx.AsyncClient, fake_device: FakeEspHomeServer):
    await client.post("/api/devices", json={"name": "First", "host": fake_device.host, "port": fake_device.port})
    other = (await client.post("/api/devices", json={"name": "Second", "host": "10.0.0.77", "port": 6053})).json()

    # must match both host AND port to collide -- a shared host with a
    # different port is a legitimate distinct target (see
    # _ensure_unique_host's comment)
    resp = await client.put(
        f"/api/devices/{other['id']}", json={"host": fake_device.host, "port": fake_device.port}
    )
    assert resp.status_code == 409


class _FakeConnection:
    """Stands in for esphome.connection.EspHomeConnection in the
    devices.py module namespace -- monkeypatched in so
    _reject_if_encryption_mismatch's throwaway pre-check hits a
    deterministic outcome without a real Noise handshake (the fake
    ESPHome test server is plaintext-only, see
    test_connection_encryption_errors.py).
    """

    def __init__(self, *, host, port, password=None, noise_psk=None, connect_timeout_s=10):
        pass

    async def connect(self):
        raise self._exc_cls("simulated")

    async def disconnect(self):
        pass


def _fake_connection_raising(exc_cls: type[Exception]):
    def factory(**kwargs):
        conn = _FakeConnection(**kwargs)
        conn._exc_cls = exc_cls
        return conn

    return factory


async def test_create_device_rejects_when_device_requires_encryption(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        devices_module, "EspHomeConnection", _fake_connection_raising(DeviceRequiresEncryptionError)
    )
    resp = await client.post("/api/devices", json={"name": "Needs Key", "host": "10.0.0.99", "port": 6053})
    assert resp.status_code == 422
    assert "requires an encryption key" in resp.json()["detail"]
    assert (await client.get("/api/devices")).json() == []


async def test_create_device_rejects_when_encryption_key_is_wrong(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        devices_module, "EspHomeConnection", _fake_connection_raising(DeviceEncryptionKeyInvalidError)
    )
    resp = await client.post(
        "/api/devices",
        json={"name": "Wrong Key", "host": "10.0.0.99", "port": 6053, "encryption_key": "not-the-real-key"},
    )
    assert resp.status_code == 422
    assert "incorrect" in resp.json()["detail"]
    assert (await client.get("/api/devices")).json() == []


async def test_create_device_rejects_when_key_given_but_not_needed(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        devices_module, "EspHomeConnection", _fake_connection_raising(DeviceUnexpectedEncryptionError)
    )
    resp = await client.post(
        "/api/devices",
        json={"name": "No Encryption Here", "host": "10.0.0.99", "port": 6053, "encryption_key": "unnecessary"},
    )
    assert resp.status_code == 422
    assert "leave the key blank" in resp.json()["detail"]
    assert (await client.get("/api/devices")).json() == []


async def test_update_device_rejects_new_encryption_key_that_is_wrong(
    client: httpx.AsyncClient, fake_device: FakeEspHomeServer, monkeypatch: pytest.MonkeyPatch
):
    created = (
        await client.post("/api/devices", json={"name": "Living Room", "host": fake_device.host, "port": fake_device.port})
    ).json()

    monkeypatch.setattr(
        devices_module, "EspHomeConnection", _fake_connection_raising(DeviceEncryptionKeyInvalidError)
    )
    resp = await client.put(f"/api/devices/{created['id']}", json={"encryption_key": "wrong-key"})
    assert resp.status_code == 422

    # the device is untouched -- still connectable under its old (no-key) config
    unchanged = (await client.get("/api/devices")).json()[0]
    assert unchanged["name"] == "Living Room"


async def test_update_device_without_touching_connection_fields_skips_the_precheck(
    client: httpx.AsyncClient, fake_device: FakeEspHomeServer, monkeypatch: pytest.MonkeyPatch
):
    created = (
        await client.post("/api/devices", json={"name": "Living Room", "host": fake_device.host, "port": fake_device.port})
    ).json()

    # if the pre-check ran here, this would reject the update -- proves it
    # only fires when host/port/encryption_key/password actually change
    monkeypatch.setattr(
        devices_module, "EspHomeConnection", _fake_connection_raising(DeviceRequiresEncryptionError)
    )
    resp = await client.put(f"/api/devices/{created['id']}", json={"name": "Living Room Renamed"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Living Room Renamed"
