"""Tests the /api/pairing-status flow the SPA's blocking first-run gate
polls: unpaired shows a code, the first successful /api/integration/*
auth flips it to paired permanently, and the code stops being handed out
once paired.
"""

from __future__ import annotations

import httpx
import pytest

from ir_rf_hub.main import create_app
from ir_rf_hub.security import decode_pairing_code


@pytest.fixture
async def client():
    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        async with app.router.lifespan_context(app):
            yield c


async def test_starts_unpaired_with_a_valid_code(client: httpx.AsyncClient):
    resp = await client.get("/api/pairing-status")
    body = resp.json()
    assert body["paired"] is False
    assert body["code"] is not None
    # the code must actually decode to something usable
    decoded = decode_pairing_code(body["code"])
    assert decoded["port"] == 8099


async def test_code_is_stable_across_polls_while_unpaired(client: httpx.AsyncClient):
    first = (await client.get("/api/pairing-status")).json()
    second = (await client.get("/api/pairing-status")).json()
    assert first["code"] == second["code"]


async def test_successful_integration_auth_flips_paired_permanently(client: httpx.AsyncClient):
    status = (await client.get("/api/pairing-status")).json()
    token = decode_pairing_code(status["code"])["token"]

    # not paired yet -- no integration call has happened
    assert (await client.get("/api/pairing-status")).json()["paired"] is False

    health = await client.get("/api/integration/health", headers={"Authorization": f"Bearer {token}"})
    assert health.status_code == 200

    after = (await client.get("/api/pairing-status")).json()
    assert after["paired"] is True
    assert after["code"] is None


async def test_wrong_token_does_not_flip_paired(client: httpx.AsyncClient):
    await client.get("/api/integration/health", headers={"Authorization": "Bearer garbage"})
    assert (await client.get("/api/pairing-status")).json()["paired"] is False
