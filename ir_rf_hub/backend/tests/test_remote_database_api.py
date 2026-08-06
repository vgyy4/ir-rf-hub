from __future__ import annotations

import httpx
import pytest

from ir_rf_hub.main import create_app


@pytest.fixture
async def client():
    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        async with app.router.lifespan_context(app):
            yield c


async def test_search_returns_fireable_results(client: httpx.AsyncClient):
    resp = await client.get("/api/remote-database/search", params={"q": "awa power"})
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) > 0
    match = next(r for r in results if r["brand"] == "AWA")
    assert match["model"] == "MSDV3268O5D0"
    assert match["button"] == "Power"
    assert match["raw_timings"][0] == 9000
    assert match["raw_timings"][1] == -4500
    assert match["carrier_frequency_hz"] == 38000
    assert match["repeat_count"] == 1


async def test_search_rejects_too_short_query(client: httpx.AsyncClient):
    resp = await client.get("/api/remote-database/search", params={"q": "a"})
    assert resp.status_code == 422


async def test_search_respects_limit(client: httpx.AsyncClient):
    resp = await client.get("/api/remote-database/search", params={"q": "power", "limit": 5})
    assert resp.status_code == 200
    assert len(resp.json()) == 5


async def test_search_no_results_for_nonsense_query(client: httpx.AsyncClient):
    resp = await client.get("/api/remote-database/search", params={"q": "zzzznonexistentqueryxyz"})
    assert resp.status_code == 200
    assert resp.json() == []


async def test_search_rf_returns_fireable_rf_results(client: httpx.AsyncClient):
    resp = await client.get("/api/remote-database/search", params={"q": "ceiling fan", "type": "rf"})
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) > 0
    # RF results are unmodulated -- 0 Hz carrier, unlike IR's 38000.
    assert all(r["carrier_frequency_hz"] == 0 for r in results)
    assert all(len(r["raw_timings"]) > 0 for r in results)


async def test_search_rejects_invalid_type(client: httpx.AsyncClient):
    resp = await client.get("/api/remote-database/search", params={"q": "power", "type": "bluetooth"})
    assert resp.status_code == 400
