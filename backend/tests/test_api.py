import os

os.environ["DATABASE_URL"] = "sqlite:///./data/test_market_agent.db"
os.environ["AUTO_SEED_DEMO_DATA"] = "false"

import pandas as pd
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.api import router as api_router
from app.main import app
from app.database import SessionLocal, engine
from app.models import CollectionJob, KlineDaily, News
from app.services.news_collector_service import NewsCollector
from app.services.real_collector_service import AkshareCollector


class FakeAkshare:
    def stock_zh_a_spot_em(self):
        return pd.DataFrame(
            [
                {"代码": "300308", "名称": "中际旭创", "最新价": 188.5, "涨跌幅": 2.1, "涨跌额": 3.8, "成交量": 10000, "成交额": 188500000, "今开": 185, "最高": 190, "最低": 184, "振幅": 3.2, "换手率": 2.0, "量比": 1.2, "市盈率-动态": 45, "市净率": 8.2, "总市值": 150000000000, "流通市值": 140000000000},
                {"代码": "300502", "名称": "新易盛", "最新价": 122.2, "涨跌幅": 1.5, "涨跌额": 1.8, "成交量": 9000, "成交额": 110000000, "今开": 120, "最高": 124, "最低": 119, "振幅": 4.0, "换手率": 1.8, "量比": 1.1, "市盈率-动态": 40, "市净率": 7.1, "总市值": 90000000000, "流通市值": 85000000000},
            ]
        )

    def stock_zh_index_spot_em(self, symbol: str):
        return pd.DataFrame(
            [
                {"代码": "000001", "名称": "上证指数", "最新价": 3100, "涨跌幅": 0.2, "涨跌额": 6, "成交量": 1000000, "成交额": 300000000000, "今开": 3090, "最高": 3110, "最低": 3080},
                {"代码": "399001", "名称": "深证成指", "最新价": 9800, "涨跌幅": 0.4, "涨跌额": 38, "成交量": 1000000, "成交额": 400000000000, "今开": 9760, "最高": 9850, "最低": 9700},
                {"代码": "399006", "名称": "创业板指", "最新价": 1900, "涨跌幅": 0.5, "涨跌额": 10, "成交量": 1000000, "成交额": 100000000000, "今开": 1888, "最高": 1910, "最低": 1870},
                {"代码": "000300", "名称": "沪深300", "最新价": 3600, "涨跌幅": 0.3, "涨跌额": 11, "成交量": 1000000, "成交额": 200000000000, "今开": 3580, "最高": 3620, "最低": 3570},
                {"代码": "000905", "名称": "中证500", "最新价": 5500, "涨跌幅": 0.1, "涨跌额": 5, "成交量": 1000000, "成交额": 150000000000, "今开": 5480, "最高": 5520, "最低": 5470},
            ]
        )

    def stock_zh_a_hist(self, symbol: str, period: str, start_date: str, end_date: str, adjust: str):
        return history_frame()

    def index_zh_a_hist(self, symbol: str, period: str, start_date: str, end_date: str):
        return history_frame()

    def stock_zh_a_hist_min_em(self, symbol: str, start_date: str, end_date: str, period: str, adjust: str):
        return intraday_frame(symbol)


def history_frame():
    rows = []
    for day in range(1, 31):
        rows.append({"日期": f"2026-04-{day:02d}", "开盘": 10 + day, "收盘": 10.2 + day, "最高": 10.5 + day, "最低": 9.8 + day, "成交量": 1000 + day, "成交额": 20000 + day, "振幅": 2.0, "涨跌幅": 1.0, "换手率": 0.8})
    return pd.DataFrame(rows)


def intraday_frame(symbol: str):
    rows = []
    for day in range(1, 13):
        for bar in ("09:35:00", "09:40:00"):
            rows.append(
                {
                    "时间": f"2026-05-{day:02d} {bar}",
                    "开盘": 100 + day,
                    "收盘": 100.5 + day,
                    "最高": 101 + day,
                    "最低": 99.5 + day,
                    "成交量": 5000 + day,
                    "成交额": 600000 + day,
                    "振幅": 1.2,
                    "涨跌幅": 0.5,
                    "涨跌额": 0.4,
                    "换手率": 0.2,
                }
            )
    return pd.DataFrame(rows)


def test_health_and_real_bootstrap(monkeypatch):
    monkeypatch.setattr(api_router, "AkshareCollector", lambda: AkshareCollector(FakeAkshare(), sleep_fn=lambda _: None))
    with TestClient(app) as client:
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        bootstrap = client.post("/api/v1/collector/real/bootstrap")
        assert bootstrap.status_code == 200
        market = client.get("/api/v1/market/snapshot?page_size=10")
        assert market.status_code == 200
        assert market.json()["total"] > 0
    with SessionLocal() as db:
        assert db.query(KlineDaily).filter(KlineDaily.source == "demo").count() == 0
        assert db.query(News).filter(News.source == "demo-finance").count() == 0


def test_trigger_analysis_for_real_watch_stock(monkeypatch):
    monkeypatch.setattr(api_router, "AkshareCollector", lambda: AkshareCollector(FakeAkshare(), sleep_fn=lambda _: None))
    with TestClient(app) as client:
        client.post("/api/v1/collector/real/bootstrap")
        response = client.post("/api/v1/analysis/300308.SZ")
        assert response.status_code == 200
        assert response.json()["signal"] in {"重点关注", "谨慎买入", "持有", "减仓", "回避"}


def test_collect_and_query_watchlist_intraday_5m(monkeypatch):
    monkeypatch.setattr(api_router, "AkshareCollector", lambda: AkshareCollector(FakeAkshare(), sleep_fn=lambda _: None))
    with TestClient(app) as client:
        client.post("/api/v1/collector/real/bootstrap")
        response = client.post("/api/v1/collector/real/intraday")
        assert response.status_code == 200
        assert response.json()["inserted"] == 100
        assert response.json()["failed"] == 0

        intraday = client.get("/api/v1/stocks/300308.SZ/intraday?period=5&days=10")
        assert intraday.status_code == 200
        body = intraday.json()
        assert body["total"] == 20
        assert body["items"][0]["period_minutes"] == 5
        assert body["items"][0]["bar_time"] == "2026-05-03T09:35:00"
        assert body["items"][-1]["bar_time"] == "2026-05-12T09:40:00"


def test_advice_summary_uses_bounded_queries(monkeypatch):
    monkeypatch.setattr(api_router, "AkshareCollector", lambda: AkshareCollector(FakeAkshare(), sleep_fn=lambda _: None))
    with TestClient(app) as client:
        client.post("/api/v1/collector/real/bootstrap")
        statements: list[str] = []

        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().lower().startswith("select"):
                statements.append(statement)

        event.listen(engine, "before_cursor_execute", before_cursor_execute)
        try:
            response = client.get("/api/v1/advice")
        finally:
            event.remove(engine, "before_cursor_execute", before_cursor_execute)

        assert response.status_code == 200
        assert response.json()["total"] == 5
        assert len(statements) <= 3


def test_settings_watchlist_limit_is_20():
    with TestClient(app) as client:
        response = client.get("/api/v1/settings")
        assert response.status_code == 200
        assert response.json()["risk_control"]["max_watchlist_size"] == 20
        assert response.json()["news"]["llm_provider"] == "deepseek"
        assert response.json()["news"]["api_base_url"] == "https://api.deepseek.com"
        assert response.json()["news"]["api_key_configured"] is False


class FakeNewsFetcher:
    def fetch_source(self, source_id: str, source_name: str, limit: int):
        return [
            {
                "source_id": source_id,
                "source_name": source_name,
                "id": "n-1",
                "title": "中际旭创CPO订单增长，AI算力链条延续高景气",
                "url": "https://example.com/news/1",
                "published_at": "2026-05-14T10:00:00+08:00",
                "raw": {"id": "n-1", "title": "中际旭创CPO订单增长，AI算力链条延续高景气"},
            }
        ]


class FakeNewsFormatter:
    model = "fake-deepseek"

    def format_items(self, items, watchlist):
        assert watchlist[0]["code"] == "300308.SZ"
        return [
            {
                "source_item_id": "n-1",
                "title": "中际旭创CPO订单增长",
                "summary": "DeepSeek整理：CPO和AI算力需求继续支撑光模块龙头订单。",
                "content": "DeepSeek整理正文：新闻提到中际旭创CPO订单增长，并提示关注AI算力链条景气度。",
                "source": "newsnow:财联社",
                "url": "https://example.com/news/1",
                "published_at": "2026-05-14T10:00:00+08:00",
                "scope": "stock",
                "code": "300308.SZ",
                "sentiment": "positive",
                "importance": 4,
                "raw_payload": {"source_item_id": "n-1"},
            }
        ]


def test_collect_real_news_with_deepseek_summary(monkeypatch):
    monkeypatch.setattr(
        api_router,
        "NewsCollector",
        lambda: NewsCollector(
            fetcher=FakeNewsFetcher(),
            formatter=FakeNewsFormatter(),
            source_ids=[("cls-telegraph", "财联社")],
            sleep_fn=lambda _: None,
        ),
    )
    monkeypatch.setattr(api_router, "AkshareCollector", lambda: AkshareCollector(FakeAkshare(), sleep_fn=lambda _: None))
    with TestClient(app) as client:
        client.post("/api/v1/collector/real/bootstrap")
        response = client.post("/api/v1/collector/real/news?limit=5")
        assert response.status_code == 200
        assert response.json()["inserted"] == 1

        news = client.get("/api/v1/news")
        assert news.status_code == 200
        body = news.json()
        assert body["total"] == 1
        item = body["items"][0]
        assert item["title"] == "中际旭创CPO订单增长"
        assert item["content"].startswith("DeepSeek整理正文")
        assert item["url"] == "https://example.com/news/1"
        assert item["source"] == "newsnow:财联社"
        assert item["code"] == "300308.SZ"

    with SessionLocal() as db:
        row = db.query(CollectionJob).filter(CollectionJob.job_type == "news").order_by(CollectionJob.id.desc()).first()
        assert row.source == "newsnow+deepseek"
        assert row.status == "success"
