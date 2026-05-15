from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class Subscriber:
    id: str
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue[dict[str, Any]]


_subscribers: dict[str, Subscriber] = {}
_lock = Lock()


def publish_event(event_type: str, payload: dict[str, Any] | None = None) -> None:
    event = {
        "type": event_type,
        "payload": payload or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with _lock:
        subscribers = list(_subscribers.values())
    for subscriber in subscribers:
        try:
            subscriber.loop.call_soon_threadsafe(_enqueue_event, subscriber, event)
        except RuntimeError:
            unsubscribe(subscriber.id)


def subscribe(max_queue_size: int = 100) -> Subscriber:
    subscriber = Subscriber(
        id=uuid4().hex,
        loop=asyncio.get_running_loop(),
        queue=asyncio.Queue(maxsize=max_queue_size),
    )
    with _lock:
        _subscribers[subscriber.id] = subscriber
    return subscriber


def unsubscribe(subscriber_id: str) -> None:
    with _lock:
        _subscribers.pop(subscriber_id, None)


def _enqueue_event(subscriber: Subscriber, event: dict[str, Any]) -> None:
    if subscriber.queue.full():
        try:
            subscriber.queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
    subscriber.queue.put_nowait(event)
