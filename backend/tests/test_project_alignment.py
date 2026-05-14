from __future__ import annotations

import importlib
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OPENCLAW_ROOT = PROJECT_ROOT / "openclaw"


def test_sql_migration_includes_intraday_kline_table() -> None:
    sql = (PROJECT_ROOT / "data" / "migrations" / "001_init.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS kline_intraday" in sql
    assert "period_minutes INTEGER NOT NULL" in sql
    assert "bar_time TIMESTAMP NOT NULL" in sql
    assert "PRIMARY KEY (stock_id, period_minutes, bar_time)" in sql


def test_openclaw_scripts_do_not_call_demo_collectors() -> None:
    data_fetcher = (OPENCLAW_ROOT / "market-data-fetcher" / "run.py").read_text(encoding="utf-8")
    info_fetcher = (OPENCLAW_ROOT / "market-info-fetcher" / "run.py").read_text(encoding="utf-8")

    assert "market-data-fetcher" in data_fetcher
    assert "collector/demo" not in data_fetcher
    assert "collector/demo" not in info_fetcher
    assert "market-info-fetcher" in info_fetcher


def test_openclaw_scheduler_uses_real_endpoints() -> None:
    sys.path.insert(0, str(OPENCLAW_ROOT))
    try:
        scheduler = importlib.import_module("common.scheduler")
    finally:
        sys.path.remove(str(OPENCLAW_ROOT))

    calls: list[str] = []

    def fake_post(path: str, payload: dict | None = None) -> dict:
        calls.append(path)
        return {"ok": True}

    market_result = scheduler.run_task("market-data-fetcher", post=fake_post, enforce_trading_hours=False)
    intraday_result = scheduler.run_task("market-intraday-fetcher", post=fake_post, enforce_trading_hours=False)
    news_result = scheduler.run_task("market-info-fetcher", post=fake_post, enforce_trading_hours=False)

    assert market_result["status"] == "success"
    assert intraday_result["status"] == "success"
    assert news_result["status"] == "success"
    assert calls == ["/api/v1/collector/real/market", "/api/v1/collector/real/intraday", "/api/v1/collector/real/news"]
    assert all("collector/demo" not in (task.endpoint or "") for task in scheduler.default_tasks())
