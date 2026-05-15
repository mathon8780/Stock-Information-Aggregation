from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CollectionJob, KlineDaily, KlineIntraday, MarketSnapshot, News, Stock, WatchSnapshot
from app.services.event_bus import publish_event
from app.services.notification_service import create_price_alert_if_needed
from app.services.sentiment_service import classify_sentiment, estimate_importance


NEWS_ORIGINAL_TITLE_MAX_LENGTH = 240


def truncate_news_original_title(value: Any) -> str:
    return str(value or "").strip()[:NEWS_ORIGINAL_TITLE_MAX_LENGTH]


def normalize_code(code: str) -> str:
    raw = code.strip().upper()
    if "." in raw:
        return raw
    if raw.startswith(("000", "001", "002", "003", "300", "301")):
        return f"{raw}.SZ"
    if raw.startswith(("600", "601", "603", "605", "688", "689")):
        return f"{raw}.SH"
    return raw


def infer_market(code: str, supplied: str | None = None) -> str:
    if supplied:
        return supplied.upper()
    normalized = normalize_code(code)
    if normalized.endswith(".SH"):
        return "SH"
    if normalized.endswith(".SZ"):
        return "SZ"
    return "INDEX"


def parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if value is None:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def parse_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value)[:10])


def decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(float(value))


def content_hash(*parts: Any) -> str:
    joined = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def get_or_create_stock(db: Session, item: dict[str, Any]) -> Stock:
    code = normalize_code(str(item.get("code") or item.get("symbol")))
    stock = db.execute(select(Stock).where(Stock.code == code)).scalar_one_or_none()
    market = infer_market(code, item.get("market"))
    if stock is None:
        stock = Stock(code=code, name=str(item.get("name") or code), market=market, security_type=str(item.get("security_type") or ("index" if market == "INDEX" else "stock")), industry=item.get("industry"))
        db.add(stock)
        db.flush()
    else:
        stock.name = str(item.get("name") or stock.name)
        stock.market = market
        stock.industry = item.get("industry") or stock.industry
    return stock


def _record_job(db: Session, job_type: str, source: str, status: str, result_summary: dict[str, Any], requested_payload: dict[str, Any] | None = None, error_message: str | None = None) -> CollectionJob:
    now = datetime.now(timezone.utc)
    row = CollectionJob(job_type=job_type, status=status, source=source, requested_payload=requested_payload or {}, result_summary=result_summary, error_message=error_message, started_at=now, finished_at=now)
    db.add(row)
    db.flush()
    return row


def record_collection_job(
    db: Session,
    job_type: str,
    source: str,
    status: str,
    result_summary: dict[str, Any],
    requested_payload: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> CollectionJob:
    return _record_job(db, job_type, source, status, result_summary, requested_payload, error_message)


SNAPSHOT_FIELDS = {"price", "change_pct", "change_amount", "amount", "open", "high", "low", "amplitude", "turnover_rate", "volume_ratio", "pe", "pb", "total_mv", "circ_mv"}


def ingest_market_payload(db: Session, payload: dict[str, Any], watch_only: bool = False) -> dict[str, Any]:
    items = payload.get("items") or []
    source = payload.get("source", "openclaw")
    fetched_at = parse_datetime(payload.get("fetched_at"))
    inserted_market = inserted_watch = skipped = 0
    for item in items:
        stock = get_or_create_stock(db, item)
        key = item.get("idempotency_key") or f"market:{stock.code}:{fetched_at.isoformat()}"
        existing = db.execute(select(MarketSnapshot).where(MarketSnapshot.idempotency_key == key)).scalar_one_or_none()
        market_snapshot = existing
        if existing is None and not watch_only:
            values = {field: decimal_or_none(item.get(field)) for field in SNAPSHOT_FIELDS}
            market_snapshot = MarketSnapshot(snapshot_time=parse_datetime(item.get("snapshot_time") or payload.get("fetched_at")), stock_id=stock.id, volume=int_or_none(item.get("volume")), idempotency_key=key, **values)
            db.add(market_snapshot)
            db.flush()
            inserted_market += 1
            create_price_alert_if_needed(db, stock, market_snapshot.change_pct, market_snapshot.price)
        else:
            skipped += 1
        watch_key = item.get("watch_idempotency_key") or f"watch:{stock.code}:{fetched_at.isoformat()}"
        if watch_only or bool(item.get("is_watch")):
            existing_watch = db.execute(select(WatchSnapshot).where(WatchSnapshot.idempotency_key == watch_key)).scalar_one_or_none()
            if existing_watch is None:
                values = {field: decimal_or_none(item.get(field)) for field in SNAPSHOT_FIELDS}
                db.add(WatchSnapshot(snapshot_time=parse_datetime(item.get("snapshot_time") or payload.get("fetched_at")), stock_id=stock.id, source_snapshot_id=market_snapshot.id if market_snapshot is not None else None, volume=int_or_none(item.get("volume")), idempotency_key=watch_key, **values))
                inserted_watch += 1
            else:
                skipped += 1
    summary = {"inserted_market": inserted_market, "inserted_watch": inserted_watch, "skipped": skipped, "failed": len(payload.get("failed_items") or [])}
    _record_job(db, payload.get("job_type", "market_snapshot"), source, "success", summary, {"count": len(items)})
    db.commit()
    publish_event("market.updated", summary)
    if inserted_watch:
        publish_event("watchlist.updated", summary)
    publish_event("notifications.updated", {"source": "market"})
    publish_event("jobs.updated", {"job_type": payload.get("job_type", "market_snapshot")})
    return summary


def ingest_kline_payload(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    items = payload.get("items") or []
    source = payload.get("source", "openclaw")
    inserted = updated = 0
    for item in items:
        stock = get_or_create_stock(db, item)
        trade_date = parse_date(item.get("trade_date"))
        row = db.get(KlineDaily, {"stock_id": stock.id, "trade_date": trade_date})
        values = {
            "open": decimal_or_none(item.get("open")),
            "high": decimal_or_none(item.get("high")),
            "low": decimal_or_none(item.get("low")),
            "close": decimal_or_none(item.get("close")),
            "volume": int_or_none(item.get("volume")),
            "amount": decimal_or_none(item.get("amount")),
            "amplitude": decimal_or_none(item.get("amplitude")),
            "change_pct": decimal_or_none(item.get("change_pct")),
            "turnover_rate": decimal_or_none(item.get("turnover_rate")),
            "source": source,
        }
        if row is None:
            db.add(KlineDaily(stock_id=stock.id, trade_date=trade_date, **values))
            inserted += 1
        else:
            for field, value in values.items():
                setattr(row, field, value)
            updated += 1
    summary = {"inserted": inserted, "updated": updated, "failed": len(payload.get("failed_items") or [])}
    _record_job(db, payload.get("job_type", "daily_kline"), source, "success", summary, {"count": len(items)})
    db.commit()
    publish_event("kline.updated", summary)
    publish_event("jobs.updated", {"job_type": payload.get("job_type", "daily_kline")})
    return summary


def ingest_intraday_kline_payload(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    items = payload.get("items") or []
    source = payload.get("source", "akshare")
    inserted = updated = 0
    for item in items:
        stock = get_or_create_stock(db, item)
        bar_time = parse_datetime(item.get("bar_time")).replace(tzinfo=None)
        period_minutes = int(item.get("period_minutes") or 5)
        row = db.get(KlineIntraday, {"stock_id": stock.id, "period_minutes": period_minutes, "bar_time": bar_time})
        values = {
            "open": decimal_or_none(item.get("open")),
            "high": decimal_or_none(item.get("high")),
            "low": decimal_or_none(item.get("low")),
            "close": decimal_or_none(item.get("close")),
            "volume": int_or_none(item.get("volume")),
            "amount": decimal_or_none(item.get("amount")),
            "amplitude": decimal_or_none(item.get("amplitude")),
            "change_pct": decimal_or_none(item.get("change_pct")),
            "change_amount": decimal_or_none(item.get("change_amount")),
            "turnover_rate": decimal_or_none(item.get("turnover_rate")),
            "source": source,
        }
        if row is None:
            db.add(KlineIntraday(stock_id=stock.id, period_minutes=period_minutes, bar_time=bar_time, **values))
            inserted += 1
        else:
            for field, value in values.items():
                setattr(row, field, value)
            updated += 1
    summary = {"inserted": inserted, "updated": updated, "failed": len(payload.get("failed_items") or [])}
    _record_job(db, payload.get("job_type", "intraday_kline"), source, "success", summary, {"count": len(items), "period_minutes": payload.get("period_minutes")})
    db.commit()
    publish_event("intraday.updated", summary)
    publish_event("jobs.updated", {"job_type": payload.get("job_type", "intraday_kline")})
    return summary


def ingest_news_payload(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    items = payload.get("items") or []
    source = payload.get("source", "openclaw")
    fetched_at = parse_datetime(payload.get("fetched_at"))
    inserted = skipped = 0
    for item in items:
        stock = get_or_create_stock(db, item) if item.get("code") else None
        title = str(item.get("title") or "").strip()
        summary_text = str(item.get("summary") or "").strip()
        raw_payload = item.get("raw_payload") if isinstance(item.get("raw_payload"), dict) else {}
        original_title = truncate_news_original_title(item.get("original_title") or raw_payload.get("original_title") or title)
        digest = item.get("content_hash") or item.get("idempotency_key") or content_hash(item.get("url"), title, summary_text)
        if db.execute(select(News).where(News.content_hash == digest)).scalar_one_or_none() is not None:
            skipped += 1
            continue
        text_for_sentiment = f"{title} {summary_text}"
        db.add(
            News(
                stock_id=stock.id if stock is not None else None,
                scope=str(item.get("scope") or ("stock" if stock is not None else "market")),
                title=title,
                original_title=original_title,
                summary=summary_text,
                content=item.get("content"),
                source=str(item.get("source") or source),
                url=item.get("url"),
                content_hash=digest,
                sentiment=item.get("sentiment") or classify_sentiment(text_for_sentiment),
                importance=max(1, min(5, int(item.get("importance") or estimate_importance(text_for_sentiment)))),
                published_at=parse_datetime(item.get("published_at")) if item.get("published_at") else fetched_at,
                fetched_at=fetched_at,
                raw_payload=item,
                simplification_status=str(item.get("simplification_status") or ("simplified" if item.get("content") else "pending")),
                simplified_at=parse_datetime(item.get("simplified_at")) if item.get("simplified_at") else None,
                llm_provider=item.get("llm_provider"),
                llm_model=item.get("llm_model"),
                prompt_name=item.get("prompt_name"),
                error_message=item.get("error_message"),
            )
        )
        inserted += 1
    summary = {"inserted": inserted, "skipped": skipped, "failed": len(payload.get("failed_items") or [])}
    _record_job(db, payload.get("job_type", "news"), source, "success", summary, {"count": len(items)})
    db.commit()
    publish_event("news.updated", summary)
    publish_event("jobs.updated", {"job_type": payload.get("job_type", "news")})
    return summary
