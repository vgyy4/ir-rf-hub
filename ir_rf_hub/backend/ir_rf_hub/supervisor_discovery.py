"""Announces the App to the companion integration via Home Assistant
Supervisor's Discovery API, so pairing needs no code to copy/paste in the
common case (running as a Supervisor-managed App). POSTing
{service: <integration domain>, config: {...}} to http://supervisor/discovery
makes Home Assistant Core route the config straight into that integration's
config_flow via async_step_hassio -- see the companion integration's
config_flow.py. Mirrors the mechanism Music Assistant's own App+integration
pair uses for the identical problem.

Deliberately does not need host_network (unlike real mDNS/zeroconf): this
is a plain Supervisor API call, reachable over the isolated internal
network config.yaml already keeps the App on. See ARCHITECTURE.md's
Pairing section.

A no-op outside Supervisor (SUPERVISOR_TOKEN unset) -- local dev / a
plain `docker run` never gets this, and falls back to the App's own
displayed pairing code, unaffected by any of this.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

_SUPERVISOR_DISCOVERY_URL = "http://supervisor/discovery"
# Must equal the companion integration's manifest.json "domain" -- that's
# how Home Assistant Core decides whose config_flow.async_step_hassio to
# route this to.
_DISCOVERY_SERVICE = "ir_rf_hub"


async def announce_pairing(*, host: str, port: int, token: str) -> None:
    supervisor_token = os.environ.get("SUPERVISOR_TOKEN")
    if not supervisor_token:
        logger.debug("SUPERVISOR_TOKEN not set -- not running under Supervisor, skipping discovery announce")
        return

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                _SUPERVISOR_DISCOVERY_URL,
                headers={"Authorization": f"Bearer {supervisor_token}"},
                json={"service": _DISCOVERY_SERVICE, "config": {"host": host, "port": port, "token": token}},
            )
            response.raise_for_status()
    except httpx.HTTPError:
        logger.warning("Failed to announce pairing info to Supervisor", exc_info=True)
