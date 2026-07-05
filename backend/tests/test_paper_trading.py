import os
from datetime import datetime, timezone

os.environ["DATABASE_URL"] = "sqlite:///./data/test_market_agent.db"
os.environ["AUTO_SEED_DEMO_DATA"] = "false"
os.environ["STARTUP_SYNC_ENABLED"] = "false"
os.environ["NEWS_AUTO_SYNC_ENABLED"] = "false"
os.environ["PUSH_MESSAGE_ENABLED"] = "false"

from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import MarketSnapshot, PaperPosition, Stock


def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def seed_tradeable_stock(price: float = 10.0) -> None:
    with SessionLocal() as db:
        stock = Stock(code="300308.SZ", name="中际旭创", market="SZ", security_type="stock", industry="CPO")
        db.add(stock)
        db.flush()
        db.add(
            MarketSnapshot(
                stock_id=stock.id,
                snapshot_time=datetime(2026, 7, 3, 14, 30, tzinfo=timezone.utc),
                price=price,
                change_pct=1.2,
                change_amount=0.12,
                volume=100000,
                amount=1000000,
                idempotency_key="paper-test-300308",
            )
        )
        db.commit()


def create_and_login(client: TestClient) -> str:
    created = client.post("/api/v1/paper/accounts", json={"owner_name": "demo", "password": "secret123"})
    assert created.status_code == 200
    login = client.post("/api/v1/paper/sessions", json={"owner_name": "demo", "password": "secret123"})
    assert login.status_code == 200
    return login.json()["token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_paper_account_create_login_and_summary_require_session():
    reset_database()

    with TestClient(app) as client:
        anonymous = client.get("/api/v1/paper/summary")
        assert anonymous.status_code == 401

        token = create_and_login(client)
        summary = client.get("/api/v1/paper/summary", headers=auth(token))

        assert summary.status_code == 200
        body = summary.json()
        assert body["account"]["owner_name"] == "demo"
        assert body["cash_balance"] == 500000.0
        assert body["cash_available"] == 500000.0
        assert body["position_market_value"] == 0.0
        assert body["total_assets"] == 500000.0

        duplicate = client.post("/api/v1/paper/accounts", json={"owner_name": "demo", "password": "secret123"})
        assert duplicate.status_code == 400


def test_paper_market_buy_fills_from_latest_snapshot_and_updates_portfolio():
    reset_database()
    seed_tradeable_stock(price=10.0)

    with TestClient(app) as client:
        token = create_and_login(client)
        order = client.post(
            "/api/v1/paper/orders",
            headers=auth(token),
            json={"code": "300308.SZ", "side": "buy", "order_type": "market", "quantity": 100},
        )

        assert order.status_code == 200
        body = order.json()
        assert body["status"] == "filled"
        assert body["avg_fill_price"] == 10.0
        assert body["filled_quantity"] == 100
        assert body["fee_total"] == 0.26

        summary = client.get("/api/v1/paper/summary", headers=auth(token)).json()
        assert summary["cash_balance"] == 498999.74
        assert summary["cash_available"] == 498999.74
        assert summary["position_market_value"] == 1000.0
        assert summary["total_assets"] == 499999.74
        assert summary["position_count"] == 1
        assert summary["trade_count"] == 1

        positions = client.get("/api/v1/paper/positions", headers=auth(token)).json()["items"]
        assert positions == [
            {
                "stock_id": 1,
                "code": "300308.SZ",
                "name": "中际旭创",
                "market": "SZ",
                "total_quantity": 100,
                "available_quantity": 0,
                "today_buy_quantity": 100,
                "frozen_quantity": 0,
                "avg_cost": 10.0026,
                "market_price": 10.0,
                "market_value": 1000.0,
                "floating_pnl": -0.26,
                "floating_pnl_pct": -0.026,
            }
        ]

        trades = client.get("/api/v1/paper/trades", headers=auth(token)).json()["items"]
        assert len(trades) == 1
        assert trades[0]["amount"] == 1000.0
        assert trades[0]["price_source"] == "market_snapshot"

        flows = client.get("/api/v1/paper/cash-flows", headers=auth(token)).json()["items"]
        assert [flow["flow_type"] for flow in flows] == ["fee", "buy_cost"]


def test_paper_order_rejects_invalid_lot_and_insufficient_cash():
    reset_database()
    seed_tradeable_stock(price=6000.0)

    with TestClient(app) as client:
        token = create_and_login(client)
        invalid_lot = client.post(
            "/api/v1/paper/orders",
            headers=auth(token),
            json={"code": "300308.SZ", "side": "buy", "order_type": "market", "quantity": 50},
        )
        assert invalid_lot.status_code == 400
        assert "100" in invalid_lot.json()["detail"]

        insufficient = client.post(
            "/api/v1/paper/orders",
            headers=auth(token),
            json={"code": "300308.SZ", "side": "buy", "order_type": "market", "quantity": 100},
        )
        assert insufficient.status_code == 400
        assert "资金不足" in insufficient.json()["detail"]


def test_limit_buy_pending_freezes_cash_and_cancel_releases_it():
    reset_database()
    seed_tradeable_stock(price=10.0)

    with TestClient(app) as client:
        token = create_and_login(client)
        order = client.post(
            "/api/v1/paper/orders",
            headers=auth(token),
            json={"code": "300308.SZ", "side": "buy", "order_type": "limit", "quantity": 100, "limit_price": 9.0},
        )

        assert order.status_code == 200
        body = order.json()
        assert body["status"] == "pending"
        assert body["filled_quantity"] == 0
        assert body["limit_price"] == 9.0
        assert body["frozen_cash"] == 900.24

        summary = client.get("/api/v1/paper/summary", headers=auth(token)).json()
        assert summary["cash_balance"] == 500000.0
        assert summary["cash_available"] == 499099.76
        assert summary["cash_frozen"] == 900.24
        assert summary["open_order_count"] == 1

        cancelled = client.post(f"/api/v1/paper/orders/{body['id']}/cancel", headers=auth(token))
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        assert cancelled.json()["frozen_cash"] == 0.0

        released = client.get("/api/v1/paper/summary", headers=auth(token)).json()
        assert released["cash_available"] == 500000.0
        assert released["cash_frozen"] == 0.0
        assert released["open_order_count"] == 0


def test_limit_sell_pending_freezes_position_and_cancel_releases_it():
    reset_database()
    seed_tradeable_stock(price=10.0)

    with TestClient(app) as client:
        token = create_and_login(client)
        bought = client.post(
            "/api/v1/paper/orders",
            headers=auth(token),
            json={"code": "300308.SZ", "side": "buy", "order_type": "market", "quantity": 100},
        )
        assert bought.status_code == 200

        with SessionLocal() as db:
            position = db.query(PaperPosition).one()
            position.available_quantity = 100
            position.today_buy_quantity = 0
            db.commit()

        order = client.post(
            "/api/v1/paper/orders",
            headers=auth(token),
            json={"code": "300308.SZ", "side": "sell", "order_type": "limit", "quantity": 100, "limit_price": 11.0},
        )

        assert order.status_code == 200
        body = order.json()
        assert body["status"] == "pending"
        assert body["filled_quantity"] == 0
        assert body["frozen_quantity"] == 100

        position_after_order = client.get("/api/v1/paper/positions", headers=auth(token)).json()["items"][0]
        assert position_after_order["available_quantity"] == 0
        assert position_after_order["frozen_quantity"] == 100

        cancelled = client.post(f"/api/v1/paper/orders/{body['id']}/cancel", headers=auth(token))
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        assert cancelled.json()["frozen_quantity"] == 0

        position_after_cancel = client.get("/api/v1/paper/positions", headers=auth(token)).json()["items"][0]
        assert position_after_cancel["available_quantity"] == 100
        assert position_after_cancel["frozen_quantity"] == 0


def test_same_day_market_sell_is_blocked_by_t1_rule():
    reset_database()
    seed_tradeable_stock(price=10.0)

    with TestClient(app) as client:
        token = create_and_login(client)
        bought = client.post(
            "/api/v1/paper/orders",
            headers=auth(token),
            json={"code": "300308.SZ", "side": "buy", "order_type": "market", "quantity": 100},
        )
        assert bought.status_code == 200

        sold = client.post(
            "/api/v1/paper/orders",
            headers=auth(token),
            json={"code": "300308.SZ", "side": "sell", "order_type": "market", "quantity": 100},
        )

        assert sold.status_code == 400
        assert "T+1" in sold.json()["detail"]
