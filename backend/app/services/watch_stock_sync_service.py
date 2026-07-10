from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import CollectionJob
from app.services.analysis_service import analyze_stock
from app.services.event_bus import publish_event
from app.services.real_collector_service import AkshareCollector


WATCH_STOCK_SYNC_JOB = "watch_stock_sync"
RESUMABLE_STATUSES = {"pending", "running", "partial_failed"}
_run_lock = Lock()


def enqueue_watch_stock_sync(db: Session, code: str, reason: str = "watchlist_add") -> CollectionJob:
    normalized_code = code.strip().upper()
    existing = _find_existing_resumable_job(db, normalized_code)
    if existing is not None:
        return existing
    now = datetime.now(timezone.utc)
    job = CollectionJob(
        job_type=WATCH_STOCK_SYNC_JOB,
        status="pending",
        source="backend",
        requested_payload={"code": normalized_code, "reason": reason},
        result_summary={},
        started_at=now,
        finished_at=None,
    )
    db.add(job)
    db.flush()
    publish_event("jobs.updated", {"job_type": WATCH_STOCK_SYNC_JOB, "status": "pending", "code": normalized_code})
    return job


def run_pending_watch_stock_syncs(limit: int = 20) -> dict[str, Any]:
    with SessionLocal() as db:
        rows = (
            db.execute(
                select(CollectionJob)
                .where(CollectionJob.job_type == WATCH_STOCK_SYNC_JOB, CollectionJob.status.in_(RESUMABLE_STATUSES))
                .order_by(CollectionJob.id)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        job_ids = [row.id for row in rows]
    results = [run_watch_stock_sync_job(job_id) for job_id in job_ids]
    return {"processed": len(results), "jobs": results}


def run_watch_stock_sync_job(job_id: int) -> dict[str, Any]:
    _run_lock.acquire()
    code = ""
    reason = ""
    try:
        with SessionLocal() as db:
            job = db.get(CollectionJob, job_id)
            if job is None:
                return {"job_id": job_id, "status": "missing"}
            payload = job.requested_payload or {}
            code = str(payload.get("code") or "").strip().upper()
            reason = str(payload.get("reason") or "")
            if job.status not in RESUMABLE_STATUSES:
                return {"job_id": job_id, "code": code, "status": job.status, "reason": "already_finished"}
            if not code:
                _finish_job(db, job, "failed", {"error": "missing code"}, "missing code")
                return {"job_id": job_id, "status": "failed", "error": "missing code"}
            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            job.finished_at = None
            db.commit()

        summary = sync_watch_stock_data(code)
        failed_steps = [name for name, result in summary.items() if result.get("status") == "failed"]
        status = "success" if not failed_steps else "partial_failed"
        error_message = "; ".join(failed_steps) if failed_steps else None
        with SessionLocal() as db:
            job = db.get(CollectionJob, job_id)
            if job is not None:
                _finish_job(db, job, status, {"code": code, "steps": summary, "failed_steps": failed_steps}, error_message)
        publish_event("watchlist.updated", {"code": code, "action": "synced", "status": status})
        _publish_paper_watchlist_sync_event(code, reason, status, job_id, failed_steps=failed_steps)
        publish_event("jobs.updated", {"job_type": WATCH_STOCK_SYNC_JOB, "status": status, "code": code})
        return {"job_id": job_id, "code": code, "status": status, "failed_steps": failed_steps}
    except Exception as exc:
        with SessionLocal() as db:
            job = db.get(CollectionJob, job_id)
            if job is not None:
                payload = job.requested_payload or {}
                code = code or str(payload.get("code") or "").strip().upper()
                reason = reason or str(payload.get("reason") or "")
                _finish_job(db, job, "failed", {"error": str(exc)}, str(exc))
        _publish_paper_watchlist_sync_event(code, reason, "failed", job_id, error=str(exc))
        publish_event("jobs.updated", {"job_type": WATCH_STOCK_SYNC_JOB, "status": "failed", "job_id": job_id})
        return {"job_id": job_id, "status": "failed", "error": str(exc)}
    finally:
        _run_lock.release()


def sync_watch_stock_data(code: str) -> dict[str, Any]:
    collector = AkshareCollector()
    summary: dict[str, Any] = {}
    _run_step(summary, "market_snapshot", lambda: _with_db(lambda db: collector.collect_stock_snapshot(db, code)))
    _run_step(summary, "daily_kline", lambda: _with_db(lambda db: collector.collect_stock_history(db, code, days=settings.startup_sync_history_days)))
    _run_step(summary, "intraday_1m", lambda: _with_db(lambda db: collector.collect_stock_intraday(db, code, trading_days=1, period_minutes=1)))
    _run_step(
        summary,
        "intraday_watch_period",
        lambda: _with_db(
            lambda db: collector.collect_stock_intraday(
                db,
                code,
                trading_days=settings.startup_sync_intraday_trading_days,
                period_minutes=settings.startup_sync_intraday_period_minutes,
            )
        ),
    )
    _run_step(summary, "analysis", lambda: _with_db(lambda db: _analysis_summary(db, code)))
    return summary


def _find_existing_resumable_job(db: Session, code: str) -> CollectionJob | None:
    rows = (
        db.execute(
            select(CollectionJob)
            .where(CollectionJob.job_type == WATCH_STOCK_SYNC_JOB, CollectionJob.status.in_(RESUMABLE_STATUSES))
            .order_by(CollectionJob.id.desc())
            .limit(50)
        )
        .scalars()
        .all()
    )
    for row in rows:
        if str((row.requested_payload or {}).get("code") or "").upper() == code:
            return row
    return None


def _run_step(summary: dict[str, Any], name: str, action: Callable[[], dict[str, Any]]) -> None:
    try:
        summary[name] = {"status": "success", "result": action()}
    except Exception as exc:
        summary[name] = {"status": "failed", "error": str(exc)}


def _with_db(action: Callable[[Session], dict[str, Any]]) -> dict[str, Any]:
    with SessionLocal() as db:
        return action(db)


def _analysis_summary(db: Session, code: str) -> dict[str, Any]:
    advice = analyze_stock(db, code)
    return {"advice_id": advice.id, "signal": advice.signal, "confidence": float(advice.confidence)}


def _publish_paper_watchlist_sync_event(
    code: str,
    reason: str,
    status: str,
    job_id: int,
    failed_steps: list[str] | None = None,
    error: str | None = None,
) -> None:
    if not reason.startswith("paper_watchlist"):
        return
    payload: dict[str, Any] = {"code": code, "action": "synced", "status": status, "sync_job_id": job_id}
    if failed_steps:
        payload["failed_steps"] = failed_steps
    if error:
        payload["error"] = error
    publish_event("paper_watchlist.updated", payload)


def _finish_job(db: Session, job: CollectionJob, status: str, summary: dict[str, Any], error_message: str | None) -> None:
    job.status = status
    job.result_summary = summary
    job.error_message = error_message
    job.finished_at = datetime.now(timezone.utc)
    db.commit()
