from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import market_boards as routes
from app.services.market_board_service import MarketBoardService


def test_board_normalization_cache_expiry_and_stale_fallback():
    now = [0.0]
    calls = []
    blocked = [False]

    def fetch(params):
        calls.append(params)
        if blocked[0]:
            raise RuntimeError("provider unavailable")
        return {"total": 496, "diff": [
            {"f12": "BK1234", "f14": "测试行业", "f2": "-", "f3": 2.5, "f6": float("nan"), "f104": 9, "f105": 2, "f124": 1794382797},
            {"f12": "invalid", "f14": "无效数据"},
        ]}

    service = MarketBoardService(fetch, lambda: now[0])
    first = service.boards("industry")
    assert len(calls) == 2
    assert [p["po"] for p in calls] == ["1", "0"]
    assert all(p["pz"] == "4" and "t:2" in p["fs"] for p in calls)
    assert first["total"] == 496 and len(first["items"]) == 1
    assert first["items"][0]["price"] is None and first["items"][0]["amount"] is None
    assert first["items"][0]["quote_time"].endswith("+00:00")
    assert first["error"] is None and first["stale"] is False
    now[0] = 299
    assert service.boards("industry") == first
    assert len(calls) == 2
    blocked[0] = True
    now[0] = 301
    stale = service.boards("industry")
    assert stale["stale"] and stale["error"]
    assert stale["items"] == first["items"] and stale["fetched_at"] == first["fetched_at"]
    now[0] = 320
    service.boards("industry")
    assert len(calls) == 3  # Failed sources are not retried on every page read.
    blocked[0] = False
    now[0] = 362
    assert service.boards("industry")["stale"] is False
    assert len(calls) == 5


def test_empty_source_does_not_invent_boards_and_cools_down():
    calls = []
    service = MarketBoardService(lambda params: calls.append(params) or {"diff": [], "total": 0})
    result = service.boards("concept")
    assert result["items"] == [] and result["total"] == 0
    assert result["error"] and not result["stale"] and result["fetched_at"] is None
    service.boards("concept")
    assert len(calls) == 2
    assert "t:3" in calls[0]["fs"]


def test_constituents_keep_real_nulls_exchange_and_page():
    calls = []

    def fetch(params):
        calls.append(params)
        return {"total": 99, "diff": {str(i): {"f12": code, "f14": code, "f2": "-", "f3": -1.2, "f124": 0} for i, code in enumerate(["600000", "300308", "920001", "830001", "bad"])}}

    service = MarketBoardService(fetch)
    result = service.constituents("BK1128", 2, 20, "asc")
    assert [item["code"] for item in result["items"]] == ["600000.SH", "300308.SZ", "920001.BJ", "830001.BJ"]
    assert all(item["price"] is None and item["change_pct"] == -1.2 for item in result["items"])
    assert result["total"] == 99 and result["page"] == 2
    assert calls[0]["pn"] == "2" and calls[0]["po"] == "0"
    service.constituents("BK1128", 2, 20, "asc")
    assert len(calls) == 1
    service.constituents("BK1128", 3, 20, "asc")
    assert len(calls) == 2


def test_board_routes_validate_and_only_offer_reads(monkeypatch):
    service = MarketBoardService(lambda _: {"total": 1, "diff": [{"f12": "BK1234", "f14": "行业"}]})
    monkeypatch.setattr(routes, "market_boards", service)
    app = FastAPI()
    app.include_router(routes.router)
    with TestClient(app) as client:
        assert client.get("/api/v1/market/boards").status_code == 200
        assert client.get("/api/v1/market/boards?kind=region").status_code == 422
        for suffix in ["bad/constituents", "BK1128/constituents?page=0", "BK1128/constituents?page_size=101", "BK1128/constituents?sort_order=random"]:
            assert client.get(f"/api/v1/market/boards/{suffix}").status_code == 422
        assert client.post("/api/v1/market/boards").status_code == 405
