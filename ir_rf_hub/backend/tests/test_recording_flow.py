"""End-to-end recording flow: create a device, start a recording session,
watch captures arrive on the scoped WS stream, clear & retry, stop, and
confirm the half-duplex lock actually blocks a concurrent recording attempt
against the same device -- the same guarantee proven at the FSM level in
test_device_session_fsm.py, now proven through the real HTTP/WS surface the
frontend will actually use.

Deliberately uses httpx.AsyncClient + httpx_ws (not Starlette's TestClient)
so the whole test -- REST calls, the WS connection, and the fake ESPHome
server's emit_receive_event() -- all run on the *same* asyncio event loop.
TestClient runs the ASGI app on its own background thread with its own
loop, which would make the shared in-process event_bus's asyncio.Queue
objects get touched from two different loops -- asyncio.Queue isn't
thread-safe across loops, so that combination is a latent race, not just a
style preference.

The `client` helper below is a plain @asynccontextmanager used inline in
each test's body (`async with running_client() as client:`), not a
pytest-asyncio fixture spanning a `yield`. httpx_ws's ASGIWebSocketTransport
opens an anyio cancel scope tied to whatever task calls __aenter__; when a
fixture instead splits setup/teardown across pytest-asyncio's finalizer,
teardown can run in a different Task than setup, and anyio's cancel scope
raises "Attempted to exit cancel scope in a different task" even though
every assertion already passed. Keeping the whole `async with` inside one
test-body coroutine sidesteps that entirely.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
import pytest
from httpx_ws import aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport

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
        name="recording-esp",
        infrared_entities=[
            FakeInfraredEntity(key=1, object_id="ir_rx", name="IR Receiver", capabilities=2),
            FakeInfraredEntity(key=2, object_id="ir_tx", name="IR Transmitter", capabilities=1),
        ],
    )
    async with server:
        yield server


@asynccontextmanager
async def running_client():
    app = create_app()
    transport = ASGIWebSocketTransport(app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        async with app.router.lifespan_context(app):
            yield c


async def test_recording_session_streams_captures_over_ws(fake_device: FakeEspHomeServer):
    async with running_client() as client:
        created = (
            await client.post(
                "/api/devices", json={"name": "Bedroom", "host": fake_device.host, "port": fake_device.port}
            )
        ).json()

        started = await client.post("/api/recording/sessions", json={"type": "ir", "device_id": created["id"]})
        assert started.status_code == 201
        session_id = started.json()["session_id"]

        async with aconnect_ws(f"/api/ws/recording/{session_id}", client) as ws:
            await fake_device.emit_receive_event(key=1, timings=[9000, -4500, 560, -560])
            message = await ws.receive_json()
            assert message == {"type": "capture", "seq": 1, "timings": [9000, -4500, 560, -560]}

            cleared = await client.post(f"/api/recording/sessions/{session_id}/clear")
            assert cleared.status_code == 204

            await fake_device.emit_receive_event(key=1, timings=[100, -100])
            message2 = await ws.receive_json()
            assert message2["timings"] == [100, -100]

        stopped = await client.post(f"/api/recording/sessions/{session_id}/stop")
        assert stopped.status_code == 200
        body = stopped.json()
        assert body["timings"] == [100, -100]
        assert body["capture_count"] == 1


async def test_second_recording_attempt_is_rejected_via_http(fake_device: FakeEspHomeServer):
    async with running_client() as client:
        created = (
            await client.post(
                "/api/devices", json={"name": "Hallway", "host": fake_device.host, "port": fake_device.port}
            )
        ).json()

        started = await client.post("/api/recording/sessions", json={"type": "ir", "device_id": created["id"]})
        session_id = started.json()["session_id"]

        second = await client.post("/api/recording/sessions", json={"type": "ir", "device_id": created["id"]})
        assert second.status_code == 409

        await client.post(f"/api/recording/sessions/{session_id}/stop")


async def test_stop_recording_detects_nec_leader_and_repeat_shapes(fake_device: FakeEspHomeServer):
    leader = [9000, -4500] + [560, -560, 560, -1690] * 16
    repeat = [9000, -2250, 560]

    async with running_client() as client:
        created = (
            await client.post(
                "/api/devices", json={"name": "Hallway", "host": fake_device.host, "port": fake_device.port}
            )
        ).json()
        started = await client.post("/api/recording/sessions", json={"type": "ir", "device_id": created["id"]})
        session_id = started.json()["session_id"]

        async with aconnect_ws(f"/api/ws/recording/{session_id}", client) as ws:
            await fake_device.emit_receive_event(key=1, timings=leader)
            await ws.receive_json()
            await fake_device.emit_receive_event(key=1, timings=repeat)
            await ws.receive_json()

        stopped = await client.post(f"/api/recording/sessions/{session_id}/stop")
        assert stopped.status_code == 200
        body = stopped.json()
        assert body["timings"] is None
        assert body["shape_candidates"] is None
        assert body["detected_protocol"] == {
            "name": "nec_leader_repeat",
            "leader_timings": leader,
            "repeat_timings": repeat,
        }


async def test_stop_recording_offers_shape_candidates_when_ambiguous(fake_device: FakeEspHomeServer):
    # Neither shape looks like a recognized protocol -- e.g. a real full
    # frame plus a garbled receiver-noise echo (the "Netflix" bug) --
    # so both must be surfaced for the user to choose from, not silently
    # collapsed or discarded.
    full_frame = [4500, -4500] + [560, -560] * 32
    garbled_echo = [278, -997, 276, -398, 278, -699, 275]

    async with running_client() as client:
        created = (
            await client.post(
                "/api/devices", json={"name": "Hallway", "host": fake_device.host, "port": fake_device.port}
            )
        ).json()
        started = await client.post("/api/recording/sessions", json={"type": "ir", "device_id": created["id"]})
        session_id = started.json()["session_id"]

        async with aconnect_ws(f"/api/ws/recording/{session_id}", client) as ws:
            await fake_device.emit_receive_event(key=1, timings=full_frame)
            await ws.receive_json()
            await fake_device.emit_receive_event(key=1, timings=garbled_echo)
            await ws.receive_json()

        stopped = await client.post(f"/api/recording/sessions/{session_id}/stop")
        assert stopped.status_code == 200
        body = stopped.json()
        assert body["timings"] is None
        assert body["detected_protocol"] is None
        assert body["shape_candidates"] == [
            {"timings": full_frame, "edge_count": len(full_frame), "occurrences": 1},
            {"timings": garbled_echo, "edge_count": len(garbled_echo), "occurrences": 1},
        ]


async def test_recording_on_device_without_receiver_returns_400():
    async with running_client() as client:
        tx_only_server = FakeEspHomeServer(
            name="tx-only-esp",
            infrared_entities=[FakeInfraredEntity(key=1, object_id="ir_tx", name="IR TX", capabilities=1)],
        )
        async with tx_only_server:
            created = (
                await client.post(
                    "/api/devices",
                    json={"name": "TX Only", "host": tx_only_server.host, "port": tx_only_server.port},
                )
            ).json()
            resp = await client.post("/api/recording/sessions", json={"type": "ir", "device_id": created["id"]})
            assert resp.status_code == 400
