from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import CollectionJob, KlineDaily, KlineIntraday, MarketSnapshot, News, Notification, Stock, TradingAdvice, WatchSnapshot, Watchlist
from app.schemas import AddWatchRequest, NotificationResultRequest, UpdateWatchRequest
from app.services.analysis_service import DISCLAIMER, analyze_stock, analyze_watchlist
from app.services.ingest_service import ingest_kline_payload, ingest_market_payload, ingest_news_payload, normalize_code
from app.services.notification_service import update_notification_result
from app.services.real_collector_service import AkshareCollector, DEFAULT_WATCHLIST
from app.services.serializers import advice_dict, intraday_kline_dict, job_dict, kline_dict, news_dict, notification_dict, snapshot_dict, stock_dict, watchlist_dict


router = APIRouter(prefix="/api/v1")


@router.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat(), "env": settings.app_env}


@router.get("/settings")
def get_settings() -> dict[str, Any]:
    return {
        "app_env": settings.app_env,
        "database": "sqlite" if settings.database_url.startswith("sqlite") else "postgresql",
        "auto_seed_demo_data": settings.auto_seed_demo_data,
        "market_data_primary": settings.market_data_primary,
        "default_watchlist": DEFAULT_WATCHLIST,
        "collector_intervals": {"market_snapshot_seconds": settings.market_snapshot_interval_seconds, "watch_snapshot_seconds": settings.watch_snapshot_interval_seconds, "news_seconds": settings.news_interval_seconds, "advice_seconds": settings.advice_interval_seconds},
        "risk_control": {"request_min_interval_seconds": settings.request_min_interval_seconds, "fetch_failure_downgrade_threshold": settings.fetch_failure_downgrade_threshold, "max_watchlist_size": settings.max_watchlist_size},
        "qqbot": {"target": settings.qqbot_target, "price_alert": settings.qqbot_enable_price_alert, "strategy_alert": settings.qqbot_enable_strategy_alert, "daily_summary": settings.qqbot_enable_daily_summary, "job_failed_alert": settings.qqbot_enable_job_failed_alert},
        "analysis_engine": settings.analysis_engine,
        "disclaimer": DISCLAIMER,
    }


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
        .limit(days * 120)
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
    rows = _latest_market_rows(db)
    if q:
        needle = q.lower().strip()
        rows = [(s, stock) for s, stock in rows if needle in stock.code.lower() or needle in stock.name.lower() or needle in (stock.industry or "").lower()]
    if market:
        rows = [(s, stock) for s, stock in rows if stock.market == market]
    if industry:
        rows = [(s, stock) for s, stock in rows if stock.industry == industry]
    if change_min is not None:
        rows = [(s, stock) for s, stock in rows if s.change_pct is not None and float(s.change_pct) >= change_min]
    if change_max is not None:
        rows = [(s, stock) for s, stock in rows if s.change_pct is not None and float(s.change_pct) <= change_max]
    rows.sort(key=lambda pair: _sort_value(pair[0], pair[1], sort_by), reverse=sort_order.lower() != "asc")
    total = len(rows)
    start = (page - 1) * page_size
    return {"items": [snapshot_dict(snapshot, stock) for snapshot, stock in rows[start : start + page_size]], "total": total, "page": page, "page_size": page_size}


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
    rows: list[dict[str, Any]] = []
    for stock in db.execute(select(Stock).where(Stock.security_type == "stock").order_by(Stock.code)).scalars().all():
        advice = _latest_advice(db, stock.id)
        if advice is not None:
            item = advice_dict(advice, stock)
            if signal is None or item["signal"] == signal:
                rows.append(item)
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


@router.post("/analysis/{code}")
def trigger_analysis(code: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    stock = _get_stock_or_404(db, code)
    return advice_dict(analyze_stock(db, stock.code), stock)


@router.post("/analysis/watchlist")
def trigger_watchlist_analysis(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = analyze_watchlist(db)
    return {"items": [advice_dict(row, row.stock) for row in rows], "total": len(rows)}


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
def add_watch(request: AddWatchRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    current_count = db.execute(select(func.count()).select_from(Watchlist)).scalar_one()
    if current_count >= settings.max_watchlist_size:
        raise HTTPException(status_code=400, detail="Watchlist size limit reached")
    stock = _get_stock_or_404(db, request.code)
    if _watch_item(db, stock.id) is not None:
        return {"status": "exists", "item": stock_dict(stock)}
    db.add(Watchlist(stock_id=stock.id, display_order=current_count + 1, alert_enabled=request.alert_enabled, alert_threshold_pct=Decimal(str(request.alert_threshold_pct)), strategy_push_enabled=request.strategy_push_enabled))
    db.commit()
    return {"status": "created", "item": stock_dict(stock)}


@router.patch("/watchlist/{code}")
def update_watch(code: str, request: UpdateWatchRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    stock = _get_stock_or_404(db, code)
    row = _watch_item(db, stock.id)
    if row is None:
        raise HTTPException(status_code=404, detail="Watchlist item not found")
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(row, field, Decimal(str(value)) if field == "alert_threshold_pct" and value is not None else value)
    db.commit()
    return {"status": "updated", "item": stock_dict(stock)}


@router.delete("/watchlist/{code}")
def delete_watch(code: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    stock = _get_stock_or_404(db, code)
    row = _watch_item(db, stock.id)
    if row is None:
        raise HTTPException(status_code=404, detail="Watchlist item not found")
    db.delete(row)
    db.commit()
    return {"status": "deleted", "code": stock.code}


@router.post("/ingest/openclaw/market")
def ingest_market(payload: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
    return ingest_market_payload(db, payload, watch_only=payload.get("job_type") == "watch_snapshot")


@router.post("/ingest/openclaw/kline")
def ingest_kline(payload: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
    return ingest_kline_payload(db, payload)


@router.post("/ingest/openclaw/news")
def ingest_news(payload: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
    return ingest_news_payload(db, payload)


@router.post("/ingest/openclaw/notification-result")
def ingest_notification_result(request: NotificationResultRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        row = update_notification_result(db, request.notification_id, request.status, request.sent_at, request.error_message)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return notification_dict(row)


@router.post("/collector/real/bootstrap")
def collect_real_bootstrap(reset: bool = True, db: Session = Depends(get_db)) -> dict[str, Any]:
    return AkshareCollector().bootstrap(db, reset=reset)


@router.post("/collector/real/market")
def collect_real_market(db: Session = Depends(get_db)) -> dict[str, Any]:
    return AkshareCollector().collect_market_snapshot(db)


@router.post("/collector/real/history")
def collect_real_history(db: Session = Depends(get_db)) -> dict[str, Any]:
    return AkshareCollector().collect_history(db)


@router.post("/collector/real/intraday")
def collect_real_intraday(trading_days: int = Query(10, ge=1, le=30), period: int = Query(5, ge=1, le=60), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return AkshareCollector().collect_intraday(db, trading_days=trading_days, period_minutes=period)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/collection-jobs")
def collection_jobs(limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.execute(select(CollectionJob).order_by(desc(CollectionJob.started_at)).limit(limit)).scalars().all()
    return {"items": [job_dict(row) for row in rows], "total": len(rows)}


@router.get("/notifications")
def notifications(status: str | None = None, limit: int = Query(100, ge=1, le=300), db: Session = Depends(get_db)) -> dict[str, Any]:
    stmt = select(Notification).order_by(desc(Notification.created_at))
    if status:
        stmt = stmt.where(Notification.status == status)
    rows = db.execute(stmt.limit(limit)).scalars().all()
    return {"items": [notification_dict(row) for row in rows], "total": len(rows)}


def _get_stock_or_404(db: Session, code: str) -> Stock:
    stock = db.execute(select(Stock).where(Stock.code == normalize_code(code))).scalar_one_or_none()
    if stock is None:
        raise HTTPException(status_code=404, detail="Stock not found")
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


def _sort_value(snapshot: MarketSnapshot, stock: Stock, sort_by: str) -> Any:
    if sort_by in {"code", "name", "market", "industry"}:
        return getattr(stock, sort_by) or ""
    value = getattr(snapshot, sort_by, None)
    return float(value) if value is not None else -999999999
