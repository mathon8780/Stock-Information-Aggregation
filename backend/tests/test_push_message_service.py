from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.models import Notification, Stock, TradingAdvice
from app.services.push_message_service import render_strategy_markdown, write_push_message, write_strategy_message


def test_news_digest_messages_share_fifteen_minute_file_without_length_limit(tmp_path):
    first = Notification(
        id=1,
        notification_type="news_digest",
        target_channel="configured_qqbot_default",
        title="新闻一",
        content="A" * 700,
        payload={"source": "newsnow:财联社", "url": "https://example.com/1"},
        created_at=datetime(2026, 5, 28, 10, 1, tzinfo=timezone.utc),
    )
    second = Notification(
        id=2,
        notification_type="news_digest",
        target_channel="configured_qqbot_default",
        title="新闻二",
        content="B" * 700,
        payload={"source": "newsnow:证券时报", "url": "https://example.com/2"},
        created_at=datetime(2026, 5, 28, 10, 14, tzinfo=timezone.utc),
    )

    first_path = write_push_message(first, str(tmp_path))
    second_path = write_push_message(second, str(tmp_path))

    assert first_path == second_path
    assert first_path.endswith("20260528_1000_news_digest.md")
    content = tmp_path.joinpath("20260528_1000_news_digest.md").read_text(encoding="utf-8")
    assert "# 新闻摘要聚合提醒" in content
    assert "新闻一" in content
    assert "新闻二" in content
    assert "A" * 650 in content
    assert "B" * 650 in content
    assert "内容已截断" not in content


def test_news_digest_messages_use_new_file_for_next_fifteen_minute_window(tmp_path):
    first = Notification(
        id=1,
        notification_type="news_digest",
        target_channel="configured_qqbot_default",
        title="新闻一",
        content="摘要一",
        payload={},
        created_at=datetime(2026, 5, 28, 10, 14, tzinfo=timezone.utc),
    )
    second = Notification(
        id=2,
        notification_type="news_digest",
        target_channel="configured_qqbot_default",
        title="新闻二",
        content="摘要二",
        payload={},
        created_at=datetime(2026, 5, 28, 10, 15, tzinfo=timezone.utc),
    )

    first_path = write_push_message(first, str(tmp_path))
    second_path = write_push_message(second, str(tmp_path))

    assert first_path.endswith("20260528_1000_news_digest.md")
    assert second_path.endswith("20260528_1015_news_digest.md")
    assert first_path != second_path


def test_strategy_message_uses_dedicated_template_and_one_file_per_advice(tmp_path):
    stock = Stock(code="300308.SZ", name="中际旭创", market="SZ", security_type="stock", industry="CPO/光模块")
    first = TradingAdvice(
        id=101,
        stock_id=1,
        signal="重点关注",
        confidence=Decimal("82.00"),
        reasoning="MA5 高于 MA20，短期趋势占优；近期个股资讯偏积极",
        strategy="加入重点观察，关注量能延续和指数配合，不追高。",
        risk_notes="重点关注不是买入指令，需要等待价格和量能确认。",
        indicators={
            "latest_close": 188.5,
            "ma5": 180.2,
            "ma20": 170.8,
            "rsi14": 62.5,
            "macd": {"cross": "golden"},
            "volume_change_rate": 0.25,
        },
        news_summary={"summary": "市场消息偏暖，个股资讯偏积极。", "important_news_count": 2},
        market_context={"index_trend": "positive", "index_average_change_pct": 0.45},
        engine="rule_engine",
        created_at=datetime(2026, 5, 28, 10, 16, 30, tzinfo=timezone.utc),
    )
    second = TradingAdvice(
        id=102,
        stock_id=1,
        signal="持有",
        confidence=Decimal("61.00"),
        reasoning="均线结构暂未形成明确方向",
        strategy="维持观察。",
        risk_notes="持有阶段需要设置止损或退出条件。",
        indicators={},
        news_summary={},
        market_context={},
        engine="rule_engine",
        created_at=datetime(2026, 5, 28, 10, 16, 31, tzinfo=timezone.utc),
    )

    first_path = write_strategy_message(first, stock, str(tmp_path))
    second_path = write_strategy_message(second, stock, str(tmp_path))
    markdown = render_strategy_markdown(first, stock)

    assert first_path.endswith("20260528_101630_strategy_300308_SZ_101.md")
    assert second_path.endswith("20260528_101631_strategy_300308_SZ_102.md")
    assert first_path != second_path
    assert "# 策略建议" in markdown
    assert "- 类型：策略建议" in markdown
    assert "## 决策依据" in markdown
    assert "## 执行策略" in markdown
    assert "## 风险提示" in markdown
    assert "## 关键指标" in markdown
