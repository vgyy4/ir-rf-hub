from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ir_rf_hub.api.rest.devices import _to_summary
from ir_rf_hub.db.models import Command, DeviceEntity, DeviceRole, EspDevice, SignalDomain, SignalType
from ir_rf_hub.db.session import get_session
from ir_rf_hub.esphome.connection import DeviceUnreachableError
from ir_rf_hub.esphome.device_manager import device_manager
from ir_rf_hub.esphome.device_session import DeviceBusyTimeoutError
from ir_rf_hub.events import Event, event_bus
from ir_rf_hub.schemas import CommandDetail, CommandSummary, EspDeviceSummary

router = APIRouter(prefix="/api/commands", tags=["commands"])


class CommandCreateRequest(BaseModel):
    name: str
    type: str  # "ir" | "rf"
    raw_timings: list[int]
    carrier_frequency_hz: int = 0
    repeat_count: int = 1
    default_device_id: str | None = None
    # Informational only -- the device a command was recorded *from* (a
    # receiver) is not necessarily valid as a transmit target, so this is
    # never used to set default_device_id automatically. See devices.py's
    # candidate-devices filtering for why: default_device_id must point at
    # a device with a tx-role entity of the matching domain.
    recorded_from_device_id: str | None = None
    # Set only for a two-shape command -- see fire_command()'s firing
    # semantics and esphome/signal_shapes.py.
    repeat_timings: list[int] | None = None
    repeat_protocol: str | None = None


class CommandUpdateRequest(BaseModel):
    name: str | None = None
    raw_timings: list[int] | None = None
    carrier_frequency_hz: int | None = None
    repeat_count: int | None = None
    default_device_id: str | None = None
    repeat_timings: list[int] | None = None
    repeat_protocol: str | None = None


class FireRequest(BaseModel):
    device_id: str | None = None


def _domain_for_type(type_: str) -> SignalDomain:
    if type_ == "ir":
        return SignalDomain.infrared
    if type_ == "rf":
        return SignalDomain.radio_frequency
    raise HTTPException(400, "type must be 'ir' or 'rf'")


async def _ensure_unique_name(name: str, session: AsyncSession, *, exclude_id: str | None = None) -> None:
    query = select(Command.id).where(func.lower(Command.name) == name.strip().lower())
    if exclude_id is not None:
        query = query.where(Command.id != exclude_id)
    if (await session.execute(query)).scalars().first() is not None:
        raise HTTPException(409, f"A command named \"{name.strip()}\" already exists")


async def _candidate_tx_device_ids(domain: SignalDomain, session: AsyncSession) -> list[str]:
    result = await session.execute(
        select(EspDevice.id)
        .join(DeviceEntity, DeviceEntity.device_id == EspDevice.id)
        .where(DeviceEntity.domain == domain, DeviceEntity.role == DeviceRole.tx)
        .distinct()
    )
    return list(result.scalars().all())


@router.get("", response_model=list[CommandSummary])
async def list_commands(session: AsyncSession = Depends(get_session)) -> list[CommandSummary]:
    result = await session.execute(select(Command).order_by(Command.name))
    return [CommandSummary.model_validate(c) for c in result.scalars().all()]


@router.get("/{command_id}", response_model=CommandDetail)
async def get_command(command_id: str, session: AsyncSession = Depends(get_session)) -> CommandDetail:
    command = await session.get(Command, command_id)
    if command is None:
        raise HTTPException(404, "Command not found")
    return CommandDetail.model_validate(command)


@router.post("", response_model=CommandDetail, status_code=201)
async def create_command(payload: CommandCreateRequest, session: AsyncSession = Depends(get_session)) -> CommandDetail:
    _domain_for_type(payload.type)  # validates
    await _ensure_unique_name(payload.name, session)
    command = Command(
        name=payload.name,
        type=SignalType(payload.type),
        raw_timings=payload.raw_timings,
        carrier_frequency_hz=payload.carrier_frequency_hz,
        repeat_count=payload.repeat_count,
        default_device_id=payload.default_device_id,
        recorded_from_device_id=payload.recorded_from_device_id,
        repeat_timings=payload.repeat_timings,
        repeat_protocol=payload.repeat_protocol,
    )
    session.add(command)
    await session.commit()
    event_bus.publish(Event(type="command.created", data={"command_id": command.id}))
    return CommandDetail.model_validate(command)


@router.put("/{command_id}", response_model=CommandDetail)
async def update_command(
    command_id: str, payload: CommandUpdateRequest, session: AsyncSession = Depends(get_session)
) -> CommandDetail:
    command = await session.get(Command, command_id)
    if command is None:
        raise HTTPException(404, "Command not found")

    updates = payload.model_dump(exclude_unset=True)
    if "name" in updates:
        await _ensure_unique_name(updates["name"], session, exclude_id=command_id)
    for field, value in updates.items():
        setattr(command, field, value)

    await session.commit()
    event_bus.publish(Event(type="command.updated", data={"command_id": command.id}))
    return CommandDetail.model_validate(command)


@router.delete("/{command_id}", status_code=204)
async def delete_command(command_id: str, session: AsyncSession = Depends(get_session)) -> None:
    command = await session.get(Command, command_id)
    if command is None:
        raise HTTPException(404, "Command not found")
    await session.delete(command)
    await session.commit()
    event_bus.publish(Event(type="command.deleted", data={"command_id": command_id}))


@router.get("/{command_id}/candidate-devices", response_model=list[EspDeviceSummary])
async def candidate_devices(command_id: str, session: AsyncSession = Depends(get_session)) -> list[EspDeviceSummary]:
    command = await session.get(Command, command_id)
    if command is None:
        raise HTTPException(404, "Command not found")
    domain = _domain_for_type(command.type.value)

    result = await session.execute(
        select(EspDevice)
        .join(DeviceEntity, DeviceEntity.device_id == EspDevice.id)
        .where(DeviceEntity.domain == domain, DeviceEntity.role == DeviceRole.tx)
        .distinct()
        .options(selectinload(EspDevice.entities))
    )
    devices = result.scalars().all()
    return [_to_summary(d) for d in devices]


async def _fire_signal(
    device_session,
    *,
    domain: SignalDomain,
    tx_key: int,
    carrier_frequency_hz: int,
    raw_timings: list[int],
    repeat_count: int,
    repeat_timings: list[int] | None,
) -> None:
    """Shared by fire_command (a saved Command) and test_fire (an
    in-progress, unsaved payload from the raw editor) -- same two-shape
    firing semantics either way, see fire_command's original inline
    comment for why the leader/repeat split isn't `timings x repeat_count`
    twice over.
    """
    if repeat_timings is None:
        await device_session.transmit(
            domain=domain,
            tx_key=tx_key,
            timings=raw_timings,
            carrier_frequency_hz=carrier_frequency_hz,
            repeat_count=repeat_count,
        )
    else:
        await device_session.transmit(
            domain=domain, tx_key=tx_key, timings=raw_timings, carrier_frequency_hz=carrier_frequency_hz, repeat_count=1
        )
        if repeat_count > 1:
            await device_session.transmit(
                domain=domain,
                tx_key=tx_key,
                timings=repeat_timings,
                carrier_frequency_hz=carrier_frequency_hz,
                repeat_count=repeat_count - 1,
            )


async def _get_tx_entity(device: EspDevice, domain: SignalDomain, session: AsyncSession) -> DeviceEntity:
    entity = (
        await session.execute(
            select(DeviceEntity).where(
                DeviceEntity.device_id == device.id,
                DeviceEntity.domain == domain,
                DeviceEntity.role == DeviceRole.tx,
            )
        )
    ).scalars().first()
    if entity is None:
        raise HTTPException(400, f"Device {device.name} has no {domain.value} transmitter")
    return entity


@router.post("/{command_id}/fire", status_code=204)
async def fire_command(command_id: str, payload: FireRequest, session: AsyncSession = Depends(get_session)) -> None:
    command = await session.get(Command, command_id)
    if command is None:
        raise HTTPException(404, "Command not found")

    domain = _domain_for_type(command.type.value)
    device_id = payload.device_id or command.default_device_id
    if device_id is None:
        # No explicit target and no default -- the App's own UI can ask
        # "which ESP?" interactively (see /candidate-devices), but a
        # button/switch press or automation call from the companion
        # integration has no way to prompt anyone. If there's exactly
        # one device that could possibly send this, use it rather than
        # failing every fire from Home Assistant for commands nobody
        # bothered to set a default on (the common case if you only own
        # one IR and one RF transmitter). Still refuses to guess when
        # it's genuinely ambiguous.
        candidates = await _candidate_tx_device_ids(domain, session)
        if len(candidates) == 1:
            device_id = candidates[0]
    if device_id is None:
        raise HTTPException(400, "No device specified and this command has no default device")

    device = await session.get(EspDevice, device_id)
    if device is None:
        raise HTTPException(404, "Device not found")

    entity = await _get_tx_entity(device, domain, session)

    try:
        device_session = await device_manager.connect(session, device)
        await _fire_signal(
            device_session,
            domain=domain,
            tx_key=entity.esphome_key,
            carrier_frequency_hz=command.carrier_frequency_hz,
            raw_timings=command.raw_timings,
            repeat_count=command.repeat_count,
            repeat_timings=command.repeat_timings,
        )
    except DeviceUnreachableError as exc:
        raise HTTPException(502, f"Could not reach device: {exc}") from exc
    except DeviceBusyTimeoutError as exc:
        raise HTTPException(504, str(exc)) from exc


class TestFireRequest(BaseModel):
    """Fires an in-progress payload straight from the raw editor, without
    saving it as (or already existing as) a Command first -- lets you
    verify a hand-edited signal actually does something before committing
    to it. Intentionally mirrors CommandCreateRequest's raw-signal fields
    rather than reusing it: default_device_id/recorded_from_device_id have
    no meaning for a payload that was never saved.
    """

    type: str  # "ir" | "rf"
    device_id: str
    raw_timings: list[int]
    carrier_frequency_hz: int = 0
    repeat_count: int = 1
    repeat_timings: list[int] | None = None


@router.post("/test-fire", status_code=204)
async def test_fire(payload: TestFireRequest, session: AsyncSession = Depends(get_session)) -> None:
    domain = _domain_for_type(payload.type)
    device = await session.get(EspDevice, payload.device_id)
    if device is None:
        raise HTTPException(404, "Device not found")

    entity = await _get_tx_entity(device, domain, session)

    try:
        device_session = await device_manager.connect(session, device)
        await _fire_signal(
            device_session,
            domain=domain,
            tx_key=entity.esphome_key,
            carrier_frequency_hz=payload.carrier_frequency_hz,
            raw_timings=payload.raw_timings,
            repeat_count=payload.repeat_count,
            repeat_timings=payload.repeat_timings,
        )
    except DeviceUnreachableError as exc:
        raise HTTPException(502, f"Could not reach device: {exc}") from exc
    except DeviceBusyTimeoutError as exc:
        raise HTTPException(504, str(exc)) from exc
