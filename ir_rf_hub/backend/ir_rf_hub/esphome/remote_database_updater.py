"""Keeps the runtime database cache (see remote_database.py's module
docstring for the two-copy design) current: checked on startup, on every
App version bump, and periodically thereafter -- so the bundled snapshot
baked into a given App release doesn't just get more and more out of date
as new codes get added upstream between releases.

"Checked", not "always refetched": a bare restart doesn't force a real
network fetch unless the cache is missing, the App version changed since
the last successful refresh, or enough wall-clock time has passed (see
_MIN_REFRESH_INTERVAL_S) -- a crash-loop or someone restarting the App
repeatedly shouldn't hammer GitHub on every single one.

Only the two small IR sources (Flipper-IRDB, IRDB) are ever fetched here
-- the RF Sub-GHz source is deliberately excluded (see
remote_database_build.py's docstring: ~600MB, too large to re-fetch on a
schedule on typical add-on hardware). A runtime refresh therefore only
ever touches/improves IR coverage; RF stays whatever the bundled snapshot
shipped with until a maintainer rebuilds and ships a new release.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from ir_rf_hub import __version__
from ir_rf_hub.esphome.remote_database import RUNTIME_CACHE_FILENAME, invalidate_cache, runtime_cache_dir
from ir_rf_hub.esphome.remote_database_build import build_index

logger = logging.getLogger(__name__)

_META_FILENAME = "meta.json"
_PERIODIC_INTERVAL_S = 7 * 24 * 60 * 60  # weekly
_MIN_REFRESH_INTERVAL_S = 60 * 60  # don't refetch more than once an hour, even across restarts


def _meta_path() -> Path:
    return runtime_cache_dir() / _META_FILENAME


def _read_meta() -> dict | None:
    path = _meta_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _needs_refresh() -> bool:
    meta = _read_meta()
    if meta is None:
        return True  # never refreshed at runtime -- only the bundled snapshot exists (or nothing)
    if meta.get("app_version") != __version__:
        return True  # a new App release may have newer upstream data worth picking up sooner
    updated_at = meta.get("updated_at")
    if not isinstance(updated_at, str):
        return True
    try:
        last_refresh = datetime.fromisoformat(updated_at)
    except ValueError:
        return True
    return (datetime.now(UTC) - last_refresh).total_seconds() >= _MIN_REFRESH_INTERVAL_S


def _write_index_sync() -> None:
    """Runs in a worker thread (see refresh()) -- git clone and file I/O
    are all blocking calls, and a real fetch can take a while (it's
    network-bound)."""
    cache_dir = runtime_cache_dir()
    with tempfile.TemporaryDirectory() as tmp:
        index = build_index(Path(tmp), include_subghz=False)

    cache_dir.mkdir(parents=True, exist_ok=True)
    index_path = cache_dir / RUNTIME_CACHE_FILENAME
    tmp_path = index_path.with_suffix(".tmp")
    payload = json.dumps(index, separators=(",", ":"), sort_keys=True).encode("utf-8")
    with gzip.open(tmp_path, "wb") as f:
        f.write(payload)
    tmp_path.replace(index_path)  # atomic on the same filesystem -- readers never see a half-written index

    _meta_path().write_text(
        json.dumps({"app_version": __version__, "updated_at": datetime.now(UTC).isoformat()}), encoding="utf-8"
    )


async def refresh(*, force: bool = False) -> bool:
    """Returns True if a refresh actually ran -- False if skipped because
    it wasn't due yet. Never raises: a failed fetch (no network, GitHub
    unreachable, a stale git binary, ...) just means the existing runtime
    cache or bundled snapshot keeps serving lookups as before, logged but
    not fatal -- this is a best-effort naming aid, not core functionality.
    """
    if not force and not _needs_refresh():
        return False
    try:
        await asyncio.to_thread(_write_index_sync)
    except Exception:
        logger.warning("Remote database refresh failed -- keeping the existing cache/bundled snapshot", exc_info=True)
        return False
    invalidate_cache()
    logger.info("Remote database cache refreshed")
    return True


async def refresh_periodically() -> None:
    """Forever-loop background task (see main.py's lifespan for
    cancel-on-shutdown). The first iteration's refresh() call is what
    satisfies "check on startup"; every iteration after the sleep is the
    "periodically" part -- both go through the same _needs_refresh() rate
    limit, so this is safe to start unconditionally on every boot.
    """
    while True:
        await refresh()
        await asyncio.sleep(_PERIODIC_INTERVAL_S)
