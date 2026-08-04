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

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ir_rf_hub.db.models import Command, Setting
from ir_rf_hub.db.session import get_session
from ir_rf_hub.schemas import CommandSummary, HealthResponse
from ir_rf_hub.security import verify_integration_token

router = APIRouter(prefix="/api/integration", tags=["integration"])

_PAIRING_TOKEN_KEY = "pairing_token"


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
