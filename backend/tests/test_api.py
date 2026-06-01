import asyncio
import os
from datetime import date, datetime, timezone

os.environ["DATABASE_URL"] = "sqlite:///./data/test_market_agent.db"
os.environ["AUTO_SEED_DEMO_DATA"] = "false"
os.environ["STARTUP_SYNC_ENABLED"] = "false"
os.environ["NEWS_AUTO_SYNC_ENABLED"] = "false"
os.environ["PUSH_MESSAGE_ENABLED"] = "false"

import pandas as pd
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.api import router as api_router
from app.main import app
from app.database import Base, SessionLocal, engine
from app.models import CollectionJob, KlineDaily, KlineIntraday, News, Notification, Stock, TradingAdvice, Watchlist
from app.services import news_auto_sync_service, real_collector_service, watch_stock_sync_service
from app.services.event_bus import publish_event, subscribe, unsubscribe
from app.services.news_collector_service import NewsCollector, OpenAICompatibleNewsFormatter
from app.services.push_message_service import render_notification_markdown
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


class FakeInfoAkshare:
    def stock_info_sh_name_code(self):
        return pd.DataFrame([{"证券代码": "600000", "证券简称": "浦发银行"}])

    def stock_info_sz_name_code(self):
        return pd.DataFrame([{"A股代码": "000001", "A股简称": "平安银行", "所属行业": "J 金融业"}])

    def stock_info_bj_name_code(self):
        return pd.DataFrame([{"证券代码": "920000", "证券简称": "安徽凤凰", "所属行业": "汽车制造业"}])

    def stock_zh_a_hist(self, symbol: str, period: str, start_date: str, end_date: str, adjust: str):
        return history_frame()


class FakeBulkDailyAkshare(FakeInfoAkshare):
    hist_called = False

    def stock_zh_a_hist(self, symbol: str, period: str, start_date: str, end_date: str, adjust: str):
        self.hist_called = True
        raise RuntimeError("bulk full-market history should avoid stock_zh_a_hist")

    def stock_zh_a_daily(self, symbol: str, start_date: str, end_date: str, adjust: str):
        return history_frame()


class FakeResolveAkshare(FakeAkshare):
    def stock_zh_a_spot_em(self):
        base = super().stock_zh_a_spot_em()
        extra = pd.DataFrame(
            [
                {
                    "代码": "300999",
                    "名称": "测试光模块",
                    "最新价": 50.0,
                    "涨跌幅": 1.0,
                    "涨跌额": 0.5,
                    "成交量": 1000,
                    "成交额": 50000000,
                    "今开": 49.5,
                    "最高": 51.0,
                    "最低": 49.0,
                    "振幅": 4.0,
                    "换手率": 1.2,
                    "量比": 1.1,
                    "市盈率-动态": 30,
                    "市净率": 4,
                    "总市值": 5000000000,
                    "流通市值": 4500000000,
                }
            ]
        )
        return pd.concat([base, extra], ignore_index=True)


class FakeIndexUnavailableAkshare:
    def stock_zh_index_spot_em(self, symbol: str):
        raise RuntimeError("index spot unavailable")


class FakeStockSpotUnavailableAkshare(FakeAkshare):
    def stock_zh_a_spot_em(self):
        raise RuntimeError("stock spot unavailable")

    def stock_zh_a_spot(self):
        raise RuntimeError("sina spot unavailable")


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
        index = client.get("/api/v1/stocks/000001.SH")
        assert index.status_code == 200
        assert index.json()["latest_snapshot"]["price"] == 3100
        assert index.json()["latest_snapshot"]["change_pct"] == 0.2
    with SessionLocal() as db:
        assert db.query(KlineDaily).filter(KlineDaily.source == "demo").count() == 0
        assert db.query(News).filter(News.source == "demo-finance").count() == 0


def test_index_spot_falls_back_to_eastmoney(monkeypatch):
    def fake_eastmoney_get(self, url: str, params: dict[str, str]):
        assert url == real_collector_service.EASTMONEY_QUOTE_URL
        assert "secids" in params
        return {
            "data": {
                "diff": [
                    {"f12": "000001", "f14": "上证指数", "f2": 4057.74, "f3": -1.07, "f4": -43.95, "f5": 100, "f6": 200, "f7": 1.16, "f10": 0.88, "f15": 4093.04, "f16": 4045.69, "f17": 4067.16},
                    {"f12": "399001", "f14": "深证成指", "f2": 15000.0, "f3": -2.0, "f4": -300.0, "f5": 101, "f6": 201, "f7": 2.0, "f10": 0.9, "f15": 15300.0, "f16": 14900.0, "f17": 15200.0},
                    {"f12": "399006", "f14": "创业板指", "f2": 3800.0, "f3": -3.0, "f4": -120.0, "f5": 102, "f6": 202, "f7": 3.0, "f10": 0.91, "f15": 3920.0, "f16": 3790.0, "f17": 3900.0},
                    {"f12": "000300", "f14": "沪深300", "f2": 4800.0, "f3": -1.0, "f4": -48.0, "f5": 103, "f6": 203, "f7": 1.4, "f10": 0.92, "f15": 4860.0, "f16": 4790.0, "f17": 4850.0},
                    {"f12": "000905", "f14": "中证500", "f2": 8400.0, "f3": -1.5, "f4": -127.0, "f5": 104, "f6": 204, "f7": 1.8, "f10": 0.93, "f15": 8520.0, "f16": 8390.0, "f17": 8500.0},
                ]
            }
        }

    monkeypatch.setattr(AkshareCollector, "_eastmoney_get", fake_eastmoney_get)
    items, failed = AkshareCollector(FakeIndexUnavailableAkshare(), sleep_fn=lambda _: None)._build_index_spot_items(
        datetime(2026, 6, 1, tzinfo=timezone.utc)
    )
    by_code = {item["code"]: item for item in items}
    assert failed == []
    assert by_code["000001.SH"]["price"] == 4057.74
    assert by_code["000001.SH"]["change_pct"] == -1.07


def test_stock_spot_falls_back_to_eastmoney(monkeypatch):
    def fake_eastmoney_get(self, url: str, params: dict[str, str]):
        assert url == real_collector_service.EASTMONEY_A_SPOT_URL
        assert params["pn"] == "1"
        return {
            "data": {
                "total": 1,
                "diff": [
                    {"f12": "300308", "f14": "中际旭创", "f2": 1130.0, "f3": -2.68, "f4": -31.16, "f5": 269782, "f6": 30968403448.51, "f7": 6.0, "f8": 2.4, "f9": 45.0, "f10": 1.1, "f15": 1183.61, "f16": 1113.9, "f17": 1161.0, "f20": 1000000000, "f21": 900000000, "f23": 8.2},
                ],
            }
        }

    monkeypatch.setattr(AkshareCollector, "_eastmoney_get", fake_eastmoney_get)
    items = AkshareCollector(FakeStockSpotUnavailableAkshare(), sleep_fn=lambda _: None)._build_stock_spot_items(
        datetime(2026, 6, 1, tzinfo=timezone.utc),
        [{"code": "300308.SZ", "name": "中际旭创", "market": "SZ", "security_type": "stock", "industry": "CPO/光模块"}],
    )
    item = next(row for row in items if row["code"] == "300308.SZ")
    assert item["name"] == "中际旭创"
    assert item["price"] == 1130.0
    assert item["is_watch"] is True


def test_stock_spot_falls_back_to_sina_quotes(monkeypatch):
    def fake_eastmoney_get(self, url: str, params: dict[str, str]):
        raise RuntimeError("eastmoney unavailable")

    def fake_sina_quotes(self, targets: list[dict[str, str]]):
        return [{"代码": "300308.SZ", "名称": "中际旭创", "最新价": 1130.0, "涨跌幅": -2.68, "涨跌额": -31.16, "成交量": 26978189, "成交额": 30968403448.51, "今开": 1161.0, "最高": 1183.61, "最低": 1113.9}]

    monkeypatch.setattr(AkshareCollector, "_eastmoney_get", fake_eastmoney_get)
    monkeypatch.setattr(AkshareCollector, "_sina_quote_rows_for_targets", fake_sina_quotes)
    items = AkshareCollector(FakeStockSpotUnavailableAkshare(), sleep_fn=lambda _: None)._build_stock_spot_items(
        datetime(2026, 6, 1, tzinfo=timezone.utc),
        [{"code": "300308.SZ", "name": "中际旭创", "market": "SZ", "security_type": "stock", "industry": "CPO/光模块"}],
    )
    assert items[0]["code"] == "300308.SZ"
    assert items[0]["price"] == 1130.0


def test_index_spot_falls_back_to_sina_quotes(monkeypatch):
    def fake_eastmoney_get(self, url: str, params: dict[str, str]):
        raise RuntimeError("eastmoney unavailable")

    def fake_sina_quotes(self, targets: list[dict[str, str]]):
        return [{"代码": item["code"], "名称": item["name"], "最新价": 4057.74, "涨跌幅": -0.27, "涨跌额": -10.83, "成交量": 1, "成交额": 2, "今开": 4067.16, "最高": 4093.04, "最低": 4045.69} for item in real_collector_service.MAIN_INDICES]

    monkeypatch.setattr(AkshareCollector, "_eastmoney_get", fake_eastmoney_get)
    monkeypatch.setattr(AkshareCollector, "_sina_quote_rows_for_targets", fake_sina_quotes)
    items, failed = AkshareCollector(FakeIndexUnavailableAkshare(), sleep_fn=lambda _: None)._build_index_spot_items(
        datetime(2026, 6, 1, tzinfo=timezone.utc)
    )
    assert failed == []
    assert {item["code"] for item in items} == {item["code"] for item in real_collector_service.MAIN_INDICES}


def test_event_bus_delivers_events():
    async def run() -> None:
        subscriber = subscribe()
        try:
            publish_event("news.updated", {"inserted": 1})
            event = await asyncio.wait_for(subscriber.queue.get(), timeout=1)
            assert event["type"] == "news.updated"
            assert event["payload"] == {"inserted": 1}
        finally:
            unsubscribe(subscriber.id)

    asyncio.run(run())


def test_trigger_analysis_for_real_watch_stock(monkeypatch):
    monkeypatch.setattr(api_router, "AkshareCollector", lambda: AkshareCollector(FakeAkshare(), sleep_fn=lambda _: None))
    with TestClient(app) as client:
        client.post("/api/v1/collector/real/bootstrap")
        response = client.post("/api/v1/analysis/300308.SZ")
        assert response.status_code == 200
        assert response.json()["signal"] in {"重点关注", "谨慎买入", "持有", "减仓", "回避"}


def test_trigger_watchlist_analysis_route_is_not_shadowed(monkeypatch):
    monkeypatch.setattr(api_router, "AkshareCollector", lambda: AkshareCollector(FakeAkshare(), sleep_fn=lambda _: None))
    with TestClient(app) as client:
        client.post("/api/v1/collector/real/bootstrap")
        response = client.post("/api/v1/analysis/watchlist")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] > 0
        assert body["items"][0]["code"] != "WATCHLIST"


def test_add_watch_auto_triggers_analysis(monkeypatch):
    monkeypatch.setattr(api_router, "AkshareCollector", lambda: AkshareCollector(FakeInfoAkshare(), sleep_fn=lambda _: None))
    monkeypatch.setattr(watch_stock_sync_service, "AkshareCollector", lambda: AkshareCollector(FakeInfoAkshare(), sleep_fn=lambda _: None, backoff_seconds=[]))
    with TestClient(app) as client:
        client.post("/api/v1/collector/real/full-market-history?days=365&limit=1")
        with SessionLocal() as db:
            stock = db.query(Stock).filter(Stock.code == "600000.SH").one()
            db.query(Watchlist).filter(Watchlist.stock_id == stock.id).delete()
            db.query(TradingAdvice).filter(TradingAdvice.stock_id == stock.id).delete()
            db.commit()

        response = client.post("/api/v1/watchlist", json={"code": "600000.SH"})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "created"
        assert body["analysis_status"] == "success"
        assert body["sync_status"] == "queued"
        assert body["latest_advice"]["code"] == "600000.SH"

        with SessionLocal() as db:
            stock = db.query(Stock).filter(Stock.code == "600000.SH").one()
            assert db.query(TradingAdvice).filter(TradingAdvice.stock_id == stock.id).count() >= 1
            jobs = db.query(CollectionJob).filter(CollectionJob.job_type == "watch_stock_sync").all()
            assert any((job.requested_payload or {}).get("code") == "600000.SH" for job in jobs)


def test_add_watch_resolves_missing_stock_and_syncs_required_data(monkeypatch):
    monkeypatch.setattr(api_router, "AkshareCollector", lambda: AkshareCollector(FakeResolveAkshare(), sleep_fn=lambda _: None, backoff_seconds=[]))
    monkeypatch.setattr(watch_stock_sync_service, "AkshareCollector", lambda: AkshareCollector(FakeResolveAkshare(), sleep_fn=lambda _: None, backoff_seconds=[]))
    with TestClient(app) as client:
        client.post("/api/v1/collector/real/bootstrap")
        response = client.post("/api/v1/watchlist", json={"code": "300999"})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "created"
        assert body["item"]["code"] == "300999.SZ"
        assert body["sync_status"] == "queued"

    with SessionLocal() as db:
        stock = db.query(Stock).filter(Stock.code == "300999.SZ").one()
        assert db.query(Watchlist).filter(Watchlist.stock_id == stock.id).count() == 1
        assert db.query(KlineDaily).filter(KlineDaily.stock_id == stock.id).count() > 0
        assert db.query(CollectionJob).filter(CollectionJob.job_type == "watch_stock_sync").order_by(CollectionJob.id.desc()).first().status == "success"


def test_remove_watch_keeps_collected_kline_data(monkeypatch):
    monkeypatch.setattr(api_router, "AkshareCollector", lambda: AkshareCollector(FakeAkshare(), sleep_fn=lambda _: None, backoff_seconds=[]))
    with TestClient(app) as client:
        client.post("/api/v1/collector/real/bootstrap")
        client.post("/api/v1/collector/real/intraday")
        with SessionLocal() as db:
            stock = db.query(Stock).filter(Stock.code == "300308.SZ").one()
            daily_count = db.query(KlineDaily).filter(KlineDaily.stock_id == stock.id).count()
            intraday_count = db.query(KlineIntraday).filter(KlineIntraday.stock_id == stock.id).count()
            assert daily_count > 0
            assert intraday_count > 0

        response = client.delete("/api/v1/watchlist/300308.SZ")
        assert response.status_code == 200

    with SessionLocal() as db:
        stock = db.query(Stock).filter(Stock.code == "300308.SZ").one()
        assert db.query(Watchlist).filter(Watchlist.stock_id == stock.id).count() == 0
        assert db.query(KlineDaily).filter(KlineDaily.stock_id == stock.id).count() == daily_count
        assert db.query(KlineIntraday).filter(KlineIntraday.stock_id == stock.id).count() == intraday_count


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


def test_collect_single_stock_intraday_for_detail_page(monkeypatch):
    monkeypatch.setattr(api_router, "AkshareCollector", lambda: AkshareCollector(FakeAkshare(), sleep_fn=lambda _: None))
    with TestClient(app) as client:
        client.post("/api/v1/collector/real/bootstrap")
        response = client.post("/api/v1/collector/real/intraday/300308.SZ?period=1&trading_days=1")
        assert response.status_code == 200
        body = response.json()
        assert body["code"] == "300308.SZ"
        assert body["period_minutes"] == 1
        assert body["inserted"] + body["updated"] == 2

        intraday = client.get("/api/v1/stocks/300308.SZ/intraday?period=1&days=1").json()
        assert intraday["total"] == 2
        assert intraday["items"][-1]["bar_time"] == "2026-05-12T09:40:00"

        other = client.get("/api/v1/stocks/300502.SZ/intraday?period=1&days=1").json()
        assert other["total"] == 0


def test_collect_single_stock_daily_kline_for_detail_page(monkeypatch):
    monkeypatch.setattr(api_router, "AkshareCollector", lambda: AkshareCollector(FakeAkshare(), sleep_fn=lambda _: None))
    with TestClient(app) as client:
        client.post("/api/v1/collector/real/bootstrap")
        with SessionLocal() as db:
            stock = db.query(Stock).filter(Stock.code == "300308.SZ").one()
            db.query(KlineDaily).filter(KlineDaily.stock_id == stock.id).delete()
            db.commit()

        response = client.post("/api/v1/collector/real/daily-kline/300308.SZ?days=365")
        assert response.status_code == 200
        body = response.json()
        assert body["code"] == "300308.SZ"
        assert body["days"] == 365
        assert body["inserted"] == 30
        assert body["failed"] == 0

        daily = client.get("/api/v1/stocks/300308.SZ/kline?limit=365").json()
        assert daily["total"] == 30


def test_intraday_query_limit_scales_for_minute_periods():
    assert api_router._intraday_query_limit(days=1, period_minutes=1) >= 240
    assert api_router._intraday_query_limit(days=10, period_minutes=1) >= 2400
    assert api_router._intraday_query_limit(days=10, period_minutes=5) >= 1200


def test_collect_full_market_history_persists_all_spot_stocks(monkeypatch):
    monkeypatch.setattr(api_router, "AkshareCollector", lambda: AkshareCollector(FakeAkshare(), sleep_fn=lambda _: None))
    with TestClient(app) as client:
        response = client.post("/api/v1/collector/real/full-market-history?days=365")
        assert response.status_code == 200
        body = response.json()
        assert body["total_targets"] == 2
        assert body["processed"] == 2
        assert body["inserted"] + body["updated"] == 60
        assert body["failed"] == 0

        first = client.get("/api/v1/stocks/300308.SZ/kline?limit=40")
        second = client.get("/api/v1/stocks/300502.SZ/kline?limit=40")
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["total"] == 30
        assert second.json()["total"] == 30


def test_collect_full_market_history_uses_exchange_code_list_when_spot_is_unavailable(monkeypatch):
    monkeypatch.setattr(api_router, "AkshareCollector", lambda: AkshareCollector(FakeInfoAkshare(), sleep_fn=lambda _: None))
    with TestClient(app) as client:
        response = client.post("/api/v1/collector/real/full-market-history?days=365")
        assert response.status_code == 200
        body = response.json()
        assert body["total_targets"] == 3
        assert body["processed"] == 3
        assert body["failed"] == 0

        bj = client.get("/api/v1/stocks/920000.BJ/kline?limit=40")
        assert bj.status_code == 200
        assert bj.json()["total"] == 30


def test_collect_full_market_history_prefers_daily_interface_for_bulk_import(monkeypatch):
    fake = FakeBulkDailyAkshare()
    monkeypatch.setattr(api_router, "AkshareCollector", lambda: AkshareCollector(fake, sleep_fn=lambda _: None))
    with TestClient(app) as client:
        response = client.post("/api/v1/collector/real/full-market-history?days=365&limit=1")
        assert response.status_code == 200
        body = response.json()
        assert body["total_targets"] == 1
        assert body["processed"] == 1
        assert body["failed"] == 0
        assert fake.hist_called is False


def test_start_full_market_history_uses_background_entrypoint(monkeypatch):
    fake = FakeBulkDailyAkshare()
    monkeypatch.setattr(api_router, "AkshareCollector", lambda: AkshareCollector(fake, sleep_fn=lambda _: None))
    with TestClient(app) as client:
        response = client.post("/api/v1/collector/real/full-market-history/start?days=365&limit=1")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "started"
        assert body["job_type"] == "full_market_daily_kline"
        assert body["limit"] == 1

        first = client.get("/api/v1/stocks/600000.SH/kline?limit=40")
        assert first.status_code == 200
        assert first.json()["total"] == 30


def test_start_missing_daily_kline_only_fills_targets_without_daily_kline(monkeypatch):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(api_router, "AkshareCollector", lambda: AkshareCollector(FakeInfoAkshare(), sleep_fn=lambda _: None))

    with SessionLocal() as db:
        stock = Stock(code="600000.SH", name="浦发银行", market="SH", security_type="stock")
        db.add(stock)
        db.flush()
        db.add(KlineDaily(stock_id=stock.id, trade_date=date(2026, 4, 1), close=1, source="test"))
        db.commit()

    with TestClient(app) as client:
        response = client.post("/api/v1/collector/real/missing-daily-kline/start?days=365")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "started"
        assert body["job_type"] == "missing_daily_kline"

    with SessionLocal() as db:
        existing = db.query(Stock).filter(Stock.code == "600000.SH").one()
        assert db.query(KlineDaily).filter(KlineDaily.stock_id == existing.id).count() == 1

        missing_filled = db.query(Stock).filter(Stock.code.in_(("000001.SZ", "920000.BJ"))).all()
        assert len(missing_filled) == 2
        assert sum(db.query(KlineDaily).filter(KlineDaily.stock_id == row.id).count() for row in missing_filled) == 60

        job = db.query(CollectionJob).filter(CollectionJob.job_type == "missing_daily_kline").order_by(CollectionJob.id.desc()).first()
        assert job is not None
        assert job.status == "success"
        assert job.result_summary["total_targets"] == 2
        assert job.result_summary["processed"] == 2
        assert job.result_summary["failed"] == 0


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
        assert response.json()["startup_sync"]["enabled"] is False


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
            }
        ]


class FakeArticleFetcher:
    def fetch(self, url: str) -> str:
        assert url == "https://example.com/news/1"
        return "原文正文：中际旭创CPO订单增长，AI算力链条延续高景气，机构关注光模块需求。"


class FakeNewsFormatter:
    model = "fake-deepseek"

    def format_items(self, items, watchlist):
        assert watchlist[0]["code"] == "300308.SZ"
        assert "article_text" in items[0]
        return [
            {
                "source_item_id": items[0]["source_item_id"],
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


class InvalidNewsFormatter:
    model = "broken-json-model"

    def format_items(self, items, watchlist):
        raise ValueError("LLM response is not valid JSON")


def test_deepseek_formatter_uses_v4_flash_non_thinking_timeout(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"items":[{"source_item_id":"1","title":"简化标题","summary":"摘要","content":"正文"}]}'
                        }
                    }
                ]
            }

    def fake_post(endpoint, timeout, headers, json):
        captured.update({"endpoint": endpoint, "timeout": timeout, "headers": headers, "json": json})
        return FakeResponse()

    monkeypatch.setattr("app.services.news_collector_service.requests.post", fake_post)
    formatter = OpenAICompatibleNewsFormatter(
        api_key="deepseek-test-key",
        api_base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        timeout=40,
    )

    result = formatter.format_items(
        [
            {
                "source_item_id": "1",
                "source": "newsnow:财联社",
                "title": "原始标题",
                "url": "https://example.com/news/1",
                "published_at": "2026-05-14T10:00:00+08:00",
                "article_text": "正文",
            }
        ],
        [],
    )

    assert result[0]["source_item_id"] == "1"
    assert captured["endpoint"] == "https://api.deepseek.com/chat/completions"
    assert captured["timeout"] == 40
    assert captured["headers"]["Authorization"] == "Bearer deepseek-test-key"
    assert captured["json"]["model"] == "deepseek-v4-flash"
    assert captured["json"]["thinking"] == {"type": "disabled"}


def test_collect_real_news_without_key_stores_pending_metadata(monkeypatch):
    monkeypatch.setattr(api_router, "AkshareCollector", lambda: AkshareCollector(FakeAkshare(), sleep_fn=lambda _: None))
    monkeypatch.setattr(
        api_router,
        "NewsCollector",
        lambda: NewsCollector(
            fetcher=FakeNewsFetcher(),
            source_ids=[("cls-telegraph", "财联社")],
            sleep_fn=lambda _: None,
        ),
    )
    with TestClient(app) as client:
        client.post("/api/v1/collector/real/bootstrap")
        response = client.post("/api/v1/collector/real/news?limit=5")
        assert response.status_code == 200
        body = response.json()
        assert body["inserted"] == 1
        assert body["simplify"]["skipped"] == 1

        news = client.get("/api/v1/news")
        item = news.json()["items"][0]
        assert item["title"] == "中际旭创CPO订单增长，AI算力链条延续高景气"
        assert item["original_title"] == "中际旭创CPO订单增长，AI算力链条延续高景气"
        assert item["content"] is None
        assert item["url"] == "https://example.com/news/1"
        assert item["simplification_status"] == "pending"


def test_collect_real_news_with_deepseek_summary(monkeypatch):
    monkeypatch.setattr(
        api_router,
        "NewsCollector",
        lambda: NewsCollector(
            fetcher=FakeNewsFetcher(),
            formatter=FakeNewsFormatter(),
            article_fetcher=FakeArticleFetcher(),
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
        assert item["original_title"] == "中际旭创CPO订单增长，AI算力链条延续高景气"
        assert item["content"].startswith("DeepSeek整理正文")
        assert item["url"] == "https://example.com/news/1"
        assert item["source"] == "newsnow:财联社"
        assert item["code"] == "300308.SZ"
        assert item["simplification_status"] == "simplified"
        assert item["llm_model"] == "fake-deepseek"
        assert item["simplified_at"] is not None

        notifications = client.get("/api/v1/notifications?status=pending").json()["items"]
        digest = next(row for row in notifications if row["notification_type"] == "news_digest" and row["payload"].get("news_id") == item["id"])
        assert digest["target_channel"] == "configured_qqbot_default"
        assert "财联社" in digest["title"]
        assert "https://example.com/news/1" in digest["content"]
        major = next(row for row in notifications if row["notification_type"] == "major_event" and row["payload"].get("news_id") == item["id"])
        assert major["payload"]["importance"] == 4
        assert "重大事件" in major["title"]

    with SessionLocal() as db:
        row = db.query(CollectionJob).filter(CollectionJob.job_type == "news").order_by(CollectionJob.id.desc()).first()
        assert row.source == "newsnow"
        assert row.status == "success"


def test_notification_markdown_is_structured_and_bounded():
    row = Notification(
        id=99,
        notification_type="major_event",
        target_channel="configured_qqbot_default",
        title="重大事件：测试公告",
        content="公司发布重大公告，涉及业绩增长和回购计划。" * 40,
        payload={"source": "newsnow:财联社", "url": "https://example.com/news/99", "importance": 5, "sentiment": "positive"},
    )
    markdown = render_notification_markdown(row)

    assert markdown.startswith("# 重大事件提醒")
    assert "- 类型：重大事件" in markdown
    assert "https://example.com/news/99" in markdown
    assert len(markdown) <= 600


def test_news_llm_config_is_saved_without_returning_key():
    triggered: list[bool] = []
    original = api_router.trigger_news_simplification
    api_router.trigger_news_simplification = lambda: triggered.append(True) or True
    with TestClient(app) as client:
        try:
            response = client.put(
                "/api/v1/news-llm-config",
                json={
                    "provider": "deepseek",
                    "api_base_url": "https://api.deepseek.com",
                    "model": "deepseek-v4-flash",
                    "api_key": "secret-key",
                    "prompt_preset": "default",
                    "custom_prompt": "请更简洁。",
                },
            )
            assert response.status_code == 200
            body = response.json()
            assert "api_key" not in body
            assert body["api_key_configured"] is True
            assert body["custom_prompt_configured"] is True
            assert body["simplification_triggered"] is True
            assert triggered == [True]

            settings_response = client.get("/api/v1/settings")
            assert settings_response.status_code == 200
            assert settings_response.json()["news"]["api_key_configured"] is True
        finally:
            api_router.trigger_news_simplification = original


def test_simplify_pending_news_updates_existing_metadata(monkeypatch):
    monkeypatch.setattr(api_router, "AkshareCollector", lambda: AkshareCollector(FakeAkshare(), sleep_fn=lambda _: None))
    monkeypatch.setattr(
        api_router,
        "NewsCollector",
        lambda: NewsCollector(
            fetcher=FakeNewsFetcher(),
            source_ids=[("cls-telegraph", "财联社")],
            sleep_fn=lambda _: None,
        ),
    )
    with TestClient(app) as client:
        client.post("/api/v1/collector/real/bootstrap")
        client.post("/api/v1/collector/real/news?limit=5")
        pending = client.get("/api/v1/news").json()["items"][0]
        assert pending["simplification_status"] == "pending"

        monkeypatch.setattr(
            api_router,
            "NewsCollector",
            lambda: NewsCollector(formatter=FakeNewsFormatter(), article_fetcher=FakeArticleFetcher()),
        )
        response = client.post("/api/v1/news/simplify-pending?limit=5")
        assert response.status_code == 200
        assert response.json()["simplified"] == 1

        item = client.get("/api/v1/news").json()["items"][0]
        assert item["simplification_status"] == "simplified"
        assert item["original_title"] == "中际旭创CPO订单增长，AI算力链条延续高景气"
        assert item["content"].startswith("DeepSeek整理正文")
        assert item["url"] == "https://example.com/news/1"
        with SessionLocal() as db:
            news_digest_count = db.query(Notification).filter(Notification.notification_type == "news_digest").count()
        response = client.post("/api/v1/news/simplify-pending?limit=5")
        assert response.status_code == 200
        with SessionLocal() as db:
            assert db.query(Notification).filter(Notification.notification_type == "news_digest").count() == news_digest_count


def test_simplify_pending_news_marks_invalid_llm_response_failed(monkeypatch):
    monkeypatch.setattr(api_router, "AkshareCollector", lambda: AkshareCollector(FakeAkshare(), sleep_fn=lambda _: None))
    monkeypatch.setattr(
        api_router,
        "NewsCollector",
        lambda: NewsCollector(
            fetcher=FakeNewsFetcher(),
            source_ids=[("cls-telegraph", "财联社")],
            sleep_fn=lambda _: None,
        ),
    )
    with TestClient(app) as client:
        client.post("/api/v1/collector/real/bootstrap")
        client.post("/api/v1/collector/real/news?limit=5")

        monkeypatch.setattr(
            api_router,
            "NewsCollector",
            lambda: NewsCollector(formatter=InvalidNewsFormatter(), article_fetcher=FakeArticleFetcher()),
        )
        response = client.post("/api/v1/news/simplify-pending?limit=5")
        assert response.status_code == 200
        assert response.json()["failed"] == 1

        item = client.get("/api/v1/news").json()["items"][0]
        assert item["simplification_status"] == "failed"
        assert "valid JSON" in item["error_message"]


def test_auto_sync_once_stores_pending_without_llm(monkeypatch):
    class AutoSyncNewsFetcher:
        def fetch_source(self, source_id: str, source_name: str, limit: int):
            return [
                {
                    "source_id": source_id,
                    "source_name": source_name,
                    "id": "auto-sync-1",
                    "title": "自动同步新闻元数据",
                    "url": "https://example.com/news/auto-sync-1",
                    "published_at": "2026-05-14T11:00:00+08:00",
                }
            ]

    monkeypatch.setattr(
        news_auto_sync_service,
        "NewsCollector",
        lambda: NewsCollector(
            fetcher=AutoSyncNewsFetcher(),
            source_ids=[("cls-telegraph", "财联社")],
            sleep_fn=lambda _: None,
        ),
    )
    summary = news_auto_sync_service.run_news_auto_sync_once()
    assert summary["inserted"] == 1
    assert summary["simplify"]["reason"] == "NEWS_LLM_API_KEY is not configured"
    with SessionLocal() as db:
        row = db.query(News).order_by(News.id.desc()).first()
        assert row.simplification_status == "pending"
