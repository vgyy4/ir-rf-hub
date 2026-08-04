"""Scoped live capture stream: /api/ws/recording/{session_id}. Separate from
the general /api/ws fan-out because this is high-frequency and per-session,
not something every tab needs. Each ir_rf_proxy raw receive event arrives
as one complete mark/space timings array (not a byte-by-byte stream -- see
device_session.py), so each message here is one full capture, not one
sample.

Session end (stop/clear/discard) is driven by the initiating tab's own
REST calls, whose responses already carry the result -- this socket only
needs to push new captures as they arrive while the modal is open.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket

from ir_rf_hub.api.ws._util import run_until_client_disconnects
from ir_rf_hub.events import event_bus

router = APIRouter()


@router.websocket("/api/ws/recording/{session_id}")
async def ws_recording(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    queue = event_bus.subscribe()
    seq = 0

    async def _forward_next() -> None:
        nonlocal seq
        while True:
            event = await queue.get()
            if event.type == "recording.capture" and event.data.get("session_id") == session_id:
                seq += 1
                await websocket.send_json({"type": "capture", "seq": seq, "timings": event.data["timings"]})
                return

    try:
        await run_until_client_disconnects(websocket, _forward_next)
    finally:
        event_bus.unsubscribe(queue)
