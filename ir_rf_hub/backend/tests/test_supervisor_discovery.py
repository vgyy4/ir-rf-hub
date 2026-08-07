"""Unit tests for the Supervisor Discovery API announce call -- the
zero-code pairing path. Real Supervisor is obviously not available in
tests, so httpx.AsyncClient is swapped for a tiny recorder/failer instead
of hitting the network.
"""

from __future__ import annotations

import httpx
import pytest

import ir_rf_hub.supervisor_discovery as supervisor_discovery
from ir_rf_hub.supervisor_discovery import announce_pairing


class _RecordingClient:
    def __init__(self, **kwargs: object) -> None:
        self.requests: list[tuple[str, dict, dict]] = []

    async def __aenter__(self) -> _RecordingClient:
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        return False

    async def post(self, url: str, *, headers: dict, json: dict) -> httpx.Response:
        self.requests.append((url, headers, json))
        return httpx.Response(200, json={"uuid": "test-uuid"}, request=httpx.Request("POST", url))


class _FailingClient(_RecordingClient):
    async def post(self, url: str, *, headers: dict, json: dict) -> httpx.Response:
        raise httpx.ConnectError("no supervisor here", request=httpx.Request("POST", url))


def _recording_client_factory(created: list[_RecordingClient]):
    def factory(**kwargs: object) -> _RecordingClient:
        client = _RecordingClient(**kwargs)
        created.append(client)
        return client

    return factory


async def test_skips_entirely_outside_supervisor(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    created: list[_RecordingClient] = []
    monkeypatch.setattr(supervisor_discovery.httpx, "AsyncClient", _recording_client_factory(created))

    await announce_pairing(host="local-ir-rf-hub", port=8099, token="secret")

    assert created == []


async def test_posts_service_and_config_with_supervisor_bearer_token(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "sup3rvis0r-token")
    created: list[_RecordingClient] = []
    monkeypatch.setattr(supervisor_discovery.httpx, "AsyncClient", _recording_client_factory(created))

    await announce_pairing(host="local-ir-rf-hub", port=8099, token="secret")

    assert len(created) == 1
    [(url, headers, body)] = created[0].requests
    assert url == "http://supervisor/discovery"
    assert headers == {"Authorization": "Bearer sup3rvis0r-token"}
    assert body == {
        "service": "ir_rf_hub",
        "config": {"host": "local-ir-rf-hub", "port": 8099, "token": "secret"},
    }


async def test_swallows_connection_errors(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "token")
    monkeypatch.setattr(supervisor_discovery.httpx, "AsyncClient", lambda **kw: _FailingClient(**kw))

    await announce_pairing(host="h", port=1, token="t")  # must not raise
