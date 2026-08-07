from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
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
from ir_rf_hub.api.rest.remote_database import router as remote_database_router
from ir_rf_hub.api.ws.events import router as ws_events_router
from ir_rf_hub.api.ws.recording_ws import router as ws_recording_router
from ir_rf_hub.config import settings
from ir_rf_hub.db.models import EspDevice, Setting
from ir_rf_hub.db.session import session_scope
from ir_rf_hub.esphome.connection import DeviceUnreachableError
from ir_rf_hub.esphome.device_manager import device_manager
from ir_rf_hub.esphome.remote_database_updater import refresh_periodically as refresh_remote_database_periodically
from ir_rf_hub.schemas import HealthResponse, PairingStatusResponse
from ir_rf_hub.security import encode_pairing_code, generate_pairing_token
from ir_rf_hub.supervisor_discovery import announce_pairing

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
_DISCOVERY_REANNOUNCE_INTERVAL_S = 60


def _pairing_host() -> str:
    # The container's own hostname *is* the Supervisor-network DNS name
    # other add-ons/integrations use to reach it -- Supervisor sets it
    # when creating the container. Hardcoding `local-ir-rf-hub` only
    # works for the special "local" add-ons folder; installs from this
    # repo's custom repository (see repository.yaml) get a different,
    # repo-hash-based hostname, so that assumption silently broke pairing.
    return socket.gethostname()


async def _is_paired() -> bool:
    async with session_scope() as session:
        paired_row = await session.get(Setting, PAIRED_KEY)
    return paired_row is not None and paired_row.value == "true"


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


async def _connect_known_devices() -> None:
    """Best-effort: connects to every saved device once at startup, so
    the device list's connection_state reflects reality right away
    instead of showing every device as "disconnected" until the user
    happens to fire/record/test one -- device_manager only ever learns a
    device is reachable as a side effect of some other action, and a
    restart (routine: HA restarts, App updates like this one) wipes its
    in-memory session cache entirely. A genuinely offline device just
    stays disconnected, same as create_device's own best-effort connect.

    Concurrent, each with its own DB session -- AsyncSession isn't safe
    to share across concurrently-running coroutines -- so total delay is
    roughly the single slowest device's connect_timeout_s, not their sum.
    """
    async with session_scope() as session:
        device_ids = list((await session.execute(select(EspDevice.id))).scalars().all())

    async def _connect_one(device_id: str) -> None:
        async with session_scope() as device_session:
            device = await device_session.get(EspDevice, device_id)
            if device is None:
                return
            try:
                await device_manager.connect(device_session, device)
            except DeviceUnreachableError:
                pass

    results = await asyncio.gather(*(_connect_one(d) for d in device_ids), return_exceptions=True)
    for device_id, result in zip(device_ids, results, strict=True):
        if isinstance(result, BaseException):
            logger.warning("Startup connect to device %s failed unexpectedly", device_id, exc_info=result)


async def _announce_pairing_until_paired(token: str) -> None:
    """Re-announces on an interval rather than once: Supervisor's
    Discovery API doesn't persist across a Supervisor/Core restart the
    way our own DB-backed pairing token does, and the companion
    integration might not even be installed yet the first few times this
    runs. Stops for good once paired -- the manual code flow (still
    served by /api/pairing-status) remains the fallback if this never
    gets picked up (e.g. the App isn't running under Supervisor at all).
    """
    while not await _is_paired():
        await announce_pairing(host=_pairing_host(), port=_INTEGRATION_API_PORT, token=token)
        await asyncio.sleep(_DISCOVERY_REANNOUNCE_INTERVAL_S)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logging.basicConfig(level=settings.log_level.upper())
    logger.info("IR/RF Hub backend starting (version %s)", __version__)
    # Alembic's upgrade() drives env.py's own asyncio.run() internally, which
    # can't nest inside the loop already running this lifespan -- give it a
    # thread with no running loop of its own.
    await asyncio.to_thread(_run_migrations)
    # Only touched while unpaired. After pairing the stored value is a hash
    # (see api/rest/integration.py), which is useless to announce -- and the
    # announce loop would exit immediately anyway.
    announce_task = (
        None
        if await _is_paired()
        else asyncio.create_task(_announce_pairing_until_paired(await _get_or_create_pairing_token()))
    )
    connect_task = asyncio.create_task(_connect_known_devices())
    # Checks (not unconditionally refetches -- see the module's own
    # docstring) whether the bundled-database runtime cache needs
    # refreshing, then keeps checking on an interval for the rest of the
    # process's life. A slow/failed first check just means recording
    # keeps using whatever's already cached/bundled -- never blocks
    # startup on it. Skippable (see disable_remote_database_updater) so
    # the test suite never triggers a real git clone against GitHub.
    remote_database_update_task = (
        None
        if settings.disable_remote_database_updater
        else asyncio.create_task(refresh_remote_database_periodically())
    )
    yield
    if remote_database_update_task is not None:
        remote_database_update_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await remote_database_update_task
    if announce_task is not None:
        announce_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await announce_task
    # Deliberately awaited, not cancelled, unlike announce_task above:
    # this is a bounded one-shot (each device already has its own
    # connect_timeout_s, and _connect_one/gather(return_exceptions=True)
    # already swallow every expected failure) rather than a forever-loop,
    # so there's no need to cut it short. Cancelling mid-flight risked
    # interrupting an aiosqlite operation and leaving its background
    # worker thread trying to call back into an event loop that's since
    # closed -- confirmed by a real "Event loop is closed" warning
    # surfacing in unrelated tests during development.
    with contextlib.suppress(Exception):
        await connect_task
    await device_manager.disconnect_all()
    logger.info("IR/RF Hub backend shutting down")


def create_app() -> FastAPI:
    app = FastAPI(title="IR/RF Hub", version=__version__, lifespan=lifespan)

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

        The code here is the manual-pairing fallback -- the primary path
        is the companion integration finding the App on its own via
        _announce_pairing_until_paired()'s Supervisor Discovery push,
        which needs no code copied at all. See config_flow.py.
        """
        if await _is_paired():
            return PairingStatusResponse(paired=True, code=None)

        token = await _get_or_create_pairing_token()
        code = encode_pairing_code(host=_pairing_host(), port=_INTEGRATION_API_PORT, token=token)
        return PairingStatusResponse(paired=False, code=code)

    app.include_router(devices_router)
    app.include_router(commands_router)
    app.include_router(integration_router)
    app.include_router(recording_router)
    app.include_router(remote_database_router)
    app.include_router(ws_events_router)
    app.include_router(ws_recording_router)

    if _STATIC_DIR.exists():
        app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")
    else:
        logger.warning("Static frontend build not found at %s; SPA will not be served", _STATIC_DIR)

    return app


app = create_app()
