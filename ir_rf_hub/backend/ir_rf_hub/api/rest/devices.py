from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ir_rf_hub.db.models import Command, EspDevice
from ir_rf_hub.db.session import get_session
from ir_rf_hub.esphome.connection import DeviceUnreachableError
from ir_rf_hub.esphome.device_manager import device_manager
from ir_rf_hub.esphome.discovery import discover_esphome_devices
from ir_rf_hub.esphome.integration_discovery import get_reported_devices
from ir_rf_hub.events import Event, event_bus
from ir_rf_hub.schemas import (
    DeviceEntitySummary,
    DiscoveredDeviceSchema,
    EspDeviceCreate,
    EspDeviceSummary,
    EspDeviceUpdate,
)
from ir_rf_hub.security import encrypt_secret

router = APIRouter(prefix="/api/devices", tags=["devices"])


def _to_summary(device: EspDevice) -> EspDeviceSummary:
    session = device_manager.get_cached(device.id)
    return EspDeviceSummary(
        id=device.id,
        name=device.name,
        host=device.host,
        port=device.port,
        tx_settle_ms=device.tx_settle_ms,
        rx_stop_settle_ms=device.rx_stop_settle_ms,
        connect_timeout_s=device.connect_timeout_s,
        last_connected_at=device.last_connected_at,
        last_error=device.last_error,
        connection_state=session.state.value if session else "disconnected",
        entities=[DeviceEntitySummary.model_validate(e) for e in device.entities],
    )


@router.get("", response_model=list[EspDeviceSummary])
async def list_devices(session: AsyncSession = Depends(get_session)) -> list[EspDeviceSummary]:
    result = await session.execute(select(EspDevice).options(selectinload(EspDevice.entities)))
    return [_to_summary(d) for d in result.scalars().all()]


@router.post("", response_model=EspDeviceSummary, status_code=201)
async def create_device(payload: EspDeviceCreate, session: AsyncSession = Depends(get_session)) -> EspDeviceSummary:
    device = EspDevice(
        name=payload.name,
        host=payload.host,
        port=payload.port,
        encryption_key_enc=encrypt_secret(payload.encryption_key) if payload.encryption_key else None,
        password_enc=encrypt_secret(payload.password) if payload.password else None,
        tx_settle_ms=payload.tx_settle_ms,
        rx_stop_settle_ms=payload.rx_stop_settle_ms,
        connect_timeout_s=payload.connect_timeout_s,
    )
    session.add(device)
    await session.commit()
    await session.refresh(device, attribute_names=["entities"])

    try:
        await device_manager.connect(session, device)
    except DeviceUnreachableError:
        pass  # device row is still saved; last_error/connection_state reflect the failure

    await session.refresh(device, attribute_names=["entities"])
    event_bus.publish(Event(type="device.status_changed", data={"device_id": device.id, "status": "created"}))
    return _to_summary(device)


@router.put("/{device_id}", response_model=EspDeviceSummary)
async def update_device(
    device_id: str, payload: EspDeviceUpdate, session: AsyncSession = Depends(get_session)
) -> EspDeviceSummary:
    device = await session.get(EspDevice, device_id, options=[selectinload(EspDevice.entities)])
    if device is None:
        raise HTTPException(404, "Device not found")

    updates = payload.model_dump(exclude_unset=True)
    if "encryption_key" in updates:
        key = updates.pop("encryption_key")
        device.encryption_key_enc = encrypt_secret(key) if key else None
    if "password" in updates:
        pw = updates.pop("password")
        device.password_enc = encrypt_secret(pw) if pw else None
    for field, value in updates.items():
        setattr(device, field, value)

    await session.commit()
    # Connection settings may have changed -- drop any live session so the
    # next use reconnects with the new host/port/credentials.
    await device_manager.disconnect(device_id)
    await session.refresh(device, attribute_names=["entities"])
    return _to_summary(device)


@router.delete("/{device_id}", status_code=204)
async def delete_device(device_id: str, session: AsyncSession = Depends(get_session)) -> None:
    device = await session.get(EspDevice, device_id)
    if device is None:
        raise HTTPException(404, "Device not found")
    await device_manager.disconnect(device_id)
    # Commands that default to this device fall back to "ask which ESP"
    # behavior via the FK's ON DELETE SET NULL -- no cascade, no block.
    await session.delete(device)
    await session.commit()


@router.post("/{device_id}/test", response_model=EspDeviceSummary)
async def test_device(device_id: str, session: AsyncSession = Depends(get_session)) -> EspDeviceSummary:
    device = await session.get(EspDevice, device_id, options=[selectinload(EspDevice.entities)])
    if device is None:
        raise HTTPException(404, "Device not found")

    await device_manager.disconnect(device_id)  # force a fresh connection attempt
    try:
        await device_manager.connect(session, device)
    except DeviceUnreachableError as exc:
        raise HTTPException(502, f"Could not connect: {exc}") from exc

    await session.refresh(device, attribute_names=["entities"])
    return _to_summary(device)


@router.get("/discover", response_model=list[DiscoveredDeviceSchema])
async def discover_devices(session: AsyncSession = Depends(get_session)) -> list[DiscoveredDeviceSchema]:
    """Merges two sources: the App's own local mDNS browse (works if
    Supervisor's Multicast plugin reaches this container -- not
    guaranteed for every install) and whatever the companion integration
    most recently reported (reliable -- it browses from inside Home
    Assistant Core, see integration_discovery.py). Local results win on
    a host collision since they're fresher (this request just ran it).
    """
    existing_hosts = {d.host for d in (await session.execute(select(EspDevice))).scalars().all()}
    local = await discover_esphome_devices()

    by_host = {d.host: DiscoveredDeviceSchema(name=d.name, host=d.host, port=d.port) for d in get_reported_devices()}
    by_host.update({d.host: DiscoveredDeviceSchema(name=d.name, host=d.host, port=d.port) for d in local})

    return [d for d in by_host.values() if d.host not in existing_hosts]
