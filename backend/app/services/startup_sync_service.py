from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import func, select

from app.config import settings
from app.database import SessionLocal
from app.models import Watchlist
from app.services.analysis_service import analyze_watchlist
from app.services.event_bus import publish_event
from app.services.ingest_service import record_collection_job
from app.services.news_collector_service import NewsCollector
from app.services.real_collector_service import AkshareCollector, ensure_default_watchlist
from app.services.watch_stock_sync_service import run_pending_watch_stock_syncs


_task: asyncio.Task[None] | None = None
_state: dict[str, Any] = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "summary": None,
}


def start_startup_sync() -> bool:
    global _task
    if not settings.startup_sync_enabled:
        return False
    if _task is not None and not _task.done():
        return False
    _task = asyncio.create_task(_run_startup_sync(), name="startup-sync")
    return True


async def stop_startup_sync() -> None:
    global _task
    if _task is not None and not _task.done():
        _task.cancel()
        with suppress(asyncio.CancelledError):
            await _task
    _task = None


def startup_sync_status() -> dict[str, Any]:
    return dict(_state)


async def _run_startup_sync() -> None:
    try:
        await asyncio.to_thread(run_startup_sync_once)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        _state.update(
            {
                "running": False,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "summary": {"status": "failed", "error": str(exc)},
            }
        )


def run_startup_sync_once() -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    _state.update({"running": True, "started_at": started_at.isoformat(), "finished_at": None, "summary": None})
    summary: dict[str, Any] = {}

    collector = AkshareCollector()
    _run_step(summary, "watchlist", settings.startup_sync_watchlist_enabled, lambda: _with_db(_ensure_watchlist_seeded))
    _run_step(summary, "pending_watch_stock_syncs", True, run_pending_watch_stock_syncs)
    _run_step(summary, "market", settings.startup_sync_market_enabled, lambda: _with_db(collector.collect_market_snapshot))
    _run_step(summary, "history", settings.startup_sync_history_enabled, lambda: _with_db(lambda db: collector.collect_history(db, days=settings.startup_sync_history_days)))
    _run_step(
        summary,
        "intraday",
        settings.startup_sync_intraday_enabled,
        lambda: _with_db(
            lambda db: collector.collect_intraday(
                db,
                trading_days=settings.startup_sync_intraday_trading_days,
                period_minutes=settings.startup_sync_intraday_period_minutes,
            )
        ),
    )
    _run_step(summary, "news", settings.startup_sync_news_enabled, lambda: _with_db(lambda db: NewsCollector().collect(db, limit=settings.news_auto_sync_limit)))
    _run_step(summary, "analysis", settings.startup_sync_analysis_enabled, lambda: _with_db(lambda db: {"analyzed": len(analyze_watchlist(db))}))
    _run_step(
        summary,
        "full_market_history",
        settings.startup_sync_full_market_history_enabled,
        lambda: _with_db(
            lambda db: collector.collect_full_market_history(
                db,
                days=settings.startup_sync_full_market_history_days,
                batch_size=settings.startup_sync_full_market_history_batch_size,
                limit=settings.startup_sync_full_market_history_limit,
            )
        ),
    )

    failed = [name for name, result in summary.items() if result.get("status") == "failed"]
    status = "success" if not failed else "partial_failed"
    finished_at = datetime.now(timezone.utc)
    overall = {
        "status": status,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "steps": summary,
        "failed_steps": failed,
    }
    _record_startup_sync_job(overall)
    _state.update({"running": False, "finished_at": finished_at.isoformat(), "summary": overall})
    publish_event("jobs.updated", {"job_type": "startup_sync", "status": status})
    return overall


def _run_step(summary: dict[str, Any], name: str, enabled: bool, action: Callable[[], dict[str, Any]]) -> None:
    if not enabled:
        summary[name] = {"status": "skipped", "reason": "disabled"}
        return
    try:
        summary[name] = {"status": "success", "result": action()}
    except Exception as exc:
        summary[name] = {"status": "failed", "error": str(exc)}


def _with_db(action: Callable[[Any], dict[str, Any]]) -> dict[str, Any]:
    with SessionLocal() as db:
        return action(db)


def _ensure_watchlist_seeded(db: Any) -> dict[str, Any]:
    existing_count = db.execute(select(func.count()).select_from(Watchlist)).scalar_one()
    if existing_count:
        return {"existing": existing_count, "inserted": 0}
    return ensure_default_watchlist(db)


def _record_startup_sync_job(summary: dict[str, Any]) -> None:
    with SessionLocal() as db:
        record_collection_job(
            db,
            "startup_sync",
            "backend",
            summary["status"],
            {
                "failed_steps": len(summary["failed_steps"]),
                "steps": {name: result["status"] for name, result in summary["steps"].items()},
            },
            {
                "history_days": settings.startup_sync_history_days,
                "intraday_trading_days": settings.startup_sync_intraday_trading_days,
                "intraday_period_minutes": settings.startup_sync_intraday_period_minutes,
                "full_market_history_enabled": settings.startup_sync_full_market_history_enabled,
            },
            "; ".join(summary["failed_steps"]) if summary["failed_steps"] else None,
        )
        db.commit()
