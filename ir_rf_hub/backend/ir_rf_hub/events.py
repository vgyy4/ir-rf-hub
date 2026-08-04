"""In-process pub/sub used to fan events out to every open /api/ws
connection (SPA tabs and the companion integration's WS client alike).
Deliberately just an asyncio broadcast, not a message broker -- this is a
single-process, single-worker app (see main.py), so there's no cross-process
delivery problem to solve.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Event:
    type: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_wire(self) -> dict[str, Any]:
        return {"type": self.type, "data": self.data}


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[Event]] = set()

    def subscribe(self) -> asyncio.Queue[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=256)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Event]) -> None:
        self._subscribers.discard(queue)

    def publish(self, event: Event) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Dropping event for a slow subscriber: %s", event.type)


event_bus = EventBus()
