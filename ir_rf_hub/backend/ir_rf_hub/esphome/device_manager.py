"""Registry of live DeviceSession actors, keyed by EspDevice.id. This is the
single place that turns a DB row into a connection -- REST handlers and the
future recording/transmit code all go through here rather than touching
EspHomeConnection/DeviceSession directly, so there is exactly one
DeviceSession per device no matter how many requests come in concurrently.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ir_rf_hub.db.models import DeviceEntity, EspDevice
from ir_rf_hub.esphome.connection import DeviceUnreachableError
from ir_rf_hub.esphome.device_session import DeviceSession, DeviceSessionConfig
from ir_rf_hub.events import EventBus, event_bus
from ir_rf_hub.security import decrypt_secret

logger = logging.getLogger(__name__)


class DeviceManager:
    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._sessions: dict[str, DeviceSession] = {}

    def _config_from_row(self, device: EspDevice) -> DeviceSessionConfig:
        return DeviceSessionConfig(
            device_id=device.id,
            host=device.host,
            port=device.port,
            password=decrypt_secret(device.password_enc) if device.password_enc else None,
            noise_psk=decrypt_secret(device.encryption_key_enc) if device.encryption_key_enc else None,
            connect_timeout_s=device.connect_timeout_s,
            tx_settle_ms=device.tx_settle_ms,
            rx_stop_settle_ms=device.rx_stop_settle_ms,
        )

    def get_cached(self, device_id: str) -> DeviceSession | None:
        return self._sessions.get(device_id)

    async def connect(
        self, session: AsyncSession, device: EspDevice, *, persist_entities: bool = True
    ) -> DeviceSession:
        """Connect (or reuse an existing connection) to a device and, by
        default, persist its discovered DeviceEntity rows.
        """
        existing = self._sessions.get(device.id)
        if existing is not None and existing.state.value not in ("disconnected", "error"):
            return existing

        device_session = DeviceSession(self._config_from_row(device), self._event_bus)
        try:
            entities = await device_session.connect()
        except DeviceUnreachableError:
            device.last_error = device_session.last_error
            await session.commit()
            self._sessions[device.id] = device_session
            raise

        self._sessions[device.id] = device_session
        device.last_connected_at = datetime.now(UTC)
        device.last_error = None

        if persist_entities:
            await self._persist_entities(session, device.id, entities)

        await session.commit()
        return device_session

    async def _persist_entities(self, session: AsyncSession, device_id: str, entities) -> None:
        existing = (
            await session.execute(select(DeviceEntity).where(DeviceEntity.device_id == device_id))
        ).scalars().all()
        for row in existing:
            await session.delete(row)
        await session.flush()

        for entity in entities:
            session.add(
                DeviceEntity(
                    device_id=device_id,
                    esphome_key=entity.esphome_key,
                    object_id=entity.object_id,
                    domain=entity.domain,
                    role=entity.role,
                    frequency_hz=entity.frequency_hz,
                )
            )

    async def disconnect(self, device_id: str) -> None:
        session = self._sessions.pop(device_id, None)
        if session is not None:
            await session.disconnect()

    async def disconnect_all(self) -> None:
        for device_id in list(self._sessions.keys()):
            await self.disconnect(device_id)


device_manager = DeviceManager(event_bus=event_bus)
