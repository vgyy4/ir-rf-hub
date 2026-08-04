from __future__ import annotations

import httpx
import pytest

from ir_rf_hub.esphome.device_manager import device_manager
from ir_rf_hub.main import create_app
from tests.fakes.fake_esphome_server import FakeEspHomeServer, FakeInfraredEntity


@pytest.fixture(autouse=True)
async def _reset_device_manager():
    yield
    await device_manager.disconnect_all()
    device_manager._sessions.clear()  # noqa: SLF001


@pytest.fixture
async def fake_device():
    server = FakeEspHomeServer(
        name="commands-esp",
        infrared_entities=[
            FakeInfraredEntity(key=1, object_id="ir_rx", name="IR Receiver", capabilities=2),
            FakeInfraredEntity(key=2, object_id="ir_tx", name="IR Transmitter", capabilities=1),
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


async def test_create_list_and_get_command_omits_raw_timings_from_list(client: httpx.AsyncClient):
    created = (
        await client.post(
            "/api/commands",
            json={"name": "TV Power", "type": "ir", "raw_timings": [9000, -4500, 560, -560], "carrier_frequency_hz": 38000},
        )
    ).json()
    assert created["raw_timings"] == [9000, -4500, 560, -560]

    listed = (await client.get("/api/commands")).json()
    assert listed[0]["name"] == "TV Power"
    assert "raw_timings" not in listed[0]

    detail = (await client.get(f"/api/commands/{created['id']}")).json()
    assert detail["raw_timings"] == [9000, -4500, 560, -560]


async def test_fire_without_default_device_and_no_device_given_fails(client: httpx.AsyncClient):
    created = (
        await client.post(
            "/api/commands", json={"name": "No Default", "type": "ir", "raw_timings": [1, -1]}
        )
    ).json()
    resp = await client.post(f"/api/commands/{created['id']}/fire", json={})
    assert resp.status_code == 400


async def test_fire_via_explicit_device_reaches_fake_server(client: httpx.AsyncClient, fake_device: FakeEspHomeServer):
    device = (
        await client.post("/api/devices", json={"name": "Living Room", "host": fake_device.host, "port": fake_device.port})
    ).json()
    command = (
        await client.post(
            "/api/commands",
            json={"name": "AC On", "type": "ir", "raw_timings": [9000, -4500, 560, -560], "carrier_frequency_hz": 38000},
        )
    ).json()

    resp = await client.post(f"/api/commands/{command['id']}/fire", json={"device_id": device["id"]})
    assert resp.status_code == 204
    assert len(fake_device.transmitted) == 1
    assert fake_device.transmitted[0].timings == [9000, -4500, 560, -560]
    assert fake_device.transmitted[0].carrier_frequency == 38000


async def test_fire_uses_default_device_when_none_given(client: httpx.AsyncClient, fake_device: FakeEspHomeServer):
    device = (
        await client.post("/api/devices", json={"name": "Bedroom", "host": fake_device.host, "port": fake_device.port})
    ).json()
    command = (
        await client.post(
            "/api/commands",
            json={
                "name": "Fan Toggle",
                "type": "ir",
                "raw_timings": [1, -1],
                "default_device_id": device["id"],
            },
        )
    ).json()

    resp = await client.post(f"/api/commands/{command['id']}/fire", json={})
    assert resp.status_code == 204
    assert len(fake_device.transmitted) == 1


async def test_candidate_devices_filters_to_transmitters_of_matching_type(
    client: httpx.AsyncClient, fake_device: FakeEspHomeServer
):
    rx_only_server = FakeEspHomeServer(
        name="rx-only-esp",
        infrared_entities=[FakeInfraredEntity(key=1, object_id="ir_rx", name="IR RX", capabilities=2)],
    )
    async with rx_only_server:
        tx_device = (
            await client.post(
                "/api/devices", json={"name": "TX Device", "host": fake_device.host, "port": fake_device.port}
            )
        ).json()
        await client.post(
            "/api/devices", json={"name": "RX Only Device", "host": rx_only_server.host, "port": rx_only_server.port}
        )

        command = (
            await client.post("/api/commands", json={"name": "Test", "type": "ir", "raw_timings": [1, -1]})
        ).json()

        candidates = (await client.get(f"/api/commands/{command['id']}/candidate-devices")).json()
        assert [d["id"] for d in candidates] == [tx_device["id"]]


async def test_delete_command(client: httpx.AsyncClient):
    created = (
        await client.post("/api/commands", json={"name": "Delete Me", "type": "rf", "raw_timings": [1, -1]})
    ).json()
    resp = await client.delete(f"/api/commands/{created['id']}")
    assert resp.status_code == 204
    assert (await client.get(f"/api/commands/{created['id']}")).status_code == 404
