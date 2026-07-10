import hashlib
import os
from datetime import date, datetime, timezone

os.environ["DATABASE_URL"] = "sqlite:///./data/test_market_agent.db"
os.environ["AUTO_SEED_DEMO_DATA"] = "false"
os.environ["STARTUP_SYNC_ENABLED"] = "false"
os.environ["NEWS_AUTO_SYNC_ENABLED"] = "false"
os.environ["PUSH_MESSAGE_ENABLED"] = "false"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import (
    KlineDaily,
    MarketSnapshot,
    Notification,
    PaperAccount,
    PaperCashFlow,
    PaperEquitySnapshot,
    PaperOrder,
    PaperPosition,
    PaperSession,
    PaperTrade,
    PaperWatchlist,
    Stock,
)
from app.services import paper_trading_service as paper_service


TRADING_TIME = datetime(2026, 7, 3, 6, 30, tzinfo=timezone.utc)
AFTER_HOURS = datetime(2026, 7, 3, 8, 5, tzinfo=timezone.utc)
NEXT_TRADING_DAY = datetime(2026, 7, 6, 1, 45, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def paper_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paper_service, "_now", lambda: TRADING_TIME)


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


def seed_daily_close(close: float = 10.0) -> None:
    with SessionLocal() as db:
        stock = db.query(Stock).filter(Stock.code == "300308.SZ").one()
        db.add(
            KlineDaily(
                stock_id=stock.id,
                trade_date=date(2026, 7, 2),
                open=close,
                high=close,
                low=close,
                close=close,
                volume=100000,
                amount=1000000,
            )
        )
        db.commit()


def seed_hs300_benchmark() -> None:
    with SessionLocal() as db:
        index = Stock(code="000300.SH", name="沪深300", market="SH", security_type="index", industry="指数")
        db.add(index)
        db.flush()
        db.add_all(
            [
                KlineDaily(
                    stock_id=index.id,
                    trade_date=date(2026, 7, 1),
                    open=4000,
                    high=4000,
                    low=4000,
                    close=4000,
                    volume=1,
                    amount=4000,
                ),
                KlineDaily(
                    stock_id=index.id,
                    trade_date=date(2026, 7, 3),
                    open=4200,
                    high=4200,
                    low=4200,
                    close=4200,
                    volume=1,
                    amount=4200,
                ),
            ]
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


def legacy_pbkdf2_password_hash(password: str) -> str:
    salt = "legacy-salt-for-tests"
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000).hex()
    return f"{salt}${digest}"


_phone_counter = 0


def next_phone() -> str:
    global _phone_counter
    _phone_counter += 1
    return f"139{_phone_counter:08d}"


def account_payload(client: TestClient, owner_name: str, password: str = "secret123", phone: str | None = None) -> dict[str, str]:
    normalized_phone = phone or next_phone()
    captcha = client.post("/api/v1/paper/account-captchas", json={"phone": normalized_phone})
    assert captcha.status_code == 200
    body = captcha.json()
    return {
        "owner_name": owner_name,
        "password": password,
        "phone": body["phone"],
        "captcha_id": body["captcha_id"],
        "captcha_code": body["captcha_code"],
    }


def create_account(client: TestClient, owner_name: str, password: str = "secret123", phone: str | None = None):
    return client.post("/api/v1/paper/accounts", json=account_payload(client, owner_name, password, phone))


def create_and_login(client: TestClient) -> str:
    created = create_account(client, "demo")
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

        duplicate = create_account(client, "demo")
        assert duplicate.status_code == 400


def test_paper_account_passwords_use_bcrypt_and_reject_short_passwords():
    reset_database()

    with TestClient(app) as client:
        too_short = create_account(client, "shorty", password="12345")
        assert too_short.status_code == 422

        six_chars = create_account(client, "six-pass", password="123456")
        assert six_chars.status_code == 200

        created = create_account(client, "bcrypt-demo")
        assert created.status_code == 200

        with SessionLocal() as db:
            account = db.query(PaperAccount).filter(PaperAccount.owner_name == "bcrypt-demo").one()
            assert account.password_hash.startswith("$2")
            assert "secret123" not in account.password_hash

        short_login = client.post("/api/v1/paper/sessions", json={"owner_name": "bcrypt-demo", "password": "12345"})
        assert short_login.status_code == 422

        six_char_login = client.post("/api/v1/paper/sessions", json={"owner_name": "six-pass", "password": "123456"})
        assert six_char_login.status_code == 200

        login = client.post("/api/v1/paper/sessions", json={"owner_name": "bcrypt-demo", "password": "secret123"})
        assert login.status_code == 200


def test_legacy_pbkdf2_password_hash_is_upgraded_to_bcrypt_after_login():
    reset_database()

    with SessionLocal() as db:
        account = PaperAccount(owner_name="legacy-demo", password_hash=legacy_pbkdf2_password_hash("legacy123"))
        db.add(account)
        db.commit()

    with TestClient(app) as client:
        login = client.post("/api/v1/paper/sessions", json={"owner_name": "legacy-demo", "password": "legacy123"})
        assert login.status_code == 200

    with SessionLocal() as db:
        account = db.query(PaperAccount).filter(PaperAccount.owner_name == "legacy-demo").one()
        assert account.password_hash.startswith("$2")
        assert "$" in account.password_hash
        assert account.password_hash != legacy_pbkdf2_password_hash("legacy123")


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


def test_paper_account_creation_requires_phone_bound_captcha():
    reset_database()

    with TestClient(app) as client:
        invalid_phone = client.post("/api/v1/paper/account-captchas", json={"phone": "123456"})
        assert invalid_phone.status_code == 400

        first = client.post("/api/v1/paper/account-captchas", json={"phone": "13900000001"})
        assert first.status_code == 200
        first_body = first.json()
        assert first_body["phone"] == "13900000001"
        assert first_body["captcha_code"]

        wrong_phone = client.post(
            "/api/v1/paper/accounts",
            json={
                "owner_name": "phone-bound",
                "password": "secret123",
                "phone": "13900000002",
                "captcha_id": first_body["captcha_id"],
                "captcha_code": first_body["captcha_code"],
            },
        )
        assert wrong_phone.status_code == 400
        assert "手机号" in wrong_phone.json()["detail"]

        wrong_code = client.post(
            "/api/v1/paper/accounts",
            json={
                "owner_name": "phone-bound",
                "password": "secret123",
                "phone": "13900000001",
                "captcha_id": first_body["captcha_id"],
                "captcha_code": "WRONG1",
            },
        )
        assert wrong_code.status_code == 400

        created = client.post(
            "/api/v1/paper/accounts",
            json={
                "owner_name": "phone-bound",
                "password": "secret123",
                "phone": "13900000001",
                "captcha_id": first_body["captcha_id"],
                "captcha_code": first_body["captcha_code"],
            },
        )
        assert created.status_code == 200
        assert created.json()["phone"] == "13900000001"
        assert created.json()["masked_phone"] == "139****0001"

        reused = client.post(
            "/api/v1/paper/accounts",
            json={
                "owner_name": "phone-reuse",
                "password": "secret123",
                "phone": "13900000001",
                "captcha_id": first_body["captcha_id"],
                "captcha_code": first_body["captcha_code"],
            },
        )
        assert reused.status_code == 400

        registered_phone = client.post("/api/v1/paper/account-captchas", json={"phone": "13900000001"})
        assert registered_phone.status_code == 400
        assert "已注册" in registered_phone.json()["detail"]


def test_paper_accounts_list_exposes_registered_account_names_only():
    reset_database()

    with TestClient(app) as client:
        assert create_account(client, "beta").status_code == 200
        assert create_account(client, "alpha").status_code == 200

        response = client.get("/api/v1/paper/accounts")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        assert [account["owner_name"] for account in body["items"]] == ["alpha", "beta"]
        assert all("password_hash" not in account for account in body["items"])


def test_paper_watchlist_is_scoped_to_current_account():
    reset_database()
    seed_tradeable_stock(price=10.0)

    with TestClient(app) as client:
        anonymous = client.get("/api/v1/paper/watchlist")
        assert anonymous.status_code == 401

        first_token = create_and_login(client)
        created_second = create_account(client, "other")
        assert created_second.status_code == 200
        second_login = client.post("/api/v1/paper/sessions", json={"owner_name": "other", "password": "secret123"})
        assert second_login.status_code == 200
        second_token = second_login.json()["token"]

        created = client.post("/api/v1/paper/watchlist", headers=auth(first_token), json={"code": "300308.SZ"})
        assert created.status_code == 200
        assert created.json()["status"] == "created"
        assert created.json()["item"]["stock"]["code"] == "300308.SZ"

        duplicate = client.post("/api/v1/paper/watchlist", headers=auth(first_token), json={"code": "300308.SZ"})
        assert duplicate.status_code == 200
        assert duplicate.json()["status"] == "exists"

        first_list = client.get("/api/v1/paper/watchlist", headers=auth(first_token))
        second_list = client.get("/api/v1/paper/watchlist", headers=auth(second_token))

        assert first_list.status_code == 200
        assert second_list.status_code == 200
        assert first_list.json()["total"] == 1
        assert first_list.json()["items"][0]["stock"]["code"] == "300308.SZ"
        assert second_list.json()["total"] == 0

        blocked_delete = client.delete("/api/v1/paper/watchlist/300308.SZ", headers=auth(second_token))
        assert blocked_delete.status_code == 404

        deleted = client.delete("/api/v1/paper/watchlist/300308.SZ", headers=auth(first_token))
        assert deleted.status_code == 200
        assert deleted.json() == {"status": "deleted", "code": "300308.SZ"}
        assert client.get("/api/v1/paper/watchlist", headers=auth(first_token)).json()["total"] == 0


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
        assert len(positions) == 1
        position = positions[0]
        assert {
            "stock_id": position["stock_id"],
            "code": position["code"],
            "name": position["name"],
            "market": position["market"],
            "total_quantity": position["total_quantity"],
            "available_quantity": position["available_quantity"],
            "today_buy_quantity": position["today_buy_quantity"],
            "frozen_quantity": position["frozen_quantity"],
            "avg_cost": position["avg_cost"],
            "market_price": position["market_price"],
            "market_value": position["market_value"],
            "floating_pnl": position["floating_pnl"],
            "floating_pnl_pct": position["floating_pnl_pct"],
        } == {
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
        assert position["price_source"] == "market_snapshot"
        assert position["asset_ratio_pct"] == 0.2

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


def test_paper_admin_login_requires_admin_credentials():
    reset_database()

    with TestClient(app) as client:
        too_short = client.post("/api/v1/paper/admin/sessions", json={"username": "admin", "password": "admin"})
        assert too_short.status_code == 422

        rejected = client.post("/api/v1/paper/admin/sessions", json={"username": "admin", "password": "wrong.."})
        assert rejected.status_code == 401

        logged_in = client.post("/api/v1/paper/admin/sessions", json={"username": "admin", "password": "admin..."})
        assert logged_in.status_code == 200
        body = logged_in.json()
        assert body["admin"] == {"username": "admin"}
        assert body["token"]

        anonymous = client.get("/api/v1/paper/admin/overview")
        assert anonymous.status_code == 401

        overview = client.get("/api/v1/paper/admin/overview", headers=auth(body["token"]))
        assert overview.status_code == 200
        assert overview.json()["totals"]["account_count"] == 0


def test_paper_admin_overview_lists_account_cash_flows():
    reset_database()
    seed_tradeable_stock(price=10.0)

    with TestClient(app) as client:
        first_created = create_account(client, "alpha")
        assert first_created.status_code == 200
        first_login = client.post("/api/v1/paper/sessions", json={"owner_name": "alpha", "password": "secret123"})
        assert first_login.status_code == 200
        first_token = first_login.json()["token"]

        second_created = create_account(client, "beta")
        assert second_created.status_code == 200

        order = client.post(
            "/api/v1/paper/orders",
            headers=auth(first_token),
            json={"code": "300308.SZ", "side": "buy", "order_type": "market", "quantity": 100},
        )
        assert order.status_code == 200

        blocked = client.get("/api/v1/paper/admin/overview", headers=auth(first_token))
        assert blocked.status_code == 401

        admin_login = client.post("/api/v1/paper/admin/sessions", json={"username": "admin", "password": "admin..."})
        admin_token = admin_login.json()["token"]
        overview = client.get("/api/v1/paper/admin/overview", headers=auth(admin_token))

        assert overview.status_code == 200
        body = overview.json()
        assert body["totals"]["account_count"] == 2
        assert body["totals"]["flow_count"] == 2
        assert body["totals"]["flow_out"] == 1000.26
        assert {account["owner_name"] for account in body["accounts"]} == {"alpha", "beta"}

        alpha = next(account for account in body["accounts"] if account["owner_name"] == "alpha")
        beta = next(account for account in body["accounts"] if account["owner_name"] == "beta")
        assert alpha["flow_out"] == 1000.26
        assert alpha["net_flow"] == -1000.26
        assert alpha["trade_count"] == 1
        assert beta["flow_out"] == 0.0
        assert beta["net_flow"] == 0.0

        flows = body["flows"]["items"]
        assert [flow["flow_type"] for flow in flows] == ["fee", "buy_cost"]
        assert {flow["owner_name"] for flow in flows} == {"alpha"}
        assert flows[0]["account_id"] == alpha["account_id"]
        assert {flow["code"] for flow in flows} == {"300308.SZ"}
        assert {flow["name"] for flow in flows} == {"中际旭创"}


def test_paper_admin_can_update_and_reset_single_account():
    reset_database()
    seed_tradeable_stock(price=10.0)

    with TestClient(app) as client:
        first_token = create_and_login(client)
        order = client.post(
            "/api/v1/paper/orders",
            headers=auth(first_token),
            json={"code": "300308.SZ", "side": "buy", "order_type": "market", "quantity": 100},
        )
        assert order.status_code == 200
        assert create_account(client, "other").status_code == 200

        admin_login = client.post("/api/v1/paper/admin/sessions", json={"username": "admin", "password": "admin..."})
        assert admin_login.status_code == 200
        admin_token = admin_login.json()["token"]
        overview = client.get("/api/v1/paper/admin/overview", headers=auth(admin_token)).json()
        demo = next(account for account in overview["accounts"] if account["owner_name"] == "demo")

        blocked = client.patch(
            f"/api/v1/paper/admin/accounts/{demo['account_id']}",
            headers=auth(first_token),
            json={"status": "suspended"},
        )
        assert blocked.status_code == 401

        suspended = client.patch(
            f"/api/v1/paper/admin/accounts/{demo['account_id']}",
            headers=auth(admin_token),
            json={"status": "suspended"},
        )
        assert suspended.status_code == 200
        assert suspended.json()["status"] == "suspended"
        assert client.get("/api/v1/paper/summary", headers=auth(first_token)).status_code == 401

        restored = client.patch(
            f"/api/v1/paper/admin/accounts/{demo['account_id']}",
            headers=auth(admin_token),
            json={"status": "active"},
        )
        assert restored.status_code == 200
        assert restored.json()["status"] == "active"

        reset = client.post(f"/api/v1/paper/admin/accounts/{demo['account_id']}/reset", headers=auth(admin_token))
        assert reset.status_code == 200
        reset_body = reset.json()
        assert reset_body["account"]["id"] == demo["account_id"]
        assert reset_body["position_count"] == 0
        assert reset_body["trade_count"] == 0
        assert reset_body["cash_balance"] == 500000.0

        with SessionLocal() as db:
            account = db.get(PaperAccount, demo["account_id"])
            assert account is not None
            assert account.status == "active"
            assert db.query(PaperOrder).filter(PaperOrder.account_id == demo["account_id"]).count() == 0
            assert db.query(PaperTrade).filter(PaperTrade.account_id == demo["account_id"]).count() == 0
            assert db.query(PaperPosition).filter(PaperPosition.account_id == demo["account_id"]).count() == 0


def test_paper_admin_can_clear_all_accounts_and_related_data():
    reset_database()
    seed_tradeable_stock(price=10.0)

    with TestClient(app) as client:
        first_token = create_and_login(client)
        with SessionLocal() as db:
            account = db.query(PaperAccount).filter(PaperAccount.owner_name == "demo").one()
            stock = db.query(Stock).filter(Stock.code == "300308.SZ").one()
            db.add(PaperWatchlist(account_id=account.id, stock_id=stock.id, display_order=1))
            db.commit()
        order = client.post(
            "/api/v1/paper/orders",
            headers=auth(first_token),
            json={"code": "300308.SZ", "side": "buy", "order_type": "market", "quantity": 100},
        )
        assert order.status_code == 200
        assert create_account(client, "other").status_code == 200

        with SessionLocal() as db:
            assert db.query(PaperAccount).count() == 2
            assert db.query(PaperSession).count() == 1
            assert db.query(PaperWatchlist).count() == 1
            assert db.query(PaperOrder).count() == 1
            assert db.query(PaperTrade).count() == 1
            assert db.query(PaperPosition).count() == 1
            assert db.query(PaperCashFlow).count() == 2
            assert db.query(PaperEquitySnapshot).count() >= 2
            assert db.query(Notification).filter(Notification.notification_type.in_(("paper_order", "paper_trade", "paper_risk"))).count() >= 1

        blocked = client.delete("/api/v1/paper/admin/accounts", headers=auth(first_token))
        assert blocked.status_code == 401

        admin_login = client.post("/api/v1/paper/admin/sessions", json={"username": "admin", "password": "admin..."})
        admin_token = admin_login.json()["token"]
        cleared = client.delete("/api/v1/paper/admin/accounts", headers=auth(admin_token))

        assert cleared.status_code == 200
        body = cleared.json()
        assert body["status"] == "deleted"
        assert body["deleted"]["accounts"] == 2
        assert body["deleted"]["sessions"] == 1
        assert body["deleted"]["watchlist"] == 1
        assert body["deleted"]["orders"] == 1
        assert body["deleted"]["trades"] == 1
        assert body["deleted"]["positions"] == 1
        assert body["deleted"]["cash_flows"] == 2
        assert body["deleted"]["equity_snapshots"] >= 2
        assert body["deleted"]["notifications"] >= 1

        with SessionLocal() as db:
            assert db.query(PaperAccount).count() == 0
            assert db.query(PaperSession).count() == 0
            assert db.query(PaperWatchlist).count() == 0
            assert db.query(PaperOrder).count() == 0
            assert db.query(PaperTrade).count() == 0
            assert db.query(PaperPosition).count() == 0
            assert db.query(PaperCashFlow).count() == 0
            assert db.query(PaperEquitySnapshot).count() == 0
            assert db.query(Notification).filter(Notification.notification_type.in_(("paper_order", "paper_trade", "paper_risk"))).count() == 0

        assert client.get("/api/v1/paper/accounts").json()["total"] == 0
        assert client.get("/api/v1/paper/summary", headers=auth(first_token)).status_code == 401


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


def test_market_order_rejects_outside_trading_hours_and_limit_waits_for_session(monkeypatch: pytest.MonkeyPatch):
    reset_database()
    seed_tradeable_stock(price=10.0)

    with TestClient(app) as client:
        token = create_and_login(client)
        monkeypatch.setattr(paper_service, "_now", lambda: AFTER_HOURS)

        market = client.post(
            "/api/v1/paper/orders",
            headers=auth(token),
            json={"code": "300308.SZ", "side": "buy", "order_type": "market", "quantity": 100},
        )
        assert market.status_code == 400
        assert "交易时间" in market.json()["detail"]

        limit = client.post(
            "/api/v1/paper/orders",
            headers=auth(token),
            json={"code": "300308.SZ", "side": "buy", "order_type": "limit", "quantity": 100, "limit_price": 11.0},
        )
        assert limit.status_code == 200
        assert limit.json()["status"] == "pending"

        matched_after_hours = client.post("/api/v1/paper/match/run", headers=auth(token))
        assert matched_after_hours.status_code == 200
        assert matched_after_hours.json()["checked"] == 1
        assert matched_after_hours.json()["filled"] == 0

        monkeypatch.setattr(paper_service, "_now", lambda: NEXT_TRADING_DAY)
        matched_in_session = client.post("/api/v1/paper/match/run", headers=auth(token))
        assert matched_in_session.status_code == 200
        assert matched_in_session.json()["filled"] == 1


def test_orders_reject_prices_outside_daily_limit_band():
    reset_database()
    seed_tradeable_stock(price=13.0)
    seed_daily_close(close=10.0)

    with TestClient(app) as client:
        token = create_and_login(client)

        market = client.post(
            "/api/v1/paper/orders",
            headers=auth(token),
            json={"code": "300308.SZ", "side": "buy", "order_type": "market", "quantity": 100},
        )
        assert market.status_code == 400
        assert "涨跌停" in market.json()["detail"]

        limit = client.post(
            "/api/v1/paper/orders",
            headers=auth(token),
            json={"code": "300308.SZ", "side": "buy", "order_type": "limit", "quantity": 100, "limit_price": 13.0},
        )
        assert limit.status_code == 400
        assert "涨跌停" in limit.json()["detail"]


def test_beijing_exchange_market_order_uses_30_percent_limit_band():
    reset_database()
    with SessionLocal() as db:
        stock = Stock(code="920000.BJ", name="瀹夊窘鍑ゅ嚢", market="BJ", security_type="stock")
        db.add(stock)
        db.flush()
        db.add(
            MarketSnapshot(
                stock_id=stock.id,
                snapshot_time=datetime(2026, 7, 3, 14, 30, tzinfo=timezone.utc),
                price=30.0,
                change_pct=18.58,
                change_amount=4.7,
                volume=100000,
                amount=3000000,
                idempotency_key="paper-test-bj-920000",
            )
        )
        db.add(
            KlineDaily(
                stock_id=stock.id,
                trade_date=date(2026, 7, 2),
                open=25.3,
                high=25.3,
                low=25.3,
                close=25.3,
                volume=100000,
                amount=2530000,
            )
        )
        db.commit()

    with TestClient(app) as client:
        token = create_and_login(client)
        quote = client.get("/api/v1/paper/quote?code=920000.BJ", headers=auth(token))
        assert quote.status_code == 200
        assert quote.json()["limit_down"] == 17.71
        assert quote.json()["limit_up"] == 32.89
        assert quote.json()["limit_rate_pct"] == 30.0

        order = client.post(
            "/api/v1/paper/orders",
            headers=auth(token),
            json={"code": "920000.BJ", "side": "buy", "order_type": "market", "quantity": 100},
        )

        assert order.status_code == 200
        assert order.json()["status"] == "filled"
        assert order.json()["avg_fill_price"] == 30.0


def test_market_order_ignores_stale_daily_limit_band():
    reset_database()
    seed_tradeable_stock(price=13.0)
    with SessionLocal() as db:
        stock = db.query(Stock).filter(Stock.code == "300308.SZ").one()
        db.add(
            KlineDaily(
                stock_id=stock.id,
                trade_date=date(2026, 6, 30),
                open=10.0,
                high=10.0,
                low=10.0,
                close=10.0,
                volume=100000,
                amount=1000000,
            )
        )
        db.commit()

    with TestClient(app) as client:
        token = create_and_login(client)
        order = client.post(
            "/api/v1/paper/orders",
            headers=auth(token),
            json={"code": "300308.SZ", "side": "buy", "order_type": "market", "quantity": 100},
        )

        assert order.status_code == 200
        assert order.json()["status"] == "filled"
        assert order.json()["avg_fill_price"] == 13.0


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


def test_t1_quantity_rolls_to_available_on_next_trading_day(monkeypatch: pytest.MonkeyPatch):
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

        same_day_position = client.get("/api/v1/paper/positions", headers=auth(token)).json()["items"][0]
        assert same_day_position["available_quantity"] == 0
        assert same_day_position["today_buy_quantity"] == 100

        monkeypatch.setattr(paper_service, "_now", lambda: NEXT_TRADING_DAY)
        add_market_price(12.0, "paper-test-300308-t1-rollover")
        sold = client.post(
            "/api/v1/paper/orders",
            headers=auth(token),
            json={"code": "300308.SZ", "side": "sell", "order_type": "market", "quantity": 100},
        )

        assert sold.status_code == 200
        assert sold.json()["status"] == "filled"
        assert client.get("/api/v1/paper/positions", headers=auth(token)).json()["items"] == []


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
        assert body["profit_loss_ratio"] == 0.0
        assert "max_drawdown_pct" in body
        assert "annualized_return_pct" in body


def test_paper_equity_endpoint_returns_account_curve_with_benchmark():
    reset_database()
    seed_tradeable_stock(price=10.0)
    seed_hs300_benchmark()

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

        add_market_price(12.0, "paper-test-300308-equity")
        sold = client.post(
            "/api/v1/paper/orders",
            headers=auth(token),
            json={"code": "300308.SZ", "side": "sell", "order_type": "market", "quantity": 100},
        )
        assert sold.status_code == 200

        response = client.get("/api/v1/paper/equity", headers=auth(token))

        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 2
        latest = body["items"][-1]
        assert latest["total_assets"] == 500198.23
        assert latest["net_value"] == 1.00039646
        assert latest["benchmark_code"] == "000300.SH"
        assert latest["benchmark_value"] == 1.05


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
