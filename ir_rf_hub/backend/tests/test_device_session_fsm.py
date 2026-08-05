"""Exercises the half-duplex concurrency design in device_session.py against
the fake ESPHome server: every state transition in the design plan's FSM,
plus the two contention scenarios that matter most -- a second recording
attempt while one is active (must reject fast), and a transmit attempt
while a recording is active (must queue and complete once the recording
ends, not be dropped or racily interleaved).
"""

from __future__ import annotations

import asyncio
import time

import pytest

from ir_rf_hub.db.models import DeviceRole, SignalDomain
from ir_rf_hub.esphome.device_session import (
    DeviceBusyRecordingError,
    DeviceBusyTimeoutError,
    DeviceSession,
    DeviceSessionConfig,
    DeviceSessionState,
)
from ir_rf_hub.events import EventBus
from tests.fakes.fake_esphome_server import FakeEspHomeServer, FakeInfraredEntity, FakeRadioFrequencyEntity


@pytest.fixture
async def fake_device():
    server = FakeEspHomeServer(
        name="test-esp",
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


@pytest.fixture
async def connected_session(fake_device: FakeEspHomeServer):
    config = DeviceSessionConfig(
        device_id="dev-1",
        host=fake_device.host,
        port=fake_device.port,
        tx_settle_ms=20,
        rx_stop_settle_ms=20,
    )
    session = DeviceSession(config, EventBus())
    await session.connect()
    yield session
    if session.state != DeviceSessionState.disconnected:
        await session.disconnect()


async def test_connect_discovers_entities_with_correct_roles(connected_session: DeviceSession):
    ir_rx = connected_session.find_entity(domain=SignalDomain.infrared, role=DeviceRole.rx)
    ir_tx = connected_session.find_entity(domain=SignalDomain.infrared, role=DeviceRole.tx)
    rf_tx = connected_session.find_entity(domain=SignalDomain.radio_frequency, role=DeviceRole.tx)

    assert ir_rx is not None and ir_rx.esphome_key == 1
    assert ir_tx is not None and ir_tx.esphome_key == 2
    assert rf_tx is not None and rf_tx.esphome_key == 3
    assert connected_session.state == DeviceSessionState.idle


async def test_recording_captures_raw_timings_and_returns_to_idle(
    connected_session: DeviceSession, fake_device: FakeEspHomeServer
):
    recording = await connected_session.start_recording(domain=SignalDomain.infrared, rx_key=1)
    assert connected_session.state == DeviceSessionState.rx_active

    await fake_device.emit_receive_event(key=1, timings=[9000, -4500, 560, -560])
    await asyncio.sleep(0.05)
    assert recording.capture_count == 1
    assert recording.best_timings == [9000, -4500, 560, -560]

    finished = await connected_session.stop_recording(recording.id)
    assert finished.best_timings == [9000, -4500, 560, -560]
    assert connected_session.state == DeviceSessionState.idle


async def test_recording_keeps_the_most_complete_capture_not_the_last_one(
    connected_session: DeviceSession, fake_device: FakeEspHomeServer
):
    # Reproduces a real bug: a Samsung TV remote's button press produced a
    # correct full 68-edge frame followed by a garbled short trailing
    # blip, and the recorder saved the garbage because it just kept
    # whatever arrived most recently. A real frame has far more edges
    # than a truncated echo, so the longer capture must win regardless of
    # arrival order.
    full_frame = [4500, -4500] + [560, -560] * 32
    garbled_echo = [278, -997, 276, -398, 278, -699, 275]

    recording = await connected_session.start_recording(domain=SignalDomain.infrared, rx_key=1)
    await fake_device.emit_receive_event(key=1, timings=full_frame)
    await asyncio.sleep(0.02)
    await fake_device.emit_receive_event(key=1, timings=garbled_echo)
    await asyncio.sleep(0.02)

    assert recording.capture_count == 2
    assert recording.best_timings == full_frame

    finished = await connected_session.stop_recording(recording.id)
    assert finished.best_timings == full_frame


async def test_clear_and_retry_resets_buffer_without_ending_session(
    connected_session: DeviceSession, fake_device: FakeEspHomeServer
):
    recording = await connected_session.start_recording(domain=SignalDomain.infrared, rx_key=1)
    await fake_device.emit_receive_event(key=1, timings=[100, -100])
    await asyncio.sleep(0.02)
    assert recording.capture_count == 1

    connected_session.clear_recording(recording.id)
    assert recording.capture_count == 0
    assert recording.best_timings is None
    # Still the same active session -- no reconnect, no state change.
    assert connected_session.state == DeviceSessionState.rx_active

    await fake_device.emit_receive_event(key=1, timings=[200, -200])
    await asyncio.sleep(0.02)
    assert recording.best_timings == [200, -200]

    await connected_session.stop_recording(recording.id)


async def test_second_recording_attempt_is_rejected_immediately(connected_session: DeviceSession):
    recording = await connected_session.start_recording(domain=SignalDomain.infrared, rx_key=1)

    start = time.monotonic()
    with pytest.raises(DeviceBusyRecordingError):
        await connected_session.start_recording(domain=SignalDomain.infrared, rx_key=1)
    elapsed = time.monotonic() - start

    assert elapsed < 0.5, "a second recording attempt must fail fast, not wait on the device lock"
    await connected_session.stop_recording(recording.id)


async def test_transmit_queues_behind_an_active_recording_and_completes_after(
    connected_session: DeviceSession, fake_device: FakeEspHomeServer
):
    recording = await connected_session.start_recording(domain=SignalDomain.infrared, rx_key=1)

    transmit_task = asyncio.ensure_future(
        connected_session.transmit(domain=SignalDomain.infrared, tx_key=2, timings=[500, -500], carrier_frequency_hz=38000)
    )
    await asyncio.sleep(0.1)
    assert not transmit_task.done(), "transmit must not proceed while a recording holds the device"
    assert len(fake_device.transmitted) == 0

    await connected_session.stop_recording(recording.id)
    await asyncio.wait_for(transmit_task, timeout=2)

    assert len(fake_device.transmitted) == 1
    assert fake_device.transmitted[0].timings == [500, -500]


async def test_transmit_then_settle_before_releasing_device(
    connected_session: DeviceSession, fake_device: FakeEspHomeServer
):
    await connected_session.transmit(domain=SignalDomain.infrared, tx_key=2, timings=[1, -1], carrier_frequency_hz=38000)
    assert connected_session.state == DeviceSessionState.idle
    assert len(fake_device.transmitted) == 1


async def test_recording_start_times_out_if_device_stuck_transmitting(connected_session: DeviceSession):
    # Hold the device lock open by starting a transmit that never lets go
    # (simulate a stuck/slow device) -- start_recording must give up after
    # its bounded wait rather than hanging forever.
    async def _hold_lock_forever():
        await connected_session._device_lock.acquire()  # noqa: SLF001 -- test-only direct lock manipulation
        await asyncio.sleep(10)

    holder = asyncio.ensure_future(_hold_lock_forever())
    await asyncio.sleep(0.05)

    with pytest.raises(DeviceBusyTimeoutError):
        await connected_session.start_recording(domain=SignalDomain.infrared, rx_key=1)

    holder.cancel()
    with pytest.raises(asyncio.CancelledError):
        await holder
    connected_session._device_lock.release()  # noqa: SLF001 -- undo the manual acquire above
