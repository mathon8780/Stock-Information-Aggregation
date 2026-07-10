from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


PK_TYPE = BigInteger().with_variant(Integer, "sqlite")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Stock(Base):
    __tablename__ = "stocks"
    __table_args__ = (CheckConstraint("security_type in ('stock', 'index')", name="ck_stocks_security_type"),)

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    market: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    security_type: Mapped[str] = mapped_column(String(16), default="stock", nullable=False)
    industry: Mapped[str | None] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    klines: Mapped[list[KlineDaily]] = relationship(back_populates="stock", cascade="all, delete-orphan")
    intraday_klines: Mapped[list[KlineIntraday]] = relationship(back_populates="stock", cascade="all, delete-orphan")
    market_snapshots: Mapped[list[MarketSnapshot]] = relationship(back_populates="stock")
    watch_snapshots: Mapped[list[WatchSnapshot]] = relationship(back_populates="stock")
    news: Mapped[list[News]] = relationship(back_populates="stock")
    advice: Mapped[list[TradingAdvice]] = relationship(back_populates="stock")
    watchlist_item: Mapped[Watchlist | None] = relationship(back_populates="stock")


class KlineDaily(Base):
    __tablename__ = "kline_daily"

    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    high: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    low: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    close: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    volume: Mapped[int | None] = mapped_column(BigInteger)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    amplitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    change_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    turnover_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    source: Mapped[str] = mapped_column(String(64), default="akshare", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    stock: Mapped[Stock] = relationship(back_populates="klines")


class KlineIntraday(Base):
    __tablename__ = "kline_intraday"

    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), primary_key=True)
    period_minutes: Mapped[int] = mapped_column(Integer, primary_key=True)
    bar_time: Mapped[datetime] = mapped_column(DateTime(timezone=False), primary_key=True)
    open: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    high: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    low: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    close: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    volume: Mapped[int | None] = mapped_column(BigInteger)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    amplitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    change_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    change_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    turnover_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    source: Mapped[str] = mapped_column(String(64), default="akshare", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    stock: Mapped[Stock] = relationship(back_populates="intraday_klines")


class MarketSnapshot(Base):
    __tablename__ = "market_snapshot"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_market_snapshot_idempotency_key"),)

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    snapshot_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True, nullable=False)
    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    change_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    change_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    volume: Mapped[int | None] = mapped_column(BigInteger)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    open: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    high: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    low: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    amplitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    turnover_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    volume_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    pe: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    pb: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    total_mv: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    circ_mv: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)

    stock: Mapped[Stock] = relationship(back_populates="market_snapshots")


class WatchSnapshot(Base):
    __tablename__ = "watch_snapshot"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_watch_snapshot_idempotency_key"),)

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    snapshot_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True, nullable=False)
    source_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("market_snapshot.id"))
    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    change_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    change_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    volume: Mapped[int | None] = mapped_column(BigInteger)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    open: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    high: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    low: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    amplitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    turnover_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    volume_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    pe: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    pb: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    total_mv: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    circ_mv: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)

    stock: Mapped[Stock] = relationship(back_populates="watch_snapshots")


class News(Base):
    __tablename__ = "news"
    __table_args__ = (
        UniqueConstraint("content_hash", name="uq_news_content_hash"),
        CheckConstraint("scope in ('market', 'stock', 'security')", name="ck_news_scope"),
        CheckConstraint("simplification_status in ('pending', 'simplified', 'failed')", name="ck_news_simplification_status"),
    )

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    stock_id: Mapped[int | None] = mapped_column(ForeignKey("stocks.id"), index=True)
    scope: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    original_title: Mapped[str | None] = mapped_column(String(240))
    summary: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(128), default="manual", nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    sentiment: Mapped[str] = mapped_column(String(16), default="neutral", nullable=False)
    importance: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    simplification_status: Mapped[str] = mapped_column(String(16), default="pending", index=True, nullable=False)
    simplified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    llm_provider: Mapped[str | None] = mapped_column(String(64))
    llm_model: Mapped[str | None] = mapped_column(String(128))
    prompt_name: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)

    stock: Mapped[Stock | None] = relationship(back_populates="news")


class NewsLlmConfig(Base):
    __tablename__ = "news_llm_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    provider: Mapped[str] = mapped_column(String(64), default="deepseek", nullable=False)
    api_base_url: Mapped[str] = mapped_column(Text, default="https://api.deepseek.com", nullable=False)
    model: Mapped[str] = mapped_column(String(128), default="deepseek-v4-flash", nullable=False)
    api_key: Mapped[str | None] = mapped_column(Text)
    prompt_preset: Mapped[str] = mapped_column(String(64), default="default", nullable=False)
    custom_prompt: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class TradingAdvice(Base):
    __tablename__ = "trading_advice"

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True, nullable=False)
    signal: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    strategy: Mapped[str] = mapped_column(Text, nullable=False)
    risk_notes: Mapped[str] = mapped_column(Text, nullable=False)
    indicators: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    news_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    market_context: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    engine: Mapped[str] = mapped_column(String(32), default="rule_engine", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True, nullable=False)

    stock: Mapped[Stock] = relationship(back_populates="advice")


class Watchlist(Base):
    __tablename__ = "watchlist"
    __table_args__ = (UniqueConstraint("stock_id", name="uq_watchlist_stock_id"),)

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    alert_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    alert_threshold_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("3.0000"), nullable=False)
    strategy_push_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    stock: Mapped[Stock] = relationship(back_populates="watchlist_item")


class PaperWatchlist(Base):
    __tablename__ = "paper_watchlist"
    __table_args__ = (UniqueConstraint("account_id", "stock_id", name="uq_paper_watchlist_account_stock"),)

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_accounts.id"), index=True, nullable=False)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    stock: Mapped[Stock] = relationship()


class CollectionJob(Base):
    __tablename__ = "collection_jobs"

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="system", nullable=False)
    requested_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    result_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    notification_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    target_channel: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaperAccount(Base):
    __tablename__ = "paper_accounts"
    __table_args__ = (
        UniqueConstraint("owner_name", name="uq_paper_accounts_owner_name"),
        UniqueConstraint("phone", name="uq_paper_accounts_phone"),
        CheckConstraint("cash_balance >= 0", name="ck_paper_accounts_cash_balance"),
        CheckConstraint("cash_available >= 0", name="ck_paper_accounts_cash_available"),
        CheckConstraint("cash_frozen >= 0", name="ck_paper_accounts_cash_frozen"),
    )

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    owner_name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    initial_cash: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("500000.0000"), nullable=False)
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("500000.0000"), nullable=False)
    cash_available: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("500000.0000"), nullable=False)
    cash_frozen: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaperSession(Base):
    __tablename__ = "paper_sessions"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_paper_sessions_token_hash"),)

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_accounts.id"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaperOrder(Base):
    __tablename__ = "paper_orders"

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_accounts.id"), index=True, nullable=False)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True, nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    filled_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    trigger_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    avg_fill_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    frozen_cash: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    frozen_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fee_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    reject_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaperTrade(Base):
    __tablename__ = "paper_trades"

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_accounts.id"), index=True, nullable=False)
    order_id: Mapped[int] = mapped_column(ForeignKey("paper_orders.id"), index=True, nullable=False)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True, nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    commission: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    stamp_tax: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    transfer_fee: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    fee_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    trade_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    price_source: Mapped[str] = mapped_column(String(32), nullable=False)


class PaperPosition(Base):
    __tablename__ = "paper_positions"
    __table_args__ = (UniqueConstraint("account_id", "stock_id", name="uq_paper_positions_account_stock"),)

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_accounts.id"), index=True, nullable=False)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True, nullable=False)
    total_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    today_buy_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    frozen_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    cost_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class PaperCashFlow(Base):
    __tablename__ = "paper_cash_flows"

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_accounts.id"), index=True, nullable=False)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("paper_orders.id"))
    trade_id: Mapped[int | None] = mapped_column(ForeignKey("paper_trades.id"))
    flow_type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    cash_balance_after: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    remark: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class PaperEquitySnapshot(Base):
    __tablename__ = "paper_equity_snapshots"

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_accounts.id"), index=True, nullable=False)
    snapshot_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, default=utcnow, nullable=False)
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    cash_frozen: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    position_market_value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    total_assets: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    net_value: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    daily_return_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    benchmark_code: Mapped[str | None] = mapped_column(String(32))
    benchmark_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
