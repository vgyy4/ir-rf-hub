from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from ir_rf_hub import __version__
from ir_rf_hub.api.rest.commands import router as commands_router
from ir_rf_hub.api.rest.devices import router as devices_router
from ir_rf_hub.api.rest.integration import PAIRED_KEY
from ir_rf_hub.api.rest.integration import router as integration_router
from ir_rf_hub.api.rest.recording import router as recording_router
from ir_rf_hub.api.ws.events import router as ws_events_router
from ir_rf_hub.api.ws.recording_ws import router as ws_recording_router
from ir_rf_hub.config import settings
from ir_rf_hub.db.session import session_scope
from ir_rf_hub.db.models import Setting
from ir_rf_hub.esphome.device_manager import device_manager
from ir_rf_hub.schemas import HealthResponse, PairingStatusResponse
from ir_rf_hub.security import encode_pairing_code, generate_pairing_token

logger = logging.getLogger(__name__)

# Anchored to wherever the ir_rf_hub package itself actually lives -- true
# both in local dev (backend/ir_rf_hub/) and once pip-installed inside a
# container (e.g. site-packages/ir_rf_hub/, an entirely different layout).
# db/migrations/ is a real subdirectory of the package so this always finds
# it; alembic.ini is a sibling of the package in the source tree (not
# shipped by `pip install .` at all), so it needs its own path -- see
# config.py's alembic_ini_path / the Dockerfile's explicit COPY of it.
_PACKAGE_DIR = Path(__file__).resolve().parent
_STATIC_DIR = _PACKAGE_DIR / "static"

_PAIRING_TOKEN_KEY = "pairing_token"
_INTEGRATION_API_PORT = 8099  # single port serves both Ingress UI and the integration API


def _run_migrations() -> None:
    alembic_ini = settings.alembic_ini or (_PACKAGE_DIR.parent / "alembic.ini")
    if not alembic_ini.exists():
        logger.warning("alembic.ini not found at %s, skipping migrations", alembic_ini)
        return
    cfg = AlembicConfig(str(alembic_ini))
    cfg.set_main_option("script_location", str(_PACKAGE_DIR / "db" / "migrations"))
    alembic_command.upgrade(cfg, "head")


async def _get_or_create_pairing_token() -> str:
    async with session_scope() as session:
        row = await session.get(Setting, _PAIRING_TOKEN_KEY)
        if row is not None:
            return row.value
        token = generate_pairing_token()
        session.add(Setting(key=_PAIRING_TOKEN_KEY, value=token))
        await session.commit()
        return token


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logging.basicConfig(level=settings.log_level.upper())
    logger.info("IR/RF Command Hub backend starting (version %s)", __version__)
    # Alembic's upgrade() drives env.py's own asyncio.run() internally, which
    # can't nest inside the loop already running this lifespan -- give it a
    # thread with no running loop of its own.
    await asyncio.to_thread(_run_migrations)
    await _get_or_create_pairing_token()
    yield
    await device_manager.disconnect_all()
    logger.info("IR/RF Command Hub backend shutting down")


def create_app() -> FastAPI:
    app = FastAPI(title="IR/RF Command Hub", version=__version__, lifespan=lifespan)

    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(version=__version__)

    @app.get("/api/pairing-status", response_model=PairingStatusResponse)
    async def pairing_status() -> PairingStatusResponse:
        """Polled by the SPA on load (and while showing the blocking
        pairing gate) to decide whether to show the rest of the app at
        all. There's deliberately no "Settings" page this lives on --
        this is the only place the pairing code is ever shown, and only
        for as long as nothing has paired yet.
        """
        async with session_scope() as session:
            paired_row = await session.get(Setting, PAIRED_KEY)
        if paired_row is not None and paired_row.value == "true":
            return PairingStatusResponse(paired=True, code=None)

        token = await _get_or_create_pairing_token()
        # Internal Supervisor-network hostname for a locally-installed App
        # with slug ir_rf_hub follows the `local-<slug-with-dashes>` pattern.
        code = encode_pairing_code(host="local-ir-rf-hub", port=_INTEGRATION_API_PORT, token=token)
        return PairingStatusResponse(paired=False, code=code)

    app.include_router(devices_router)
    app.include_router(commands_router)
    app.include_router(integration_router)
    app.include_router(recording_router)
    app.include_router(ws_events_router)
    app.include_router(ws_recording_router)

    if _STATIC_DIR.exists():
        app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")
    else:
        logger.warning("Static frontend build not found at %s; SPA will not be served", _STATIC_DIR)

    return app


app = create_app()
