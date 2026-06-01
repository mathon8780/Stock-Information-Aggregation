from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import News, Notification, Stock, Watchlist
from app.services.push_message_service import write_push_message


def create_notification(db: Session, notification_type: str, title: str, content: str, payload: dict[str, Any] | None = None, status: str = "pending") -> Notification:
    row = Notification(notification_type=notification_type, target_channel=settings.qqbot_target, title=title, content=content, payload=payload or {}, status=status)
    db.add(row)
    db.flush()
    _write_markdown_message(row)
    return row


def create_price_alert_if_needed(db: Session, stock: Stock, change_pct: Decimal | None, price: Decimal | None) -> None:
    if not settings.qqbot_enable_price_alert or change_pct is None:
        return
    watch = db.execute(select(Watchlist).where(Watchlist.stock_id == stock.id)).scalar_one_or_none()
    if watch is None or not watch.alert_enabled or abs(float(change_pct)) < float(watch.alert_threshold_pct):
        return
    recent_alerts = db.execute(select(Notification).where(Notification.notification_type == "price_alert").order_by(desc(Notification.created_at)).limit(50)).scalars().all()
    existing = next((row for row in recent_alerts if (row.payload or {}).get("code") == stock.code), None)
    if existing is not None and existing.created_at.date() == datetime.now(timezone.utc).date():
        return
    create_notification(
        db,
        "price_alert",
        f"{stock.name} 价格异动",
        f"{stock.code} 最新价 {float(price) if price is not None else '-'}，涨跌幅 {float(change_pct):.2f}%。",
        {"code": stock.code, "name": stock.name, "price": float(price) if price is not None else None, "change_pct": float(change_pct)},
    )


def create_news_notification_if_needed(db: Session, news: News) -> Notification | None:
    if not settings.qqbot_enable_news_digest or news.simplification_status != "simplified":
        return None
    recent = db.execute(select(Notification).where(Notification.notification_type == "news_digest").order_by(desc(Notification.created_at)).limit(300)).scalars().all()
    if any((row.payload or {}).get("news_id") == news.id for row in recent):
        return None
    source_name = news.source.replace("newsnow:", "") if news.source else "新闻"
    digest = (news.summary or news.content or news.original_title or news.title or "").strip()
    if len(digest) > 240:
        digest = f"{digest[:237]}..."
    content = f"{digest}\n\n来源：{source_name}"
    if news.published_at is not None:
        content += f"\n时间：{news.published_at.isoformat()}"
    if news.url:
        content += f"\n原文：{news.url}"
    return create_notification(
        db,
        "news_digest",
        f"{source_name}：{news.title}",
        content,
        {
            "news_id": news.id,
            "source": news.source,
            "url": news.url,
            "published_at": news.published_at.isoformat() if news.published_at else None,
            "simplified_at": news.simplified_at.isoformat() if news.simplified_at else None,
        },
    )


def create_major_event_notification_if_needed(db: Session, news: News) -> Notification | None:
    if news.importance < 4:
        return None
    recent = db.execute(select(Notification).where(Notification.notification_type == "major_event").order_by(desc(Notification.created_at)).limit(500)).scalars().all()
    if any((row.payload or {}).get("news_id") == news.id for row in recent):
        return None
    source_name = news.source.replace("newsnow:", "") if news.source else "新闻"
    digest = (news.summary or news.content or news.original_title or news.title or "").strip()
    if len(digest) > 260:
        digest = f"{digest[:257]}..."
    content = f"{digest}\n\n来源：{source_name}"
    if news.published_at is not None:
        content += f"\n时间：{news.published_at.isoformat()}"
    if news.url:
        content += f"\n原文：{news.url}"
    return create_notification(
        db,
        "major_event",
        f"重大事件：{news.title}",
        content,
        {
            "news_id": news.id,
            "source": news.source,
            "url": news.url,
            "published_at": news.published_at.isoformat() if news.published_at else None,
            "importance": news.importance,
            "sentiment": news.sentiment,
            "stock_id": news.stock_id,
        },
    )


def update_notification_result(db: Session, notification_id: int, status: str, sent_at: datetime | None = None, error_message: str | None = None) -> Notification:
    row = db.get(Notification, notification_id)
    if row is None:
        raise ValueError(f"Notification {notification_id} not found")
    if status == "sent":
        row.status = "sent"
        row.error_message = None
        row.sent_at = sent_at or datetime.now(timezone.utc)
    elif status == "failed":
        row.retry_count += 1
        row.error_message = error_message
        row.status = "failed" if row.retry_count >= settings.qqbot_max_retry else "pending"
    else:
        row.status = status
        row.error_message = error_message
    db.flush()
    return row


def _write_markdown_message(row: Notification) -> None:
    if not settings.push_message_enabled:
        return
    payload = dict(row.payload or {})
    try:
        payload["push_message_path"] = write_push_message(row, settings.push_message_dir)
    except OSError as exc:
        payload["push_message_error"] = str(exc)[:300]
    row.payload = payload
