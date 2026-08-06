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


class DeviceOptionSchema(BaseModel):
    """Minimal id+name shape for the companion integration's per-command
    select entity -- picking which ESP to fire a command through. Just
    enough to populate a dropdown; unlike EspDeviceSummary this deliberately
    doesn't carry entities/connection_state, which the integration has no
    use for here.
    """

    id: str
    name: str


class RecordingStartRequest(BaseModel):
    type: str  # "ir" | "rf"
    device_id: str


class RecordingSessionResponse(BaseModel):
    session_id: str
    device_id: str
    type: str


class ShapeCandidateSchema(BaseModel):
    """One distinct signal shape seen during a recording session, offered
    to the user to choose from when stop_recording() couldn't resolve the
    session to a single shape or a recognized protocol on its own -- see
    esphome/signal_shapes.py.
    """

    timings: list[int]
    edge_count: int
    occurrences: int


class DetectedProtocolSchema(BaseModel):
    """A recognized multi-shape protocol (today: NEC-family leader +
    repeat frame) -- both parts are saved together with no user choice
    needed, unlike the ambiguous shape_candidates case.
    """

    name: str
    leader_timings: list[int]
    repeat_timings: list[int]


class DecodedSignalSchema(BaseModel):
    """Structural protocol decode of the resolved capture -- "this is NEC,
    address 0x04, command 0x08" for IR (esphome/protocol_decode.py), or
    "this is Princeton, key ..., 24 bits" for RF (esphome/
    rf_protocol_decode.py) -- independent of and unrelated to
    remote_matches below. address/command are IR-only (0 for an RF
    decode); key_hex/bit_count are RF-only (None for an IR decode)."""

    protocol: str
    address: int = 0
    command: int = 0
    key_hex: str | None = None
    bit_count: int | None = None


class RemoteMatchSchema(BaseModel):
    """One candidate name suggestion for the just-recorded signal, from
    matching its decoded (protocol, address, command) against the bundled
    remote database (Flipper-IRDB, IRDB, and a Sub-GHz RF source, merged
    and deduplicated -- see esphome/remote_database_build.py) -- always
    `source="bundled"` today."""

    source: str
    category: str
    brand: str
    model: str
    button: str


class RecordingStopResponse(BaseModel):
    session_id: str
    capture_count: int
    # Exactly one of these three is populated, depending on what
    # stop_recording() found among the session's captures:
    # - timings: every capture was the same shape (the common case) --
    #   ready to save as-is, no extra step needed.
    # - detected_protocol: a recognized multi-shape protocol was found --
    #   also ready to save as-is.
    # - shape_candidates: multiple distinct shapes were captured and
    #   neither of the above applied -- the frontend must show a picker.
    timings: list[int] | None = None
    detected_protocol: DetectedProtocolSchema | None = None
    shape_candidates: list[ShapeCandidateSchema] | None = None
    # Best-effort extras computed from `timings` or detected_protocol's
    # leader, when either is available -- never set when the response only
    # has shape_candidates (nothing's resolved to decode yet).
    decoded: DecodedSignalSchema | None = None
    remote_matches: list[RemoteMatchSchema] = Field(default_factory=list)


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
    # Set only for a two-shape command (see esphome/signal_shapes.py):
    # raw_timings is the leader, fired once; repeat_timings is fired
    # (repeat_count - 1) more times. None means a plain single-shape
    # command -- raw_timings alone, fired repeat_count times, unchanged
    # from before this existed.
    repeat_timings: list[int] | None = None
    # Informational only (e.g. "nec_leader_repeat") -- set when
    # repeat_timings was auto-detected rather than manually chosen by the
    # user from shape_candidates. Never read by the firing path.
    repeat_protocol: str | None = None


class RemoteSearchResultSchema(BaseModel):
    """One candidate from searching the bundled remote database (see
    esphome/remote_database.py) -- already fully encoded and ready to
    test-fire or save as-is via the normal test-fire/create-command
    endpoints, no extra round-trip needed to resolve it into a real
    signal."""

    category: str
    brand: str
    model: str
    button: str
    raw_timings: list[int]
    carrier_frequency_hz: int
    repeat_count: int


class HostNetworkSchema(BaseModel):
    """The Home Assistant host's real IPv4 gateway and subnet, for the
    static-IP tip. `guessed` is True when Supervisor couldn't be reached and
    the values fall back to the old home-network convention, so the UI can
    word the tip honestly instead of asserting something it doesn't know.
    """

    gateway: str
    subnet_mask: str
    guessed: bool
