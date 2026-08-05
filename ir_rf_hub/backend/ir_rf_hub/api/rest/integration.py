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

from ir_rf_hub.db.models import Command, Setting
from ir_rf_hub.db.session import get_session
from ir_rf_hub.esphome.integration_discovery import set_reported_devices
from ir_rf_hub.schemas import CommandSummary, DiscoveredDeviceSchema, HealthResponse
from ir_rf_hub.security import verify_integration_token

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
async def integration_fire_command(command_id: str, session: AsyncSession = Depends(get_session)) -> None:
    # Delegates to the same fire logic the SPA uses -- see commands.py.
    from ir_rf_hub.api.rest.commands import FireRequest, fire_command

    await fire_command(command_id, FireRequest(device_id=None), session)


@router.post("/discovered-devices", status_code=204, dependencies=[Depends(require_integration_token)])
async def integration_report_discovered_devices(devices: list[DiscoveredDeviceSchema]) -> None:
    """The integration's own periodic zeroconf browse (reliable -- it
    runs inside Home Assistant Core, not this container) reports what it
    finds here. GET /api/devices/discover merges this with the App's own
    local mDNS attempt -- see esphome/integration_discovery.py.
    """
    logger.info("Received %d discovered device(s) from the integration", len(devices))
    set_reported_devices(devices)
