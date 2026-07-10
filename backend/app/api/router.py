from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, time, timezone
from decimal import Decimal
from threading import Lock
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db
from app.models import CollectionJob, KlineDaily, KlineIntraday, MarketSnapshot, News, Notification, PaperWatchlist, Stock, TradingAdvice, WatchSnapshot, Watchlist
from app.schemas import AddWatchRequest, NewsLlmConfigRequest, PaperAccountRequest, PaperAdminAccountUpdateRequest, PaperAdminLoginRequest, PaperCaptchaRequest, PaperLoginRequest, PaperOrderRequest, UpdateWatchRequest
from app.services.analysis_service import DISCLAIMER, analyze_stock, analyze_watchlist
from app.services.event_bus import publish_event, subscribe, unsubscribe
from app.services.ingest_service import normalize_code, record_collection_job
from app.services.news_auto_sync_service import trigger_news_simplification
from app.services.news_llm_config_service import news_llm_config_dict, save_news_llm_config, validate_news_llm_config_status
from app.services.paper_trading_service import (
    admin_get_account,
    admin_update_account_status,
    admin_from_token,
    account_from_token,
    account_dict,
    cancel_order,
    clear_all_accounts,
    create_account,
    create_account_captcha,
    list_accounts,
    list_cash_flows,
    list_orders,
    list_positions,
    list_trades,
    login_admin,
    login_account,
    paper_equity,
    paper_admin_overview,
    paper_quote,
    performance_by_stock,
    performance_calendar,
    performance_summary,
    place_order,
    portfolio_summary,
    record_risk_notification,
    reset_account,
    revoke_admin_session,
    revoke_session,
    run_matching,
)
from app.services.news_collector_service import NewsCollector
from app.services.real_collector_service import AkshareCollector, DEFAULT_WATCHLIST
from app.services.serializers import advice_dict, intraday_kline_dict, job_dict, kline_dict, news_dict, notification_dict, paper_watchlist_dict, snapshot_dict, stock_dict, watchlist_dict
from app.services.startup_sync_service import startup_sync_status
from app.services.watch_stock_sync_service import enqueue_watch_stock_sync, run_watch_stock_sync_job


router = APIRouter(prefix="/api/v1")
_full_market_history_lock = Lock()
_missing_daily_kline_lock = Lock()


def _paper_account(authorization: str | None = Header(None), db: Session = Depends(get_db)):
    return account_from_token(db, _paper_token(authorization))


def _paper_token(authorization: str | None = Header(None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="请先登录模拟交易账户")
    return authorization.split(" ", 1)[1].strip()


def _paper_admin(token: str = Depends(_paper_token)):
    return admin_from_token(token)


@router.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat(), "env": settings.app_env}


@router.get("/events")
async def events(request: Request) -> StreamingResponse:
    async def stream():
        subscriber = subscribe()
        try:
            yield _sse({"type": "connected", "payload": {}, "timestamp": datetime.now(timezone.utc).isoformat()})
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(subscriber.queue.get(), timeout=25)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield _sse(event)
        finally:
            unsubscribe(subscriber.id)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)) -> dict[str, Any]:
    news_config = news_llm_config_dict(db)
    return {
        "app_env": settings.app_env,
        "database": "sqlite" if settings.database_url.startswith("sqlite") else "postgresql",
        "auto_seed_demo_data": settings.auto_seed_demo_data,
        "market_data_primary": settings.market_data_primary,
        "default_watchlist": DEFAULT_WATCHLIST,
        "collector_intervals": {"market_snapshot_seconds": settings.market_snapshot_interval_seconds, "watch_snapshot_seconds": settings.watch_snapshot_interval_seconds, "news_seconds": settings.news_interval_seconds, "news_auto_sync_seconds": settings.news_auto_sync_interval_seconds, "advice_seconds": settings.advice_interval_seconds},
        "risk_control": {"request_min_interval_seconds": settings.request_min_interval_seconds, "fetch_failure_downgrade_threshold": settings.fetch_failure_downgrade_threshold, "max_watchlist_size": settings.max_watchlist_size},
        "startup_sync": {
            "enabled": settings.startup_sync_enabled,
            "watchlist": settings.startup_sync_watchlist_enabled,
            "market": settings.startup_sync_market_enabled,
            "history": {"enabled": settings.startup_sync_history_enabled, "days": settings.startup_sync_history_days},
            "intraday": {"enabled": settings.startup_sync_intraday_enabled, "trading_days": settings.startup_sync_intraday_trading_days, "period_minutes": settings.startup_sync_intraday_period_minutes},
            "news": settings.startup_sync_news_enabled,
            "analysis": settings.startup_sync_analysis_enabled,
            "full_market_history": {
                "enabled": settings.startup_sync_full_market_history_enabled,
                "days": settings.startup_sync_full_market_history_days,
                "batch_size": settings.startup_sync_full_market_history_batch_size,
                "limit": settings.startup_sync_full_market_history_limit,
            },
            "status": startup_sync_status(),
        },
        "news": {
            "source": "newsnow",
            "llm_provider": news_config["provider"],
            "api_base_url": news_config["api_base_url"],
            "api_key_configured": news_config["api_key_configured"],
            "model": news_config["model"],
            "prompt_preset": news_config["prompt_preset"],
            "custom_prompt_configured": news_config["custom_prompt_configured"],
            "auto_sync_enabled": settings.news_auto_sync_enabled,
            "auto_sync_interval_seconds": settings.news_auto_sync_interval_seconds,
            "llm_timeout_seconds": settings.news_llm_timeout_seconds,
            "llm_max_concurrency": settings.news_llm_max_concurrency,
        },
        "qqbot": {
            "target": settings.qqbot_target,
            "webhook_configured": bool(settings.qqbot_webhook_url),
            "price_alert": settings.qqbot_enable_price_alert,
            "strategy_alert": settings.qqbot_enable_strategy_alert,
            "news_digest": settings.qqbot_enable_news_digest,
            "daily_summary": settings.qqbot_enable_daily_summary,
            "job_failed_alert": settings.qqbot_enable_job_failed_alert,
            "batch_size": settings.qqbot_batch_size,
            "max_retry": settings.qqbot_max_retry,
        },
        "push_message": {"enabled": settings.push_message_enabled, "dir": settings.push_message_dir},
        "analysis_engine": settings.analysis_engine,
        "disclaimer": DISCLAIMER,
    }


@router.get("/news-llm-config")
def get_news_llm_config(db: Session = Depends(get_db)) -> dict[str, Any]:
    return news_llm_config_dict(db)


@router.put("/news-llm-config")
def update_news_llm_config(request: NewsLlmConfigRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    save_news_llm_config(db, request.model_dump())
    config = news_llm_config_dict(db)
    publish_event("settings.updated", {"section": "news_llm_config"})
    if config["api_key_configured"]:
        config["simplification_triggered"] = trigger_news_simplification()
    return config


@router.post("/news-llm-config/validate")
def validate_news_llm_config(db: Session = Depends(get_db)) -> dict[str, Any]:
    return validate_news_llm_config_status(db)


@router.post("/paper/accounts")
def create_paper_account(request: PaperAccountRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    return create_account(db, request.owner_name, request.password, request.phone, request.captcha_id, request.captcha_code)


@router.post("/paper/account-captchas")
def create_paper_account_captcha(request: PaperCaptchaRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    return create_account_captcha(db, request.phone)


@router.get("/paper/accounts")
def list_paper_accounts(db: Session = Depends(get_db)) -> dict[str, Any]:
    return list_accounts(db)


@router.post("/paper/sessions")
def create_paper_session(request: PaperLoginRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    return login_account(db, request.owner_name, request.password)


@router.delete("/paper/sessions/current")
def delete_paper_session(token: str = Depends(_paper_token), db: Session = Depends(get_db)) -> dict[str, str]:
    return revoke_session(db, token)


@router.post("/paper/admin/sessions")
def create_paper_admin_session(request: PaperAdminLoginRequest) -> dict[str, Any]:
    return login_admin(request.username, request.password)


@router.delete("/paper/admin/sessions/current")
def delete_paper_admin_session(token: str = Depends(_paper_token)) -> dict[str, str]:
    return revoke_admin_session(token)


@router.get("/paper/admin/overview")
def get_paper_admin_overview(
    account_id: int | None = Query(None, ge=1),
    flow_type: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    _admin=Depends(_paper_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return paper_admin_overview(db, account_id=account_id, flow_type=flow_type, page=page, page_size=page_size)


@router.patch("/paper/admin/accounts/{account_id}")
def update_paper_admin_account(
    account_id: int,
    request: PaperAdminAccountUpdateRequest,
    _admin=Depends(_paper_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    account = admin_update_account_status(db, account_id, request.status)
    publish_event("paper_admin.account.updated", {"account_id": account_id, "status": request.status})
    return account


@router.post("/paper/admin/accounts/{account_id}/reset")
def reset_paper_admin_account(account_id: int, _admin=Depends(_paper_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    account = admin_get_account(db, account_id)
    summary = reset_account(db, account)
    publish_event("paper_account.reset", {"account_id": account_id, "source": "admin"})
    return summary


@router.delete("/paper/admin/accounts")
def delete_all_paper_accounts(_admin=Depends(_paper_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    result = clear_all_accounts(db)
    publish_event("paper_accounts.cleared", result["deleted"])
    return result


@router.get("/paper/account")
def get_paper_account(account=Depends(_paper_account)) -> dict[str, Any]:
    return account_dict(account)


@router.get("/paper/summary")
def get_paper_summary(account=Depends(_paper_account), db: Session = Depends(get_db)) -> dict[str, Any]:
    return portfolio_summary(db, account)


@router.get("/paper/performance/summary")
def get_paper_performance_summary(account=Depends(_paper_account), db: Session = Depends(get_db)) -> dict[str, Any]:
    return performance_summary(db, account)


@router.get("/paper/performance/by-stock")
def get_paper_performance_by_stock(account=Depends(_paper_account), db: Session = Depends(get_db)) -> dict[str, Any]:
    return performance_by_stock(db, account)


@router.get("/paper/performance/calendar")
def get_paper_performance_calendar(limit: int = Query(30, ge=1, le=365), account=Depends(_paper_account), db: Session = Depends(get_db)) -> dict[str, Any]:
    return performance_calendar(db, account, limit)


@router.get("/paper/equity")
def get_paper_equity(account=Depends(_paper_account), db: Session = Depends(get_db)) -> dict[str, Any]:
    return paper_equity(db, account)


@router.get("/paper/quote")
def get_paper_quote(code: str = Query(..., min_length=1), account=Depends(_paper_account), db: Session = Depends(get_db)) -> dict[str, Any]:
    return paper_quote(db, code)


@router.post("/paper/account/reset")
def reset_paper_account(account=Depends(_paper_account), db: Session = Depends(get_db)) -> dict[str, Any]:
    summary = reset_account(db, account)
    publish_event("paper_account.reset", {"account_id": account.id})
    return summary


@router.get("/paper/positions")
def get_paper_positions(account=Depends(_paper_account), db: Session = Depends(get_db)) -> dict[str, Any]:
    return list_positions(db, account)


@router.post("/paper/orders")
def create_paper_order(request: PaperOrderRequest, account=Depends(_paper_account), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        order = place_order(db, account, request.code, request.side, request.order_type, request.quantity, request.limit_price, request.trigger_price)
    except HTTPException as exc:
        db.rollback()
        record_risk_notification(db, account, request.code, request.side, request.order_type, request.quantity, str(exc.detail))
        raise
    publish_event("paper_trade.filled" if order["status"] == "filled" else "paper_order.updated", {"order_id": order["id"], "code": order["code"], "status": order["status"]})
    return order


@router.get("/paper/orders")
def get_paper_orders(
    code: str | None = None,
    side: str | None = None,
    order_type: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    account=Depends(_paper_account),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return list_orders(db, account, code=code, side=side, order_type=order_type, status=status, page=page, page_size=page_size)


@router.post("/paper/orders/{order_id}/cancel")
def cancel_paper_order(order_id: int, account=Depends(_paper_account), db: Session = Depends(get_db)) -> dict[str, Any]:
    order = cancel_order(db, account, order_id)
    publish_event("paper_order.updated", {"order_id": order["id"], "code": order["code"], "status": order["status"]})
    return order


@router.get("/paper/trades")
def get_paper_trades(account=Depends(_paper_account), db: Session = Depends(get_db)) -> dict[str, Any]:
    return list_trades(db, account)


@router.get("/paper/cash-flows")
def get_paper_cash_flows(
    flow_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    account=Depends(_paper_account),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    start_at = datetime.combine(date_from, time.min, tzinfo=timezone.utc) if date_from else None
    end_at = datetime.combine(date_to, time.max, tzinfo=timezone.utc) if date_to else None
    return list_cash_flows(db, account, flow_type=flow_type, date_from=start_at, date_to=end_at, page=page, page_size=page_size)


@router.post("/paper/match/run")
def run_paper_matching(account=Depends(_paper_account), db: Session = Depends(get_db)) -> dict[str, Any]:
    result = run_matching(db, account)
    if result["filled"] or result["triggered"]:
        publish_event("paper_order.updated", {"account_id": account.id, **result})
    return result


@router.get("/paper/watchlist")
def get_paper_watchlist(account=Depends(_paper_account), db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.execute(
        select(PaperWatchlist)
        .join(Stock, PaperWatchlist.stock_id == Stock.id)
        .where(PaperWatchlist.account_id == account.id)
        .order_by(PaperWatchlist.display_order, Stock.code)
    ).scalars().all()
    items = []
    for row in rows:
        snapshot = _latest_snapshot(db, row.stock_id)
        advice = _latest_advice(db, row.stock_id)
        items.append(paper_watchlist_dict(row, snapshot_dict(snapshot, row.stock) if snapshot else None, advice_dict(advice, row.stock) if advice else None))
    return {"items": items, "total": len(items), "max_size": settings.max_watchlist_size}


@router.post("/paper/watchlist")
def add_paper_watch(request: AddWatchRequest, background_tasks: BackgroundTasks, account=Depends(_paper_account), db: Session = Depends(get_db)) -> dict[str, Any]:
    current_count = db.execute(select(func.count()).select_from(PaperWatchlist).where(PaperWatchlist.account_id == account.id)).scalar_one()
    if current_count >= settings.max_watchlist_size:
        raise HTTPException(status_code=400, detail="模拟账户自选股已达上限")
    stock = _resolve_stock_for_watch(db, request.code)
    existing = db.execute(select(PaperWatchlist).where(PaperWatchlist.account_id == account.id, PaperWatchlist.stock_id == stock.id)).scalar_one_or_none()
    if existing is not None:
        snapshot = _latest_snapshot(db, existing.stock_id)
        advice = _latest_advice(db, existing.stock_id)
        job = enqueue_watch_stock_sync(db, stock.code, reason="paper_watchlist_exists")
        db.commit()
        background_tasks.add_task(run_watch_stock_sync_job, job.id)
        return {
            "status": "exists",
            "item": paper_watchlist_dict(existing, snapshot_dict(snapshot, existing.stock) if snapshot else None, advice_dict(advice, existing.stock) if advice else None),
            "sync_status": "queued",
            "sync_job_id": job.id,
        }
    row = PaperWatchlist(account_id=account.id, stock_id=stock.id, display_order=current_count + 1)
    db.add(row)
    job = enqueue_watch_stock_sync(db, stock.code, reason="paper_watchlist_add")
    db.commit()
    db.refresh(row)
    background_tasks.add_task(run_watch_stock_sync_job, job.id)
    publish_event("paper_watchlist.updated", {"account_id": account.id, "code": stock.code, "action": "created"})
    snapshot = _latest_snapshot(db, row.stock_id)
    advice = _latest_advice(db, row.stock_id)
    return {
        "status": "created",
        "item": paper_watchlist_dict(row, snapshot_dict(snapshot, row.stock) if snapshot else None, advice_dict(advice, row.stock) if advice else None),
        "sync_status": "queued",
        "sync_job_id": job.id,
    }


@router.delete("/paper/watchlist/{code}")
def delete_paper_watch(code: str, account=Depends(_paper_account), db: Session = Depends(get_db)) -> dict[str, Any]:
    stock = _get_stock_or_404(db, code)
    row = db.execute(select(PaperWatchlist).where(PaperWatchlist.account_id == account.id, PaperWatchlist.stock_id == stock.id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="模拟账户自选股不存在")
    db.delete(row)
    db.commit()
    publish_event("paper_watchlist.updated", {"account_id": account.id, "code": stock.code, "action": "deleted"})
    return {"status": "deleted", "code": stock.code}


@router.get("/stocks")
def list_stocks(q: str | None = None, security_type: str | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    stmt = select(Stock).where(Stock.is_active.is_(True)).order_by(Stock.security_type, Stock.code)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Stock.code.ilike(like), Stock.name.ilike(like), Stock.industry.ilike(like)))
    if security_type:
        stmt = stmt.where(Stock.security_type == security_type)
    rows = db.execute(stmt.limit(300)).scalars().all()
    return {"items": [stock_dict(row) for row in rows], "total": len(rows)}


@router.get("/stocks/{code}")
def get_stock(code: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    stock = _get_stock_or_404(db, code)
    snapshot = _latest_snapshot(db, stock.id)
    advice = _latest_advice(db, stock.id)
    return {**stock_dict(stock), "latest_snapshot": snapshot_dict(snapshot, stock) if snapshot else None, "latest_advice": advice_dict(advice, stock) if advice else None, "is_watched": _watch_item(db, stock.id) is not None}


@router.get("/stocks/{code}/kline")
def get_kline(code: str, limit: int = Query(90, ge=1, le=500), db: Session = Depends(get_db)) -> dict[str, Any]:
    stock = _get_stock_or_404(db, code)
    rows = list(reversed(db.execute(select(KlineDaily).where(KlineDaily.stock_id == stock.id).order_by(desc(KlineDaily.trade_date)).limit(limit)).scalars().all()))
    return {"stock": stock_dict(stock), "items": [kline_dict(row) for row in rows], "total": len(rows)}


@router.get("/stocks/{code}/intraday")
def get_intraday_kline(code: str, period: int = Query(5, ge=1, le=60), days: int = Query(10, ge=1, le=30), db: Session = Depends(get_db)) -> dict[str, Any]:
    stock = _get_stock_or_404(db, code)
    rows_desc = db.execute(
        select(KlineIntraday)
        .where(KlineIntraday.stock_id == stock.id, KlineIntraday.period_minutes == period)
        .order_by(desc(KlineIntraday.bar_time))
        .limit(_intraday_query_limit(days, period))
    ).scalars().all()
    keep_dates: list[Any] = []
    for row in rows_desc:
        trade_date = row.bar_time.date()
        if trade_date not in keep_dates:
            keep_dates.append(trade_date)
        if len(keep_dates) >= days:
            break
    keep = set(keep_dates)
    rows = [row for row in rows_desc if row.bar_time.date() in keep]
    rows.sort(key=lambda row: row.bar_time)
    return {"stock": stock_dict(stock), "period_minutes": period, "days": days, "items": [intraday_kline_dict(row) for row in rows], "total": len(rows)}


@router.get("/stocks/{code}/snapshot")
def get_stock_snapshot(code: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    stock = _get_stock_or_404(db, code)
    snapshot = _latest_snapshot(db, stock.id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="No snapshot found")
    return snapshot_dict(snapshot, stock)


@router.get("/stocks/{code}/snapshots")
def get_stock_snapshots(code: str, limit: int = Query(120, ge=1, le=1000), db: Session = Depends(get_db)) -> dict[str, Any]:
    stock = _get_stock_or_404(db, code)
    rows = list(reversed(db.execute(select(WatchSnapshot).where(WatchSnapshot.stock_id == stock.id).order_by(desc(WatchSnapshot.snapshot_time)).limit(limit)).scalars().all()))
    if not rows:
        market_rows = db.execute(select(MarketSnapshot).where(MarketSnapshot.stock_id == stock.id).order_by(desc(MarketSnapshot.snapshot_time)).limit(limit)).scalars().all()
        return {"stock": stock_dict(stock), "items": [snapshot_dict(row, stock) for row in reversed(market_rows)], "total": len(market_rows)}
    return {"stock": stock_dict(stock), "items": [snapshot_dict(row, stock) for row in rows], "total": len(rows)}


@router.get("/market/snapshot")
def market_snapshot(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=300), q: str | None = None, market: str | None = None, industry: str | None = None, change_min: float | None = None, change_max: float | None = None, sort_by: str = "change_pct", sort_order: str = "desc", db: Session = Depends(get_db)) -> dict[str, Any]:
    subq = select(MarketSnapshot.stock_id, func.max(MarketSnapshot.snapshot_time).label("max_time")).group_by(MarketSnapshot.stock_id).subquery()
    stmt = (
        select(MarketSnapshot, Stock)
        .join(Stock, MarketSnapshot.stock_id == Stock.id)
        .join(subq, and_(MarketSnapshot.stock_id == subq.c.stock_id, MarketSnapshot.snapshot_time == subq.c.max_time))
    )
    if q:
        needle = q.lower().strip()
        like = f"%{needle}%"
        stmt = stmt.where(or_(Stock.code.ilike(like), Stock.name.ilike(like), Stock.industry.ilike(like)))
    if market:
        stmt = stmt.where(Stock.market == market)
    if industry:
        stmt = stmt.where(Stock.industry == industry)
    if change_min is not None:
        stmt = stmt.where(MarketSnapshot.change_pct >= change_min)
    if change_max is not None:
        stmt = stmt.where(MarketSnapshot.change_pct <= change_max)
    sort_column = _market_sort_column(sort_by)
    sort_expr = sort_column.asc() if sort_order.lower() == "asc" else sort_column.desc()
    stmt = stmt.order_by(sort_expr.nulls_last())
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [snapshot_dict(snapshot, stock) for snapshot, stock in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/news")
def list_news(code: str | None = None, scope: str | None = None, sentiment: str | None = None, limit: int = Query(50, ge=1, le=300), db: Session = Depends(get_db)) -> dict[str, Any]:
    stmt = select(News, Stock).join(Stock, News.stock_id == Stock.id, isouter=True).order_by(desc(News.published_at), desc(News.id))
    if code:
        stmt = stmt.where(News.stock_id == _get_stock_or_404(db, code).id)
    if scope:
        stmt = stmt.where(News.scope == scope)
    if sentiment:
        stmt = stmt.where(News.sentiment == sentiment)
    rows = db.execute(stmt.limit(limit)).all()
    return {"items": [news_dict(news, stock) for news, stock in rows], "total": len(rows)}


@router.post("/news/simplify-pending")
def simplify_pending_news(limit: int = Query(30, ge=1, le=100), db: Session = Depends(get_db)) -> dict[str, Any]:
    return NewsCollector().simplify_pending(db, limit=limit)


@router.get("/news/{news_id}")
def get_news(news_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.execute(select(News, Stock).join(Stock, News.stock_id == Stock.id, isouter=True).where(News.id == news_id)).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="News not found")
    return news_dict(row[0], row[1])


@router.get("/stocks/{code}/news")
def stock_news(code: str, limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)) -> dict[str, Any]:
    stock = _get_stock_or_404(db, code)
    rows = db.execute(select(News).where(News.stock_id == stock.id).order_by(desc(News.published_at)).limit(limit)).scalars().all()
    return {"stock": stock_dict(stock), "items": [news_dict(row, stock) for row in rows], "total": len(rows)}


@router.get("/advice")
def advice_summary(signal: str | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    latest = select(TradingAdvice.stock_id, func.max(TradingAdvice.id).label("latest_id")).group_by(TradingAdvice.stock_id).subquery()
    stmt = (
        select(TradingAdvice, Stock)
        .join(Stock, TradingAdvice.stock_id == Stock.id)
        .join(latest, TradingAdvice.id == latest.c.latest_id)
        .where(Stock.security_type == "stock")
    )
    if signal:
        stmt = stmt.where(TradingAdvice.signal == signal)
    rows = [advice_dict(row, stock) for row, stock in db.execute(stmt).all()]
    rows.sort(key=lambda item: item["confidence"], reverse=True)
    return {"items": rows, "total": len(rows)}


@router.get("/advice/{code}")
def latest_advice(code: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    stock = _get_stock_or_404(db, code)
    advice = _latest_advice(db, stock.id) or analyze_stock(db, stock.code)
    return advice_dict(advice, stock)


@router.get("/advice/{code}/history")
def advice_history(code: str, limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)) -> dict[str, Any]:
    stock = _get_stock_or_404(db, code)
    rows = db.execute(select(TradingAdvice).where(TradingAdvice.stock_id == stock.id).order_by(desc(TradingAdvice.created_at)).limit(limit)).scalars().all()
    return {"stock": stock_dict(stock), "items": [advice_dict(row, stock) for row in rows], "total": len(rows)}


@router.post("/analysis/watchlist")
def trigger_watchlist_analysis(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = analyze_watchlist(db)
    return {"items": [advice_dict(row, row.stock) for row in rows], "total": len(rows)}


@router.post("/analysis/{code}")
def trigger_analysis(code: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    stock = _get_stock_or_404(db, code)
    return advice_dict(analyze_stock(db, stock.code), stock)


@router.get("/watchlist")
def get_watchlist(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.execute(select(Watchlist).join(Stock).order_by(Watchlist.display_order, Stock.code)).scalars().all()
    items = []
    for row in rows:
        snapshot = _latest_snapshot(db, row.stock_id)
        advice = _latest_advice(db, row.stock_id)
        items.append(watchlist_dict(row, snapshot_dict(snapshot, row.stock) if snapshot else None, advice_dict(advice, row.stock) if advice else None))
    return {"items": items, "total": len(items), "max_size": settings.max_watchlist_size}


@router.post("/watchlist")
def add_watch(request: AddWatchRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)) -> dict[str, Any]:
    current_count = db.execute(select(func.count()).select_from(Watchlist)).scalar_one()
    if current_count >= settings.max_watchlist_size:
        raise HTTPException(status_code=400, detail="Watchlist size limit reached")
    stock = _resolve_stock_for_watch(db, request.code)
    if _watch_item(db, stock.id) is not None:
        advice = _latest_advice(db, stock.id)
        job = enqueue_watch_stock_sync(db, stock.code, reason="watchlist_exists")
        db.commit()
        background_tasks.add_task(run_watch_stock_sync_job, job.id)
        return {"status": "exists", "item": stock_dict(stock), "analysis_status": "skipped", "sync_status": "queued", "sync_job_id": job.id, "latest_advice": advice_dict(advice, stock) if advice else None}
    db.add(Watchlist(stock_id=stock.id, display_order=current_count + 1, alert_enabled=request.alert_enabled, alert_threshold_pct=Decimal(str(request.alert_threshold_pct)), strategy_push_enabled=request.strategy_push_enabled))
    job = enqueue_watch_stock_sync(db, stock.code, reason="watchlist_add")
    db.commit()
    background_tasks.add_task(run_watch_stock_sync_job, job.id)
    analysis_status = "success"
    latest_advice = None
    analysis_error = None
    try:
        latest_advice = advice_dict(analyze_stock(db, stock.code), stock)
    except Exception as exc:
        db.rollback()
        analysis_status = "failed"
        analysis_error = str(exc)
    publish_event("watchlist.updated", {"code": stock.code, "action": "created"})
    return {"status": "created", "item": stock_dict(stock), "analysis_status": analysis_status, "sync_status": "queued", "sync_job_id": job.id, "latest_advice": latest_advice, "analysis_error": analysis_error}


@router.patch("/watchlist/{code}")
def update_watch(code: str, request: UpdateWatchRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    stock = _get_stock_or_404(db, code)
    row = _watch_item(db, stock.id)
    if row is None:
        raise HTTPException(status_code=404, detail="Watchlist item not found")
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(row, field, Decimal(str(value)) if field == "alert_threshold_pct" and value is not None else value)
    db.commit()
    publish_event("watchlist.updated", {"code": stock.code, "action": "updated"})
    return {"status": "updated", "item": stock_dict(stock)}


@router.delete("/watchlist/{code}")
def delete_watch(code: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    stock = _get_stock_or_404(db, code)
    row = _watch_item(db, stock.id)
    if row is None:
        raise HTTPException(status_code=404, detail="Watchlist item not found")
    db.delete(row)
    db.commit()
    publish_event("watchlist.updated", {"code": stock.code, "action": "deleted"})
    return {"status": "deleted", "code": stock.code}


@router.post("/collector/real/bootstrap")
def collect_real_bootstrap(reset: bool = True, db: Session = Depends(get_db)) -> dict[str, Any]:
    return AkshareCollector().bootstrap(db, reset=reset)


@router.post("/collector/real/market")
def collect_real_market(db: Session = Depends(get_db)) -> dict[str, Any]:
    return AkshareCollector().collect_market_snapshot(db)


@router.post("/collector/real/history")
def collect_real_history(db: Session = Depends(get_db)) -> dict[str, Any]:
    return AkshareCollector().collect_history(db)


@router.post("/collector/real/daily-kline/{code}")
def collect_real_stock_daily_kline(code: str, days: int = Query(365, ge=1, le=3650), db: Session = Depends(get_db)) -> dict[str, Any]:
    _get_stock_or_404(db, code)
    try:
        return AkshareCollector().collect_stock_history(db, code, days=days)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/collector/real/full-market-history")
def collect_real_full_market_history(
    days: int = Query(365, ge=1, le=3650),
    batch_size: int = Query(30, ge=1, le=200),
    limit: int | None = Query(None, ge=1, le=10000),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return AkshareCollector().collect_full_market_history(db, days=days, batch_size=batch_size, limit=limit)


@router.post("/collector/real/full-market-history/start")
def start_real_full_market_history(
    background_tasks: BackgroundTasks,
    days: int = Query(365, ge=1, le=3650),
    batch_size: int = Query(30, ge=1, le=200),
    limit: int | None = Query(None, ge=1, le=10000),
) -> dict[str, Any]:
    if not _full_market_history_lock.acquire(blocking=False):
        return {"status": "already_running", "job_type": "full_market_daily_kline", "days": days, "batch_size": batch_size, "limit": limit}
    background_tasks.add_task(_run_full_market_history_background, days, batch_size, limit)
    publish_event("jobs.updated", {"job_type": "full_market_daily_kline", "status": "started"})
    return {"status": "started", "job_type": "full_market_daily_kline", "days": days, "batch_size": batch_size, "limit": limit}


@router.post("/collector/real/missing-daily-kline")
def collect_real_missing_daily_kline(
    days: int = Query(365, ge=1, le=3650),
    batch_size: int = Query(30, ge=1, le=200),
    limit: int | None = Query(None, ge=1, le=10000),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return AkshareCollector().collect_missing_daily_kline(db, days=days, batch_size=batch_size, limit=limit)


@router.post("/collector/real/missing-daily-kline/start")
def start_real_missing_daily_kline(
    background_tasks: BackgroundTasks,
    days: int = Query(365, ge=1, le=3650),
    batch_size: int = Query(30, ge=1, le=200),
    limit: int | None = Query(None, ge=1, le=10000),
) -> dict[str, Any]:
    if not _missing_daily_kline_lock.acquire(blocking=False):
        return {"status": "already_running", "job_type": "missing_daily_kline", "days": days, "batch_size": batch_size, "limit": limit}
    background_tasks.add_task(_run_missing_daily_kline_background, days, batch_size, limit)
    publish_event("jobs.updated", {"job_type": "missing_daily_kline", "status": "started"})
    return {"status": "started", "job_type": "missing_daily_kline", "days": days, "batch_size": batch_size, "limit": limit}


@router.post("/collector/real/intraday")
def collect_real_intraday(trading_days: int = Query(10, ge=1, le=30), period: int = Query(5, ge=1, le=60), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return AkshareCollector().collect_intraday(db, trading_days=trading_days, period_minutes=period)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/collector/real/intraday/{code}")
def collect_real_stock_intraday(code: str, trading_days: int = Query(1, ge=1, le=30), period: int = Query(1, ge=1, le=60), db: Session = Depends(get_db)) -> dict[str, Any]:
    _get_stock_or_404(db, code)
    try:
        return AkshareCollector().collect_stock_intraday(db, code, trading_days=trading_days, period_minutes=period)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/collector/real/news")
def collect_real_news(limit: int = Query(30, ge=1, le=100), db: Session = Depends(get_db)) -> dict[str, Any]:
    return NewsCollector().collect(db, limit=limit)


@router.get("/collection-jobs")
def collection_jobs(limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.execute(select(CollectionJob).order_by(desc(CollectionJob.started_at)).limit(limit)).scalars().all()
    return {"items": [job_dict(row) for row in rows], "total": len(rows)}


@router.get("/notifications")
def notifications(notification_type: str | None = None, limit: int = Query(100, ge=1, le=300), db: Session = Depends(get_db)) -> dict[str, Any]:
    stmt = select(Notification).order_by(desc(Notification.created_at))
    if notification_type:
        stmt = stmt.where(Notification.notification_type == notification_type)
    rows = db.execute(stmt.limit(limit)).scalars().all()
    return {"items": [notification_dict(row) for row in rows], "total": len(rows)}


def _get_stock_or_404(db: Session, code: str) -> Stock:
    stock = db.execute(select(Stock).where(Stock.code == normalize_code(code))).scalar_one_or_none()
    if stock is None:
        raise HTTPException(status_code=404, detail="Stock not found")
    return stock


def _resolve_stock_for_watch(db: Session, value: str) -> Stock:
    query = value.strip()
    if not query:
        raise HTTPException(status_code=400, detail="请输入股票代码或名称")
    normalized_code = normalize_code(query)
    stock = db.execute(select(Stock).where(Stock.code == normalized_code)).scalar_one_or_none()
    if stock is not None:
        return stock
    if "." not in query:
        stock = db.execute(select(Stock).where(Stock.code.like(f"{query.upper()}.%"))).scalar_one_or_none()
        if stock is not None:
            return stock
    try:
        target = AkshareCollector().resolve_stock_target(query)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"本地未找到该股票，尝试从数据源解析失败：{exc}") from exc
    if target is None:
        raise HTTPException(status_code=404, detail="未找到匹配股票，请输入 6 位股票代码或先同步全市场股票列表")
    stock = db.execute(select(Stock).where(Stock.code == target["code"])).scalar_one_or_none()
    if stock is None:
        stock = Stock(
            code=target["code"],
            name=target["name"],
            market=target["market"],
            security_type=target.get("security_type") or "stock",
            industry=target.get("industry"),
        )
        db.add(stock)
        db.flush()
    else:
        stock.name = target["name"] or stock.name
        stock.market = target["market"] or stock.market
        stock.industry = target.get("industry") or stock.industry
    return stock


def _watch_item(db: Session, stock_id: int) -> Watchlist | None:
    return db.execute(select(Watchlist).where(Watchlist.stock_id == stock_id)).scalar_one_or_none()


def _latest_snapshot(db: Session, stock_id: int) -> MarketSnapshot | None:
    return db.execute(select(MarketSnapshot).where(MarketSnapshot.stock_id == stock_id).order_by(desc(MarketSnapshot.snapshot_time)).limit(1)).scalar_one_or_none()


def _latest_advice(db: Session, stock_id: int) -> TradingAdvice | None:
    return db.execute(select(TradingAdvice).where(TradingAdvice.stock_id == stock_id).order_by(desc(TradingAdvice.created_at)).limit(1)).scalar_one_or_none()


def _latest_market_rows(db: Session) -> list[tuple[MarketSnapshot, Stock]]:
    subq = select(MarketSnapshot.stock_id, func.max(MarketSnapshot.snapshot_time).label("max_time")).group_by(MarketSnapshot.stock_id).subquery()
    stmt = select(MarketSnapshot, Stock).join(Stock, MarketSnapshot.stock_id == Stock.id).join(subq, and_(MarketSnapshot.stock_id == subq.c.stock_id, MarketSnapshot.snapshot_time == subq.c.max_time))
    return list(db.execute(stmt).all())


def _intraday_query_limit(days: int, period_minutes: int) -> int:
    bars_per_day = max(120, (300 // max(1, period_minutes)) + 20)
    return days * bars_per_day


def _run_full_market_history_background(days: int, batch_size: int, limit: int | None) -> None:
    try:
        with SessionLocal() as db:
            AkshareCollector().collect_full_market_history(db, days=days, batch_size=batch_size, limit=limit)
    except Exception as exc:
        with SessionLocal() as db:
            record_collection_job(
                db,
                "full_market_daily_kline",
                "akshare",
                "failed",
                {"inserted": 0, "updated": 0, "failed": 1},
                {"days": days, "batch_size": batch_size, "limit": limit},
                str(exc),
            )
            db.commit()
        publish_event("jobs.updated", {"job_type": "full_market_daily_kline", "status": "failed"})
    finally:
        _full_market_history_lock.release()


def _run_missing_daily_kline_background(days: int, batch_size: int, limit: int | None) -> None:
    try:
        with SessionLocal() as db:
            AkshareCollector().collect_missing_daily_kline(db, days=days, batch_size=batch_size, limit=limit)
    except Exception as exc:
        with SessionLocal() as db:
            record_collection_job(
                db,
                "missing_daily_kline",
                "akshare",
                "failed",
                {"inserted": 0, "updated": 0, "failed": 1},
                {"days": days, "batch_size": batch_size, "limit": limit},
                str(exc),
            )
            db.commit()
        publish_event("jobs.updated", {"job_type": "missing_daily_kline", "status": "failed"})
    finally:
        _missing_daily_kline_lock.release()


def _market_sort_column(sort_by: str) -> Any:
    stock_columns = {"code": Stock.code, "name": Stock.name, "market": Stock.market, "industry": Stock.industry}
    if sort_by in stock_columns:
        return stock_columns[sort_by]
    snapshot_columns = {
        "price": MarketSnapshot.price,
        "change_pct": MarketSnapshot.change_pct,
        "change_amount": MarketSnapshot.change_amount,
        "volume": MarketSnapshot.volume,
        "amount": MarketSnapshot.amount,
        "turnover_rate": MarketSnapshot.turnover_rate,
        "volume_ratio": MarketSnapshot.volume_ratio,
        "pe": MarketSnapshot.pe,
        "pb": MarketSnapshot.pb,
        "total_mv": MarketSnapshot.total_mv,
        "circ_mv": MarketSnapshot.circ_mv,
    }
    return snapshot_columns.get(sort_by, MarketSnapshot.change_pct)
