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


async def test_fire_without_default_auto_resolves_the_sole_candidate_device(
    client: httpx.AsyncClient, fake_device: FakeEspHomeServer
):
    # No default_device_id and no explicit device in the fire request --
    # this is exactly what the companion integration's button/switch
    # entities send, since they have no way to prompt "which ESP?" the
    # way the App's own UI can.
    await client.post("/api/devices", json={"name": "Only ESP", "host": fake_device.host, "port": fake_device.port})
    command = (
        await client.post("/api/commands", json={"name": "Fan", "type": "ir", "raw_timings": [1, -1]})
    ).json()

    resp = await client.post(f"/api/commands/{command['id']}/fire", json={})
    assert resp.status_code == 204
    assert len(fake_device.transmitted) == 1


async def test_fire_without_default_stays_ambiguous_with_two_candidate_devices(
    client: httpx.AsyncClient, fake_device: FakeEspHomeServer
):
    second_server = FakeEspHomeServer(
        name="second-esp",
        infrared_entities=[FakeInfraredEntity(key=2, object_id="ir_tx", name="IR TX", capabilities=1)],
    )
    async with second_server:
        await client.post("/api/devices", json={"name": "ESP One", "host": fake_device.host, "port": fake_device.port})
        await client.post(
            "/api/devices", json={"name": "ESP Two", "host": second_server.host, "port": second_server.port}
        )
        command = (
            await client.post("/api/commands", json={"name": "Fan", "type": "ir", "raw_timings": [1, -1]})
        ).json()

        resp = await client.post(f"/api/commands/{command['id']}/fire", json={})
        assert resp.status_code == 400


async def test_create_command_rejects_duplicate_name_case_insensitively(client: httpx.AsyncClient):
    await client.post("/api/commands", json={"name": "TV Power", "type": "ir", "raw_timings": [1, -1]})
    resp = await client.post("/api/commands", json={"name": "tv power", "type": "rf", "raw_timings": [1, -1]})
    assert resp.status_code == 409


async def test_update_command_rejects_renaming_to_a_duplicate(client: httpx.AsyncClient):
    await client.post("/api/commands", json={"name": "Fan On", "type": "rf", "raw_timings": [1, -1]})
    other = (await client.post("/api/commands", json={"name": "Fan Off", "type": "rf", "raw_timings": [1, -1]})).json()

    resp = await client.put(f"/api/commands/{other['id']}", json={"name": "fan on"})
    assert resp.status_code == 409

    # Renaming to its own current name (unchanged) must still be allowed.
    resp2 = await client.put(f"/api/commands/{other['id']}", json={"name": "Fan Off"})
    assert resp2.status_code == 200


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


async def test_create_and_get_command_round_trips_repeat_timings_and_protocol(client: httpx.AsyncClient):
    created = (
        await client.post(
            "/api/commands",
            json={
                "name": "TV Power",
                "type": "ir",
                "raw_timings": [9000, -4500, 560, -560],
                "repeat_timings": [9000, -2250, 560],
                "repeat_protocol": "nec_leader_repeat",
            },
        )
    ).json()
    assert created["repeat_timings"] == [9000, -2250, 560]
    assert created["repeat_protocol"] == "nec_leader_repeat"

    detail = (await client.get(f"/api/commands/{created['id']}")).json()
    assert detail["repeat_timings"] == [9000, -2250, 560]
    assert detail["repeat_protocol"] == "nec_leader_repeat"


async def test_create_command_without_repeat_timings_leaves_it_null(client: httpx.AsyncClient):
    created = (
        await client.post("/api/commands", json={"name": "Simple", "type": "ir", "raw_timings": [1, -1]})
    ).json()
    assert created["repeat_timings"] is None
    assert created["repeat_protocol"] is None


async def test_update_command_can_clear_repeat_timings(client: httpx.AsyncClient):
    created = (
        await client.post(
            "/api/commands",
            json={
                "name": "Two Shape",
                "type": "ir",
                "raw_timings": [9000, -4500, 560, -560],
                "repeat_timings": [9000, -2250, 560],
            },
        )
    ).json()

    updated = (
        await client.put(f"/api/commands/{created['id']}", json={"repeat_timings": None, "repeat_protocol": None})
    ).json()
    assert updated["repeat_timings"] is None
    assert updated["repeat_protocol"] is None


async def test_fire_single_shape_command_sends_one_burst_repeated_n_times(
    client: httpx.AsyncClient, fake_device: FakeEspHomeServer
):
    device = (
        await client.post("/api/devices", json={"name": "Living Room", "host": fake_device.host, "port": fake_device.port})
    ).json()
    command = (
        await client.post(
            "/api/commands",
            json={"name": "AC On", "type": "ir", "raw_timings": [1, -1], "repeat_count": 3, "default_device_id": device["id"]},
        )
    ).json()

    resp = await client.post(f"/api/commands/{command['id']}/fire", json={})
    assert resp.status_code == 204
    # Unchanged from before repeat_timings existed: one firmware call,
    # firmware handles repeating the same burst.
    assert len(fake_device.transmitted) == 1
    assert fake_device.transmitted[0].timings == [1, -1]
    assert fake_device.transmitted[0].repeat_count == 3


async def test_fire_two_shape_command_sends_leader_once_then_repeat_shape_n_minus_one_times(
    client: httpx.AsyncClient, fake_device: FakeEspHomeServer
):
    device = (
        await client.post("/api/devices", json={"name": "Living Room", "host": fake_device.host, "port": fake_device.port})
    ).json()
    command = (
        await client.post(
            "/api/commands",
            json={
                "name": "TV Power",
                "type": "ir",
                "raw_timings": [9000, -4500, 560, -560],
                "repeat_timings": [9000, -2250, 560],
                "repeat_count": 4,
                "default_device_id": device["id"],
            },
        )
    ).json()

    resp = await client.post(f"/api/commands/{command['id']}/fire", json={})
    assert resp.status_code == 204

    # Exactly two firmware calls -- leader once, repeat shape (4 - 1)
    # times -- never `raw_timings x repeat_count` AND `repeat_timings x
    # repeat_count`, which would double the total activations.
    assert len(fake_device.transmitted) == 2
    assert fake_device.transmitted[0].timings == [9000, -4500, 560, -560]
    assert fake_device.transmitted[0].repeat_count == 1
    assert fake_device.transmitted[1].timings == [9000, -2250, 560]
    assert fake_device.transmitted[1].repeat_count == 3


async def test_fire_two_shape_command_with_repeat_count_one_skips_the_repeat_shape_entirely(
    client: httpx.AsyncClient, fake_device: FakeEspHomeServer
):
    device = (
        await client.post("/api/devices", json={"name": "Living Room", "host": fake_device.host, "port": fake_device.port})
    ).json()
    command = (
        await client.post(
            "/api/commands",
            json={
                "name": "TV Power",
                "type": "ir",
                "raw_timings": [9000, -4500, 560, -560],
                "repeat_timings": [9000, -2250, 560],
                "repeat_count": 1,
                "default_device_id": device["id"],
            },
        )
    ).json()

    resp = await client.post(f"/api/commands/{command['id']}/fire", json={})
    assert resp.status_code == 204
    assert len(fake_device.transmitted) == 1
    assert fake_device.transmitted[0].timings == [9000, -4500, 560, -560]
    assert fake_device.transmitted[0].repeat_count == 1


async def test_test_fire_reaches_fake_server_without_saving_a_command(
    client: httpx.AsyncClient, fake_device: FakeEspHomeServer
):
    device = (
        await client.post("/api/devices", json={"name": "Living Room", "host": fake_device.host, "port": fake_device.port})
    ).json()

    resp = await client.post(
        "/api/commands/test-fire",
        json={
            "type": "ir",
            "device_id": device["id"],
            "raw_timings": [9000, -4500, 560, -560],
            "carrier_frequency_hz": 38000,
        },
    )
    assert resp.status_code == 204
    assert len(fake_device.transmitted) == 1
    assert fake_device.transmitted[0].timings == [9000, -4500, 560, -560]
    assert fake_device.transmitted[0].carrier_frequency == 38000
    # Nothing was persisted -- this is purely a firmware call.
    assert (await client.get("/api/commands")).json() == []


async def test_test_fire_two_shape_payload_sends_leader_once_then_repeat_shape(
    client: httpx.AsyncClient, fake_device: FakeEspHomeServer
):
    device = (
        await client.post("/api/devices", json={"name": "Living Room", "host": fake_device.host, "port": fake_device.port})
    ).json()

    resp = await client.post(
        "/api/commands/test-fire",
        json={
            "type": "ir",
            "device_id": device["id"],
            "raw_timings": [9000, -4500, 560, -560],
            "repeat_timings": [9000, -2250, 560],
            "repeat_count": 3,
        },
    )
    assert resp.status_code == 204
    assert len(fake_device.transmitted) == 2
    assert fake_device.transmitted[0].repeat_count == 1
    assert fake_device.transmitted[1].timings == [9000, -2250, 560]
    assert fake_device.transmitted[1].repeat_count == 2


async def test_test_fire_unknown_device_returns_404(client: httpx.AsyncClient):
    resp = await client.post(
        "/api/commands/test-fire",
        json={"type": "ir", "device_id": "does-not-exist", "raw_timings": [1, -1]},
    )
    assert resp.status_code == 404


async def test_delete_command(client: httpx.AsyncClient):
    created = (
        await client.post("/api/commands", json={"name": "Delete Me", "type": "rf", "raw_timings": [1, -1]})
    ).json()
    resp = await client.delete(f"/api/commands/{created['id']}")
    assert resp.status_code == 204
    assert (await client.get(f"/api/commands/{created['id']}")).status_code == 404
