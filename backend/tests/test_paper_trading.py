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
from app.models import MarketSnapshot, Notification, PaperPosition, Stock


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


def add_market_price(price: float, key: str) -> None:
    with SessionLocal() as db:
        stock = db.query(Stock).filter(Stock.code == "300308.SZ").one()
        db.add(
            MarketSnapshot(
                stock_id=stock.id,
                snapshot_time=datetime(2026, 7, 3, 14, 31, tzinfo=timezone.utc),
                price=price,
                change_pct=1.2,
                change_amount=0.12,
                volume=100000,
                amount=1000000,
                idempotency_key=key,
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


def test_paper_account_current_and_logout_revoke_session():
    reset_database()

    with TestClient(app) as client:
        token = create_and_login(client)
        account = client.get("/api/v1/paper/account", headers=auth(token))

        assert account.status_code == 200
        assert account.json()["owner_name"] == "demo"
        assert account.json()["cash_balance"] == 500000.0

        logged_out = client.delete("/api/v1/paper/sessions/current", headers=auth(token))

        assert logged_out.status_code == 200
        assert logged_out.json() == {"status": "revoked"}

        summary = client.get("/api/v1/paper/summary", headers=auth(token))
        assert summary.status_code == 401


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


def test_paper_cash_flows_support_filtering_and_pagination():
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

        flows = client.get("/api/v1/paper/cash-flows", headers=auth(token)).json()["items"]
        trade_date = flows[0]["created_at"][:10]
        response = client.get(
            f"/api/v1/paper/cash-flows?flow_type=fee&date_from={trade_date}&date_to={trade_date}&page=1&page_size=1",
            headers=auth(token),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["page"] == 1
        assert body["page_size"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["flow_type"] == "fee"
        assert body["items"][0]["amount"] == -0.26


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


def test_paper_trade_order_and_risk_notifications_are_recorded():
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

        pending = client.post(
            "/api/v1/paper/orders",
            headers=auth(token),
            json={"code": "300308.SZ", "side": "buy", "order_type": "limit", "quantity": 100, "limit_price": 9.0},
        )
        assert pending.status_code == 200

        cancelled = client.post(f"/api/v1/paper/orders/{pending.json()['id']}/cancel", headers=auth(token))
        assert cancelled.status_code == 200

        rejected = client.post(
            "/api/v1/paper/orders",
            headers=auth(token),
            json={"code": "300308.SZ", "side": "buy", "order_type": "market", "quantity": 50},
        )
        assert rejected.status_code == 400

    with SessionLocal() as db:
        notifications = db.query(Notification).order_by(Notification.id).all()
        by_type = {row.notification_type: [] for row in notifications}
        for row in notifications:
            by_type[row.notification_type].append(row)

    assert len(by_type["paper_trade"]) == 1
    assert by_type["paper_trade"][0].payload["code"] == "300308.SZ"
    assert by_type["paper_trade"][0].payload["status"] == "filled"
    assert by_type["paper_trade"][0].payload["quantity"] == 100

    assert [row.payload["status"] for row in by_type["paper_order"]] == ["pending", "cancelled"]
    assert by_type["paper_order"][0].payload["order_type"] == "limit"
    assert by_type["paper_order"][1].payload["order_id"] == pending.json()["id"]

    assert len(by_type["paper_risk"]) == 1
    assert by_type["paper_risk"][0].payload["code"] == "300308.SZ"
    assert by_type["paper_risk"][0].payload["order_type"] == "market"
    assert "100" in by_type["paper_risk"][0].content


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


def test_paper_orders_support_filtering_and_pagination():
    reset_database()
    seed_tradeable_stock(price=10.0)

    with TestClient(app) as client:
        token = create_and_login(client)
        filled = client.post(
            "/api/v1/paper/orders",
            headers=auth(token),
            json={"code": "300308.SZ", "side": "buy", "order_type": "market", "quantity": 100},
        )
        assert filled.status_code == 200

        pending = client.post(
            "/api/v1/paper/orders",
            headers=auth(token),
            json={"code": "300308.SZ", "side": "buy", "order_type": "limit", "quantity": 100, "limit_price": 9.0},
        )
        assert pending.status_code == 200

        response = client.get(
            "/api/v1/paper/orders?status=pending&order_type=limit&side=buy&code=300308.SZ&page=1&page_size=1",
            headers=auth(token),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["page"] == 1
        assert body["page_size"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["id"] == pending.json()["id"]
        assert body["items"][0]["status"] == "pending"
        assert body["items"][0]["order_type"] == "limit"


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


def test_match_run_fills_pending_limit_buy_at_latest_price_and_refunds_excess_freeze():
    reset_database()
    seed_tradeable_stock(price=10.0)

    with TestClient(app) as client:
        token = create_and_login(client)
        order = client.post(
            "/api/v1/paper/orders",
            headers=auth(token),
            json={"code": "300308.SZ", "side": "buy", "order_type": "limit", "quantity": 100, "limit_price": 9.0},
        ).json()
        assert order["status"] == "pending"
        add_market_price(8.0, "paper-test-300308-lower")

        matched = client.post("/api/v1/paper/match/run", headers=auth(token))

        assert matched.status_code == 200
        assert matched.json()["filled"] == 1
        assert matched.json()["triggered"] == 0

        filled_order = client.get("/api/v1/paper/orders", headers=auth(token)).json()["items"][0]
        assert filled_order["id"] == order["id"]
        assert filled_order["status"] == "filled"
        assert filled_order["avg_fill_price"] == 8.0
        assert filled_order["filled_quantity"] == 100
        assert filled_order["frozen_cash"] == 0.0

        summary = client.get("/api/v1/paper/summary", headers=auth(token)).json()
        assert summary["cash_balance"] == 499199.79
        assert summary["cash_available"] == 499199.79
        assert summary["cash_frozen"] == 0.0
        assert summary["open_order_count"] == 0


def test_take_profit_order_triggers_and_sells_on_match_run():
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

        take_profit = client.post(
            "/api/v1/paper/orders",
            headers=auth(token),
            json={"code": "300308.SZ", "side": "sell", "order_type": "take_profit", "quantity": 100, "trigger_price": 11.0},
        )
        assert take_profit.status_code == 200
        assert take_profit.json()["status"] == "monitoring"

        add_market_price(12.0, "paper-test-300308-profit")
        matched = client.post("/api/v1/paper/match/run", headers=auth(token))

        assert matched.status_code == 200
        assert matched.json()["triggered"] == 1
        assert matched.json()["filled"] == 1

        orders = client.get("/api/v1/paper/orders", headers=auth(token)).json()["items"]
        triggered = next(row for row in orders if row["order_type"] == "take_profit")
        assert triggered["status"] == "filled"
        assert triggered["avg_fill_price"] == 12.0
        assert triggered["filled_quantity"] == 100

        positions = client.get("/api/v1/paper/positions", headers=auth(token)).json()["items"]
        assert positions == []
        summary = client.get("/api/v1/paper/summary", headers=auth(token)).json()
        assert summary["trade_count"] == 2
        assert summary["open_order_count"] == 0


def test_paper_performance_summary_tracks_realized_returns():
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

        add_market_price(12.0, "paper-test-300308-performance")
        sold = client.post(
            "/api/v1/paper/orders",
            headers=auth(token),
            json={"code": "300308.SZ", "side": "sell", "order_type": "market", "quantity": 100},
        )
        assert sold.status_code == 200

        performance = client.get("/api/v1/paper/performance/summary", headers=auth(token))

        assert performance.status_code == 200
        body = performance.json()
        assert body["initial_cash"] == 500000.0
        assert body["current_total_assets"] == 500198.23
        assert body["total_return_pct"] == 0.04
        assert body["total_trades"] == 2
        assert body["closed_trade_count"] == 1
        assert body["winning_trades"] == 1
        assert body["losing_trades"] == 0
        assert body["win_rate_pct"] == 100.0
        assert body["realized_pnl"] == 198.23
        assert body["average_pnl"] == 198.23
        assert body["average_profit"] == 198.23
        assert body["average_loss"] == 0.0
        assert body["max_single_profit"] == 198.23
        assert body["max_single_loss"] == 0.0


def test_paper_performance_by_stock_summarizes_trades_and_position_pnl():
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

        add_market_price(12.0, "paper-test-300308-by-stock")
        sold = client.post(
            "/api/v1/paper/orders",
            headers=auth(token),
            json={"code": "300308.SZ", "side": "sell", "order_type": "market", "quantity": 100},
        )
        assert sold.status_code == 200

        response = client.get("/api/v1/paper/performance/by-stock", headers=auth(token))

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"] == [
            {
                "stock_id": 1,
                "code": "300308.SZ",
                "name": "中际旭创",
                "buy_quantity": 100,
                "sell_quantity": 100,
                "current_quantity": 0,
                "buy_amount": 1000.0,
                "sell_amount": 1200.0,
                "fee_total": 1.77,
                "realized_pnl": 198.23,
                "floating_pnl": 0.0,
                "total_pnl": 198.23,
                "trade_count": 2,
            }
        ]


def test_paper_performance_calendar_groups_daily_trading_activity():
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

        add_market_price(12.0, "paper-test-300308-calendar")
        sold = client.post(
            "/api/v1/paper/orders",
            headers=auth(token),
            json={"code": "300308.SZ", "side": "sell", "order_type": "market", "quantity": 100},
        )
        assert sold.status_code == 200

        response = client.get("/api/v1/paper/performance/calendar", headers=auth(token))

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        row = body["items"][0]
        assert row["realized_pnl"] == 198.23
        assert row["buy_amount"] == 1000.0
        assert row["sell_amount"] == 1200.0
        assert row["fee_total"] == 1.77
        assert row["trade_count"] == 2
        assert row["order_count"] == 2
        assert row["cash_flow_count"] == 4
        assert [trade["side"] for trade in row["trades"]] == ["sell", "buy"]
        assert {order["status"] for order in row["orders"]} == {"filled"}
        assert [flow["flow_type"] for flow in row["cash_flows"]] == ["fee", "sell_income", "fee", "buy_cost"]
