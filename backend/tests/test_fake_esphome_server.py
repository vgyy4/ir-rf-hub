"""Proves the fake ESPHome server (tests/fakes/fake_esphome_server.py)
round-trips correctly against the *real* aioesphomeapi.APIClient -- this is
the Phase 0 spike the design plan called for, confirming the actual wire
behavior of ir_rf_proxy-style entities before Phase 1 builds
esphome/connection.py on top of it.
"""

from __future__ import annotations

import asyncio

import aioesphomeapi as api
import pytest

from tests.fakes.fake_esphome_server import (
    FakeEspHomeServer,
    FakeInfraredEntity,
    FakeRadioFrequencyEntity,
)


@pytest.fixture
async def fake_device():
    server = FakeEspHomeServer(
        name="living-room-esp",
        infrared_entities=[
            FakeInfraredEntity(key=1, object_id="ir_rx", name="IR Receiver", capabilities=2),
            FakeInfraredEntity(key=2, object_id="ir_tx", name="IR Transmitter", capabilities=1),
        ],
        radio_frequency_entities=[
            FakeRadioFrequencyEntity(key=3, object_id="rf_tx", name="RF Transmitter", capabilities=1),
        ],
    )
    async with server:
        yield server


async def _connected_client(server: FakeEspHomeServer) -> api.APIClient:
    client = api.APIClient(server.host, server.port, password=None)
    await client.connect(login=False)
    return client


async def test_hello_and_device_info(fake_device: FakeEspHomeServer):
    client = await _connected_client(fake_device)
    try:
        info = await client.device_info()
        assert info.name == "living-room-esp"
    finally:
        await client.disconnect()


async def test_list_entities_reports_infrared_and_radio_frequency(fake_device: FakeEspHomeServer):
    client = await _connected_client(fake_device)
    try:
        entities, _services = await client.list_entities_services()
        infrared = [e for e in entities if isinstance(e, api.InfraredInfo)]
        rf = [e for e in entities if isinstance(e, api.RadioFrequencyInfo)]

        assert {e.object_id for e in infrared} == {"ir_rx", "ir_tx"}
        rx = next(e for e in infrared if e.object_id == "ir_rx")
        tx = next(e for e in infrared if e.object_id == "ir_tx")
        assert rx.capabilities & api.InfraredCapability.RECEIVER
        assert tx.capabilities & api.InfraredCapability.TRANSMITTER

        assert len(rf) == 1
        assert rf[0].capabilities & api.RadioFrequencyCapability.TRANSMITTER
    finally:
        await client.disconnect()


async def test_receive_event_streams_to_subscriber(fake_device: FakeEspHomeServer):
    client = await _connected_client(fake_device)
    received: list[api.InfraredRFReceiveEvent] = []
    try:
        client.subscribe_infrared_rf_receive(received.append)
        await fake_device.emit_receive_event(key=1, timings=[560, -1690, 560, -560])
        await asyncio.sleep(0.05)

        assert len(received) == 1
        assert received[0].key == 1
        assert list(received[0].timings) == [560, -1690, 560, -560]
    finally:
        await client.disconnect()


async def test_transmit_raw_timings_is_recorded_by_server(fake_device: FakeEspHomeServer):
    client = await _connected_client(fake_device)
    try:
        client.infrared_rf_transmit_raw_timings(
            key=2, carrier_frequency=38000, timings=[9000, -4500, 560, -560], repeat_count=1
        )
        await asyncio.sleep(0.05)

        assert len(fake_device.transmitted) == 1
        call = fake_device.transmitted[0]
        assert call.key == 2
        assert call.carrier_frequency == 38000
        assert call.timings == [9000, -4500, 560, -560]
    finally:
        await client.disconnect()
