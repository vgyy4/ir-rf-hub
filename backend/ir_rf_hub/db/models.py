"""SQLAlchemy models. This is the canonical schema both the REST API and the
companion HA integration's data contract derive from -- see
esphome/device_session.py for how EspDevice/DeviceEntity map onto live
connections, and api/rest/commands.py for how Command maps onto the wire
format sent to both the SPA and the integration.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class SignalDomain(str, enum.Enum):
    infrared = "infrared"
    radio_frequency = "radio_frequency"


class SignalType(str, enum.Enum):
    ir = "ir"
    rf = "rf"


class DeviceRole(str, enum.Enum):
    tx = "tx"
    rx = "rx"


class Modulation(str, enum.Enum):
    ook = "OOK"


class EspDevice(Base):
    """A configured ESPHome device the App connects to directly over its
    native API. Credentials are stored encrypted at rest (see security.py).
    """

    __tablename__ = "esp_devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128))
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer, default=6053)

    # Fernet-encrypted blobs (nullable -- a device may use neither, one, or
    # the other depending on its ESPHome API configuration).
    encryption_key_enc: Mapped[bytes | None] = mapped_column(nullable=True)
    password_enc: Mapped[bytes | None] = mapped_column(nullable=True)

    mdns_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Half-duplex settle timers, per-device tunable -- see device_session.py.
    tx_settle_ms: Mapped[int] = mapped_column(Integer, default=150)
    rx_stop_settle_ms: Mapped[int] = mapped_column(Integer, default=150)
    connect_timeout_s: Mapped[int] = mapped_column(Integer, default=10)

    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    entities: Mapped[list["DeviceEntity"]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )


class DeviceEntity(Base):
    """One row per `ir_rf_proxy` platform instance discovered on a device via
    ListEntities. This is what every "which devices are valid here" filter
    in the UI queries against (recording device picker = rx + domain match;
    fire/default-ESP pickers = tx + domain match) -- no ad-hoc guessing.
    """

    __tablename__ = "device_entities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(ForeignKey("esp_devices.id", ondelete="CASCADE"))

    esphome_key: Mapped[int] = mapped_column(Integer)
    object_id: Mapped[str] = mapped_column(String(255))
    domain: Mapped[SignalDomain] = mapped_column(Enum(SignalDomain))
    role: Mapped[DeviceRole] = mapped_column(Enum(DeviceRole))
    frequency_hz: Mapped[int | None] = mapped_column(Integer, nullable=True)

    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    device: Mapped[EspDevice] = relationship(back_populates="entities")


class Command(Base):
    """A saved, named IR/RF command. Deliberately raw end-to-end: recorded
    raw, stored raw, transmitted raw -- no protocol-decoding subsystem.
    """

    __tablename__ = "commands"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128))
    type: Mapped[SignalType] = mapped_column(Enum(SignalType))

    # Alternating mark/space microsecond durations, first element = mark.
    raw_timings: Mapped[list[int]] = mapped_column(JSON)

    carrier_frequency_hz: Mapped[int] = mapped_column(Integer, default=0)
    modulation: Mapped[Modulation] = mapped_column(Enum(Modulation), default=Modulation.ook)
    repeat_count: Mapped[int] = mapped_column(Integer, default=1)

    default_device_id: Mapped[str | None] = mapped_column(
        ForeignKey("esp_devices.id", ondelete="SET NULL"), nullable=True
    )
    recorded_from_device_id: Mapped[str | None] = mapped_column(
        ForeignKey("esp_devices.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Setting(Base):
    """Small key/value store: Fernet key reference, pairing identity, misc
    UI prefs. Not worth a bespoke table per flag.
    """

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
