from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from statistics import mean
from typing import Any

from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from app.analysis import calculate_indicators
from app.config import settings
from app.models import KlineDaily, MarketSnapshot, News, Stock, TradingAdvice, Watchlist
from app.services.event_bus import publish_event
from app.services.ingest_service import normalize_code
from app.services.notification_service import create_notification


DISCLAIMER = "本系统生成的交易建议仅用于课程项目、学习研究和辅助分析，不构成任何投资建议，不承诺收益，也不替代用户独立判断。"


def _to_kline_rows(klines: list[KlineDaily]) -> list[dict[str, Any]]:
    return [
        {
            "trade_date": row.trade_date.isoformat(),
            "open": float(row.open) if row.open is not None else None,
            "high": float(row.high) if row.high is not None else None,
            "low": float(row.low) if row.low is not None else None,
            "close": float(row.close) if row.close is not None else None,
            "volume": row.volume,
        }
        for row in klines
    ]


def _aggregate_news(db: Session, stock: Stock) -> dict[str, Any]:
    since = datetime.now(timezone.utc) - timedelta(days=7)
    rows = db.execute(select(News).where(or_(News.stock_id == stock.id, News.scope == "market"), News.published_at >= since).order_by(desc(News.published_at)).limit(50)).scalars().all()
    positive = sum(1 for row in rows if row.sentiment == "positive")
    negative = sum(1 for row in rows if row.sentiment == "negative")
    neutral = sum(1 for row in rows if row.sentiment == "neutral")
    important = sum(1 for row in rows if row.importance >= 4)
    market_rows = [row for row in rows if row.scope == "market"]
    stock_sentiment = "negative" if negative > positive else "positive" if positive > negative else "neutral"
    market_positive = sum(1 for row in market_rows if row.sentiment == "positive")
    market_negative = sum(1 for row in market_rows if row.sentiment == "negative")
    market_sentiment = "negative" if market_negative > market_positive else "positive" if market_positive > market_negative else "neutral"
    return {
        "market_sentiment": market_sentiment,
        "stock_sentiment": stock_sentiment,
        "positive_news_count": positive,
        "negative_news_count": negative,
        "neutral_news_count": neutral,
        "important_news_count": important,
        "stock_news_count": sum(1 for row in rows if row.stock_id == stock.id),
        "summary": _news_summary_sentence(stock_sentiment, market_sentiment, important, negative),
        "latest_titles": [row.title for row in rows[:5]],
    }


def _news_summary_sentence(stock_sentiment: str, market_sentiment: str, important: int, negative: int) -> str:
    stock_text = {"positive": "个股资讯偏积极", "negative": "个股资讯偏负面", "neutral": "个股资讯中性"}.get(stock_sentiment, "个股资讯中性")
    market_text = {"positive": "市场消息偏暖", "negative": "市场消息偏弱", "neutral": "市场消息中性"}.get(market_sentiment, "市场消息中性")
    risk = f"，其中 {negative} 条负面信息需跟踪" if negative else ""
    return f"{market_text}，{stock_text}，近 7 日重要资讯 {important} 条{risk}。"


def _market_context(db: Session) -> dict[str, Any]:
    index_stocks = db.execute(select(Stock).where(Stock.security_type == "index")).scalars().all()
    changes: list[float] = []
    rows: list[dict[str, Any]] = []
    for stock in index_stocks:
        snapshot = db.execute(select(MarketSnapshot).where(MarketSnapshot.stock_id == stock.id).order_by(desc(MarketSnapshot.snapshot_time)).limit(1)).scalar_one_or_none()
        if snapshot is None:
            continue
        change = float(snapshot.change_pct or 0)
        changes.append(change)
        rows.append({"code": stock.code, "name": stock.name, "change_pct": change})
    avg_change = round(mean(changes), 4) if changes else 0.0
    trend = "positive" if avg_change > 0.4 else "negative" if avg_change < -0.4 else "neutral"
    return {"index_average_change_pct": avg_change, "index_trend": trend, "indices": rows}


def _rule_engine(indicators: dict[str, Any], news: dict[str, Any], market: dict[str, Any]) -> dict[str, Any]:
    ma5 = indicators.get("ma5")
    ma20 = indicators.get("ma20")
    rsi = indicators.get("rsi14")
    macd_cross = (indicators.get("macd") or {}).get("cross")
    boll_upper = (indicators.get("boll") or {}).get("upper")
    latest_close = indicators.get("latest_close")
    volume_change = indicators.get("volume_change_rate") or 0
    stock_sentiment = news.get("stock_sentiment")
    market_trend = market.get("index_trend")
    trend_up = ma5 is not None and ma20 is not None and ma5 > ma20
    trend_down = ma5 is not None and ma20 is not None and ma5 < ma20
    rsi_healthy = rsi is not None and 40 <= rsi <= 70
    rsi_overheat = rsi is not None and rsi > 75
    near_boll_upper = latest_close is not None and boll_upper is not None and latest_close >= boll_upper * 0.98
    volume_expands = volume_change is not None and 0.1 <= volume_change <= 0.8
    volume_abnormal = volume_change is not None and volume_change > 1.2
    score = 58
    reasons: list[str] = []
    if trend_up:
        score += 10
        reasons.append("MA5 高于 MA20，短期趋势占优")
    elif trend_down:
        score -= 12
        reasons.append("MA5 低于 MA20，短期趋势偏弱")
    else:
        reasons.append("均线结构暂未形成明确方向")
    if macd_cross == "golden":
        score += 10
        reasons.append("MACD 出现金叉信号")
    elif macd_cross == "death":
        score -= 12
        reasons.append("MACD 出现死叉信号")
    if rsi_healthy:
        score += 6
        reasons.append("RSI 位于相对健康区间")
    elif rsi_overheat:
        score -= 12
        reasons.append("RSI 进入过热区间")
    if near_boll_upper and volume_abnormal:
        score -= 12
        reasons.append("价格接近 BOLL 上轨且量能异常放大")
    elif volume_expands and trend_up:
        score += 6
        reasons.append("成交量温和放大")
    if stock_sentiment == "positive":
        score += 8
        reasons.append("近期个股资讯偏积极")
    elif stock_sentiment == "negative":
        score -= 14
        reasons.append("近期个股资讯偏负面")
    if market_trend == "positive":
        score += 5
        reasons.append("主要指数环境偏正向")
    elif market_trend == "negative":
        score -= 8
        reasons.append("主要指数环境偏弱")
    if trend_up and macd_cross == "golden" and rsi_healthy and stock_sentiment != "negative":
        signal = "重点关注"
    elif trend_up and market_trend == "positive" and volume_expands:
        signal = "谨慎买入"
    elif rsi_overheat or near_boll_upper and volume_abnormal:
        signal = "减仓"
    elif trend_down and macd_cross == "death" and stock_sentiment == "negative":
        signal = "回避"
    else:
        signal = "持有"
    return {"signal": signal, "confidence": max(45, min(92, score)), "reasoning": "；".join(reasons[:5]) or "数据不足，维持观察。", "strategy": _strategy_text(signal, indicators), "risk_notes": _risk_text(signal, market_trend)}


def _strategy_text(signal: str, indicators: dict[str, Any]) -> str:
    latest = indicators.get("latest_close")
    boll = indicators.get("boll") or {}
    lower = boll.get("lower")
    upper = boll.get("upper")
    if signal == "谨慎买入":
        return f"等待回踩不破 MA20 或放量突破后再分批介入，参考区间 {lower or '-'} 至 {upper or '-'}。"
    if signal == "重点关注":
        return f"加入重点观察，关注 {latest or '-'} 附近的量能延续和指数配合，不追高。"
    if signal == "减仓":
        return "优先降低仓位，等待过热指标修复后再评估。"
    if signal == "回避":
        return "暂不参与，等待均线和资讯风险改善后重新分析。"
    return "维持观察，短线不追涨杀跌，等待更明确的趋势或资讯信号。"


def _risk_text(signal: str, market_trend: str | None) -> str:
    market = "若主要指数继续走弱，应降低仓位或暂停操作。" if market_trend == "negative" else "需持续跟踪指数环境和成交量变化。"
    signal_risk = {"谨慎买入": "谨慎买入仍需控制单次仓位，避免在冲高时一次性买入。", "重点关注": "重点关注不是买入指令，需要等待价格和量能确认。", "减仓": "减仓信号出现后应优先控制回撤。", "回避": "回避阶段应避免因短线反弹忽略基本风险。", "持有": "持有阶段需要设置止损或退出条件。"}.get(signal, "需保持风险控制。")
    return f"{signal_risk}{market}{DISCLAIMER}"


def analyze_stock(db: Session, code: str) -> TradingAdvice:
    stock = db.execute(select(Stock).where(Stock.code == normalize_code(code))).scalar_one_or_none()
    if stock is None:
        raise ValueError(f"Stock {code} not found")
    klines = list(reversed(db.execute(select(KlineDaily).where(KlineDaily.stock_id == stock.id).order_by(desc(KlineDaily.trade_date)).limit(90)).scalars().all()))
    rows = _to_kline_rows(klines)
    if not rows:
        latest_snapshot = db.execute(select(MarketSnapshot).where(MarketSnapshot.stock_id == stock.id).order_by(desc(MarketSnapshot.snapshot_time)).limit(1)).scalar_one_or_none()
        if latest_snapshot is not None:
            rows = [{"close": float(latest_snapshot.price or 0), "open": float(latest_snapshot.open or latest_snapshot.price or 0), "high": float(latest_snapshot.high or latest_snapshot.price or 0), "low": float(latest_snapshot.low or latest_snapshot.price or 0), "volume": latest_snapshot.volume or 0}]
    indicators = calculate_indicators(rows)
    news_summary = _aggregate_news(db, stock)
    market_context = _market_context(db)
    result = _rule_engine(indicators, news_summary, market_context)
    previous = db.execute(select(TradingAdvice).where(TradingAdvice.stock_id == stock.id).order_by(desc(TradingAdvice.created_at)).limit(1)).scalar_one_or_none()
    advice = TradingAdvice(stock_id=stock.id, signal=result["signal"], confidence=Decimal(str(result["confidence"])), reasoning=result["reasoning"], strategy=result["strategy"], risk_notes=result["risk_notes"], indicators=indicators, news_summary=news_summary, market_context=market_context, engine=settings.analysis_engine)
    db.add(advice)
    db.flush()
    watch = db.execute(select(Watchlist).where(Watchlist.stock_id == stock.id)).scalar_one_or_none()
    if settings.qqbot_enable_strategy_alert and watch is not None and watch.strategy_push_enabled and previous is not None and previous.signal != advice.signal:
        create_notification(db, "strategy_change", f"{stock.name} 策略变化", f"{stock.code} 策略由 {previous.signal} 变为 {advice.signal}，置信度 {float(advice.confidence):.0f}%。", {"code": stock.code, "old_signal": previous.signal, "new_signal": advice.signal, "confidence": float(advice.confidence)})
    db.commit()
    publish_event("advice.updated", {"code": stock.code})
    if settings.qqbot_enable_strategy_alert:
        publish_event("notifications.updated", {"source": "strategy_change"})
    db.refresh(advice)
    return advice


def analyze_watchlist(db: Session) -> list[TradingAdvice]:
    rows = db.execute(select(Watchlist).join(Stock).order_by(Watchlist.display_order, Stock.code)).scalars().all()
    result: list[TradingAdvice] = []
    for item in rows:
        result.append(analyze_stock(db, item.stock.code))
    return result
