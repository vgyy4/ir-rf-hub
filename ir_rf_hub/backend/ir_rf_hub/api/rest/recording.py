"""Recording session control. Session start/stop/clear/discard are
discrete, idempotency-sensitive actions, so they're REST -- the live
capture feed itself is a push stream, handled separately by
api/ws/recording_ws.py. See device_session.py for why "start recording"
doesn't send any command to the ESPHome device at all: reception is
always-on at the ESPHome level, so starting a session just begins
listening to the (already-flowing) raw receive events for one entity key.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ir_rf_hub.db.models import DeviceEntity, DeviceRole, EspDevice, SignalDomain
from ir_rf_hub.db.session import get_session
from ir_rf_hub.esphome.connection import DeviceUnreachableError
from ir_rf_hub.esphome.device_manager import device_manager
from ir_rf_hub.esphome.device_session import DeviceBusyRecordingError, DeviceBusyTimeoutError
from ir_rf_hub.esphome.signal_shapes import cluster_captures, detect_multi_shape_protocol
from ir_rf_hub.schemas import (
    DetectedProtocolSchema,
    RecordingSessionResponse,
    RecordingStartRequest,
    RecordingStopResponse,
    ShapeCandidateSchema,
)

router = APIRouter(prefix="/api/recording", tags=["recording"])

# session_id -> device_id. Recording sessions are short-lived and
# interactive (one open modal), so an in-memory registry is enough -- it
# doesn't need to survive a backend restart, unlike Command storage.
_session_devices: dict[str, str] = {}


def _domain_for_type(type_: str) -> SignalDomain:
    if type_ == "ir":
        return SignalDomain.infrared
    if type_ == "rf":
        return SignalDomain.radio_frequency
    raise HTTPException(400, "type must be 'ir' or 'rf'")


@router.post("/sessions", response_model=RecordingSessionResponse, status_code=201)
async def start_recording(
    payload: RecordingStartRequest, session: AsyncSession = Depends(get_session)
) -> RecordingSessionResponse:
    domain = _domain_for_type(payload.type)

    device = await session.get(EspDevice, payload.device_id)
    if device is None:
        raise HTTPException(404, "Device not found")

    entity = (
        await session.execute(
            select(DeviceEntity).where(
                DeviceEntity.device_id == device.id,
                DeviceEntity.domain == domain,
                DeviceEntity.role == DeviceRole.rx,
            )
        )
    ).scalars().first()
    if entity is None:
        raise HTTPException(400, f"Device {device.name} has no {payload.type.upper()} receiver")

    try:
        device_session = await device_manager.connect(session, device)
        recording = await device_session.start_recording(domain=domain, rx_key=entity.esphome_key)
    except DeviceUnreachableError as exc:
        raise HTTPException(502, f"Could not reach device: {exc}") from exc
    except DeviceBusyRecordingError as exc:
        raise HTTPException(409, str(exc)) from exc
    except DeviceBusyTimeoutError as exc:
        raise HTTPException(504, str(exc)) from exc

    _session_devices[recording.id] = device.id
    return RecordingSessionResponse(session_id=recording.id, device_id=device.id, type=payload.type)


def _device_session_for(session_id: str):
    device_id = _session_devices.get(session_id)
    if device_id is None:
        raise HTTPException(404, "Unknown recording session")
    device_session = device_manager.get_cached(device_id)
    if device_session is None:
        raise HTTPException(404, "Device session no longer available")
    return device_session


@router.post("/sessions/{session_id}/clear", status_code=204)
async def clear_recording(session_id: str) -> None:
    device_session = _device_session_for(session_id)
    try:
        device_session.clear_recording(session_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/sessions/{session_id}/stop", response_model=RecordingStopResponse)
async def stop_recording(session_id: str) -> RecordingStopResponse:
    device_session = _device_session_for(session_id)
    try:
        finished = await device_session.stop_recording(session_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    _session_devices.pop(session_id, None)

    if not finished.captures:
        raise HTTPException(422, "No signal was captured during this recording")

    clusters = cluster_captures(finished.captures)

    if len(clusters) == 1:
        return RecordingStopResponse(
            session_id=session_id, capture_count=finished.capture_count, timings=clusters[0].timings
        )

    detected = detect_multi_shape_protocol(clusters)
    if detected is not None:
        return RecordingStopResponse(
            session_id=session_id,
            capture_count=finished.capture_count,
            detected_protocol=DetectedProtocolSchema(
                name=detected.name, leader_timings=detected.leader_timings, repeat_timings=detected.repeat_timings
            ),
        )

    return RecordingStopResponse(
        session_id=session_id,
        capture_count=finished.capture_count,
        shape_candidates=[
            ShapeCandidateSchema(timings=c.timings, edge_count=c.edge_count, occurrences=c.occurrences)
            for c in clusters
        ],
    )


@router.post("/sessions/{session_id}/discard", status_code=204)
async def discard_recording(session_id: str) -> None:
    device_session = _device_session_for(session_id)
    try:
        await device_session.discard_recording(session_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    _session_devices.pop(session_id, None)
