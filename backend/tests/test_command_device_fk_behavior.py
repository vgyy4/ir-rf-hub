"""Confirms the deliberate design choice from the plan: deleting an
EspDevice that a Command defaults to nulls the reference (command reverts
to "ask which ESP") rather than blocking the delete or cascading.
"""

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
async def client():
    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        async with app.router.lifespan_context(app):
            yield c


async def test_deleting_default_device_nulls_command_reference(client: httpx.AsyncClient):
    server = FakeEspHomeServer(
        name="fk-esp",
        infrared_entities=[FakeInfraredEntity(key=1, object_id="ir_tx", name="IR TX", capabilities=1)],
    )
    async with server:
        device = (
            await client.post("/api/devices", json={"name": "Doomed Device", "host": server.host, "port": server.port})
        ).json()
        command = (
            await client.post(
                "/api/commands",
                json={"name": "Orphan Me", "type": "ir", "raw_timings": [1, -1], "default_device_id": device["id"]},
            )
        ).json()
        assert command["default_device_id"] == device["id"]

        deleted = await client.delete(f"/api/devices/{device['id']}")
        assert deleted.status_code == 204

        after = (await client.get(f"/api/commands/{command['id']}")).json()
        assert after["default_device_id"] is None
