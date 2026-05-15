from __future__ import annotations

import asyncio
from contextlib import suppress

from app.config import settings
from app.database import SessionLocal
from app.services.news_collector_service import NewsCollector
from app.services.news_llm_config_service import get_effective_news_llm_config


_task: asyncio.Task[None] | None = None
_stop_event: asyncio.Event | None = None
_simplify_event: asyncio.Event | None = None


def start_news_auto_sync() -> None:
    global _task, _stop_event, _simplify_event
    if not settings.news_auto_sync_enabled or settings.news_auto_sync_interval_seconds <= 0:
        return
    if _task is not None and not _task.done():
        return
    _stop_event = asyncio.Event()
    _simplify_event = asyncio.Event()
    _task = asyncio.create_task(_run_loop(), name="news-auto-sync")


async def stop_news_auto_sync() -> None:
    global _task
    if _stop_event is not None:
        _stop_event.set()
    if _task is not None:
        _task.cancel()
        with suppress(asyncio.CancelledError):
            await _task
    _task = None


def trigger_news_simplification() -> bool:
    if _simplify_event is None:
        return False
    _simplify_event.set()
    return True


async def _run_loop() -> None:
    assert _stop_event is not None
    assert _simplify_event is not None
    while not _stop_event.is_set():
        await asyncio.to_thread(run_news_auto_sync_once)
        try:
            await asyncio.wait_for(_simplify_event.wait(), timeout=settings.news_auto_sync_interval_seconds)
        except TimeoutError:
            continue
        _simplify_event.clear()
        await asyncio.to_thread(run_pending_simplification_once)


def run_news_auto_sync_once() -> dict[str, object]:
    with SessionLocal() as db:
        return NewsCollector().collect(db, limit=settings.news_auto_sync_limit)


def run_pending_simplification_once() -> dict[str, object]:
    with SessionLocal() as db:
        config = get_effective_news_llm_config(db)
        if not config.api_key_configured:
            return {"processed": 0, "simplified": 0, "failed": 0, "skipped": 0, "reason": "NEWS_LLM_API_KEY is not configured"}
        return NewsCollector().simplify_pending(db, limit=settings.news_auto_simplify_limit)
