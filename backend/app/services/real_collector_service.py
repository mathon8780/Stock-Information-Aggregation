from __future__ import annotations

import importlib
import math
import time
from datetime import date, datetime, time as wall_time, timedelta, timezone
from typing import Any, Callable, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis import calculate_indicators
from app.config import settings
from app.database import Base, engine, init_db
from app.models import Stock, Watchlist
from app.services.analysis_service import analyze_watchlist
from app.services.ingest_service import ingest_intraday_kline_payload, ingest_kline_payload, ingest_market_payload, record_collection_job


DEFAULT_WATCHLIST = [
    {"code": "300308.SZ", "name": "中际旭创", "market": "SZ", "security_type": "stock", "industry": "CPO/光模块"},
    {"code": "300502.SZ", "name": "新易盛", "market": "SZ", "security_type": "stock", "industry": "CPO/光模块"},
    {"code": "300394.SZ", "name": "天孚通信", "market": "SZ", "security_type": "stock", "industry": "CPO/光模块"},
    {"code": "601138.SH", "name": "工业富联", "market": "SH", "security_type": "stock", "industry": "AI算力"},
    {"code": "000977.SZ", "name": "浪潮信息", "market": "SZ", "security_type": "stock", "industry": "AI算力"},
]

MAIN_INDICES = [
    {"code": "000001.SH", "symbol": "000001", "name": "上证指数", "market": "INDEX", "security_type": "index", "industry": "指数"},
    {"code": "399001.SZ", "symbol": "399001", "name": "深证成指", "market": "INDEX", "security_type": "index", "industry": "指数"},
    {"code": "399006.SZ", "symbol": "399006", "name": "创业板指", "market": "INDEX", "security_type": "index", "industry": "指数"},
    {"code": "000300.SH", "symbol": "000300", "name": "沪深300", "market": "INDEX", "security_type": "index", "industry": "指数"},
    {"code": "000905.SH", "symbol": "000905", "name": "中证500", "market": "INDEX", "security_type": "index", "industry": "指数"},
]

INDEX_SPOT_GROUPS = ["沪深重要指数", "上证系列指数", "深证系列指数", "中证系列指数"]
BACKOFF_SECONDS = [60, 120, 300]


class AkshareCollector:
    def __init__(
        self,
        ak_module: Any | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        request_interval_seconds: float | None = None,
        backoff_seconds: Iterable[float] | None = None,
    ):
        self.ak = ak_module or importlib.import_module("akshare")
        self.sleep = sleep_fn
        self.request_interval_seconds = (
            settings.request_min_interval_seconds if request_interval_seconds is None else request_interval_seconds
        )
        self.backoff_seconds = list(BACKOFF_SECONDS if backoff_seconds is None else backoff_seconds)

    def bootstrap(self, db: Session, reset: bool = True) -> dict[str, Any]:
        if reset:
            Base.metadata.drop_all(bind=engine)
            Base.metadata.create_all(bind=engine)
            init_db()

        market_summary = self.collect_market_snapshot(db)
        watch_summary = ensure_default_watchlist(db)
        history_summary = self.collect_history(db)
        try:
            advice_rows = analyze_watchlist(db)
            advice_summary = {"analyzed": len(advice_rows)}
        except Exception as exc:  # strategy failure should not hide successful data sync
            record_collection_job(
                db,
                "analysis",
                "rule_engine",
                "failed",
                {"analyzed": 0},
                {"scope": "watchlist"},
                str(exc),
            )
            db.commit()
            advice_summary = {"analyzed": 0, "error": str(exc)}
        return {
            "market": market_summary,
            "watchlist": watch_summary,
            "history": history_summary,
            "advice": advice_summary,
        }

    def collect_market_snapshot(self, db: Session) -> dict[str, Any]:
        try:
            now = datetime.now(timezone.utc)
            stock_items = self._build_stock_spot_items(now)
            index_items, failed_items = self._build_index_spot_items(now)
            payload = {
                "job_type": "market_snapshot",
                "source": "akshare",
                "fetched_at": now.isoformat(),
                "items": stock_items + index_items,
                "failed_items": failed_items,
            }
            return ingest_market_payload(db, payload)
        except Exception as exc:
            record_collection_job(db, "market_snapshot", "akshare", "failed", {"inserted_market": 0, "failed": 1}, {}, str(exc))
            db.commit()
            return {"inserted_market": 0, "inserted_watch": 0, "skipped": 0, "failed": 1, "error": str(exc)}

    def collect_history(self, db: Session, days: int = 365) -> dict[str, Any]:
        end = date.today()
        start = end - timedelta(days=days)
        items: list[dict[str, Any]] = []
        failed_items: list[dict[str, Any]] = []
        targets = [*DEFAULT_WATCHLIST, *MAIN_INDICES]

        for idx, target in enumerate(targets):
            if idx:
                self.sleep(self.request_interval_seconds)
            try:
                rows = self._call_with_backoff(lambda t=target: self._history_rows_for_target(t, start, end), target["code"])
                items.extend(rows)
            except Exception as exc:
                failed_items.append({"code": target["code"], "name": target["name"], "error": str(exc)})

        if not items:
            record_collection_job(
                db,
                "daily_kline",
                "akshare",
                "failed",
                {"inserted": 0, "updated": 0, "failed": len(failed_items)},
                {"days": days, "targets": [item["code"] for item in targets]},
                "; ".join(item["error"] for item in failed_items[:3]),
            )
            db.commit()
            return {"inserted": 0, "updated": 0, "failed": len(failed_items), "failed_items": failed_items}

        payload = {
            "job_type": "daily_kline",
            "source": "akshare",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "items": items,
            "failed_items": failed_items,
        }
        summary = ingest_kline_payload(db, payload)
        summary["failed_items"] = failed_items
        return summary

    def collect_full_market_history(
        self,
        db: Session,
        days: int = 365,
        batch_size: int = 30,
        limit: int | None = None,
    ) -> dict[str, Any]:
        end = date.today()
        start = end - timedelta(days=days)
        targets = self._full_market_stock_targets()
        if limit is not None:
            targets = targets[:limit]

        result: dict[str, Any] = {
            "total_targets": len(targets),
            "processed": 0,
            "inserted": 0,
            "updated": 0,
            "failed": 0,
            "failed_items": [],
        }
        batch: list[dict[str, Any]] = []
        batch_targets = 0

        def flush_batch() -> None:
            nonlocal batch, batch_targets
            if not batch:
                batch_targets = 0
                return
            summary = ingest_kline_payload(
                db,
                {
                    "job_type": "full_market_daily_kline",
                    "source": "akshare",
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "items": batch,
                    "failed_items": [],
                },
            )
            result["inserted"] += summary.get("inserted", 0)
            result["updated"] += summary.get("updated", 0)
            batch = []
            batch_targets = 0

        for idx, target in enumerate(targets):
            if idx:
                self.sleep(self.request_interval_seconds)
            try:
                rows = self._call_with_backoff(lambda t=target: self._history_rows_for_target(t, start, end, prefer_bulk_daily=True), target["code"])
                batch.extend(rows)
                batch_targets += 1
                result["processed"] += 1
            except Exception as exc:
                result["failed_items"].append({"code": target["code"], "name": target["name"], "error": str(exc)})
            if batch_targets >= batch_size:
                flush_batch()

        flush_batch()
        result["failed"] = len(result["failed_items"])
        record_collection_job(
            db,
            "full_market_daily_kline",
            "akshare",
            "success" if result["failed"] == 0 else "partial_failed",
            {key: value for key, value in result.items() if key != "failed_items"},
            {"days": days, "batch_size": batch_size, "limit": limit, "total_targets": len(targets)},
            None if result["failed"] == 0 else f"{result['failed']} targets failed",
        )
        db.commit()
        return result

    def collect_intraday(self, db: Session, trading_days: int = 10, period_minutes: int = 1) -> dict[str, Any]:
        if period_minutes not in {1, 5, 15, 30, 60}:
            raise ValueError("period_minutes must be one of 1, 5, 15, 30, 60")
        ensure_default_watchlist(db)
        start_dt, end_dt = _intraday_window(trading_days)
        items: list[dict[str, Any]] = []
        failed_items: list[dict[str, Any]] = []

        for idx, target in enumerate(DEFAULT_WATCHLIST):
            if idx:
                self.sleep(self.request_interval_seconds)
            try:
                rows = self._call_with_backoff(
                    lambda t=target: self._intraday_rows_for_target(t, start_dt, end_dt, trading_days, period_minutes),
                    target["code"],
                )
                items.extend(rows)
            except Exception as exc:
                failed_items.append({"code": target["code"], "name": target["name"], "error": str(exc)})

        if not items:
            record_collection_job(
                db,
                "intraday_kline",
                "akshare",
                "failed",
                {"inserted": 0, "updated": 0, "failed": len(failed_items)},
                {"trading_days": trading_days, "period_minutes": period_minutes, "targets": [item["code"] for item in DEFAULT_WATCHLIST]},
                "; ".join(item["error"] for item in failed_items[:3]),
            )
            db.commit()
            return {"inserted": 0, "updated": 0, "failed": len(failed_items), "failed_items": failed_items}

        payload = {
            "job_type": "intraday_kline",
            "source": "akshare",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "period_minutes": period_minutes,
            "items": items,
            "failed_items": failed_items,
        }
        summary = ingest_intraday_kline_payload(db, payload)
        summary["failed_items"] = failed_items
        return summary

    def collect_stock_intraday(self, db: Session, code: str, trading_days: int = 1, period_minutes: int = 1) -> dict[str, Any]:
        if period_minutes not in {1, 5, 15, 30, 60}:
            raise ValueError("period_minutes must be one of 1, 5, 15, 30, 60")
        normalized_code = normalize_a_code(code)
        stock = db.execute(select(Stock).where(Stock.code == normalized_code)).scalar_one_or_none()
        if stock is None:
            raise ValueError(f"stock {normalized_code} is not found")
        target = {
            "code": stock.code,
            "name": stock.name,
            "market": stock.market,
            "security_type": stock.security_type,
            "industry": stock.industry or "",
        }
        start_dt, end_dt = _intraday_window(trading_days)
        try:
            items = self._call_with_backoff(
                lambda: self._intraday_rows_for_target(target, start_dt, end_dt, trading_days, period_minutes),
                target["code"],
            )
        except Exception as exc:
            record_collection_job(
                db,
                "intraday_kline",
                "akshare",
                "failed",
                {"inserted": 0, "updated": 0, "failed": 1},
                {"code": target["code"], "trading_days": trading_days, "period_minutes": period_minutes},
                str(exc),
            )
            db.commit()
            return {"inserted": 0, "updated": 0, "failed": 1, "failed_items": [{"code": target["code"], "name": target["name"], "error": str(exc)}]}

        summary = ingest_intraday_kline_payload(
            db,
            {
                "job_type": "intraday_kline",
                "source": "akshare",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "period_minutes": period_minutes,
                "items": items,
                "failed_items": [],
            },
        )
        summary["code"] = target["code"]
        summary["trading_days"] = trading_days
        summary["period_minutes"] = period_minutes
        return summary

    def _build_stock_spot_items(self, now: datetime) -> list[dict[str, Any]]:
        df = self._stock_spot_frame()
        items: list[dict[str, Any]] = []
        watch_codes = {item["code"] for item in DEFAULT_WATCHLIST}
        watch_meta = {item["code"]: item for item in DEFAULT_WATCHLIST}
        for row in _records(df):
            raw_code = str(_value(row, "代码", "code") or "").strip()
            if not raw_code:
                continue
            code = normalize_a_code(raw_code)
            meta = watch_meta.get(code)
            items.append(
                {
                    "code": code,
                    "name": str(_value(row, "名称", "name") or (meta or {}).get("name") or code),
                    "market": infer_market_from_code(code),
                    "security_type": "stock",
                    "industry": (meta or {}).get("industry"),
                    "price": _float(row, "最新价"),
                    "change_pct": _float(row, "涨跌幅"),
                    "change_amount": _float(row, "涨跌额"),
                    "volume": _int(row, "成交量"),
                    "amount": _float(row, "成交额"),
                    "open": _float(row, "今开", "开盘"),
                    "high": _float(row, "最高"),
                    "low": _float(row, "最低"),
                    "amplitude": _float(row, "振幅"),
                    "turnover_rate": _float(row, "换手率"),
                    "volume_ratio": _float(row, "量比"),
                    "pe": _float(row, "市盈率-动态", "市盈率"),
                    "pb": _float(row, "市净率"),
                    "total_mv": _float(row, "总市值"),
                    "circ_mv": _float(row, "流通市值"),
                    "is_watch": code in watch_codes,
                    "idempotency_key": f"akshare:market:{code}:{now.isoformat(timespec='minutes')}",
                    "watch_idempotency_key": f"akshare:watch:{code}:{now.isoformat(timespec='minutes')}",
                }
            )
        return items

    def _stock_spot_frame(self) -> Any:
        errors: list[str] = []
        if hasattr(self.ak, "stock_zh_a_spot_em"):
            try:
                return self.ak.stock_zh_a_spot_em()
            except Exception as exc:
                errors.append(f"stock_zh_a_spot_em: {exc}")
        if hasattr(self.ak, "stock_zh_a_spot"):
            try:
                return self.ak.stock_zh_a_spot()
            except Exception as exc:
                errors.append(f"stock_zh_a_spot: {exc}")
        raise RuntimeError("; ".join(errors) or "AKShare stock spot interface is unavailable")

    def _build_index_spot_items(self, now: datetime) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        wanted = {item["symbol"]: item for item in MAIN_INDICES}
        found: dict[str, dict[str, Any]] = {}
        errors: list[str] = []
        for idx, group in enumerate(INDEX_SPOT_GROUPS):
            if idx:
                self.sleep(min(self.request_interval_seconds, 1))
            try:
                df = self.ak.stock_zh_index_spot_em(symbol=group)
            except Exception as exc:
                errors.append(f"stock_zh_index_spot_em({group}): {exc}")
                continue
            for row in _records(df):
                symbol = _index_symbol(_value(row, "代码", "code"))
                if symbol in wanted:
                    found[symbol] = row
        if len(found) < len(wanted) and hasattr(self.ak, "stock_zh_index_spot_sina"):
            try:
                df = self.ak.stock_zh_index_spot_sina()
                for row in _records(df):
                    symbol = _index_symbol(_value(row, "代码", "code"))
                    if symbol in wanted:
                        found[symbol] = row
            except Exception as exc:
                errors.append(f"stock_zh_index_spot_sina: {exc}")

        items: list[dict[str, Any]] = []
        failed_items: list[dict[str, Any]] = []
        for symbol, meta in wanted.items():
            row = found.get(symbol)
            if row is None:
                failed_items.append(
                    {
                        "code": meta["code"],
                        "name": meta["name"],
                        "error": "; ".join(errors[-2:]) or "index spot row not found",
                    }
                )
                continue
            items.append(
                {
                    **meta,
                    "price": _float(row, "最新价", "最新"),
                    "change_pct": _float(row, "涨跌幅"),
                    "change_amount": _float(row, "涨跌额"),
                    "volume": _int(row, "成交量"),
                    "amount": _float(row, "成交额"),
                    "open": _float(row, "今开", "开盘"),
                    "high": _float(row, "最高"),
                    "low": _float(row, "最低"),
                    "amplitude": _float(row, "振幅"),
                    "volume_ratio": _float(row, "量比"),
                    "idempotency_key": f"akshare:market:{meta['code']}:{now.isoformat(timespec='minutes')}",
                }
            )
        return items, failed_items

    def _full_market_stock_targets(self) -> list[dict[str, str]]:
        exchange_targets = self._exchange_stock_info_targets()
        if exchange_targets:
            return exchange_targets
        return self._spot_stock_targets()

    def _exchange_stock_info_targets(self) -> list[dict[str, str]]:
        sources = [
            ("stock_info_sh_name_code", "证券代码", "证券简称", "所属行业"),
            ("stock_info_sz_name_code", "A股代码", "A股简称", "所属行业"),
            ("stock_info_bj_name_code", "证券代码", "证券简称", "所属行业"),
        ]
        targets: list[dict[str, str]] = []
        seen: set[str] = set()
        for function_name, code_field, name_field, industry_field in sources:
            if not hasattr(self.ak, function_name):
                continue
            try:
                df = getattr(self.ak, function_name)()
            except Exception:
                continue
            for row in _records(df):
                raw_code = str(_value(row, code_field, "代码", "code") or "").strip()
                if not raw_code:
                    continue
                code = normalize_a_code(raw_code)
                if not _is_a_share_code(code) or code in seen:
                    continue
                seen.add(code)
                targets.append(
                    {
                        "code": code,
                        "name": str(_value(row, name_field, "名称", "name") or code),
                        "market": infer_market_from_code(code),
                        "security_type": "stock",
                        "industry": str(_value(row, industry_field, "行业", "板块") or ""),
                    }
                )
        return targets

    def _spot_stock_targets(self) -> list[dict[str, str]]:
        df = self._stock_spot_frame()
        targets: list[dict[str, str]] = []
        seen: set[str] = set()
        for row in _records(df):
            raw_code = str(_value(row, "代码", "code") or "").strip()
            if not raw_code:
                continue
            code = normalize_a_code(raw_code)
            if not _is_a_share_code(code) or code in seen:
                continue
            seen.add(code)
            targets.append(
                {
                    "code": code,
                    "name": str(_value(row, "名称", "name") or code),
                    "market": infer_market_from_code(code),
                    "security_type": "stock",
                    "industry": str(_value(row, "行业", "所属行业", "板块") or ""),
                }
            )
        return targets

    def _history_rows_for_target(self, target: dict[str, str], start: date, end: date, prefer_bulk_daily: bool = False) -> list[dict[str, Any]]:
        start_text = start.strftime("%Y%m%d")
        end_text = end.strftime("%Y%m%d")
        symbol = target.get("symbol") or target["code"].split(".")[0]
        if target["security_type"] == "index":
            df = self._index_history_frame(target, start_text, end_text)
        else:
            df = self._stock_history_frame(target, symbol, start_text, end_text, prefer_bulk_daily=prefer_bulk_daily)

        rows: list[dict[str, Any]] = []
        for row in _records(df):
            trade_date = _as_date(_value(row, "日期", "date"))
            if not trade_date:
                continue
            if trade_date < start or trade_date > end:
                continue
            rows.append(
                {
                    **target,
                    "trade_date": trade_date.isoformat(),
                    "open": _float(row, "开盘", "open"),
                    "high": _float(row, "最高", "high"),
                    "low": _float(row, "最低", "low"),
                    "close": _float(row, "收盘", "close"),
                    "volume": _int(row, "成交量", "volume"),
                    "amount": _float(row, "成交额", "成交金额", "amount"),
                    "amplitude": _float(row, "振幅", "amplitude"),
                    "change_pct": _float(row, "涨跌幅", "change_pct"),
                    "turnover_rate": _turnover_rate(row),
                }
            )
        return rows

    def _stock_history_frame(self, target: dict[str, str], symbol: str, start_text: str, end_text: str, prefer_bulk_daily: bool = False) -> Any:
        errors: list[str] = []

        def try_stock_zh_a_hist() -> Any:
            if not hasattr(self.ak, "stock_zh_a_hist"):
                raise RuntimeError("stock_zh_a_hist is unavailable")
            return self.ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start_text,
                end_date=end_text,
                adjust="qfq",
            )

        def try_stock_zh_a_daily() -> Any:
            if not hasattr(self.ak, "stock_zh_a_daily"):
                raise RuntimeError("stock_zh_a_daily is unavailable")
            market_symbol = _market_symbol(target["code"], symbol)
            return self.ak.stock_zh_a_daily(
                symbol=market_symbol,
                start_date=start_text,
                end_date=end_text,
                adjust="qfq",
            )

        def try_stock_zh_a_hist_tx() -> Any:
            if not hasattr(self.ak, "stock_zh_a_hist_tx"):
                raise RuntimeError("stock_zh_a_hist_tx is unavailable")
            market_symbol = _market_symbol(target["code"], symbol)
            return self.ak.stock_zh_a_hist_tx(
                symbol=market_symbol,
                start_date=start_text,
                end_date=end_text,
                adjust="qfq",
            )

        attempts = (
            (("stock_zh_a_daily", try_stock_zh_a_daily), ("stock_zh_a_hist_tx", try_stock_zh_a_hist_tx), ("stock_zh_a_hist", try_stock_zh_a_hist))
            if prefer_bulk_daily
            else (("stock_zh_a_hist", try_stock_zh_a_hist), ("stock_zh_a_daily", try_stock_zh_a_daily), ("stock_zh_a_hist_tx", try_stock_zh_a_hist_tx))
        )

        for label, attempt in attempts:
            try:
                return attempt()
            except Exception as exc:
                errors.append(f"{label}: {exc}")
        raise RuntimeError("; ".join(errors) or "AKShare stock history interface is unavailable")

    def _index_history_frame(self, target: dict[str, str], start_text: str, end_text: str) -> Any:
        symbol = target.get("symbol") or target["code"].split(".")[0]
        errors: list[str] = []
        if hasattr(self.ak, "index_zh_a_hist"):
            try:
                return self.ak.index_zh_a_hist(symbol=symbol, period="daily", start_date=start_text, end_date=end_text)
            except Exception as exc:
                errors.append(f"index_zh_a_hist: {exc}")

        market_symbol = f"{'sh' if target['code'].endswith('.SH') else 'sz'}{symbol}"
        for function_name in ("stock_zh_index_daily", "stock_zh_index_daily_tx"):
            if not hasattr(self.ak, function_name):
                continue
            try:
                return getattr(self.ak, function_name)(symbol=market_symbol)
            except Exception as exc:
                errors.append(f"{function_name}: {exc}")
        raise RuntimeError("; ".join(errors) or "AKShare index history interface is unavailable")

    def _intraday_rows_for_target(
        self,
        target: dict[str, str],
        start_dt: datetime,
        end_dt: datetime,
        trading_days: int,
        period_minutes: int,
    ) -> list[dict[str, Any]]:
        symbol = target["code"].split(".")[0]
        df = self._intraday_frame(symbol, start_dt, end_dt, period_minutes)
        raw_rows: list[tuple[datetime, dict[str, Any]]] = []
        for row in _records(df):
            bar_time = _as_datetime(_value(row, "时间", "day", "time", "datetime"))
            if bar_time is None:
                continue
            if bar_time < start_dt or bar_time > end_dt:
                continue
            raw_rows.append((bar_time, row))
        raw_rows.sort(key=lambda item: item[0])
        keep_dates = set(sorted({bar_time.date() for bar_time, _ in raw_rows})[-trading_days:])
        rows = [
            {
                **target,
                "bar_time": bar_time.isoformat(timespec="seconds"),
                "period_minutes": period_minutes,
                "open": _float(row, "开盘", "open"),
                "high": _float(row, "最高", "high"),
                "low": _float(row, "最低", "low"),
                "close": _float(row, "收盘", "close"),
                "volume": _int(row, "成交量", "volume"),
                "amount": _float(row, "成交额", "amount"),
                "amplitude": _float(row, "振幅", "amplitude"),
                "change_pct": _float(row, "涨跌幅", "change_pct"),
                "change_amount": _float(row, "涨跌额", "change_amount"),
                "turnover_rate": _turnover_rate(row),
            }
            for bar_time, row in raw_rows
            if bar_time.date() in keep_dates
        ]
        if not rows:
            raise RuntimeError("no intraday rows returned")
        return rows

    def _intraday_frame(self, symbol: str, start_dt: datetime, end_dt: datetime, period_minutes: int) -> Any:
        errors: list[str] = []
        if hasattr(self.ak, "stock_zh_a_hist_min_em"):
            try:
                return self.ak.stock_zh_a_hist_min_em(
                    symbol=symbol,
                    start_date=start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    end_date=end_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    period=str(period_minutes),
                    adjust="",
                )
            except Exception as exc:
                errors.append(f"stock_zh_a_hist_min_em: {exc}")
        if hasattr(self.ak, "stock_zh_a_minute"):
            market_symbol = f"{'sh' if symbol.startswith(('600', '601', '603', '605', '688', '689')) else 'sz'}{symbol}"
            try:
                return self.ak.stock_zh_a_minute(symbol=market_symbol, period=str(period_minutes), adjust="")
            except Exception as exc:
                errors.append(f"stock_zh_a_minute: {exc}")
        raise RuntimeError("; ".join(errors) or "AKShare intraday interface is unavailable")

    def _call_with_backoff(self, func: Callable[[], list[dict[str, Any]]], label: str) -> list[dict[str, Any]]:
        last_error: Exception | None = None
        for attempt in range(len(self.backoff_seconds) + 1):
            try:
                return func()
            except Exception as exc:
                last_error = exc
                if attempt < len(self.backoff_seconds):
                    self.sleep(self.backoff_seconds[attempt])
        raise RuntimeError(f"{label} failed after retries: {last_error}") from last_error


def ensure_default_watchlist(db: Session) -> dict[str, Any]:
    inserted = 0
    for order, item in enumerate(DEFAULT_WATCHLIST, start=1):
        stock = db.execute(select(Stock).where(Stock.code == item["code"])).scalar_one_or_none()
        if stock is None:
            stock = Stock(**item)
            db.add(stock)
            db.flush()
        else:
            stock.name = item["name"]
            stock.market = item["market"]
            stock.security_type = item["security_type"]
            stock.industry = item["industry"]
        existing = db.execute(select(Watchlist).where(Watchlist.stock_id == stock.id)).scalar_one_or_none()
        if existing is None:
            db.add(Watchlist(stock_id=stock.id, display_order=order, alert_threshold_pct=3.0))
            inserted += 1
        else:
            existing.display_order = order
    db.commit()
    return {"default_watchlist_size": len(DEFAULT_WATCHLIST), "inserted": inserted}


def build_indicator_preview(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    return calculate_indicators(list(rows))


def normalize_a_code(raw_code: str) -> str:
    code = raw_code.strip().upper().split(".")[0]
    if len(code) >= 8 and code[:2] in {"SH", "SZ", "BJ"} and code[2:].isdigit():
        return f"{code[2:]}.{code[:2]}"
    if code.startswith(("600", "601", "603", "605", "688", "689", "900")):
        return f"{code}.SH"
    if code.startswith(("000", "001", "002", "003", "300", "301", "200")):
        return f"{code}.SZ"
    if code.startswith(("430", "8", "4", "920")):
        return f"{code}.BJ"
    return raw_code.strip().upper()


def infer_market_from_code(code: str) -> str:
    if code.endswith(".SH"):
        return "SH"
    if code.endswith(".SZ"):
        return "SZ"
    if code.endswith(".BJ"):
        return "BJ"
    return "UNKNOWN"


def _is_a_share_code(code: str) -> bool:
    if code.endswith(".SH"):
        return code.startswith(("600", "601", "603", "605", "688", "689"))
    if code.endswith(".SZ"):
        return code.startswith(("000", "001", "002", "003", "300", "301"))
    if code.endswith(".BJ"):
        return code.startswith(("430", "8", "4", "920"))
    return False


def _market_symbol(code: str, symbol: str) -> str:
    if code.endswith(".SH"):
        return f"sh{symbol}"
    if code.endswith(".SZ"):
        return f"sz{symbol}"
    if code.endswith(".BJ"):
        return f"bj{symbol}"
    return symbol


def _records(df: Any) -> list[dict[str, Any]]:
    if df is None:
        return []
    if hasattr(df, "to_dict"):
        return list(df.to_dict("records"))
    return list(df)


def _value(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in row:
            value = row[name]
            if value is not None and not (isinstance(value, float) and math.isnan(value)):
                return value
    return None


def _index_symbol(raw_code: Any) -> str:
    raw = str(raw_code or "").strip().lower()
    if len(raw) >= 8 and raw[:2] in {"sh", "sz", "bj"}:
        return raw[2:8]
    return raw.split(".")[0]


def _as_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value)[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _as_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    text = str(value).replace("T", " ")[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(str(value)).replace(tzinfo=None)
    except ValueError:
        return None


def _float(row: dict[str, Any], *names: str) -> float | None:
    value = _value(row, *names)
    if value in (None, "", "-"):
        return None
    try:
        number = float(str(value).replace(",", ""))
    except ValueError:
        return None
    if math.isnan(number):
        return None
    return number


def _int(row: dict[str, Any], *names: str) -> int | None:
    value = _float(row, *names)
    return None if value is None else int(value)


def _turnover_rate(row: dict[str, Any]) -> float | None:
    value = _float(row, "换手率", "turnover_rate")
    if value is not None:
        return value
    value = _float(row, "turnover")
    if value is not None and 0 < value <= 1:
        return value * 100
    return value


def _intraday_window(trading_days: int) -> tuple[datetime, datetime]:
    calendar_days = max(trading_days * 3, 20)
    now = datetime.now().replace(tzinfo=None)
    market_close = datetime.combine(date.today(), wall_time(15, 0))
    end_dt = min(now, market_close)
    start_dt = datetime.combine(date.today() - timedelta(days=calendar_days), wall_time(9, 30))
    return start_dt, end_dt
