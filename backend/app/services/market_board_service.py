from __future__ import annotations

import math
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

import requests

from app.config import settings
from app.services.market_request_guard import install_akshare_request_guard


def _number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _quote_time(value: Any) -> str | None:
    stamp = _number(value)
    if not stamp or stamp <= 0:
        return None
    try:
        return datetime.fromtimestamp(stamp, timezone.utc).isoformat()
    except (ValueError, OSError, OverflowError):
        return None


class MarketBoardService:
    """按需读取板块，缓存于进程内；不启动导入，不写业务数据库。"""

    def __init__(self, fetch: Callable[..., dict[str, Any]] | None = None, clock: Callable[[], float] = time.monotonic):
        self.fetch = fetch or self._fetch
        self.clock = clock
        self.cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}
        self.failures: dict[tuple[Any, ...], tuple[float, str]] = {}
        self.lock = threading.Lock()

    @staticmethod
    def _fetch(params: dict[str, str]) -> dict[str, Any]:
        throttle = install_akshare_request_guard(max(3, settings.request_min_interval_seconds))
        response = throttle.call(
            requests.get,
            "https://17.push2.eastmoney.com/api/qt/clist/get",
            params={"pn": "1", "np": "1", "ut": "bd1d9ddb04089700cf9c27f6f7426281", "fltt": "2", "invt": "2", **params},
            timeout=(5, 12),
        )
        response.raise_for_status()
        data = response.json().get("data")
        if not isinstance(data, dict) or not isinstance(data.get("diff"), (list, dict)):
            raise ValueError("板块数据源未返回有效行情")
        return data

    @staticmethod
    def _rows(data: dict[str, Any]) -> list[dict[str, Any]]:
        rows = data.get("diff", [])
        return list(rows.values()) if isinstance(rows, dict) else rows

    def _cached(self, key: tuple[Any, ...], loader: Callable[[], dict[str, Any]], ttl: int) -> dict[str, Any]:
        with self.lock:
            cached = self.cache.get(key)
            if cached and self.clock() - cached[0] < ttl:
                return {**cached[1], "stale": False, "error": None}
            failure = self.failures.get(key)
            if failure and self.clock() - failure[0] < 60:
                return {**(cached[1] if cached else {"items": [], "total": 0, "source": "eastmoney", "fetched_at": None}), "stale": bool(cached), "error": failure[1]}
            try:
                result = {**loader(), "source": "eastmoney", "fetched_at": datetime.now(timezone.utc).isoformat()}
                self.cache[key] = (self.clock(), result)
                self.failures.pop(key, None)
                return {**result, "stale": False, "error": None}
            except Exception as exc:
                error = "板块数据暂时无法读取，请稍后重试。"
                if "冷却" in str(exc) or getattr(getattr(exc, "response", None), "status_code", None) in {403, 412, 429}:
                    error = "板块数据源处于风控冷却期，请稍后重试。"
                self.failures[key] = (self.clock(), error)
                return {**(cached[1] if cached else {"items": [], "total": 0, "source": "eastmoney", "fetched_at": None}), "stale": bool(cached), "error": error}

    def boards(self, kind: str) -> dict[str, Any]:
        def load() -> dict[str, Any]:
            items: dict[str, dict[str, Any]] = {}
            total = 0
            for order in ("1", "0"):
                data = self.fetch({"pz": "4", "po": order, "fid": "f3", "fs": f"m:90 t:{'2' if kind == 'industry' else '3'} f:!50", "fields": "f12,f14,f2,f3,f6,f104,f105,f124"})
                total = max(total, int(data.get("total") or 0))
                for row in self._rows(data):
                    code = str(row.get("f12") or "")
                    if not re.fullmatch(r"BK\d+", code):
                        continue
                    items[code] = {"code": code, "name": row.get("f14") or code, "kind": kind, "price": _number(row.get("f2")), "change_pct": _number(row.get("f3")), "amount": _number(row.get("f6")), "up_count": _number(row.get("f104")), "down_count": _number(row.get("f105")), "quote_time": _quote_time(row.get("f124"))}
            if not items:
                raise ValueError("板块列表为空")
            return {"items": sorted(items.values(), key=lambda item: item["change_pct"] if item["change_pct"] is not None else -math.inf, reverse=True), "total": total, "scope": "leaders_and_laggards", "kind": kind}
        return self._cached(("boards", kind), load, 300)

    def constituents(self, code: str, page: int, page_size: int, direction: str) -> dict[str, Any]:
        def load() -> dict[str, Any]:
            data = self.fetch({"pn": str(page), "pz": str(page_size), "po": "1" if direction == "desc" else "0", "fid": "f3", "fs": f"b:{code} f:!50", "fields": "f12,f13,f14,f2,f3,f4,f5,f6,f8,f10,f15,f16,f17,f9,f23,f124"})
            fetched_at = datetime.now(timezone.utc).isoformat()
            items = []
            for row in self._rows(data):
                raw_code = str(row.get("f12") or "")
                if not re.fullmatch(r"\d{6}", raw_code):
                    continue
                market = "BJ" if raw_code.startswith(("4", "8", "92")) else "SH" if raw_code.startswith("6") else "SZ"
                item = {"id": 0, "stock_id": 0, "code": f"{raw_code}.{market}", "name": row.get("f14") or raw_code, "market": market, "security_type": "stock", "snapshot_time": _quote_time(row.get("f124")) or fetched_at}
                item.update({key: _number(row.get(field)) for key, field in {"price": "f2", "change_pct": "f3", "change_amount": "f4", "volume": "f5", "amount": "f6", "turnover_rate": "f8", "volume_ratio": "f10", "high": "f15", "low": "f16", "open": "f17", "pe": "f9", "pb": "f23"}.items()})
                items.append(item)
            return {"items": items, "total": int(data.get("total") or 0), "page": page, "page_size": page_size, "board_code": code}
        return self._cached(("members", code, page, page_size, direction), load, 60)


market_boards = MarketBoardService()
