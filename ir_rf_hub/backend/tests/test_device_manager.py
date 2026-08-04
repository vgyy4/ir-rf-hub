from __future__ import annotations

import pytest
from sqlalchemy import select

from ir_rf_hub.db.models import Base, DeviceEntity, DeviceRole, EspDevice, SignalDomain
from ir_rf_hub.db.session import get_engine, session_scope
from ir_rf_hub.esphome.device_manager import DeviceManager
from ir_rf_hub.events import EventBus
from tests.fakes.fake_esphome_server import FakeEspHomeServer, FakeInfraredEntity, FakeRadioFrequencyEntity


@pytest.fixture(autouse=True)
async def _schema():
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture
async def fake_device():
    server = FakeEspHomeServer(
        name="managed-esp",
        infrared_entities=[
            FakeInfraredEntity(key=1, object_id="ir_rx", name="IR Receiver", capabilities=2),
        ],
        radio_frequency_entities=[
            FakeRadioFrequencyEntity(key=2, object_id="rf_tx", name="RF Transmitter", capabilities=1, frequency_min=433_920_000, frequency_max=433_920_000),
        ],
    )
    async with server:
        yield server


async def test_connect_persists_discovered_entities(fake_device: FakeEspHomeServer):
    manager = DeviceManager(EventBus())
    async with session_scope() as session:
        device = EspDevice(name="managed-esp", host=fake_device.host, port=fake_device.port)
        session.add(device)
        await session.commit()
        device_id = device.id

        await manager.connect(session, device)

    async with session_scope() as session:
        rows = (
            await session.execute(select(DeviceEntity).where(DeviceEntity.device_id == device_id))
        ).scalars().all()
        by_role = {(r.domain, r.role): r for r in rows}

        assert (SignalDomain.infrared, DeviceRole.rx) in by_role
        assert (SignalDomain.radio_frequency, DeviceRole.tx) in by_role
        rf = by_role[(SignalDomain.radio_frequency, DeviceRole.tx)]
        assert rf.frequency_hz == 433_920_000

        device = await session.get(EspDevice, device_id)
        assert device.last_error is None
        assert device.last_connected_at is not None

    await manager.disconnect_all()


async def test_reconnect_replaces_stale_entities(fake_device: FakeEspHomeServer):
    manager = DeviceManager(EventBus())
    async with session_scope() as session:
        device = EspDevice(name="managed-esp", host=fake_device.host, port=fake_device.port)
        session.add(device)
        await session.commit()
        device_id = device.id
        await manager.connect(session, device)

    # Reconfigure the fake device to advertise a different entity set and
    # force a fresh connection -- persisted rows should reflect only the
    # new set, not accumulate stale ones from the first connect.
    fake_device.infrared_entities = []
    await manager.disconnect(device_id)

    async with session_scope() as session:
        device = await session.get(EspDevice, device_id)
        await manager.connect(session, device)

    async with session_scope() as session:
        rows = (
            await session.execute(select(DeviceEntity).where(DeviceEntity.device_id == device_id))
        ).scalars().all()
        assert all(r.domain != SignalDomain.infrared for r in rows)

    await manager.disconnect_all()
