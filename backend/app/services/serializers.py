from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.models import CollectionJob, KlineDaily, KlineIntraday, MarketSnapshot, News, Notification, Stock, TradingAdvice, WatchSnapshot, Watchlist


def scalar(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def stock_dict(stock: Stock) -> dict[str, Any]:
    return {
        "id": stock.id,
        "code": stock.code,
        "name": stock.name,
        "market": stock.market,
        "security_type": stock.security_type,
        "industry": stock.industry,
        "is_active": stock.is_active,
    }


def snapshot_dict(snapshot: MarketSnapshot | WatchSnapshot, stock: Stock | None = None) -> dict[str, Any]:
    data = {
        "id": snapshot.id,
        "snapshot_time": scalar(snapshot.snapshot_time),
        "stock_id": snapshot.stock_id,
        "price": scalar(snapshot.price),
        "change_pct": scalar(snapshot.change_pct),
        "change_amount": scalar(snapshot.change_amount),
        "volume": snapshot.volume,
        "amount": scalar(snapshot.amount),
        "open": scalar(snapshot.open),
        "high": scalar(snapshot.high),
        "low": scalar(snapshot.low),
        "amplitude": scalar(snapshot.amplitude),
        "turnover_rate": scalar(snapshot.turnover_rate),
        "volume_ratio": scalar(snapshot.volume_ratio),
        "pe": scalar(snapshot.pe),
        "pb": scalar(snapshot.pb),
        "total_mv": scalar(snapshot.total_mv),
        "circ_mv": scalar(snapshot.circ_mv),
        "idempotency_key": snapshot.idempotency_key,
    }
    if stock is not None:
        data.update({"code": stock.code, "name": stock.name, "market": stock.market, "security_type": stock.security_type, "industry": stock.industry})
    return data


def kline_dict(row: KlineDaily) -> dict[str, Any]:
    return {
        "trade_date": scalar(row.trade_date),
        "open": scalar(row.open),
        "high": scalar(row.high),
        "low": scalar(row.low),
        "close": scalar(row.close),
        "volume": row.volume,
        "amount": scalar(row.amount),
        "amplitude": scalar(row.amplitude),
        "change_pct": scalar(row.change_pct),
        "turnover_rate": scalar(row.turnover_rate),
        "source": row.source,
    }


def intraday_kline_dict(row: KlineIntraday) -> dict[str, Any]:
    return {
        "bar_time": scalar(row.bar_time),
        "period_minutes": row.period_minutes,
        "open": scalar(row.open),
        "high": scalar(row.high),
        "low": scalar(row.low),
        "close": scalar(row.close),
        "volume": row.volume,
        "amount": scalar(row.amount),
        "amplitude": scalar(row.amplitude),
        "change_pct": scalar(row.change_pct),
        "change_amount": scalar(row.change_amount),
        "turnover_rate": scalar(row.turnover_rate),
        "source": row.source,
    }


def news_dict(row: News, stock: Stock | None = None) -> dict[str, Any]:
    data = {
        "id": row.id,
        "stock_id": row.stock_id,
        "scope": row.scope,
        "title": row.title,
        "summary": row.summary,
        "content": row.content,
        "source": row.source,
        "url": row.url,
        "sentiment": row.sentiment,
        "importance": row.importance,
        "published_at": scalar(row.published_at),
        "fetched_at": scalar(row.fetched_at),
    }
    if stock is not None:
        data["stock"] = stock_dict(stock)
        data["code"] = stock.code
        data["name"] = stock.name
    return data


def advice_dict(row: TradingAdvice, stock: Stock | None = None) -> dict[str, Any]:
    data = {
        "id": row.id,
        "stock_id": row.stock_id,
        "signal": row.signal,
        "confidence": scalar(row.confidence),
        "reasoning": row.reasoning,
        "strategy": row.strategy,
        "risk_notes": row.risk_notes,
        "indicators": row.indicators or {},
        "news_summary": row.news_summary or {},
        "market_context": row.market_context or {},
        "engine": row.engine,
        "created_at": scalar(row.created_at),
    }
    if stock is not None:
        data["stock"] = stock_dict(stock)
        data["code"] = stock.code
        data["name"] = stock.name
        data["industry"] = stock.industry
    return data


def watchlist_dict(row: Watchlist, latest_snapshot: dict[str, Any] | None, latest_advice: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "id": row.id,
        "stock": stock_dict(row.stock),
        "display_order": row.display_order,
        "alert_enabled": row.alert_enabled,
        "alert_threshold_pct": scalar(row.alert_threshold_pct),
        "strategy_push_enabled": row.strategy_push_enabled,
        "added_at": scalar(row.added_at),
        "latest_snapshot": latest_snapshot,
        "latest_advice": latest_advice,
    }


def job_dict(row: CollectionJob) -> dict[str, Any]:
    return {
        "id": row.id,
        "job_type": row.job_type,
        "status": row.status,
        "source": row.source,
        "requested_payload": row.requested_payload,
        "result_summary": row.result_summary,
        "error_message": row.error_message,
        "started_at": scalar(row.started_at),
        "finished_at": scalar(row.finished_at),
    }


def notification_dict(row: Notification) -> dict[str, Any]:
    return {
        "id": row.id,
        "notification_type": row.notification_type,
        "target_channel": row.target_channel,
        "title": row.title,
        "content": row.content,
        "payload": row.payload,
        "status": row.status,
        "retry_count": row.retry_count,
        "error_message": row.error_message,
        "created_at": scalar(row.created_at),
        "sent_at": scalar(row.sent_at),
    }
