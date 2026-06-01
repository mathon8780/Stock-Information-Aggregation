from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path
from typing import Any

from app.models import Notification, Stock, TradingAdvice


MAX_MARKDOWN_CHARS = 600

TYPE_LABELS = {
    "price_alert": "行情异动",
    "strategy": "策略建议",
    "strategy_change": "策略变化",
    "news_digest": "新闻摘要",
    "major_event": "重大事件",
}

SENTIMENT_LABELS = {"positive": "偏积极", "neutral": "中性", "negative": "偏负面"}


def write_push_message(row: Notification, output_dir: str, max_chars: int = MAX_MARKDOWN_CHARS) -> str:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    if row.notification_type == "news_digest":
        return _write_news_digest_aggregate(row, path)
    markdown = render_notification_markdown(row, max_chars=max_chars)
    file_path = path / _message_filename(row)
    file_path.write_text(markdown, encoding="utf-8")
    return str(file_path)


def write_strategy_message(advice: TradingAdvice, stock: Stock, output_dir: str) -> str:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    file_path = path / _strategy_message_filename(advice, stock)
    file_path.write_text(render_strategy_markdown(advice, stock), encoding="utf-8")
    return str(file_path)


def render_strategy_markdown(advice: TradingAdvice, stock: Stock) -> str:
    indicators = advice.indicators or {}
    news_summary = advice.news_summary or {}
    market_context = advice.market_context or {}
    return "\n".join(
        [
            "# 策略建议",
            f"- 类型：{TYPE_LABELS['strategy']}",
            f"- 时间：{advice.created_at.isoformat() if advice.created_at else '-'}",
            f"- 标的：{stock.name}（{stock.code}）",
            f"- 市场：{stock.market}",
            f"- 行业：{stock.industry or '未分类'}",
            f"- 策略信号：{advice.signal}",
            f"- 置信度：{_percent(advice.confidence)}",
            f"- 引擎：{advice.engine}",
            "",
            "## 决策依据",
            _compact(advice.reasoning),
            "",
            "## 执行策略",
            _compact(advice.strategy),
            "",
            "## 风险提示",
            _compact(advice.risk_notes),
            "",
            "## 关键指标",
            f"- 最新收盘：{_value_text(indicators.get('latest_close'))}",
            f"- MA5 / MA20：{_value_text(indicators.get('ma5'))} / {_value_text(indicators.get('ma20'))}",
            f"- RSI14：{_value_text(indicators.get('rsi14'))}",
            f"- MACD：{((indicators.get('macd') or {}).get('cross')) or '-'}",
            f"- 量能变化：{_percent((indicators.get('volume_change_rate') or 0) * 100 if indicators.get('volume_change_rate') is not None else None)}",
            "",
            "## 新闻与市场",
            f"- 新闻概览：{_compact(news_summary.get('summary'))}",
            f"- 重要资讯数：{news_summary.get('important_news_count', '-')}",
            f"- 市场趋势：{market_context.get('index_trend') or '-'}",
            f"- 指数平均涨跌幅：{_percent(market_context.get('index_average_change_pct'))}",
            "",
        ]
    ).strip() + "\n"


def render_notification_markdown(row: Notification, max_chars: int = MAX_MARKDOWN_CHARS) -> str:
    payload = row.payload or {}
    notification_type = row.notification_type
    if notification_type == "strategy_change":
        text = _strategy_change_markdown(row, payload)
    elif notification_type == "news_digest":
        text = _news_digest_markdown(row, payload)
    elif notification_type == "major_event":
        text = _major_event_markdown(row, payload)
    elif notification_type == "price_alert":
        text = _price_alert_markdown(row, payload)
    else:
        text = _generic_markdown(row, payload)
    return _limit_markdown(text, max_chars)


def _message_filename(row: Notification) -> str:
    created_at = row.created_at
    timestamp = created_at.strftime("%Y%m%d_%H%M%S") if created_at else "unknown_time"
    safe_type = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", row.notification_type).strip("_") or "notification"
    suffix = f"_{row.id}" if row.id is not None else ""
    return f"{timestamp}_{safe_type}{suffix}.md"


def _strategy_message_filename(advice: TradingAdvice, stock: Stock) -> str:
    created_at = advice.created_at
    timestamp = created_at.strftime("%Y%m%d_%H%M%S") if created_at else "unknown_time"
    code = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", stock.code).strip("_") or "unknown"
    suffix = f"_{advice.id}" if advice.id is not None else ""
    return f"{timestamp}_strategy_{code}{suffix}.md"


def _write_news_digest_aggregate(row: Notification, output_dir: Path) -> str:
    file_path = output_dir / _news_digest_aggregate_filename(row)
    marker = f"<!-- notification:{row.id} -->" if row.id is not None else f"<!-- notification:{_time_text(row)}:{row.title} -->"
    existing = file_path.read_text(encoding="utf-8") if file_path.exists() else _news_digest_aggregate_header(row)
    if marker not in existing:
        existing = existing.rstrip()
        existing = f"{existing}\n\n{marker}\n{_news_digest_aggregate_entry(row, row.payload or {})}\n"
        file_path.write_text(existing, encoding="utf-8")
    return str(file_path)


def _news_digest_aggregate_filename(row: Notification) -> str:
    created_at = row.created_at
    if created_at is None:
        return "unknown_time_news_digest.md"
    bucket_start = created_at.replace(minute=(created_at.minute // 15) * 15, second=0, microsecond=0)
    return f"{bucket_start.strftime('%Y%m%d_%H%M')}_news_digest.md"


def _news_digest_aggregate_header(row: Notification) -> str:
    created_at = row.created_at
    if created_at is None:
        window = "-"
    else:
        bucket_start = created_at.replace(minute=(created_at.minute // 15) * 15, second=0, microsecond=0)
        bucket_end = bucket_start + timedelta(minutes=15)
        window = f"{bucket_start.isoformat(timespec='minutes')} - {bucket_end.isoformat(timespec='minutes')}"
    return "\n".join(["# 新闻摘要聚合提醒", f"- 类型：{TYPE_LABELS['news_digest']}", f"- 时间窗口：{window}", ""])


def _news_digest_aggregate_entry(row: Notification, payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"## {row.title}",
            f"- 通知ID：{row.id or '-'}",
            f"- 时间：{_time_text(row)}",
            f"- 来源：{_source_name(payload.get('source'))}",
            f"- 原文：{payload.get('url') or '-'}",
            "",
            _compact(row.content),
        ]
    )


def _strategy_change_markdown(row: Notification, payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# 策略变化提醒",
            f"- 类型：{TYPE_LABELS['strategy_change']}",
            f"- 时间：{_time_text(row)}",
            f"- 标的：{payload.get('code') or '-'}",
            f"- 变化：{payload.get('old_signal') or '-'} -> {payload.get('new_signal') or '-'}",
            f"- 置信度：{_percent(payload.get('confidence'))}",
            "",
            "## 提示",
            _compact(row.content),
        ]
    )


def _news_digest_markdown(row: Notification, payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# 新闻摘要提醒",
            f"- 类型：{TYPE_LABELS['news_digest']}",
            f"- 时间：{_time_text(row)}",
            f"- 来源：{_source_name(payload.get('source'))}",
            f"- 原文：{payload.get('url') or '-'}",
            "",
            "## 摘要",
            _compact(row.content),
        ]
    )


def _major_event_markdown(row: Notification, payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# 重大事件提醒",
            f"- 类型：{TYPE_LABELS['major_event']}",
            f"- 时间：{_time_text(row)}",
            f"- 来源：{_source_name(payload.get('source'))}",
            f"- 重要度：{payload.get('importance') or '-'} / 5",
            f"- 情绪：{SENTIMENT_LABELS.get(str(payload.get('sentiment')), payload.get('sentiment') or '-')}",
            f"- 原文：{payload.get('url') or '-'}",
            "",
            "## 摘要",
            _compact(row.content),
        ]
    )


def _price_alert_markdown(row: Notification, payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# 行情异动提醒",
            f"- 类型：{TYPE_LABELS['price_alert']}",
            f"- 时间：{_time_text(row)}",
            f"- 标的：{payload.get('name') or '-'}（{payload.get('code') or '-'}）",
            f"- 最新价：{payload.get('price') or '-'}",
            f"- 涨跌幅：{_percent(payload.get('change_pct'))}",
            "",
            "## 提示",
            _compact(row.content),
        ]
    )


def _generic_markdown(row: Notification, payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"# {TYPE_LABELS.get(row.notification_type, row.notification_type)}",
            f"- 类型：{row.notification_type}",
            f"- 时间：{_time_text(row)}",
            f"- 目标：{row.target_channel}",
            f"- 状态：{row.status}",
            "",
            "## 内容",
            _compact(row.content),
        ]
    )


def _limit_markdown(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) < max_chars:
        return f"{text}\n"
    if len(text) == max_chars:
        return text
    suffix = "\n\n> 内容已截断。"
    max_body = max_chars - 1
    keep = max(0, max_body - len(suffix) - 1)
    body = f"{text[:keep].rstrip()}…{suffix}"
    if len(body) > max_body:
        body = body[:max_body]
    return f"{body}\n"


def _compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "-")).strip()


def _source_name(value: Any) -> str:
    text = str(value or "-")
    return text.replace("newsnow:", "") if text != "-" else text


def _percent(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return str(value)


def _value_text(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _time_text(row: Notification) -> str:
    return row.created_at.isoformat() if row.created_at else "-"
