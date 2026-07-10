from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

import bcrypt
from fastapi import HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

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
    TradingAdvice,
    WatchSnapshot,
)
from app.services.ingest_service import normalize_code
from app.services.notification_service import create_notification


INITIAL_CASH = Decimal("500000.0000")
COMMISSION_RATE = Decimal("0.00025")
STAMP_TAX_RATE = Decimal("0.001")
TRANSFER_FEE_RATE = Decimal("0.00001")
CN_TZ = ZoneInfo("Asia/Shanghai")
TRADING_SESSIONS = ((time(9, 30), time(11, 30)), (time(13, 0), time(15, 0)))
PAPER_ADMIN_USERNAME = "admin"
PAPER_ADMIN_PASSWORD_HASH = "$2b$12$XBROfPU//A.Myh6BRrAxJOBkf/dcOPsR0RKXn.Z9a29vkrmPFperu"
PAPER_ADMIN_SESSION_SECONDS = 24 * 60 * 60
BCRYPT_ROUNDS = 12
PAPER_ACCOUNT_CAPTCHA_SECONDS = 5 * 60
PAPER_ACCOUNT_CAPTCHA_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_admin_session_expires: dict[str, datetime] = {}
_account_captchas: dict[str, dict[str, object]] = {}


@dataclass(frozen=True)
class PaperPrice:
    price: Decimal
    source: str


@dataclass(frozen=True)
class PaperLimitBand:
    limit_up: Decimal
    limit_down: Decimal
    previous_close: Decimal
    rate_pct: Decimal
    trade_date: date


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_account_captcha(db: Session, phone: str) -> dict[str, object]:
    normalized_phone = normalize_phone(phone)
    _assert_valid_phone(normalized_phone)
    _assert_phone_available(db, normalized_phone)
    _cleanup_account_captchas()

    captcha_id = secrets.token_urlsafe(18)
    captcha_code = "".join(secrets.choice(PAPER_ACCOUNT_CAPTCHA_ALPHABET) for _ in range(6))
    _account_captchas[captcha_id] = {
        "phone": normalized_phone,
        "code": captcha_code,
        "expires_at": _now() + timedelta(seconds=PAPER_ACCOUNT_CAPTCHA_SECONDS),
        "used": False,
    }
    for key, item in list(_account_captchas.items()):
        if key != captcha_id and item.get("phone") == normalized_phone:
            _account_captchas.pop(key, None)
    return {
        "captcha_id": captcha_id,
        "phone": normalized_phone,
        "captcha_code": captcha_code,
        "expires_in": PAPER_ACCOUNT_CAPTCHA_SECONDS,
    }


def create_account(db: Session, owner_name: str, password: str, phone: str, captcha_id: str, captcha_code: str) -> dict[str, object]:
    normalized_name = owner_name.strip()
    normalized_phone = normalize_phone(phone)
    _assert_valid_phone(normalized_phone)
    existing = db.execute(select(PaperAccount).where(PaperAccount.owner_name == normalized_name)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=400, detail="模拟账户已存在")
    _assert_phone_available(db, normalized_phone)
    _verify_account_captcha(normalized_phone, captcha_id, captcha_code)
    account = PaperAccount(
        owner_name=normalized_name,
        phone=normalized_phone,
        password_hash=_hash_password(password),
        initial_cash=INITIAL_CASH,
        cash_balance=INITIAL_CASH,
        cash_available=INITIAL_CASH,
        cash_frozen=Decimal("0.0000"),
    )
    db.add(account)
    db.flush()
    _record_equity_snapshot(db, account, _now())
    db.commit()
    db.refresh(account)
    return account_dict(account)


def normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", str(phone or ""))


def _assert_valid_phone(phone: str) -> None:
    if not re.fullmatch(r"1[3-9]\d{9}", phone):
        raise HTTPException(status_code=400, detail="手机号格式不正确")


def _assert_phone_available(db: Session, phone: str) -> None:
    existing = db.execute(select(PaperAccount).where(PaperAccount.phone == phone)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=400, detail="手机号已注册")


def _verify_account_captcha(phone: str, captcha_id: str, captcha_code: str) -> None:
    _cleanup_account_captchas()
    item = _account_captchas.get(str(captcha_id or "").strip())
    if item is None or item.get("used"):
        raise HTTPException(status_code=400, detail="验证码不存在或已失效")
    if item.get("phone") != phone:
        raise HTTPException(status_code=400, detail="验证码与手机号不匹配")
    expected = str(item.get("code") or "")
    actual = str(captcha_code or "").strip().upper()
    if not hmac.compare_digest(expected.upper(), actual):
        raise HTTPException(status_code=400, detail="验证码不正确")
    item["used"] = True
    _account_captchas.pop(str(captcha_id or "").strip(), None)


def _cleanup_account_captchas() -> None:
    now = _now()
    for key, item in list(_account_captchas.items()):
        expires_at = item.get("expires_at")
        if item.get("used") or not isinstance(expires_at, datetime) or expires_at <= now:
            _account_captchas.pop(key, None)


def list_accounts(db: Session) -> dict[str, object]:
    accounts = db.execute(select(PaperAccount).order_by(PaperAccount.owner_name)).scalars().all()
    return {"items": [account_dict(account) for account in accounts], "total": len(accounts)}


def login_account(db: Session, owner_name: str, password: str) -> dict[str, object]:
    account = db.execute(select(PaperAccount).where(PaperAccount.owner_name == owner_name.strip())).scalar_one_or_none()
    if account is None or not _verify_password(password, account.password_hash):
        raise HTTPException(status_code=401, detail="账户名或密码错误")
    token = secrets.token_urlsafe(32)
    account.last_login_at = datetime.now(timezone.utc)
    if _password_hash_needs_upgrade(account.password_hash):
        account.password_hash = _hash_password(password)
    db.add(
        PaperSession(
            account_id=account.id,
            token_hash=_hash_token(token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
    )
    db.commit()
    db.refresh(account)
    return {"token": token, "account": account_dict(account)}


def login_admin(username: str, password: str) -> dict[str, object]:
    if username.strip() != PAPER_ADMIN_USERNAME or not _verify_bcrypt_password(password, PAPER_ADMIN_PASSWORD_HASH):
        raise HTTPException(status_code=401, detail="管理员账号或密码错误")
    _cleanup_admin_sessions()
    token = secrets.token_urlsafe(32)
    _admin_session_expires[_hash_token(token)] = datetime.now(timezone.utc) + timedelta(seconds=PAPER_ADMIN_SESSION_SECONDS)
    return {"token": token, "admin": {"username": PAPER_ADMIN_USERNAME}}


def admin_from_token(token: str) -> dict[str, str]:
    _cleanup_admin_sessions()
    token_hash = _hash_token(token)
    expires_at = _admin_session_expires.get(token_hash)
    if expires_at is None or expires_at <= datetime.now(timezone.utc):
        _admin_session_expires.pop(token_hash, None)
        raise HTTPException(status_code=401, detail="管理员登录已失效")
    return {"username": PAPER_ADMIN_USERNAME}


def revoke_admin_session(token: str) -> dict[str, str]:
    token_hash = _hash_token(token)
    if token_hash not in _admin_session_expires:
        raise HTTPException(status_code=401, detail="管理员登录已失效")
    _admin_session_expires.pop(token_hash, None)
    return {"status": "revoked"}


def account_from_token(db: Session, token: str) -> PaperAccount:
    session = db.execute(select(PaperSession).where(PaperSession.token_hash == _hash_token(token))).scalar_one_or_none()
    if session is None or session.revoked_at is not None or _session_expired(session):
        raise HTTPException(status_code=401, detail="模拟交易登录已失效")
    account = db.get(PaperAccount, session.account_id)
    if account is None or account.status != "active":
        raise HTTPException(status_code=401, detail="模拟账户不可用")
    return account


def revoke_session(db: Session, token: str) -> dict[str, str]:
    session = db.execute(select(PaperSession).where(PaperSession.token_hash == _hash_token(token))).scalar_one_or_none()
    if session is None or session.revoked_at is not None or _session_expired(session):
        raise HTTPException(status_code=401, detail="模拟交易登录已失效")
    session.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "revoked"}


def reset_account(db: Session, account: PaperAccount) -> dict[str, object]:
    for model in (PaperCashFlow, PaperTrade, PaperOrder, PaperPosition, PaperEquitySnapshot):
        db.query(model).filter(model.account_id == account.id).delete(synchronize_session=False)
    account.cash_balance = INITIAL_CASH
    account.cash_available = INITIAL_CASH
    account.cash_frozen = Decimal("0.0000")
    account.reset_at = _now()
    db.commit()
    db.refresh(account)
    return portfolio_summary(db, account)


def admin_get_account(db: Session, account_id: int) -> PaperAccount:
    account = db.get(PaperAccount, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="模拟账户不存在")
    return account


def admin_update_account_status(db: Session, account_id: int, status: str) -> dict[str, object]:
    if status not in {"active", "suspended"}:
        raise HTTPException(status_code=400, detail="账户状态不支持")
    account = admin_get_account(db, account_id)
    account.status = status
    if status != "active":
        db.query(PaperSession).filter(PaperSession.account_id == account.id, PaperSession.revoked_at.is_(None)).update(
            {PaperSession.revoked_at: _now()},
            synchronize_session=False,
        )
    db.commit()
    db.refresh(account)
    return account_dict(account)


def clear_all_accounts(db: Session) -> dict[str, object]:
    paper_notification_types = ("paper_order", "paper_trade", "paper_risk")
    deleted = {
        "notifications": db.query(Notification).filter(Notification.notification_type.in_(paper_notification_types)).delete(synchronize_session=False),
        "cash_flows": db.query(PaperCashFlow).delete(synchronize_session=False),
        "trades": db.query(PaperTrade).delete(synchronize_session=False),
        "orders": db.query(PaperOrder).delete(synchronize_session=False),
        "positions": db.query(PaperPosition).delete(synchronize_session=False),
        "equity_snapshots": db.query(PaperEquitySnapshot).delete(synchronize_session=False),
        "sessions": db.query(PaperSession).delete(synchronize_session=False),
        "watchlist": db.query(PaperWatchlist).delete(synchronize_session=False),
        "accounts": db.query(PaperAccount).delete(synchronize_session=False),
    }
    db.commit()
    return {"status": "deleted", "deleted": deleted}


def portfolio_summary(db: Session, account: PaperAccount) -> dict[str, object]:
    _rollover_t1_positions(db, account, _now())
    position_rows = _positions_with_stocks(db, account.id)
    market_value = _position_market_value(db, position_rows)
    total_assets = account.cash_balance + market_value
    return {
        "account": account_dict(account),
        "cash_balance": _decimal(account.cash_balance),
        "cash_available": _decimal(account.cash_available),
        "cash_frozen": _decimal(account.cash_frozen),
        "position_market_value": _decimal(market_value),
        "total_assets": _decimal(total_assets),
        "position_count": len(position_rows),
        "open_order_count": db.execute(select(func.count()).select_from(PaperOrder).where(PaperOrder.account_id == account.id, PaperOrder.status.in_(("pending", "monitoring", "partially_filled")))).scalar_one(),
        "trade_count": db.execute(select(func.count()).select_from(PaperTrade).where(PaperTrade.account_id == account.id)).scalar_one(),
    }


def performance_summary(db: Session, account: PaperAccount) -> dict[str, object]:
    portfolio = portfolio_summary(db, account)
    current_total_assets = Decimal(str(portfolio["total_assets"]))
    total_return_pct = Decimal("0.0000")
    if account.initial_cash:
        total_return_pct = ((current_total_assets - account.initial_cash) / account.initial_cash * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    trades = db.execute(select(PaperTrade).where(PaperTrade.account_id == account.id).order_by(PaperTrade.trade_time, PaperTrade.id)).scalars().all()
    closed_pnls = [trade.realized_pnl for trade in trades if trade.side == "sell" and trade.realized_pnl is not None]
    winning_pnls = [pnl for pnl in closed_pnls if pnl > 0]
    losing_pnls = [pnl for pnl in closed_pnls if pnl < 0]
    average_profit = _average_raw(winning_pnls)
    average_loss = _average_raw(losing_pnls)
    profit_loss_ratio = Decimal("0.0000")
    if average_profit > 0 and average_loss < 0:
        profit_loss_ratio = (average_profit / abs(average_loss)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    drawdown_pct = _max_drawdown_pct(db, account)
    annualized_return_pct = _annualized_return_pct(db, account, current_total_assets)

    return {
        "initial_cash": _decimal(account.initial_cash),
        "current_total_assets": _decimal(current_total_assets),
        "total_return_pct": float(total_return_pct),
        "total_trades": len(trades),
        "closed_trade_count": len(closed_pnls),
        "winning_trades": len(winning_pnls),
        "losing_trades": len(losing_pnls),
        "win_rate_pct": _ratio(len(winning_pnls), len(closed_pnls)),
        "realized_pnl": _decimal(sum(closed_pnls, Decimal("0.0000"))),
        "average_pnl": _average_decimal(closed_pnls),
        "average_profit": _decimal(average_profit),
        "average_loss": _decimal(average_loss),
        "profit_loss_ratio": float(profit_loss_ratio),
        "max_single_profit": _decimal(max(winning_pnls, default=Decimal("0.0000"))),
        "max_single_loss": _decimal(min(losing_pnls, default=Decimal("0.0000"))),
        "max_drawdown_pct": float(drawdown_pct),
        "annualized_return_pct": float(annualized_return_pct),
    }


def performance_by_stock(db: Session, account: PaperAccount) -> dict[str, object]:
    rows: dict[int, dict[str, object]] = {}

    trade_rows = db.execute(
        select(PaperTrade, Stock)
        .join(Stock, PaperTrade.stock_id == Stock.id)
        .where(PaperTrade.account_id == account.id)
        .order_by(Stock.code)
    ).all()
    for trade, stock in trade_rows:
        item = _performance_stock_item(rows, stock)
        item["trade_count"] = int(item["trade_count"]) + 1
        item["fee_total"] = Decimal(item["fee_total"]) + trade.fee_total
        if trade.side == "buy":
            item["buy_quantity"] = int(item["buy_quantity"]) + trade.quantity
            item["buy_amount"] = Decimal(item["buy_amount"]) + trade.amount
        else:
            item["sell_quantity"] = int(item["sell_quantity"]) + trade.quantity
            item["sell_amount"] = Decimal(item["sell_amount"]) + trade.amount
            item["realized_pnl"] = Decimal(item["realized_pnl"]) + (trade.realized_pnl or Decimal("0.0000"))

    for position, stock in _positions_with_stocks(db, account.id):
        item = _performance_stock_item(rows, stock)
        latest = _latest_price(db, stock.id).price
        floating_pnl = latest * position.total_quantity - position.cost_amount
        item["current_quantity"] = position.total_quantity
        item["floating_pnl"] = floating_pnl

    items = []
    for item in rows.values():
        realized_pnl = Decimal(item["realized_pnl"])
        floating_pnl = Decimal(item["floating_pnl"])
        items.append(
            {
                "stock_id": item["stock_id"],
                "code": item["code"],
                "name": item["name"],
                "buy_quantity": item["buy_quantity"],
                "sell_quantity": item["sell_quantity"],
                "current_quantity": item["current_quantity"],
                "buy_amount": _decimal(Decimal(item["buy_amount"])),
                "sell_amount": _decimal(Decimal(item["sell_amount"])),
                "fee_total": _decimal(Decimal(item["fee_total"])),
                "realized_pnl": _decimal(realized_pnl),
                "floating_pnl": _decimal(floating_pnl),
                "total_pnl": _decimal(realized_pnl + floating_pnl),
                "trade_count": item["trade_count"],
            }
        )
    items.sort(key=lambda row: (row["total_pnl"], row["code"]), reverse=True)
    return {"items": items, "total": len(items)}


def performance_calendar(db: Session, account: PaperAccount, limit: int = 30) -> dict[str, object]:
    days: dict[str, dict[str, object]] = {}

    trade_rows = db.execute(
        select(PaperTrade, Stock)
        .join(Stock, PaperTrade.stock_id == Stock.id)
        .where(PaperTrade.account_id == account.id)
        .order_by(desc(PaperTrade.trade_time), desc(PaperTrade.id))
    ).all()
    for trade, stock in trade_rows:
        item = _calendar_day(days, trade.trade_time)
        item["trade_count"] = int(item["trade_count"]) + 1
        item["fee_total"] = Decimal(item["fee_total"]) + trade.fee_total
        if trade.side == "buy":
            item["buy_amount"] = Decimal(item["buy_amount"]) + trade.amount
        else:
            item["sell_amount"] = Decimal(item["sell_amount"]) + trade.amount
            item["realized_pnl"] = Decimal(item["realized_pnl"]) + (trade.realized_pnl or Decimal("0.0000"))
        item["trades"].append(trade_dict(trade, stock))

    order_rows = db.execute(
        select(PaperOrder, Stock)
        .join(Stock, PaperOrder.stock_id == Stock.id)
        .where(PaperOrder.account_id == account.id)
        .order_by(desc(PaperOrder.created_at), desc(PaperOrder.id))
    ).all()
    for order, stock in order_rows:
        item = _calendar_day(days, order.created_at)
        item["order_count"] = int(item["order_count"]) + 1
        item["orders"].append(order_dict(order, stock))

    cash_flows = db.execute(
        select(PaperCashFlow)
        .where(PaperCashFlow.account_id == account.id)
        .order_by(desc(PaperCashFlow.created_at), desc(PaperCashFlow.id))
    ).scalars().all()
    for flow in cash_flows:
        item = _calendar_day(days, flow.created_at)
        item["cash_flow_count"] = int(item["cash_flow_count"]) + 1
        item["cash_flows"].append(cash_flow_dict(flow))

    items = []
    for item in days.values():
        items.append(
            {
                "trade_date": item["trade_date"],
                "realized_pnl": _decimal(Decimal(item["realized_pnl"])),
                "buy_amount": _decimal(Decimal(item["buy_amount"])),
                "sell_amount": _decimal(Decimal(item["sell_amount"])),
                "fee_total": _decimal(Decimal(item["fee_total"])),
                "trade_count": item["trade_count"],
                "order_count": item["order_count"],
                "cash_flow_count": item["cash_flow_count"],
                "trades": item["trades"],
                "orders": item["orders"],
                "cash_flows": item["cash_flows"],
            }
        )
    items.sort(key=lambda row: row["trade_date"], reverse=True)
    return {"items": items[:limit], "total": len(items)}


def _performance_stock_item(rows: dict[int, dict[str, object]], stock: Stock) -> dict[str, object]:
    if stock.id not in rows:
        rows[stock.id] = {
            "stock_id": stock.id,
            "code": stock.code,
            "name": stock.name,
            "buy_quantity": 0,
            "sell_quantity": 0,
            "current_quantity": 0,
            "buy_amount": Decimal("0.0000"),
            "sell_amount": Decimal("0.0000"),
            "fee_total": Decimal("0.0000"),
            "realized_pnl": Decimal("0.0000"),
            "floating_pnl": Decimal("0.0000"),
            "trade_count": 0,
        }
    return rows[stock.id]


def _calendar_day(rows: dict[str, dict[str, object]], value: datetime) -> dict[str, object]:
    trade_date = value.date().isoformat()
    if trade_date not in rows:
        rows[trade_date] = {
            "trade_date": trade_date,
            "realized_pnl": Decimal("0.0000"),
            "buy_amount": Decimal("0.0000"),
            "sell_amount": Decimal("0.0000"),
            "fee_total": Decimal("0.0000"),
            "trade_count": 0,
            "order_count": 0,
            "cash_flow_count": 0,
            "trades": [],
            "orders": [],
            "cash_flows": [],
        }
    return rows[trade_date]


def list_positions(db: Session, account: PaperAccount) -> dict[str, object]:
    _rollover_t1_positions(db, account, _now())
    total_assets = Decimal(str(portfolio_summary(db, account)["total_assets"]))
    items = []
    for position, stock in _positions_with_stocks(db, account.id):
        latest = _latest_price(db, stock.id)
        market_value = latest.price * position.total_quantity
        floating_pnl = market_value - position.cost_amount
        floating_pnl_pct = Decimal("0.0000")
        if position.cost_amount:
            floating_pnl_pct = (floating_pnl / position.cost_amount * Decimal("100")).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        asset_ratio_pct = Decimal("0.0000")
        if total_assets:
            asset_ratio_pct = (market_value / total_assets * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        advice = _latest_advice(db, stock.id)
        items.append(
            {
                "stock_id": stock.id,
                "code": stock.code,
                "name": stock.name,
                "market": stock.market,
                "total_quantity": position.total_quantity,
                "available_quantity": position.available_quantity,
                "today_buy_quantity": position.today_buy_quantity,
                "frozen_quantity": position.frozen_quantity,
                "avg_cost": _decimal(position.avg_cost, 4),
                "market_price": _decimal(latest.price),
                "price_source": latest.source,
                "market_value": _decimal(market_value),
                "floating_pnl": _decimal(floating_pnl),
                "floating_pnl_pct": float(floating_pnl_pct),
                "asset_ratio_pct": float(asset_ratio_pct),
                "strategy_signal": advice.signal if advice else None,
                "strategy_confidence": _optional_decimal(advice.confidence) if advice else None,
            }
        )
    return {"items": items, "total": len(items)}


def list_orders(
    db: Session,
    account: PaperAccount,
    code: str | None = None,
    side: str | None = None,
    order_type: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, object]:
    conditions = [PaperOrder.account_id == account.id]
    if code:
        conditions.append(Stock.code == normalize_code(code))
    if side:
        conditions.append(PaperOrder.side == side)
    if order_type:
        conditions.append(PaperOrder.order_type == order_type)
    if status:
        conditions.append(PaperOrder.status == status)

    total = db.execute(select(func.count()).select_from(PaperOrder).join(Stock, PaperOrder.stock_id == Stock.id).where(*conditions)).scalar_one()
    rows = db.execute(
        select(PaperOrder, Stock)
        .join(Stock, PaperOrder.stock_id == Stock.id)
        .where(*conditions)
        .order_by(desc(PaperOrder.created_at), desc(PaperOrder.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {"items": [order_dict(order, stock) for order, stock in rows], "total": total, "page": page, "page_size": page_size}


def list_trades(db: Session, account: PaperAccount) -> dict[str, object]:
    rows = db.execute(select(PaperTrade, Stock).join(Stock, PaperTrade.stock_id == Stock.id).where(PaperTrade.account_id == account.id).order_by(desc(PaperTrade.trade_time), desc(PaperTrade.id))).all()
    return {"items": [trade_dict(trade, stock) for trade, stock in rows], "total": len(rows)}


def list_cash_flows(
    db: Session,
    account: PaperAccount,
    flow_type: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, object]:
    conditions = [PaperCashFlow.account_id == account.id]
    if flow_type:
        conditions.append(PaperCashFlow.flow_type == flow_type)
    if date_from:
        conditions.append(PaperCashFlow.created_at >= date_from)
    if date_to:
        conditions.append(PaperCashFlow.created_at <= date_to)

    total = db.execute(select(func.count()).select_from(PaperCashFlow).where(*conditions)).scalar_one()
    rows = db.execute(
        select(PaperCashFlow)
        .where(*conditions)
        .order_by(desc(PaperCashFlow.created_at), desc(PaperCashFlow.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).scalars().all()
    return {"items": [cash_flow_dict(row) for row in rows], "total": total, "page": page, "page_size": page_size}


def paper_admin_overview(
    db: Session,
    account_id: int | None = None,
    flow_type: str | None = None,
    page: int = 1,
    page_size: int = 100,
) -> dict[str, object]:
    accounts = db.execute(select(PaperAccount).order_by(desc(PaperAccount.created_at), desc(PaperAccount.id))).scalars().all()
    flow_stats = {account.id: _empty_flow_stats() for account in accounts}
    all_flows = db.execute(select(PaperCashFlow).order_by(PaperCashFlow.created_at, PaperCashFlow.id)).scalars().all()
    for flow in all_flows:
        stats = flow_stats.setdefault(flow.account_id, _empty_flow_stats())
        amount = Decimal(flow.amount)
        if amount >= 0:
            stats["flow_in"] += amount
        else:
            stats["flow_out"] += abs(amount)
        stats["net_flow"] += amount
        stats["flow_count"] += 1
        stats["last_flow_at"] = flow.created_at

    account_items: list[dict[str, object]] = []
    totals = {
        "account_count": len(accounts),
        "initial_cash": Decimal("0.0000"),
        "cash_balance": Decimal("0.0000"),
        "cash_available": Decimal("0.0000"),
        "cash_frozen": Decimal("0.0000"),
        "position_market_value": Decimal("0.0000"),
        "total_assets": Decimal("0.0000"),
        "flow_in": Decimal("0.0000"),
        "flow_out": Decimal("0.0000"),
        "net_flow": Decimal("0.0000"),
        "flow_count": 0,
        "trade_count": 0,
        "open_order_count": 0,
    }

    for account in accounts:
        position_rows = _positions_with_stocks(db, account.id)
        market_value = _safe_position_market_value(db, position_rows)
        total_assets = Decimal(account.cash_balance) + market_value
        open_order_count = db.execute(select(func.count()).select_from(PaperOrder).where(PaperOrder.account_id == account.id, PaperOrder.status.in_(("pending", "monitoring", "partially_filled")))).scalar_one()
        trade_count = db.execute(select(func.count()).select_from(PaperTrade).where(PaperTrade.account_id == account.id)).scalar_one()
        stats = flow_stats.get(account.id, _empty_flow_stats())
        item = {
            "account_id": account.id,
            "owner_name": account.owner_name,
            "status": account.status,
            "initial_cash": _decimal(account.initial_cash),
            "cash_balance": _decimal(account.cash_balance),
            "cash_available": _decimal(account.cash_available),
            "cash_frozen": _decimal(account.cash_frozen),
            "position_market_value": _decimal(market_value),
            "total_assets": _decimal(total_assets),
            "position_count": len(position_rows),
            "open_order_count": open_order_count,
            "trade_count": trade_count,
            "flow_in": _decimal(stats["flow_in"]),
            "flow_out": _decimal(stats["flow_out"]),
            "net_flow": _decimal(stats["net_flow"]),
            "flow_count": stats["flow_count"],
            "last_flow_at": stats["last_flow_at"].isoformat() if stats["last_flow_at"] else None,
            "created_at": account.created_at.isoformat() if account.created_at else None,
            "last_login_at": account.last_login_at.isoformat() if account.last_login_at else None,
        }
        account_items.append(item)
        totals["initial_cash"] += Decimal(account.initial_cash)
        totals["cash_balance"] += Decimal(account.cash_balance)
        totals["cash_available"] += Decimal(account.cash_available)
        totals["cash_frozen"] += Decimal(account.cash_frozen)
        totals["position_market_value"] += market_value
        totals["total_assets"] += total_assets
        totals["flow_in"] += stats["flow_in"]
        totals["flow_out"] += stats["flow_out"]
        totals["net_flow"] += stats["net_flow"]
        totals["flow_count"] += stats["flow_count"]
        totals["trade_count"] += trade_count
        totals["open_order_count"] += open_order_count

    conditions = []
    if account_id:
        conditions.append(PaperCashFlow.account_id == account_id)
    if flow_type:
        conditions.append(PaperCashFlow.flow_type == flow_type)
    total_flows = db.execute(select(func.count()).select_from(PaperCashFlow).where(*conditions)).scalar_one()
    flow_rows = db.execute(
        select(PaperCashFlow, PaperAccount, Stock)
        .join(PaperAccount, PaperCashFlow.account_id == PaperAccount.id)
        .join(PaperOrder, PaperCashFlow.order_id == PaperOrder.id, isouter=True)
        .join(Stock, PaperOrder.stock_id == Stock.id, isouter=True)
        .where(*conditions)
        .order_by(desc(PaperCashFlow.created_at), desc(PaperCashFlow.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    flow_types = db.execute(select(PaperCashFlow.flow_type).distinct().order_by(PaperCashFlow.flow_type)).scalars().all()

    return {
        "admin": {"username": PAPER_ADMIN_USERNAME},
        "accounts": account_items,
        "totals": {
            "account_count": totals["account_count"],
            "initial_cash": _decimal(totals["initial_cash"]),
            "cash_balance": _decimal(totals["cash_balance"]),
            "cash_available": _decimal(totals["cash_available"]),
            "cash_frozen": _decimal(totals["cash_frozen"]),
            "position_market_value": _decimal(totals["position_market_value"]),
            "total_assets": _decimal(totals["total_assets"]),
            "flow_in": _decimal(totals["flow_in"]),
            "flow_out": _decimal(totals["flow_out"]),
            "net_flow": _decimal(totals["net_flow"]),
            "flow_count": totals["flow_count"],
            "trade_count": totals["trade_count"],
            "open_order_count": totals["open_order_count"],
        },
        "flows": {
            "items": [admin_cash_flow_dict(flow, account, stock) for flow, account, stock in flow_rows],
            "total": total_flows,
            "page": page,
            "page_size": page_size,
        },
        "flow_types": flow_types,
    }


def paper_equity(db: Session, account: PaperAccount) -> dict[str, object]:
    if not db.execute(select(PaperEquitySnapshot).where(PaperEquitySnapshot.account_id == account.id).limit(1)).scalar_one_or_none():
        _record_equity_snapshot(db, account, _now())
        db.commit()
    rows = db.execute(
        select(PaperEquitySnapshot)
        .where(PaperEquitySnapshot.account_id == account.id)
        .order_by(PaperEquitySnapshot.snapshot_time, PaperEquitySnapshot.id)
    ).scalars().all()
    return {"items": [equity_snapshot_dict(row) for row in rows], "total": len(rows)}


def paper_quote(db: Session, code: str) -> dict[str, object]:
    stock = db.execute(select(Stock).where(Stock.code == normalize_code(code), Stock.security_type == "stock")).scalar_one_or_none()
    if stock is None:
        raise HTTPException(status_code=404, detail="交易标的不存在")
    latest = _latest_price(db, stock.id)
    band = _limit_band(db, stock)
    advice = _latest_advice(db, stock.id)
    return {
        "stock_id": stock.id,
        "code": stock.code,
        "name": stock.name,
        "market": stock.market,
        "price": _decimal(latest.price),
        "price_source": latest.source,
        "is_realtime": latest.source in {"watch_snapshot", "market_snapshot", "intraday"},
        "limit_up": _optional_decimal(band.limit_up if band else None),
        "limit_down": _optional_decimal(band.limit_down if band else None),
        "previous_close": _optional_decimal(band.previous_close if band else None),
        "limit_rate_pct": _optional_decimal(band.rate_pct if band else None),
        "strategy_signal": advice.signal if advice else None,
        "strategy_confidence": _optional_decimal(advice.confidence) if advice else None,
    }


def place_order(
    db: Session,
    account: PaperAccount,
    code: str,
    side: str,
    order_type: str,
    quantity: int,
    limit_price: float | None = None,
    trigger_price: float | None = None,
) -> dict[str, object]:
    now = _now()
    _rollover_t1_positions(db, account, now)
    if quantity < 100 or quantity % 100 != 0:
        raise HTTPException(status_code=400, detail="A 股模拟交易数量必须为 100 股整数倍")
    if order_type not in {"market", "limit", "take_profit", "stop_loss"}:
        raise HTTPException(status_code=400, detail="不支持的订单类型")
    if order_type == "limit" and limit_price is None:
        raise HTTPException(status_code=400, detail="限价单必须填写限价")
    if order_type in {"take_profit", "stop_loss"} and trigger_price is None:
        raise HTTPException(status_code=400, detail="条件单必须填写触发价")

    stock = db.execute(select(Stock).where(Stock.code == normalize_code(code), Stock.security_type == "stock")).scalar_one_or_none()
    if stock is None:
        raise HTTPException(status_code=404, detail="交易标的不存在")
    latest = _latest_price(db, stock.id)
    if order_type == "limit":
        limit = Decimal(str(limit_price))
        _assert_within_limit_band(db, stock, _money4(limit))
        order = _place_limit_order(db, account, stock, side, quantity, limit, latest, now)
        if order.status == "filled":
            _record_equity_snapshot(db, account, now)
        db.commit()
        db.refresh(order)
        return order_dict(order, stock)
    if order_type in {"take_profit", "stop_loss"}:
        trigger = Decimal(str(trigger_price))
        _assert_within_limit_band(db, stock, _money4(trigger))
        order = _place_condition_order(db, account, stock, side, order_type, quantity, trigger, now)
        db.commit()
        db.refresh(order)
        return order_dict(order, stock)
    _assert_in_trading_session(now)
    _assert_market_price_within_limit_band(db, stock, latest.price, now)
    amount = _money(latest.price * quantity)
    fees = calculate_fees(amount, side)
    fee_total = fees["fee_total"]
    if side == "buy":
        _fill_market_buy(db, account, stock, quantity, latest, amount, fees)
    else:
        _fill_market_sell(db, account, stock, quantity, latest, amount, fees)
    order = db.execute(select(PaperOrder).where(PaperOrder.account_id == account.id).order_by(desc(PaperOrder.id)).limit(1)).scalar_one()
    _record_equity_snapshot(db, account, now)
    db.commit()
    db.refresh(order)
    return order_dict(order, stock) | {"fee_total": _decimal(fee_total)}


def cancel_order(db: Session, account: PaperAccount, order_id: int) -> dict[str, object]:
    row = db.execute(
        select(PaperOrder, Stock)
        .join(Stock, PaperOrder.stock_id == Stock.id)
        .where(PaperOrder.id == order_id, PaperOrder.account_id == account.id)
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="委托不存在")
    order, stock = row
    if order.status not in {"pending", "monitoring", "partially_filled"}:
        raise HTTPException(status_code=400, detail="当前委托状态不可撤销")

    if order.side == "buy" and order.frozen_cash > 0:
        account.cash_available += order.frozen_cash
        account.cash_frozen -= order.frozen_cash
        _add_cash_flow(db, account, order.id, None, "unfreeze", order.frozen_cash, "撤销买入限价单释放冻结资金")
        order.frozen_cash = Decimal("0.0000")
    if order.side == "sell" and order.frozen_quantity > 0:
        position = _position_for_update(db, account.id, order.stock_id)
        position.available_quantity += order.frozen_quantity
        position.frozen_quantity -= order.frozen_quantity
        order.frozen_quantity = 0

    order.status = "cancelled"
    order.cancelled_at = _now()
    _notify_order_update(db, account, order, stock, "委托已撤销")
    db.commit()
    db.refresh(order)
    return order_dict(order, stock)


def record_risk_notification(
    db: Session,
    account: PaperAccount,
    code: str,
    side: str,
    order_type: str,
    quantity: int,
    reason: str,
) -> None:
    create_notification(
        db,
        "paper_risk",
        "模拟交易风控拒单",
        f"{account.owner_name} 的模拟交易委托被拒绝：{code} {side} {order_type} {quantity} 股。原因：{reason}",
        {
            "account_id": account.id,
            "owner_name": account.owner_name,
            "code": code,
            "side": side,
            "order_type": order_type,
            "quantity": quantity,
            "reason": reason,
        },
    )
    db.commit()


def run_matching(db: Session, account: PaperAccount) -> dict[str, int]:
    now = _now()
    _rollover_t1_positions(db, account, now)
    rows = db.execute(
        select(PaperOrder, Stock)
        .join(Stock, PaperOrder.stock_id == Stock.id)
        .where(PaperOrder.account_id == account.id, PaperOrder.status.in_(("pending", "monitoring")))
        .order_by(PaperOrder.created_at, PaperOrder.id)
    ).all()
    checked = 0
    triggered = 0
    filled = 0
    if not _is_trading_session(now):
        return {"checked": len(rows), "triggered": 0, "filled": 0}
    for order, stock in rows:
        checked += 1
        latest = _latest_price(db, stock.id)
        if not _price_within_limit_band(db, stock, latest.price):
            continue
        if order.order_type == "limit" and _limit_crosses(order, latest):
            _fill_existing_order(db, account, order, stock, latest)
            filled += 1
        elif order.order_type in {"take_profit", "stop_loss"} and _condition_crosses(order, latest):
            order.status = "triggered"
            order.triggered_at = now
            triggered += 1
            _fill_existing_order(db, account, order, stock, latest)
            filled += 1
    if filled:
        _record_equity_snapshot(db, account, now)
    db.commit()
    return {"checked": checked, "triggered": triggered, "filled": filled}


def calculate_fees(amount: Decimal, side: str) -> dict[str, Decimal]:
    commission = _money(amount * COMMISSION_RATE)
    transfer_fee = _money(amount * TRANSFER_FEE_RATE)
    stamp_tax = _money(amount * STAMP_TAX_RATE) if side == "sell" else Decimal("0.00")
    fee_total = _money(commission + transfer_fee + stamp_tax)
    return {
        "commission": commission,
        "transfer_fee": transfer_fee,
        "stamp_tax": stamp_tax,
        "fee_total": fee_total,
    }


def _place_limit_order(
    db: Session,
    account: PaperAccount,
    stock: Stock,
    side: str,
    quantity: int,
    limit_price: Decimal,
    latest: PaperPrice,
    now: datetime,
) -> PaperOrder:
    limit_price = _money4(limit_price)
    crosses = latest.price <= limit_price if side == "buy" else latest.price >= limit_price
    if crosses and _is_trading_session(now):
        _assert_market_price_within_limit_band(db, stock, latest.price, now)
        amount = _money(latest.price * quantity)
        fees = calculate_fees(amount, side)
        if side == "buy":
            _fill_market_buy(db, account, stock, quantity, latest, amount, fees, order_type="limit", limit_price=limit_price)
        else:
            _fill_market_sell(db, account, stock, quantity, latest, amount, fees, order_type="limit", limit_price=limit_price)
        return db.execute(select(PaperOrder).where(PaperOrder.account_id == account.id).order_by(desc(PaperOrder.id)).limit(1)).scalar_one()

    if side == "buy":
        freeze_amount = _money(limit_price * quantity)
        fees = calculate_fees(freeze_amount, "buy")
        frozen_cash = freeze_amount + fees["fee_total"]
        if account.cash_available < frozen_cash:
            raise HTTPException(status_code=400, detail="可用资金不足")
        account.cash_available -= frozen_cash
        account.cash_frozen += frozen_cash
        order = PaperOrder(
            account_id=account.id,
            stock_id=stock.id,
            side="buy",
            order_type="limit",
            status="pending",
            quantity=quantity,
            limit_price=limit_price,
            frozen_cash=frozen_cash,
            created_at=now,
        )
        db.add(order)
        db.flush()
        _add_cash_flow(db, account, order.id, None, "freeze", -frozen_cash, "买入限价单冻结资金")
        _notify_order_update(db, account, order, stock, "买入限价单待成交")
        return order

    position = _position_for_update(db, account.id, stock.id)
    if position.available_quantity < quantity:
        raise HTTPException(status_code=400, detail="可卖持仓不足，T+1 当日买入数量不可卖出")
    position.available_quantity -= quantity
    position.frozen_quantity += quantity
    order = PaperOrder(
        account_id=account.id,
        stock_id=stock.id,
        side="sell",
        order_type="limit",
        status="pending",
        quantity=quantity,
        limit_price=limit_price,
        frozen_quantity=quantity,
        created_at=now,
    )
    db.add(order)
    db.flush()
    _notify_order_update(db, account, order, stock, "卖出限价单待成交")
    return order


def _place_condition_order(
    db: Session,
    account: PaperAccount,
    stock: Stock,
    side: str,
    order_type: str,
    quantity: int,
    trigger_price: Decimal,
    now: datetime,
) -> PaperOrder:
    if side != "sell":
        raise HTTPException(status_code=400, detail="止盈/止损条件单当前仅支持卖出")
    position = _position_for_update(db, account.id, stock.id)
    if position.available_quantity < quantity:
        raise HTTPException(status_code=400, detail="可卖持仓不足，T+1 当日买入数量不可卖出")
    order = PaperOrder(
        account_id=account.id,
        stock_id=stock.id,
        side=side,
        order_type=order_type,
        status="monitoring",
        quantity=quantity,
        trigger_price=_money4(trigger_price),
        created_at=now,
    )
    db.add(order)
    db.flush()
    _notify_order_update(db, account, order, stock, "条件单监控中")
    return order


def _limit_crosses(order: PaperOrder, latest: PaperPrice) -> bool:
    if order.limit_price is None:
        return False
    return latest.price <= order.limit_price if order.side == "buy" else latest.price >= order.limit_price


def _condition_crosses(order: PaperOrder, latest: PaperPrice) -> bool:
    if order.trigger_price is None:
        return False
    if order.order_type == "take_profit":
        return latest.price >= order.trigger_price
    if order.order_type == "stop_loss":
        return latest.price <= order.trigger_price
    return False


def _fill_existing_order(db: Session, account: PaperAccount, order: PaperOrder, stock: Stock, latest: PaperPrice) -> None:
    amount = _money(latest.price * order.quantity)
    fees = calculate_fees(amount, order.side)
    if order.side == "buy":
        _fill_existing_buy(db, account, order, stock, latest, amount, fees)
    else:
        _fill_existing_sell(db, account, order, stock, latest, amount, fees)


def _fill_existing_buy(db: Session, account: PaperAccount, order: PaperOrder, stock: Stock, latest: PaperPrice, amount: Decimal, fees: dict[str, Decimal]) -> None:
    required = amount + fees["fee_total"]
    if order.frozen_cash > 0:
        refund = order.frozen_cash - required
        if refund < 0:
            raise HTTPException(status_code=400, detail="冻结资金不足，无法成交")
        account.cash_frozen -= order.frozen_cash
        account.cash_available += refund
        order.frozen_cash = Decimal("0.0000")
    elif account.cash_available >= required:
        account.cash_available -= required
    else:
        raise HTTPException(status_code=400, detail="可用资金不足")
    account.cash_balance -= required
    order.status = "filled"
    order.filled_quantity = order.quantity
    order.avg_fill_price = latest.price
    order.fee_total = fees["fee_total"]
    order.filled_at = _now()
    trade = _create_trade(db, account, order, stock, "buy", order.quantity, latest, amount, fees, realized_pnl=None)
    position = _position_for_update(db, account.id, stock.id)
    position.total_quantity += order.quantity
    position.today_buy_quantity += order.quantity
    position.cost_amount = _money4(position.cost_amount + amount + fees["fee_total"])
    position.avg_cost = _money4(position.cost_amount / position.total_quantity)
    _add_cash_flow(db, account, order.id, trade.id, "buy_cost", -amount, "委托撮合买入成交")
    _add_cash_flow(db, account, order.id, trade.id, "fee", -fees["fee_total"], "买入手续费")
    _notify_trade_filled(db, account, order, trade, stock)


def _fill_existing_sell(db: Session, account: PaperAccount, order: PaperOrder, stock: Stock, latest: PaperPrice, amount: Decimal, fees: dict[str, Decimal]) -> None:
    position = _position_for_update(db, account.id, stock.id)
    if order.frozen_quantity > 0:
        position.frozen_quantity -= order.frozen_quantity
        order.frozen_quantity = 0
    elif position.available_quantity >= order.quantity:
        position.available_quantity -= order.quantity
    else:
        raise HTTPException(status_code=400, detail="可卖持仓不足，T+1 当日买入数量不可卖出")
    cost_removed = _money4(position.avg_cost * order.quantity)
    realized_pnl = _money4(amount - cost_removed - fees["fee_total"])
    account.cash_balance += amount - fees["fee_total"]
    account.cash_available += amount - fees["fee_total"]
    order.status = "filled"
    order.filled_quantity = order.quantity
    order.avg_fill_price = latest.price
    order.fee_total = fees["fee_total"]
    order.filled_at = _now()
    trade = _create_trade(db, account, order, stock, "sell", order.quantity, latest, amount, fees, realized_pnl=realized_pnl)
    position.total_quantity -= order.quantity
    position.cost_amount = _money4(max(Decimal("0.0000"), position.cost_amount - cost_removed))
    position.realized_pnl = _money4(position.realized_pnl + realized_pnl)
    position.avg_cost = _money4(position.cost_amount / position.total_quantity) if position.total_quantity else Decimal("0.0000")
    _add_cash_flow(db, account, order.id, trade.id, "sell_income", amount, "委托撮合卖出成交")
    _add_cash_flow(db, account, order.id, trade.id, "fee", -fees["fee_total"], "卖出手续费")
    _notify_trade_filled(db, account, order, trade, stock)


def account_dict(account: PaperAccount) -> dict[str, object]:
    return {
        "id": account.id,
        "owner_name": account.owner_name,
        "phone": account.phone,
        "masked_phone": _mask_phone(account.phone),
        "initial_cash": _decimal(account.initial_cash),
        "cash_balance": _decimal(account.cash_balance),
        "cash_available": _decimal(account.cash_available),
        "cash_frozen": _decimal(account.cash_frozen),
        "status": account.status,
        "created_at": account.created_at.isoformat() if account.created_at else None,
        "last_login_at": account.last_login_at.isoformat() if account.last_login_at else None,
        "reset_at": account.reset_at.isoformat() if account.reset_at else None,
    }


def _mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    return f"{phone[:3]}****{phone[-4:]}"


def order_dict(order: PaperOrder, stock: Stock) -> dict[str, object]:
    return {
        "id": order.id,
        "stock_id": stock.id,
        "code": stock.code,
        "name": stock.name,
        "market": stock.market,
        "side": order.side,
        "order_type": order.order_type,
        "status": order.status,
        "quantity": order.quantity,
        "filled_quantity": order.filled_quantity,
        "limit_price": _optional_decimal(order.limit_price),
        "trigger_price": _optional_decimal(order.trigger_price),
        "avg_fill_price": _optional_decimal(order.avg_fill_price),
        "frozen_cash": _decimal(order.frozen_cash),
        "frozen_quantity": order.frozen_quantity,
        "fee_total": _decimal(order.fee_total),
        "reject_reason": order.reject_reason,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "filled_at": order.filled_at.isoformat() if order.filled_at else None,
    }


def trade_dict(trade: PaperTrade, stock: Stock) -> dict[str, object]:
    return {
        "id": trade.id,
        "order_id": trade.order_id,
        "stock_id": stock.id,
        "code": stock.code,
        "name": stock.name,
        "side": trade.side,
        "quantity": trade.quantity,
        "price": _decimal(trade.price),
        "amount": _decimal(trade.amount),
        "commission": _decimal(trade.commission),
        "stamp_tax": _decimal(trade.stamp_tax),
        "transfer_fee": _decimal(trade.transfer_fee),
        "fee_total": _decimal(trade.fee_total),
        "realized_pnl": _optional_decimal(trade.realized_pnl),
        "trade_time": trade.trade_time.isoformat() if trade.trade_time else None,
        "price_source": trade.price_source,
    }


def cash_flow_dict(flow: PaperCashFlow) -> dict[str, object]:
    return {
        "id": flow.id,
        "order_id": flow.order_id,
        "trade_id": flow.trade_id,
        "flow_type": flow.flow_type,
        "amount": _decimal(flow.amount),
        "cash_balance_after": _decimal(flow.cash_balance_after),
        "remark": flow.remark,
        "created_at": flow.created_at.isoformat() if flow.created_at else None,
    }


def admin_cash_flow_dict(flow: PaperCashFlow, account: PaperAccount, stock: Stock | None = None) -> dict[str, object]:
    return {
        "account_id": account.id,
        "owner_name": account.owner_name,
        "code": stock.code if stock else None,
        "name": stock.name if stock else None,
        **cash_flow_dict(flow),
    }


def equity_snapshot_dict(snapshot: PaperEquitySnapshot) -> dict[str, object]:
    return {
        "id": snapshot.id,
        "snapshot_time": snapshot.snapshot_time.isoformat() if snapshot.snapshot_time else None,
        "cash_balance": _decimal(snapshot.cash_balance),
        "cash_frozen": _decimal(snapshot.cash_frozen),
        "position_market_value": _decimal(snapshot.position_market_value),
        "total_assets": _decimal(snapshot.total_assets),
        "net_value": _decimal(snapshot.net_value, 8),
        "daily_return_pct": _optional_decimal(snapshot.daily_return_pct),
        "benchmark_code": snapshot.benchmark_code,
        "benchmark_value": _optional_decimal(snapshot.benchmark_value, 8),
    }


def _fill_market_buy(
    db: Session,
    account: PaperAccount,
    stock: Stock,
    quantity: int,
    latest: PaperPrice,
    amount: Decimal,
    fees: dict[str, Decimal],
    order_type: str = "market",
    limit_price: Decimal | None = None,
) -> None:
    required = amount + fees["fee_total"]
    if account.cash_available < required:
        raise HTTPException(status_code=400, detail="可用资金不足")
    now = _now()
    account.cash_balance -= required
    account.cash_available -= required
    order = PaperOrder(
        account_id=account.id,
        stock_id=stock.id,
        side="buy",
        order_type=order_type,
        status="filled",
        quantity=quantity,
        filled_quantity=quantity,
        limit_price=limit_price,
        avg_fill_price=latest.price,
        fee_total=fees["fee_total"],
        filled_at=now,
        created_at=now,
    )
    db.add(order)
    db.flush()
    trade = _create_trade(db, account, order, stock, "buy", quantity, latest, amount, fees, realized_pnl=None)
    position = _position_for_update(db, account.id, stock.id)
    position.total_quantity += quantity
    position.today_buy_quantity += quantity
    position.cost_amount = _money4(position.cost_amount + amount + fees["fee_total"])
    position.avg_cost = _money4(position.cost_amount / position.total_quantity)
    _add_cash_flow(db, account, order.id, trade.id, "buy_cost", -amount, "市价买入成交")
    _add_cash_flow(db, account, order.id, trade.id, "fee", -fees["fee_total"], "买入手续费")
    _notify_trade_filled(db, account, order, trade, stock)


def _fill_market_sell(
    db: Session,
    account: PaperAccount,
    stock: Stock,
    quantity: int,
    latest: PaperPrice,
    amount: Decimal,
    fees: dict[str, Decimal],
    order_type: str = "market",
    limit_price: Decimal | None = None,
) -> None:
    position = _position_for_update(db, account.id, stock.id)
    if position.available_quantity < quantity:
        raise HTTPException(status_code=400, detail="可卖持仓不足，T+1 当日买入数量不可卖出")
    now = _now()
    cost_removed = _money4(position.avg_cost * quantity)
    realized_pnl = _money4(amount - cost_removed - fees["fee_total"])
    account.cash_balance += amount - fees["fee_total"]
    account.cash_available += amount - fees["fee_total"]
    order = PaperOrder(
        account_id=account.id,
        stock_id=stock.id,
        side="sell",
        order_type=order_type,
        status="filled",
        quantity=quantity,
        filled_quantity=quantity,
        limit_price=limit_price,
        avg_fill_price=latest.price,
        fee_total=fees["fee_total"],
        filled_at=now,
        created_at=now,
    )
    db.add(order)
    db.flush()
    trade = _create_trade(db, account, order, stock, "sell", quantity, latest, amount, fees, realized_pnl=realized_pnl)
    position.total_quantity -= quantity
    position.available_quantity -= quantity
    position.cost_amount = _money4(max(Decimal("0.0000"), position.cost_amount - cost_removed))
    position.realized_pnl = _money4(position.realized_pnl + realized_pnl)
    position.avg_cost = _money4(position.cost_amount / position.total_quantity) if position.total_quantity else Decimal("0.0000")
    _add_cash_flow(db, account, order.id, trade.id, "sell_income", amount, "市价卖出成交")
    _add_cash_flow(db, account, order.id, trade.id, "fee", -fees["fee_total"], "卖出手续费")
    _notify_trade_filled(db, account, order, trade, stock)


def _create_trade(
    db: Session,
    account: PaperAccount,
    order: PaperOrder,
    stock: Stock,
    side: str,
    quantity: int,
    latest: PaperPrice,
    amount: Decimal,
    fees: dict[str, Decimal],
    realized_pnl: Decimal | None,
) -> PaperTrade:
    trade = PaperTrade(
        account_id=account.id,
        order_id=order.id,
        stock_id=stock.id,
        side=side,
        quantity=quantity,
        price=latest.price,
        amount=amount,
        commission=fees["commission"],
        stamp_tax=fees["stamp_tax"],
        transfer_fee=fees["transfer_fee"],
        fee_total=fees["fee_total"],
        realized_pnl=realized_pnl,
        trade_time=_now(),
        price_source=latest.source,
    )
    db.add(trade)
    db.flush()
    return trade


def _add_cash_flow(db: Session, account: PaperAccount, order_id: int, trade_id: int | None, flow_type: str, amount: Decimal, remark: str) -> None:
    db.add(
        PaperCashFlow(
            account_id=account.id,
            order_id=order_id,
            trade_id=trade_id,
            flow_type=flow_type,
            amount=amount,
            cash_balance_after=account.cash_balance,
            remark=remark,
            created_at=_now(),
        )
    )


def _notify_order_update(db: Session, account: PaperAccount, order: PaperOrder, stock: Stock, action: str) -> None:
    create_notification(
        db,
        "paper_order",
        f"模拟交易委托：{stock.name}",
        f"{action}：{stock.code} {order.side} {order.order_type} {order.quantity} 股，状态 {order.status}。",
        {
            "account_id": account.id,
            "owner_name": account.owner_name,
            "order_id": order.id,
            "stock_id": stock.id,
            "code": stock.code,
            "name": stock.name,
            "side": order.side,
            "order_type": order.order_type,
            "status": order.status,
            "quantity": order.quantity,
            "limit_price": _optional_decimal(order.limit_price),
            "trigger_price": _optional_decimal(order.trigger_price),
        },
    )


def _notify_trade_filled(db: Session, account: PaperAccount, order: PaperOrder, trade: PaperTrade, stock: Stock) -> None:
    create_notification(
        db,
        "paper_trade",
        f"模拟交易成交：{stock.name}",
        f"{stock.code} {trade.side} {trade.quantity} 股，成交价 {_decimal(trade.price):.2f}，成交金额 {_decimal(trade.amount):.2f}。",
        {
            "account_id": account.id,
            "owner_name": account.owner_name,
            "order_id": order.id,
            "trade_id": trade.id,
            "stock_id": stock.id,
            "code": stock.code,
            "name": stock.name,
            "side": trade.side,
            "order_type": order.order_type,
            "status": order.status,
            "quantity": trade.quantity,
            "price": _decimal(trade.price),
            "amount": _decimal(trade.amount),
            "fee_total": _decimal(trade.fee_total),
            "realized_pnl": _optional_decimal(trade.realized_pnl),
        },
    )


def _position_for_update(db: Session, account_id: int, stock_id: int) -> PaperPosition:
    position = db.execute(select(PaperPosition).where(PaperPosition.account_id == account_id, PaperPosition.stock_id == stock_id)).scalar_one_or_none()
    if position is None:
        position = PaperPosition(account_id=account_id, stock_id=stock_id)
        db.add(position)
        db.flush()
    return position


def _positions_with_stocks(db: Session, account_id: int) -> list[tuple[PaperPosition, Stock]]:
    return list(
        db.execute(
            select(PaperPosition, Stock)
            .join(Stock, PaperPosition.stock_id == Stock.id)
            .where(PaperPosition.account_id == account_id, PaperPosition.total_quantity > 0)
            .order_by(Stock.code)
        ).all()
    )


def _position_market_value(db: Session, position_rows: list[tuple[PaperPosition, Stock]]) -> Decimal:
    return sum((_latest_price(db, stock.id).price * position.total_quantity for position, stock in position_rows), Decimal("0.0000"))


def _record_equity_snapshot(db: Session, account: PaperAccount, snapshot_time: datetime) -> PaperEquitySnapshot:
    position_market_value = _position_market_value(db, _positions_with_stocks(db, account.id))
    total_assets = account.cash_balance + position_market_value
    net_value = Decimal("1.00000000")
    if account.initial_cash:
        net_value = (total_assets / account.initial_cash).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
    previous = db.execute(
        select(PaperEquitySnapshot)
        .where(PaperEquitySnapshot.account_id == account.id)
        .order_by(desc(PaperEquitySnapshot.snapshot_time), desc(PaperEquitySnapshot.id))
        .limit(1)
    ).scalar_one_or_none()
    daily_return_pct = None
    if previous is not None and previous.total_assets:
        daily_return_pct = ((total_assets - previous.total_assets) / previous.total_assets * Decimal("100")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    benchmark_code, benchmark_value = _benchmark_value(db)
    snapshot = PaperEquitySnapshot(
        account_id=account.id,
        snapshot_time=snapshot_time,
        cash_balance=account.cash_balance,
        cash_frozen=account.cash_frozen,
        position_market_value=_money4(position_market_value),
        total_assets=_money4(total_assets),
        net_value=net_value,
        daily_return_pct=daily_return_pct,
        benchmark_code=benchmark_code,
        benchmark_value=benchmark_value,
    )
    db.add(snapshot)
    db.flush()
    return snapshot


def _benchmark_value(db: Session) -> tuple[str | None, Decimal | None]:
    stock = db.execute(
        select(Stock)
        .where(Stock.security_type == "index", Stock.code.in_(("000300.SH", "399300.SZ")))
        .order_by(Stock.code)
        .limit(1)
    ).scalar_one_or_none()
    if stock is None:
        stock = db.execute(
            select(Stock)
            .where(Stock.security_type == "index", Stock.name.like("%沪深300%"))
            .order_by(Stock.code)
            .limit(1)
        ).scalar_one_or_none()
    if stock is None:
        return None, None
    first = db.execute(
        select(KlineDaily)
        .where(KlineDaily.stock_id == stock.id, KlineDaily.close.is_not(None))
        .order_by(KlineDaily.trade_date)
        .limit(1)
    ).scalar_one_or_none()
    latest = db.execute(
        select(KlineDaily)
        .where(KlineDaily.stock_id == stock.id, KlineDaily.close.is_not(None))
        .order_by(desc(KlineDaily.trade_date))
        .limit(1)
    ).scalar_one_or_none()
    if first is None or latest is None or not first.close:
        return stock.code, None
    return stock.code, (latest.close / first.close).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)


def _max_drawdown_pct(db: Session, account: PaperAccount) -> Decimal:
    snapshots = db.execute(
        select(PaperEquitySnapshot)
        .where(PaperEquitySnapshot.account_id == account.id)
        .order_by(PaperEquitySnapshot.snapshot_time, PaperEquitySnapshot.id)
    ).scalars().all()
    peak = Decimal("0.00000000")
    max_drawdown = Decimal("0.0000")
    for snapshot in snapshots:
        value = snapshot.net_value
        if value > peak:
            peak = value
        if peak:
            drawdown = (peak - value) / peak * Decimal("100")
            if drawdown > max_drawdown:
                max_drawdown = drawdown
    return max_drawdown.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _annualized_return_pct(db: Session, account: PaperAccount, current_total_assets: Decimal) -> Decimal:
    first = db.execute(
        select(PaperEquitySnapshot)
        .where(PaperEquitySnapshot.account_id == account.id)
        .order_by(PaperEquitySnapshot.snapshot_time, PaperEquitySnapshot.id)
        .limit(1)
    ).scalar_one_or_none()
    if first is None or not account.initial_cash:
        return Decimal("0.00")
    first_time = first.snapshot_time if first.snapshot_time.tzinfo is not None else first.snapshot_time.replace(tzinfo=timezone.utc)
    elapsed_days = max((_now() - first_time).total_seconds() / 86400, 1)
    total_ratio = current_total_assets / account.initial_cash
    annualized = (Decimal(str(float(total_ratio) ** (365 / elapsed_days))) - Decimal("1")) * Decimal("100")
    return annualized.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _rollover_t1_positions(db: Session, account: PaperAccount, now: datetime) -> None:
    current_date = _local_date(now)
    positions = db.execute(select(PaperPosition).where(PaperPosition.account_id == account.id, PaperPosition.today_buy_quantity > 0)).scalars().all()
    for position in positions:
        latest_buy = db.execute(
            select(PaperTrade)
            .where(PaperTrade.account_id == account.id, PaperTrade.stock_id == position.stock_id, PaperTrade.side == "buy")
            .order_by(desc(PaperTrade.trade_time), desc(PaperTrade.id))
            .limit(1)
        ).scalar_one_or_none()
        if latest_buy is None or _local_date(latest_buy.trade_time) < current_date:
            position.available_quantity += position.today_buy_quantity
            position.today_buy_quantity = 0


def _is_trading_session(value: datetime) -> bool:
    local = value.astimezone(CN_TZ)
    if local.weekday() >= 5:
        return False
    local_time = local.time()
    return any(start <= local_time <= end for start, end in TRADING_SESSIONS)


def _assert_in_trading_session(value: datetime) -> None:
    if not _is_trading_session(value):
        raise HTTPException(status_code=400, detail="市价单仅在交易时间 9:30-11:30、13:00-15:00 可用")


def _local_date(value: datetime) -> date:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(CN_TZ).date()


def _limit_band(db: Session, stock: Stock) -> PaperLimitBand | None:
    daily = db.execute(
        select(KlineDaily)
        .where(KlineDaily.stock_id == stock.id, KlineDaily.close.is_not(None))
        .order_by(desc(KlineDaily.trade_date))
        .limit(1)
    ).scalar_one_or_none()
    if daily is None or daily.close is None:
        return None
    rate = _limit_rate_for_stock(stock)
    return PaperLimitBand(
        limit_up=_money(daily.close * (Decimal("1") + rate)),
        limit_down=_money(daily.close * (Decimal("1") - rate)),
        previous_close=_money4(daily.close),
        rate_pct=(rate * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        trade_date=daily.trade_date,
    )


def _limit_rate_for_stock(stock: Stock) -> Decimal:
    raw_code = stock.code.split(".", 1)[0]
    name = (stock.name or "").upper()
    if "ST" in name:
        return Decimal("0.05")
    if stock.market == "BJ" or stock.code.endswith(".BJ") or raw_code.startswith(("430", "8", "4", "920")):
        return Decimal("0.30")
    if raw_code.startswith(("300", "301", "688")):
        return Decimal("0.20")
    return Decimal("0.10")


def _price_within_limit_band(db: Session, stock: Stock, price: Decimal) -> bool:
    band = _limit_band(db, stock)
    if band is None:
        return True
    return band.limit_down <= price <= band.limit_up


def _assert_within_limit_band(db: Session, stock: Stock, price: Decimal) -> None:
    band = _limit_band(db, stock)
    if band is None:
        return
    if price < band.limit_down or price > band.limit_up:
        raise HTTPException(status_code=400, detail=f"委托价格超出涨跌停范围：{_decimal(band.limit_down)} - {_decimal(band.limit_up)}")


def _assert_market_price_within_limit_band(db: Session, stock: Stock, price: Decimal, now: datetime) -> None:
    band = _limit_band(db, stock)
    if band is None:
        return
    if band.limit_down <= price <= band.limit_up:
        return
    if band.trade_date != _previous_trading_day(_local_date(now)):
        return
    raise HTTPException(status_code=400, detail=f"委托价格超出涨跌停范围：{_decimal(band.limit_down)} - {_decimal(band.limit_up)}")
    raise HTTPException(status_code=400, detail=f"濮旀墭浠锋牸瓒呭嚭娑ㄨ穼鍋滆寖鍥达細{_decimal(band.limit_down)} - {_decimal(band.limit_up)}")


def _previous_trading_day(value: date) -> date:
    previous = value - timedelta(days=1)
    while previous.weekday() >= 5:
        previous -= timedelta(days=1)
    return previous


def _latest_advice(db: Session, stock_id: int) -> TradingAdvice | None:
    return db.execute(
        select(TradingAdvice)
        .where(TradingAdvice.stock_id == stock_id)
        .order_by(desc(TradingAdvice.created_at))
        .limit(1)
    ).scalar_one_or_none()


def _latest_price(db: Session, stock_id: int) -> PaperPrice:
    watch = db.execute(select(WatchSnapshot).where(WatchSnapshot.stock_id == stock_id, WatchSnapshot.price.is_not(None)).order_by(desc(WatchSnapshot.snapshot_time)).limit(1)).scalar_one_or_none()
    if watch is not None and watch.price is not None:
        return PaperPrice(_money4(watch.price), "watch_snapshot")
    market = db.execute(select(MarketSnapshot).where(MarketSnapshot.stock_id == stock_id, MarketSnapshot.price.is_not(None)).order_by(desc(MarketSnapshot.snapshot_time)).limit(1)).scalar_one_or_none()
    if market is not None and market.price is not None:
        return PaperPrice(_money4(market.price), "market_snapshot")
    daily = db.execute(select(KlineDaily).where(KlineDaily.stock_id == stock_id, KlineDaily.close.is_not(None)).order_by(desc(KlineDaily.trade_date)).limit(1)).scalar_one_or_none()
    if daily is not None and daily.close is not None:
        return PaperPrice(_money4(daily.close), "daily_close")
    raise HTTPException(status_code=400, detail="没有可用于模拟交易的最新价格")


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(_bcrypt_password_bytes(password), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("utf-8")


def _verify_password(password: str, stored: str) -> bool:
    if _is_bcrypt_hash(stored):
        return _verify_bcrypt_password(password, stored)
    return _verify_legacy_pbkdf2_password(password, stored)


def _verify_legacy_pbkdf2_password(password: str, stored: str) -> bool:
    try:
        salt, expected = stored.split("$", 1)
    except ValueError:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000).hex()
    return hmac.compare_digest(actual, expected)


def _verify_bcrypt_password(password: str, stored: str) -> bool:
    try:
        return bcrypt.checkpw(_bcrypt_password_bytes(password), stored.encode("utf-8"))
    except ValueError:
        return False


def _password_hash_needs_upgrade(stored: str) -> bool:
    return not _is_bcrypt_hash(stored)


def _is_bcrypt_hash(stored: str) -> bool:
    return stored.startswith(("$2a$", "$2b$", "$2y$"))


def _bcrypt_password_bytes(password: str) -> bytes:
    return hashlib.sha256(password.encode("utf-8")).hexdigest().encode("ascii")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _session_expired(session: PaperSession) -> bool:
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        return expires_at <= datetime.now(timezone.utc).replace(tzinfo=None)
    return expires_at <= datetime.now(timezone.utc)


def _cleanup_admin_sessions() -> None:
    now = datetime.now(timezone.utc)
    expired = [token_hash for token_hash, expires_at in _admin_session_expires.items() if expires_at <= now]
    for token_hash in expired:
        _admin_session_expires.pop(token_hash, None)


def _empty_flow_stats() -> dict[str, object]:
    return {
        "flow_in": Decimal("0.0000"),
        "flow_out": Decimal("0.0000"),
        "net_flow": Decimal("0.0000"),
        "flow_count": 0,
        "last_flow_at": None,
    }


def _safe_position_market_value(db: Session, position_rows: list[tuple[PaperPosition, Stock]]) -> Decimal:
    try:
        return _position_market_value(db, position_rows)
    except HTTPException:
        return Decimal("0.0000")


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _money4(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _decimal(value: Decimal, digits: int = 2) -> float:
    quantum = Decimal("1").scaleb(-digits)
    return float(Decimal(value).quantize(quantum, rounding=ROUND_HALF_UP))


def _optional_decimal(value: Decimal | None, digits: int = 2) -> float | None:
    return None if value is None else _decimal(value, digits)


def _average_decimal(values: list[Decimal]) -> float:
    return _decimal(_average_raw(values))


def _average_raw(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal("0.0000")
    return sum(values, Decimal("0.0000")) / len(values)


def _ratio(numerator: int, denominator: int) -> float:
    if not denominator:
        return 0.0
    return float((Decimal(numerator) / Decimal(denominator) * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
