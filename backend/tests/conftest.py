from __future__ import annotations

from pathlib import Path

import pytest

from ir_rf_hub.config import settings
from ir_rf_hub.db.session import reset_engine_for_tests


@pytest.fixture(autouse=True)
async def _isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Every test gets its own /data dir, so the Fernet key and the SQLite
    file never leak between tests, and a fresh cached engine/session
    factory so it points at that new directory.

    Deliberately does NOT create the schema here: tests that exercise the
    FastAPI app (e.g. test_health.py) get their schema from the app's own
    lifespan running real Alembic migrations against settings.database_url
    -- that's the single source of truth for what the schema looks like,
    the same path production uses. Tests that need direct DB access without
    going through the app should create their own fixture that creates the
    schema explicitly (see Phase 1's device-session tests).
    """
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    await reset_engine_for_tests()
    yield
    await reset_engine_for_tests()
