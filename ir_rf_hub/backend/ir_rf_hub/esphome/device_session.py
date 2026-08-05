"""The half-duplex TX/RX concurrency design for a single ESPHome device.

Every TX and RX operation against a device is serialized through one
asyncio.Lock (`_device_lock`). This is a deliberately simpler
implementation of the state machine from the design plan (DISCONNECTED ->
IDLE <-> RX_ACTIVE -> RX_SETTLING -> IDLE, IDLE <-> TX_ACTIVE -> TX_SETTLING
-> IDLE) that preserves every required behavior while being much easier to
get right:

- A recording session holds `_device_lock` for its *entire* duration (from
  start_recording to stop/discard_recording finishing its settle sleep).
  Since asyncio.Lock is FIFO-fair, any transmit() call that arrives while a
  recording is active simply blocks on `acquire()` in queue order -- this
  *is* the "transmits queue behind an active recording, bounded wait"
  requirement, for free, without a hand-rolled queue.
- A second start_recording() call while one is already active is rejected
  immediately via the `_recording is not None` check, performed *before*
  attempting to acquire the lock -- so it never waits, matching "reject
  fast, don't queue a second interactive recording attempt".
- transmit() acquires the lock with a bounded timeout and raises
  DeviceBusyTimeoutError if it can't get in -- covers both "blocked behind
  a long recording" and "blocked behind another transmit".
- Settle timers (tx_settle_ms / rx_stop_settle_ms) run *before* the lock is
  released, not after -- so the next queued operation only starts once the
  settle window has actually elapsed, which is the mechanism that protects
  half-duplex RF front-ends.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

from ir_rf_hub.db.models import DeviceRole, SignalDomain
from ir_rf_hub.esphome.connection import DeviceUnreachableError, DiscoveredEntity, EspHomeConnection
from ir_rf_hub.events import Event, EventBus

logger = logging.getLogger(__name__)

# How long a caller will wait to acquire the device before giving up.
# Recording-start waits briefly for an in-flight (short, bounded) transmit
# to finish; a transmit waits longer since it may be queued behind a
# person's open-ended recording session and automations calling it can't
# "ask the user to retry".
RECORD_START_LOCK_TIMEOUT_S = 3.0
TRANSMIT_LOCK_TIMEOUT_S = 10.0


class DeviceSessionState(str, Enum):
    disconnected = "disconnected"
    connecting = "connecting"
    idle = "idle"
    rx_active = "rx_active"
    rx_settling = "rx_settling"
    tx_active = "tx_active"
    tx_settling = "tx_settling"
    error = "error"


class DeviceBusyRecordingError(Exception):
    """Another recording session already owns this device."""


class DeviceBusyTimeoutError(Exception):
    """Couldn't get exclusive access to the device within the wait budget."""


@dataclass
class RecordingSession:
    id: str
    domain: SignalDomain
    rx_key: int
    started_at: float = field(default_factory=time.monotonic)
    # Every raw capture in arrival order, not just one "the" signal --
    # picking which of these is the real command (vs. a repeat, vs. noise)
    # is signal_shapes.py's job, done once at stop time with the full
    # picture, not greedily as events arrive. See api/rest/recording.py's
    # stop_recording().
    captures: list[list[int]] = field(default_factory=list)
    capture_count: int = 0


@dataclass
class DeviceSessionConfig:
    device_id: str
    host: str
    port: int
    password: str | None = None
    noise_psk: str | None = None
    connect_timeout_s: int = 10
    tx_settle_ms: int = 150
    rx_stop_settle_ms: int = 150


class DeviceSession:
    """Owns the live connection and half-duplex lock for one EspDevice."""

    def __init__(self, config: DeviceSessionConfig, event_bus: EventBus) -> None:
        self.config = config
        self._event_bus = event_bus
        self._connection: EspHomeConnection | None = None
        self._device_lock = asyncio.Lock()
        self._state = DeviceSessionState.disconnected
        self._recording: RecordingSession | None = None
        self._recording_unsub: Callable[[], None] | None = None
        self._entities: list[DiscoveredEntity] = []
        self.last_error: str | None = None

    @property
    def state(self) -> DeviceSessionState:
        return self._state

    @property
    def entities(self) -> list[DiscoveredEntity]:
        return list(self._entities)

    def _set_state(self, state: DeviceSessionState) -> None:
        self._state = state
        self._event_bus.publish(
            Event(type="device.session_state_changed", data={"device_id": self.config.device_id, "state": state.value})
        )

    # -- connection lifecycle -------------------------------------------------

    async def connect(self) -> list[DiscoveredEntity]:
        self._set_state(DeviceSessionState.connecting)
        conn = EspHomeConnection(
            host=self.config.host,
            port=self.config.port,
            password=self.config.password,
            noise_psk=self.config.noise_psk,
            connect_timeout_s=self.config.connect_timeout_s,
        )
        try:
            await conn.connect()
            self._entities = await conn.list_entities()
        except DeviceUnreachableError as exc:
            self.last_error = str(exc)
            self._set_state(DeviceSessionState.error)
            raise
        self._connection = conn
        self.last_error = None
        self._set_state(DeviceSessionState.idle)
        return self._entities

    async def disconnect(self) -> None:
        if self._connection is not None:
            await self._connection.disconnect()
            self._connection = None
        self._set_state(DeviceSessionState.disconnected)

    def _require_connection(self) -> EspHomeConnection:
        if self._connection is None or not self._connection.connected:
            raise DeviceUnreachableError(f"Device {self.config.device_id} is not connected")
        return self._connection

    def find_entity(self, *, domain: SignalDomain, role: DeviceRole) -> DiscoveredEntity | None:
        for entity in self._entities:
            if entity.domain == domain and entity.role == role:
                return entity
        return None

    # -- recording --------------------------------------------------------------

    async def start_recording(self, *, domain: SignalDomain, rx_key: int) -> RecordingSession:
        if self._recording is not None:
            raise DeviceBusyRecordingError(f"Device {self.config.device_id} is already recording")

        conn = self._require_connection()
        try:
            await asyncio.wait_for(self._device_lock.acquire(), timeout=RECORD_START_LOCK_TIMEOUT_S)
        except asyncio.TimeoutError as exc:
            raise DeviceBusyTimeoutError(f"Device {self.config.device_id} busy transmitting") from exc

        session = RecordingSession(id=str(uuid.uuid4()), domain=domain, rx_key=rx_key)
        self._recording = session

        def _on_event(timings: list[int]) -> None:
            session.captures.append(timings)
            session.capture_count += 1
            self._event_bus.publish(
                Event(
                    type="recording.capture",
                    data={"session_id": session.id, "device_id": self.config.device_id, "timings": timings},
                )
            )

        self._recording_unsub = conn.add_receive_listener(rx_key, _on_event)
        self._set_state(DeviceSessionState.rx_active)
        return session

    def clear_recording(self, session_id: str) -> None:
        session = self._active_recording(session_id)
        session.captures = []
        session.capture_count = 0

    async def stop_recording(self, session_id: str) -> RecordingSession:
        session = self._active_recording(session_id)
        return await self._end_recording(session)

    async def discard_recording(self, session_id: str) -> None:
        session = self._active_recording(session_id)
        await self._end_recording(session)

    def _active_recording(self, session_id: str) -> RecordingSession:
        if self._recording is None or self._recording.id != session_id:
            raise ValueError(f"No active recording session {session_id} on device {self.config.device_id}")
        return self._recording

    async def _end_recording(self, session: RecordingSession) -> RecordingSession:
        if self._recording_unsub is not None:
            self._recording_unsub()
            self._recording_unsub = None
        self._set_state(DeviceSessionState.rx_settling)
        try:
            await asyncio.sleep(self.config.rx_stop_settle_ms / 1000)
        finally:
            self._recording = None
            self._device_lock.release()
            self._set_state(DeviceSessionState.idle)
        return session

    # -- transmit -----------------------------------------------------------

    async def transmit(
        self,
        *,
        domain: SignalDomain,
        tx_key: int,
        timings: list[int],
        carrier_frequency_hz: int = 0,
        repeat_count: int = 1,
    ) -> None:
        conn = self._require_connection()
        try:
            await asyncio.wait_for(self._device_lock.acquire(), timeout=TRANSMIT_LOCK_TIMEOUT_S)
        except asyncio.TimeoutError as exc:
            raise DeviceBusyTimeoutError(f"Device {self.config.device_id} busy") from exc

        self._set_state(DeviceSessionState.tx_active)
        try:
            if domain == SignalDomain.infrared:
                conn.transmit_infrared(
                    key=tx_key, carrier_frequency=carrier_frequency_hz, timings=timings, repeat_count=repeat_count
                )
            else:
                conn.transmit_radio_frequency(
                    key=tx_key, frequency=carrier_frequency_hz, timings=timings, repeat_count=repeat_count
                )
            self._set_state(DeviceSessionState.tx_settling)
            await asyncio.sleep(self.config.tx_settle_ms / 1000)
        finally:
            self._device_lock.release()
            self._set_state(DeviceSessionState.idle)
