from __future__ import annotations

import httpx
import pytest

from ir_rf_hub.esphome.device_manager import device_manager
from ir_rf_hub.main import create_app
from ir_rf_hub.security import decode_pairing_code
from tests.fakes.fake_esphome_server import FakeEspHomeServer, FakeInfraredEntity


@pytest.fixture(autouse=True)
async def _reset_device_manager():
    yield
    await device_manager.disconnect_all()
    device_manager._sessions.clear()  # noqa: SLF001


@pytest.fixture
async def client():
    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        async with app.router.lifespan_context(app):
            yield c


async def _token(client: httpx.AsyncClient) -> str:
    status = (await client.get("/api/pairing-status")).json()
    assert status["paired"] is False
    return decode_pairing_code(status["code"])["token"]


async def test_integration_endpoints_reject_missing_or_wrong_token(client: httpx.AsyncClient):
    no_auth = await client.get("/api/integration/commands")
    assert no_auth.status_code == 401

    wrong = await client.get("/api/integration/commands", headers={"Authorization": "Bearer wrong-token"})
    assert wrong.status_code == 401


async def test_integration_endpoints_accept_pairing_code_token(client: httpx.AsyncClient):
    token = await _token(client)
    resp = await client.get("/api/integration/commands", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == []


async def test_integration_health_requires_token(client: httpx.AsyncClient):
    token = await _token(client)
    resp = await client.get("/api/integration/health", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_integration_fire_reaches_default_device(client: httpx.AsyncClient):
    token = await _token(client)
    server = FakeEspHomeServer(
        name="integration-esp",
        infrared_entities=[FakeInfraredEntity(key=1, object_id="ir_tx", name="IR TX", capabilities=1)],
    )
    async with server:
        device = (
            await client.post("/api/devices", json={"name": "Integration ESP", "host": server.host, "port": server.port})
        ).json()
        command = (
            await client.post(
                "/api/commands",
                json={
                    "name": "Integration Fire",
                    "type": "ir",
                    "raw_timings": [1, -1],
                    "default_device_id": device["id"],
                },
            )
        ).json()

        resp = await client.post(
            f"/api/integration/commands/{command['id']}/fire", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 204
        assert len(server.transmitted) == 1


async def test_integration_fire_without_default_fails_loudly(client: httpx.AsyncClient):
    token = await _token(client)
    command = (
        await client.post("/api/commands", json={"name": "No Default", "type": "ir", "raw_timings": [1, -1]})
    ).json()

    resp = await client.post(
        f"/api/integration/commands/{command['id']}/fire", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 400


async def test_integration_fire_accepts_an_explicit_device_id(client: httpx.AsyncClient):
    # The select entity (device.py's async_select_option) posts an
    # explicit device_id -- distinct from a bare button/switch press,
    # which relies on fire_command's own default/single-candidate
    # fallback instead.
    token = await _token(client)
    server = FakeEspHomeServer(
        name="integration-esp",
        infrared_entities=[FakeInfraredEntity(key=1, object_id="ir_tx", name="IR TX", capabilities=1)],
    )
    async with server:
        device = (
            await client.post("/api/devices", json={"name": "Chosen ESP", "host": server.host, "port": server.port})
        ).json()
        command = (
            await client.post("/api/commands", json={"name": "Pick One", "type": "ir", "raw_timings": [1, -1]})
        ).json()

        resp = await client.post(
            f"/api/integration/commands/{command['id']}/fire",
            headers={"Authorization": f"Bearer {token}"},
            json={"device_id": device["id"]},
        )
        assert resp.status_code == 204
        assert len(server.transmitted) == 1


async def test_integration_candidate_devices_requires_token(client: httpx.AsyncClient):
    command = (
        await client.post("/api/commands", json={"name": "Needs Auth", "type": "ir", "raw_timings": [1, -1]})
    ).json()
    resp = await client.get(f"/api/integration/commands/{command['id']}/candidate-devices")
    assert resp.status_code == 401


async def test_integration_candidate_devices_returns_matching_transmitters(client: httpx.AsyncClient):
    token = await _token(client)
    server = FakeEspHomeServer(
        name="integration-esp",
        infrared_entities=[FakeInfraredEntity(key=1, object_id="ir_tx", name="IR TX", capabilities=1)],
    )
    async with server:
        device = (
            await client.post("/api/devices", json={"name": "Living Room", "host": server.host, "port": server.port})
        ).json()
        command = (
            await client.post("/api/commands", json={"name": "Fan", "type": "ir", "raw_timings": [1, -1]})
        ).json()

        resp = await client.get(
            f"/api/integration/commands/{command['id']}/candidate-devices",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json() == [{"id": device["id"], "name": "Living Room"}]
