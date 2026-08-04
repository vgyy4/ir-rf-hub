"""Shared disconnect-detection for server-push WebSocket routes.

Both /api/ws and /api/ws/recording/{id} only ever *send* to the client --
they never expect an incoming message. A route that only does
`await queue.get()` in a loop has no way to notice the client went away
while it's idle between bus events: nothing raises until the *next*
publish, which may never come, leaking the task (and its event_bus
subscription) for the lifetime of the process. Racing a receive() against
the queue get() is the standard fix -- receive() resolves the moment the
client disconnects, even with no bus traffic.
"""

from __future__ import annotations

import asyncio

from fastapi import WebSocket, WebSocketDisconnect


async def run_until_client_disconnects(websocket: WebSocket, on_event) -> None:
    """Runs `on_event()` in a loop, but returns as soon as the client
    disconnects -- even if `on_event` is currently blocked waiting for
    something else (e.g. queue.get()).
    """
    disconnect_task = asyncio.ensure_future(websocket.receive())
    try:
        while True:
            event_task = asyncio.ensure_future(on_event())
            done, _pending = await asyncio.wait(
                {disconnect_task, event_task}, return_when=asyncio.FIRST_COMPLETED
            )
            if disconnect_task in done:
                event_task.cancel()
                message = disconnect_task.result()
                if message.get("type") == "websocket.disconnect":
                    return
                # Client sent something we don't expect on a push-only
                # socket; keep listening for the real disconnect.
                disconnect_task = asyncio.ensure_future(websocket.receive())
                continue
            # event_task completed; disconnect_task keeps waiting for next time.
            event_task.result()
    except WebSocketDisconnect:
        pass
    finally:
        disconnect_task.cancel()
