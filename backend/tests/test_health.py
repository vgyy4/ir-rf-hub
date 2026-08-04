from __future__ import annotations

import httpx
import pytest

from ir_rf_hub.main import create_app


@pytest.fixture
async def client():
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        async with app.router.lifespan_context(app):
            yield c


async def test_health(client: httpx.AsyncClient):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_pairing_code_is_stable_across_calls(client: httpx.AsyncClient):
    first = await client.get("/api/integration/pairing-code")
    second = await client.get("/api/integration/pairing-code")
    assert first.status_code == 200
    assert first.json()["code"] == second.json()["code"]
