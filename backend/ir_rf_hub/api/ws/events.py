"""General-purpose event fan-out: /api/ws. Every SPA tab and (from Phase 5
onward) the companion integration's WS client connect here to hear about
command.created/updated/deleted and device status changes. Just forwards
whatever's published on the in-process event_bus as JSON.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket

from ir_rf_hub.api.ws._util import run_until_client_disconnects
from ir_rf_hub.events import event_bus

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/api/ws")
async def ws_events(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = event_bus.subscribe()

    async def _forward_next() -> None:
        event = await queue.get()
        await websocket.send_json(event.to_wire())

    try:
        await run_until_client_disconnects(websocket, _forward_next)
    finally:
        event_bus.unsubscribe(queue)
