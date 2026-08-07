from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ir_rf_hub.db.models import EspDevice
from ir_rf_hub.db.session import get_session
from ir_rf_hub.esphome.connection import (
    DeviceEncryptionKeyInvalidError,
    DeviceRequiresEncryptionError,
    DeviceUnexpectedEncryptionError,
    DeviceUnreachableError,
    EspHomeConnection,
)
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
    HostNetworkSchema,
)
from ir_rf_hub.security import decrypt_secret, encrypt_secret
from ir_rf_hub.supervisor_network import get_host_network

router = APIRouter(prefix="/api/devices", tags=["devices"])

# Fields where changing the value means "must actually reach this device
# again with these credentials" -- update_device only bothers with the
# throwaway pre-check below when one of these is part of the request.
_CONNECTION_FIELDS = {"host", "port", "encryption_key", "password"}


async def _ensure_unique_name(name: str, session: AsyncSession, *, exclude_id: str | None = None) -> None:
    query = select(EspDevice.id).where(func.lower(EspDevice.name) == name.strip().lower())
    if exclude_id is not None:
        query = query.where(EspDevice.id != exclude_id)
    if (await session.execute(query)).scalars().first() is not None:
        raise HTTPException(409, f'A device named "{name.strip()}" already exists')


async def _ensure_unique_host(host: str, port: int, session: AsyncSession, *, exclude_id: str | None = None) -> None:
    # Keyed on (host, port) rather than host alone -- the same host with a
    # different port is a legitimate, if unusual, distinct connection
    # target (e.g. more than one ESPHome instance behind the same
    # forwarded/loopback address in a dev setup), not "the same device
    # twice". Real duplicate-IP mistakes almost always reuse the default
    # port too, so this still catches the case that actually matters.
    query = select(EspDevice.id).where(func.lower(EspDevice.host) == host.strip().lower(), EspDevice.port == port)
    if exclude_id is not None:
        query = query.where(EspDevice.id != exclude_id)
    if (await session.execute(query)).scalars().first() is not None:
        raise HTTPException(409, f'A device at {host.strip()}:{port} already exists')


def _encryption_error_message(exc: DeviceUnreachableError) -> str:
    if isinstance(exc, DeviceRequiresEncryptionError):
        return (
            "This device requires an encryption key. Enter the noise_psk key from its "
            "ESPHome YAML's api: encryption: block."
        )
    if isinstance(exc, DeviceEncryptionKeyInvalidError):
        return "That encryption key is incorrect for this device."
    return "An encryption key was entered, but this device isn't configured to use encryption -- leave the key blank."


async def _reject_if_encryption_mismatch(
    *, host: str, port: int, encryption_key: str | None, password: str | None, connect_timeout_s: int
) -> None:
    """A throwaway connection attempt purely to catch encryption
    misconfiguration early with an actionable message, before the device
    row is ever created or modified. Deliberately narrow: a device that's
    merely offline or slow is still saved as usual by the real connect
    attempt that follows this -- only these three specific,
    certain-to-keep-failing cases are rejected outright, so the
    (redundant, but harmless) double-connect on the happy path stays rare.
    """
    conn = EspHomeConnection(
        host=host, port=port, password=password, noise_psk=encryption_key, connect_timeout_s=connect_timeout_s
    )
    try:
        await conn.connect()
    except (DeviceRequiresEncryptionError, DeviceEncryptionKeyInvalidError, DeviceUnexpectedEncryptionError) as exc:
        raise HTTPException(422, _encryption_error_message(exc)) from exc
    except DeviceUnreachableError:
        return
    else:
        await conn.disconnect()


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
    await _ensure_unique_name(payload.name, session)
    await _ensure_unique_host(payload.host, payload.port, session)
    await _reject_if_encryption_mismatch(
        host=payload.host,
        port=payload.port,
        encryption_key=payload.encryption_key,
        password=payload.password,
        connect_timeout_s=payload.connect_timeout_s,
    )

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
    if "name" in updates:
        await _ensure_unique_name(updates["name"], session, exclude_id=device_id)
    if "host" in updates or "port" in updates:
        await _ensure_unique_host(
            updates.get("host", device.host), updates.get("port", device.port), session, exclude_id=device_id
        )

    if _CONNECTION_FIELDS & updates.keys():
        # Only the fields actually being changed matter here -- anything
        # not in the request keeps its current (decrypted, for the
        # secrets) value as the candidate to test against.
        candidate_encryption_key = (
            updates["encryption_key"]
            if "encryption_key" in updates
            else (decrypt_secret(device.encryption_key_enc) if device.encryption_key_enc else None)
        )
        candidate_password = (
            updates["password"]
            if "password" in updates
            else (decrypt_secret(device.password_enc) if device.password_enc else None)
        )
        await _reject_if_encryption_mismatch(
            host=updates.get("host", device.host),
            port=updates.get("port", device.port),
            encryption_key=candidate_encryption_key,
            password=candidate_password,
            connect_timeout_s=updates.get("connect_timeout_s", device.connect_timeout_s),
        )

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
    except (DeviceRequiresEncryptionError, DeviceEncryptionKeyInvalidError, DeviceUnexpectedEncryptionError) as exc:
        raise HTTPException(422, _encryption_error_message(exc)) from exc
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


@router.get("/host-network", response_model=HostNetworkSchema)
async def host_network() -> HostNetworkSchema:
    """Backs the static-IP tip's suggested `gateway:` and `subnet:` lines.

    Supervisor knows the real values for the interface Home Assistant is on
    (`hassio_api: true` grants us the token); the ESP is assumed to share
    that subnet, which holds whenever they're on the same LAN. If Supervisor
    can't be reached -- local dev, or a Supervisor-less install -- we fall
    back to the convention this tip used to assume unconditionally, and flag
    it so the UI can say it's a guess rather than stating it as fact.
    """
    resolved = await get_host_network()
    if resolved is not None:
        return HostNetworkSchema(gateway=resolved.gateway, subnet_mask=resolved.subnet_mask, guessed=False)
    return HostNetworkSchema(gateway="", subnet_mask="255.255.255.0", guessed=True)
