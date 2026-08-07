from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime, timedelta

import pytest

from ir_rf_hub.esphome import remote_database, remote_database_updater


@pytest.fixture(autouse=True)
def _clear_index_caches():
    # remote_database's lru_caches must not leak state between tests --
    # _isolated_data_dir already gives each test its own settings.data_dir,
    # but the in-process caches don't know that on their own.
    remote_database.invalidate_cache()
    yield
    remote_database.invalidate_cache()


def _write_meta(app_version: str, updated_at: datetime) -> None:
    cache_dir = remote_database.runtime_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "meta.json").write_text(
        json.dumps({"app_version": app_version, "updated_at": updated_at.isoformat()}), encoding="utf-8"
    )


def test_needs_refresh_true_when_no_meta_exists():
    assert remote_database_updater._needs_refresh() is True


def test_needs_refresh_false_when_recently_updated_same_version(monkeypatch: pytest.MonkeyPatch):
    # remote_database_updater captured its own `from ir_rf_hub import
    # __version__` reference at import time -- patching that local name
    # (not ir_rf_hub.__version__ itself) is what _needs_refresh() reads.
    monkeypatch.setattr(remote_database_updater, "__version__", "1.2.3")
    _write_meta("1.2.3", datetime.now(UTC))
    assert remote_database_updater._needs_refresh() is False


def test_needs_refresh_true_when_app_version_changed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(remote_database_updater, "__version__", "1.2.3")
    _write_meta("0.0.1-old", datetime.now(UTC))
    assert remote_database_updater._needs_refresh() is True


def test_needs_refresh_true_when_stale(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(remote_database_updater, "__version__", "1.2.3")
    _write_meta("1.2.3", datetime.now(UTC) - timedelta(days=30))
    assert remote_database_updater._needs_refresh() is True


async def test_refresh_writes_cache_and_invalidates_in_memory_index(monkeypatch: pytest.MonkeyPatch):
    fake_index = {"NEC|AA BB 00 00|CC DD 00 00": [{"category": "Fake", "brand": "Test", "model": "X", "button": "Go"}]}
    monkeypatch.setattr(remote_database_updater, "build_index", lambda work_dir, **kw: fake_index)

    ran = await remote_database_updater.refresh(force=True)
    assert ran is True

    cache_path = remote_database.runtime_cache_dir() / remote_database.RUNTIME_CACHE_FILENAME
    assert cache_path.exists()
    with gzip.open(cache_path) as f:
        assert json.load(f) == fake_index

    meta_path = remote_database.runtime_cache_dir() / "meta.json"
    assert meta_path.exists()

    # The already-imported remote_database module picks up the new cache
    # immediately (invalidate_cache()), not only after a restart.
    assert remote_database._load_index() == fake_index


async def test_refresh_skips_when_not_due(monkeypatch: pytest.MonkeyPatch):
    called = False

    def _fake_build(work_dir, **kw):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(remote_database_updater, "build_index", _fake_build)
    monkeypatch.setattr(remote_database_updater, "_needs_refresh", lambda: False)

    ran = await remote_database_updater.refresh()
    assert ran is False
    assert called is False


async def test_refresh_handles_a_failed_fetch_gracefully(monkeypatch: pytest.MonkeyPatch):
    def _boom(work_dir, **kw):
        raise RuntimeError("network unreachable")

    monkeypatch.setattr(remote_database_updater, "build_index", _boom)

    ran = await remote_database_updater.refresh(force=True)
    assert ran is False
    # No cache file left behind from a failed attempt.
    cache_path = remote_database.runtime_cache_dir() / remote_database.RUNTIME_CACHE_FILENAME
    assert not cache_path.exists()
