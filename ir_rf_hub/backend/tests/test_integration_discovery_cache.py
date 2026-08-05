from __future__ import annotations

import pytest

import ir_rf_hub.esphome.integration_discovery as integration_discovery
from ir_rf_hub.esphome.integration_discovery import get_reported_devices, set_reported_devices
from ir_rf_hub.schemas import DiscoveredDeviceSchema


@pytest.fixture(autouse=True)
def _reset():
    set_reported_devices([])
    yield
    set_reported_devices([])


def test_returns_nothing_before_anything_reported():
    assert get_reported_devices() == []


def test_returns_what_was_just_reported():
    devices = [DiscoveredDeviceSchema(name="esp1", host="10.0.0.5", port=6053)]
    set_reported_devices(devices)
    assert get_reported_devices() == devices


def test_expires_reports_older_than_the_staleness_window(monkeypatch: pytest.MonkeyPatch):
    # Patch the recorded timestamp directly rather than time.monotonic
    # itself -- that's the real, shared `time` module, and asyncio's own
    # event loop also calls time.monotonic() for scheduling.
    set_reported_devices([DiscoveredDeviceSchema(name="esp1", host="10.0.0.5", port=6053)])
    monkeypatch.setattr(integration_discovery, "_reported_at", integration_discovery._reported_at - 301)

    assert get_reported_devices() == []
