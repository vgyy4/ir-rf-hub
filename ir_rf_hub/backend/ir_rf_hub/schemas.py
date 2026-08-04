"""Pydantic schemas shared by the REST API, the WS event payloads, and (by
construction, since these are the types the API commits to) the companion
integration's expectations of the wire format.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str


class PairingCodeResponse(BaseModel):
    code: str


class PairingStatusResponse(BaseModel):
    paired: bool
    # Only present while unpaired -- once the integration has connected,
    # the SPA no longer needs it and there's no reason to keep handing it
    # out on every poll.
    code: str | None = None


class DeviceEntitySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    esphome_key: int
    object_id: str
    domain: str
    role: str
    frequency_hz: int | None = None


class EspDeviceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    host: str
    port: int
    tx_settle_ms: int
    rx_stop_settle_ms: int
    connect_timeout_s: int
    last_connected_at: datetime | None = None
    last_error: str | None = None
    connection_state: str = "disconnected"
    entities: list[DeviceEntitySummary] = Field(default_factory=list)


class EspDeviceCreate(BaseModel):
    name: str
    host: str
    port: int = 6053
    encryption_key: str | None = None
    password: str | None = None
    tx_settle_ms: int = 150
    rx_stop_settle_ms: int = 150
    connect_timeout_s: int = 10


class EspDeviceUpdate(BaseModel):
    name: str | None = None
    host: str | None = None
    port: int | None = None
    encryption_key: str | None = None
    password: str | None = None
    tx_settle_ms: int | None = None
    rx_stop_settle_ms: int | None = None
    connect_timeout_s: int | None = None


class DiscoveredDeviceSchema(BaseModel):
    name: str
    host: str
    port: int


class RecordingStartRequest(BaseModel):
    type: str  # "ir" | "rf"
    device_id: str


class RecordingSessionResponse(BaseModel):
    session_id: str
    device_id: str
    type: str


class RecordingStopResponse(BaseModel):
    session_id: str
    capture_count: int
    timings: list[int] = Field(default_factory=list)


class CommandSummary(BaseModel):
    """List-view shape -- deliberately omits raw_timings, which can be long
    and isn't needed to render the home screen's name + IR/RF badge list.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    type: str
    default_device_id: str | None = None
    created_at: datetime
    updated_at: datetime


class CommandDetail(CommandSummary):
    """Full shape, including the raw payload -- used by the raw editor and
    by the fire/transmit path, never by the home screen's list view.
    """

    raw_timings: list[int]
    carrier_frequency_hz: int
    repeat_count: int
