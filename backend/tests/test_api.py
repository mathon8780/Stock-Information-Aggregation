import os

os.environ["DATABASE_URL"] = "sqlite:///./data/test_market_agent.db"
os.environ["AUTO_SEED_DEMO_DATA"] = "false"

import pandas as pd
from fastapi.testclient import TestClient

from app.api import router as api_router
from app.main import app
from app.database import SessionLocal
from app.models import KlineDaily, News
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


def history_frame():
    rows = []
    for day in range(1, 31):
        rows.append({"日期": f"2026-04-{day:02d}", "开盘": 10 + day, "收盘": 10.2 + day, "最高": 10.5 + day, "最低": 9.8 + day, "成交量": 1000 + day, "成交额": 20000 + day, "振幅": 2.0, "涨跌幅": 1.0, "换手率": 0.8})
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
