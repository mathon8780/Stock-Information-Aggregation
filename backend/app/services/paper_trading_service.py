from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models import (
    KlineDaily,
    MarketSnapshot,
    PaperAccount,
    PaperCashFlow,
    PaperOrder,
    PaperPosition,
    PaperSession,
    PaperTrade,
    Stock,
    WatchSnapshot,
)
from app.services.ingest_service import normalize_code
from app.services.notification_service import create_notification


INITIAL_CASH = Decimal("500000.0000")
COMMISSION_RATE = Decimal("0.00025")
STAMP_TAX_RATE = Decimal("0.001")
TRANSFER_FEE_RATE = Decimal("0.00001")


@dataclass(frozen=True)
class PaperPrice:
    price: Decimal
    source: str


def create_account(db: Session, owner_name: str, password: str) -> dict[str, object]:
    normalized_name = owner_name.strip()
    existing = db.execute(select(PaperAccount).where(PaperAccount.owner_name == normalized_name)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=400, detail="模拟账户已存在")
    account = PaperAccount(
        owner_name=normalized_name,
        password_hash=_hash_password(password),
        initial_cash=INITIAL_CASH,
        cash_balance=INITIAL_CASH,
        cash_available=INITIAL_CASH,
        cash_frozen=Decimal("0.0000"),
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account_dict(account)


def login_account(db: Session, owner_name: str, password: str) -> dict[str, object]:
    account = db.execute(select(PaperAccount).where(PaperAccount.owner_name == owner_name.strip())).scalar_one_or_none()
    if account is None or not _verify_password(password, account.password_hash):
        raise HTTPException(status_code=401, detail="账户名或密码错误")
    token = secrets.token_urlsafe(32)
    account.last_login_at = datetime.now(timezone.utc)
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


def account_from_token(db: Session, token: str) -> PaperAccount:
    session = db.execute(select(PaperSession).where(PaperSession.token_hash == _hash_token(token))).scalar_one_or_none()
    if session is None or session.revoked_at is not None or _session_expired(session):
        raise HTTPException(status_code=401, detail="模拟交易登录已失效")
    account = db.get(PaperAccount, session.account_id)
    if account is None or account.status != "active":
        raise HTTPException(status_code=401, detail="模拟账户不可用")
    return account


def reset_account(db: Session, account: PaperAccount) -> dict[str, object]:
    for model in (PaperCashFlow, PaperTrade, PaperOrder, PaperPosition):
        db.query(model).filter(model.account_id == account.id).delete(synchronize_session=False)
    account.cash_balance = INITIAL_CASH
    account.cash_available = INITIAL_CASH
    account.cash_frozen = Decimal("0.0000")
    account.reset_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(account)
    return portfolio_summary(db, account)


def portfolio_summary(db: Session, account: PaperAccount) -> dict[str, object]:
    position_rows = _positions_with_stocks(db, account.id)
    market_value = sum((_latest_price(db, stock.id).price * position.total_quantity for position, stock in position_rows), Decimal("0.0000"))
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


def list_positions(db: Session, account: PaperAccount) -> dict[str, object]:
    items = []
    for position, stock in _positions_with_stocks(db, account.id):
        latest = _latest_price(db, stock.id).price
        market_value = latest * position.total_quantity
        floating_pnl = market_value - position.cost_amount
        floating_pnl_pct = Decimal("0.0000")
        if position.cost_amount:
            floating_pnl_pct = (floating_pnl / position.cost_amount * Decimal("100")).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
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
                "market_price": _decimal(latest),
                "market_value": _decimal(market_value),
                "floating_pnl": _decimal(floating_pnl),
                "floating_pnl_pct": float(floating_pnl_pct),
            }
        )
    return {"items": items, "total": len(items)}


def list_orders(db: Session, account: PaperAccount) -> dict[str, object]:
    rows = db.execute(select(PaperOrder, Stock).join(Stock, PaperOrder.stock_id == Stock.id).where(PaperOrder.account_id == account.id).order_by(desc(PaperOrder.created_at), desc(PaperOrder.id))).all()
    return {"items": [order_dict(order, stock) for order, stock in rows], "total": len(rows)}


def list_trades(db: Session, account: PaperAccount) -> dict[str, object]:
    rows = db.execute(select(PaperTrade, Stock).join(Stock, PaperTrade.stock_id == Stock.id).where(PaperTrade.account_id == account.id).order_by(desc(PaperTrade.trade_time), desc(PaperTrade.id))).all()
    return {"items": [trade_dict(trade, stock) for trade, stock in rows], "total": len(rows)}


def list_cash_flows(db: Session, account: PaperAccount) -> dict[str, object]:
    rows = db.execute(select(PaperCashFlow).where(PaperCashFlow.account_id == account.id).order_by(desc(PaperCashFlow.created_at), desc(PaperCashFlow.id))).scalars().all()
    return {"items": [cash_flow_dict(row) for row in rows], "total": len(rows)}


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
        order = _place_limit_order(db, account, stock, side, quantity, Decimal(str(limit_price)), latest)
        db.commit()
        db.refresh(order)
        return order_dict(order, stock)
    if order_type in {"take_profit", "stop_loss"}:
        order = _place_condition_order(db, account, stock, side, order_type, quantity, Decimal(str(trigger_price)))
        db.commit()
        db.refresh(order)
        return order_dict(order, stock)
    amount = _money(latest.price * quantity)
    fees = calculate_fees(amount, side)
    fee_total = fees["fee_total"]
    if side == "buy":
        _fill_market_buy(db, account, stock, quantity, latest, amount, fees)
    else:
        _fill_market_sell(db, account, stock, quantity, latest, amount, fees)
    order = db.execute(select(PaperOrder).where(PaperOrder.account_id == account.id).order_by(desc(PaperOrder.id)).limit(1)).scalar_one()
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
    order.cancelled_at = datetime.now(timezone.utc)
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
    rows = db.execute(
        select(PaperOrder, Stock)
        .join(Stock, PaperOrder.stock_id == Stock.id)
        .where(PaperOrder.account_id == account.id, PaperOrder.status.in_(("pending", "monitoring")))
        .order_by(PaperOrder.created_at, PaperOrder.id)
    ).all()
    checked = 0
    triggered = 0
    filled = 0
    for order, stock in rows:
        checked += 1
        latest = _latest_price(db, stock.id)
        if order.order_type == "limit" and _limit_crosses(order, latest):
            _fill_existing_order(db, account, order, stock, latest)
            filled += 1
        elif order.order_type in {"take_profit", "stop_loss"} and _condition_crosses(order, latest):
            order.status = "triggered"
            order.triggered_at = datetime.now(timezone.utc)
            triggered += 1
            _fill_existing_order(db, account, order, stock, latest)
            filled += 1
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
) -> PaperOrder:
    limit_price = _money4(limit_price)
    crosses = latest.price <= limit_price if side == "buy" else latest.price >= limit_price
    if crosses:
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
    order.filled_at = datetime.now(timezone.utc)
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
    order.filled_at = datetime.now(timezone.utc)
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
        "initial_cash": _decimal(account.initial_cash),
        "cash_balance": _decimal(account.cash_balance),
        "cash_available": _decimal(account.cash_available),
        "cash_frozen": _decimal(account.cash_frozen),
        "status": account.status,
        "created_at": account.created_at.isoformat() if account.created_at else None,
        "last_login_at": account.last_login_at.isoformat() if account.last_login_at else None,
        "reset_at": account.reset_at.isoformat() if account.reset_at else None,
    }


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
    now = datetime.now(timezone.utc)
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
    now = datetime.now(timezone.utc)
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
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000).hex()
    return f"{salt}${digest}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt, expected = stored.split("$", 1)
    except ValueError:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000).hex()
    return hmac.compare_digest(actual, expected)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _session_expired(session: PaperSession) -> bool:
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        return expires_at <= datetime.now(timezone.utc).replace(tzinfo=None)
    return expires_at <= datetime.now(timezone.utc)


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _money4(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _decimal(value: Decimal, digits: int = 2) -> float:
    quantum = Decimal("0.0001") if digits == 4 else Decimal("0.01")
    return float(Decimal(value).quantize(quantum, rounding=ROUND_HALF_UP))


def _optional_decimal(value: Decimal | None) -> float | None:
    return None if value is None else _decimal(value)
