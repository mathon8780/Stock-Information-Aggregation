from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from sqlalchemy import func, select  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402
from app.models import KlineDaily, Stock  # noqa: E402
from app.services.ingest_service import ingest_kline_payload, record_collection_job  # noqa: E402
from app.services.market_request_guard import is_rate_limit_error  # noqa: E402
from app.services.market_history_lock import history_import_lock  # noqa: E402
from app.services.real_collector_service import AkshareCollector  # noqa: E402


DEFAULT_STATE = PROJECT_ROOT / "data/runtime/full_market_history.json"


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="低频采集全 A 股近一年前复权日 K，默认断点续采。")
    parser.add_argument("--days", type=positive_int, default=365)
    parser.add_argument("--end-date", type=date.fromisoformat)
    parser.add_argument("--workers", type=int, choices=[1], default=1, help="仅允许串行请求")
    parser.add_argument("--interval", type=float, default=5, help="每次 HTTP 请求完成后的最小间隔，至少 3 秒，另加 0–3 秒抖动")
    parser.add_argument("--limit", type=positive_int, help="本轮最多处理的未完成股票数量")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--source", choices=["auto", "tencent"], default="auto", help="tencent 仅请求腾讯行情，不切换其他数据源")
    parser.add_argument("--stop-on-error", action="store_true", help="首次异常立即停止，不自动重试")
    parser.add_argument("--status", action="store_true", help="只显示本地断点状态，不访问数据源")
    args = parser.parse_args(argv)
    if not 3 <= args.interval <= 3600:
        parser.error("--interval must be between 3 and 3600 seconds")
    return args


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(state, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def database_signature() -> str:
    return hashlib.sha256(settings.database_url.encode("utf-8")).hexdigest()


def new_state(days: int, end: date) -> dict[str, Any]:
    return {
        "version": 1, "database": database_signature(), "days": days,
        "start": (end - timedelta(days=days)).isoformat(), "end": end.isoformat(),
        "adjust": "qfq", "status": "initializing", "targets": [],
        "completed": {}, "failures": {}, "inserted": 0, "updated": 0,
    }


def load_state(path: Path, days: int, end: date | None) -> dict[str, Any]:
    if not path.exists():
        return new_state(days, end or date.today())
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("version") != 1 or state.get("database") != database_signature() or state.get("adjust") != "qfq":
        raise ValueError("断点版本、数据库或复权方式不匹配，请指定新的 --state 文件")
    if state["days"] != days or (end is not None and state["end"] != end.isoformat()):
        raise ValueError("日期范围与断点不同，请指定新的 --state 文件")
    return state


def committed_history_matches(db: Any, code: str, completed: dict[str, Any], start: date, end: date) -> bool:
    count, first, last = db.execute(
        select(func.count(), func.min(KlineDaily.trade_date), func.max(KlineDaily.trade_date))
        .join(Stock, Stock.id == KlineDaily.stock_id)
        .where(Stock.code == code, KlineDaily.trade_date >= start, KlineDaily.trade_date <= end)
    ).one()
    return count == completed["rows"] and str(first) == completed["first"] and str(last) == completed["last"]


def progress(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": state["status"], "start": state["start"], "end": state["end"],
        "total": len(state["targets"]), "completed": len(state["completed"]),
        "remaining": len(state["targets"]) - len(state["completed"]),
        "failed": len(state["failures"]), "inserted": state["inserted"], "updated": state["updated"],
        "current_code": state.get("current_code"), "pid": state.get("pid"),
        "retry_after": state.get("retry_after"), "stop_reason": state.get("stop_reason"),
        "updated_at": state.get("updated_at"),
        "source": state.get("source", "auto"), "stop_on_error": state.get("stop_on_error", False),
    }


def select_source(state: dict[str, Any], source: str) -> None:
    previous_source = state.get("source", "auto")
    cooldowns = state.setdefault("source_cooldowns", {})
    if state.get("retry_after"):
        cooldowns[previous_source] = state["retry_after"]
    retry_after = cooldowns.get(source)
    if retry_after and datetime.now(timezone.utc) < datetime.fromisoformat(retry_after):
        raise RuntimeError(f"{source} 冷却中，请在 {retry_after} 后续采")
    if previous_source != source:
        state.setdefault("source_history", []).append({
            "source": previous_source, "status": state["status"],
            "stop_reason": state.get("stop_reason"), "retry_after": state.get("retry_after"),
            "updated_at": state.get("updated_at"),
        })
    state["source"] = source
    state.pop("retry_after", None)


def run_import(args: argparse.Namespace, collector: Any, db: Any, state: dict[str, Any]) -> int:
    start, end = date.fromisoformat(state["start"]), date.fromisoformat(state["end"])
    source = getattr(args, "source", "auto")
    stop_on_error = getattr(args, "stop_on_error", False)
    payload_source = "akshare_tencent" if source == "tencent" else "akshare"
    if source == "tencent" and not state["targets"]:
        raise ValueError("腾讯续采需要已有名单断点，不能在此模式下向其他来源请求股票名单")
    state.update(source=source, stop_on_error=stop_on_error)
    state.update(status="running", pid=os.getpid(), stop_reason=None)
    state.pop("retry_after", None)
    save_state(args.state, state)
    if not state["targets"]:
        state["targets"] = sorted(collector._full_market_stock_targets(), key=lambda target: target["code"])
        if not state["targets"]:
            raise RuntimeError("股票名单为空，不能开始全市场采集")
        save_state(args.state, state)

    for code, completed in list(state["completed"].items()):
        if not committed_history_matches(db, code, completed, start, end):
            del state["completed"][code]
    # 网络等待期间不保留数据库读事务。
    db.rollback()
    pending = [target for target in state["targets"] if target["code"] not in state["completed"]]
    if args.limit is not None:
        pending = pending[:args.limit]
    print(json.dumps(progress(state), ensure_ascii=False), flush=True)
    consecutive_failures = 0
    try:
        for target in pending:
            code = target["code"]
            state["current_code"] = code
            save_state(args.state, state)
            try:
                if stop_on_error:
                    rows = collector._history_rows_for_target(target, start, end, prefer_bulk_daily=True)
                else:
                    rows = collector._call_with_backoff(
                        lambda: collector._history_rows_for_target(target, start, end, prefer_bulk_daily=True), code,
                    )
            except Exception as exc:
                state["failures"][code] = {"name": target["name"], "source": source, "error_type": type(exc).__name__, "error": str(exc)}
                consecutive_failures += 1
                blocked = is_rate_limit_error(exc)
                if stop_on_error or blocked or consecutive_failures >= 3:
                    state["status"] = "blocked" if blocked else "stopped"
                    state["stop_reason"] = str(exc)
                    if blocked or not stop_on_error:
                        wait = max(2700, getattr(exc, "retry_after_seconds", 0))
                        state["retry_after"] = (datetime.now(timezone.utc) + timedelta(seconds=wait)).isoformat()
                        state.setdefault("source_cooldowns", {})[source] = state["retry_after"]
                save_state(args.state, state)
                print(f"failed {code}: {exc}", flush=True)
                if state["status"] != "running":
                    break
                continue

            # 数据库成功提交后才写完成断点；落盘失败后重复运行可幂等更新。
            summary = ingest_kline_payload(db, {
                "job_type": "full_market_daily_kline", "source": payload_source,
                "fetched_at": datetime.now(timezone.utc).isoformat(), "items": rows, "failed_items": [],
            })
            state["inserted"] += int(summary.get("inserted", 0))
            state["updated"] += int(summary.get("updated", 0))
            state["completed"][code] = {
                "source": payload_source,
                "rows": len(rows), "first": min(row["trade_date"] for row in rows),
                "last": max(row["trade_date"] for row in rows),
            }
            state["failures"].pop(code, None)
            consecutive_failures = 0
            save_state(args.state, state)
            print(json.dumps(progress(state), ensure_ascii=False), flush=True)
        if state["status"] == "running":
            state["status"] = "completed" if len(state["completed"]) == len(state["targets"]) else "partial"
    except KeyboardInterrupt:
        db.rollback()
        state["status"] = "interrupted"
    except Exception as exc:
        db.rollback()
        state.update(status="failed", stop_reason=str(exc))
        raise
    finally:
        state["current_code"] = None
        save_state(args.state, state)
        job_status = "success" if state["status"] == "completed" else "partial_failed" if state["status"] == "partial" else "failed"
        record_collection_job(db, "full_market_daily_kline", payload_source, job_status, progress(state),
                              {"days": state["days"], "interval": args.interval, "state": str(args.state), "source": source,
                               "stop_on_error": stop_on_error}, state.get("stop_reason"))
        db.commit()
        print(json.dumps(progress(state), ensure_ascii=False), flush=True)
    return 0 if state["status"] == "completed" else 2


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.status:
        if not args.state.exists():
            print("尚无采集断点", flush=True)
            return 1
        state = json.loads(args.state.read_text(encoding="utf-8"))
        print(json.dumps(progress(state), ensure_ascii=False, indent=2), flush=True)
        return 0
    with history_import_lock():
        state = load_state(args.state, args.days, args.end_date)
        select_source(state, args.source)
        collector = AkshareCollector(request_interval_seconds=args.interval, backoff_seconds=[] if args.stop_on_error else [60, 180],
                                     daily_source=args.source)
        with SessionLocal() as db:
            try:
                return run_import(args, collector, db, state)
            except Exception as exc:
                state.update(status="failed", stop_reason=str(exc))
                if is_rate_limit_error(exc):
                    wait = max(2700, getattr(exc, "retry_after_seconds", 0))
                    state.update(status="blocked", retry_after=(datetime.now(timezone.utc) + timedelta(seconds=wait)).isoformat())
                    state.setdefault("source_cooldowns", {})[args.source] = state["retry_after"]
                save_state(args.state, state)
                raise


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        engine.dispose()
