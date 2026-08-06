"""Token-authed surface for the companion HA integration -- a separate HA
core process reaching the App over the internal Supervisor network, not a
browser session Ingress has already authenticated. Bearer token is the
same secret embedded in the pairing code (security.py).

/api/ws (the general event fan-out) is deliberately left unauthenticated
even though the integration also uses it for live-sync notifications: it
only carries change *notifications* (command IDs, "something changed"),
never raw command payloads or anything actionable, and the Supervisor's
internal Docker network is already a private trust boundary a browser
can't reach directly. The meaningful gate is here, on the endpoints that
actually return command data or could be used for control.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ir_rf_hub.api.rest.commands import FireRequest, _candidate_tx_device_ids, _domain_for_type, fire_command
from ir_rf_hub.db.models import Command, EspDevice, Setting
from ir_rf_hub.db.session import get_session
from ir_rf_hub.esphome.integration_discovery import set_reported_devices
from ir_rf_hub.schemas import CommandSummary, DeviceOptionSchema, DiscoveredDeviceSchema, HealthResponse
from ir_rf_hub.security import hash_integration_token, is_hashed_token, verify_integration_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integration", tags=["integration"])

_PAIRING_TOKEN_KEY = "pairing_token"
PAIRED_KEY = "paired"


async def require_integration_token(
    authorization: str = Header(default=""), session: AsyncSession = Depends(get_session)
) -> None:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token")
    presented = authorization.removeprefix("Bearer ")

    setting = await session.get(Setting, _PAIRING_TOKEN_KEY)
    expected = setting.value if setting else None
    if not expected or not verify_integration_token(presented, expected):
        raise HTTPException(401, "Invalid token")

    # First successful authenticated call from the integration is what
    # flips the App from "show the blocking pairing gate" to "usable" --
    # see main.py's /api/pairing-status, which the SPA polls for this.
    # Stays true forever once set: a later brief disconnect (HA restart,
    # network blip) shouldn't suddenly lock the user back out of their
    # own command library.
    paired = await session.get(Setting, PAIRED_KEY)
    if paired is None:
        session.add(Setting(key=PAIRED_KEY, value="true"))

    # Once something has paired, the pairing code is never shown again
    # (/api/pairing-status returns code=None), so the plaintext token has no
    # remaining purpose -- only verification does, and a hash serves that.
    # Replacing it here means the database stops holding a working bearer
    # token for /api/integration/*. Also upgrades installs that paired
    # before this existed, on their next authenticated call.
    if setting is not None and not is_hashed_token(setting.value):
        setting.value = hash_integration_token(presented)

    if session.dirty or session.new:
        await session.commit()


@router.get("/health", response_model=HealthResponse, dependencies=[Depends(require_integration_token)])
async def integration_health() -> HealthResponse:
    from ir_rf_hub import __version__

    return HealthResponse(version=__version__)


@router.get(
    "/commands", response_model=list[CommandSummary], dependencies=[Depends(require_integration_token)]
)
async def integration_list_commands(session: AsyncSession = Depends(get_session)) -> list[CommandSummary]:
    result = await session.execute(select(Command).order_by(Command.name))
    return [CommandSummary.model_validate(c) for c in result.scalars().all()]


@router.post(
    "/commands/{command_id}/fire", status_code=204, dependencies=[Depends(require_integration_token)]
)
async def integration_fire_command(
    command_id: str, payload: FireRequest | None = None, session: AsyncSession = Depends(get_session)
) -> None:
    # Delegates to the same fire logic the SPA uses -- see commands.py.
    # payload is optional: a button/switch press with no default device
    # set posts an empty body, relying on fire_command's own single-
    # candidate fallback; the select entity (device choice made
    # explicit) posts {"device_id": ...}.
    await fire_command(command_id, payload or FireRequest(device_id=None), session)


@router.get(
    "/commands/{command_id}/candidate-devices",
    response_model=list[DeviceOptionSchema],
    dependencies=[Depends(require_integration_token)],
)
async def integration_candidate_devices(
    command_id: str, session: AsyncSession = Depends(get_session)
) -> list[DeviceOptionSchema]:
    """Backs the companion integration's per-command select entity --
    which ESP devices could transmit this command, so the user can
    choose one when building an automation/script/scene (or directly
    from a dashboard card), not just from the App's own UI. See
    commands.py's candidate_devices for the App-UI equivalent this
    mirrors (that one returns full EspDeviceSummary objects for a richer
    picker; this just needs id+name for a select dropdown).
    """
    command = await session.get(Command, command_id)
    if command is None:
        raise HTTPException(404, "Command not found")

    domain = _domain_for_type(command.type.value)
    device_ids = await _candidate_tx_device_ids(domain, session)
    if not device_ids:
        return []

    result = await session.execute(select(EspDevice.id, EspDevice.name).where(EspDevice.id.in_(device_ids)))
    return [DeviceOptionSchema(id=device_id, name=name) for device_id, name in result.all()]


@router.post("/discovered-devices", status_code=204, dependencies=[Depends(require_integration_token)])
async def integration_report_discovered_devices(devices: list[DiscoveredDeviceSchema]) -> None:
    """The integration's own periodic zeroconf browse (reliable -- it
    runs inside Home Assistant Core, not this container) reports what it
    finds here. GET /api/devices/discover merges this with the App's own
    local mDNS attempt -- see esphome/integration_discovery.py.
    """
    logger.info("Received %d discovered device(s) from the integration", len(devices))
    set_reported_devices(devices)
