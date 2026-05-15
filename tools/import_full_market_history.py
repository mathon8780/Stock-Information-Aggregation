from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import func, select  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402
from app.models import KlineDaily, Stock  # noqa: E402
from app.services.ingest_service import ingest_kline_payload, record_collection_job  # noqa: E402
from app.services.real_collector_service import AkshareCollector  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import past-year full-market A-share daily K lines into the local database.")
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--batch-rows", type=int, default=20_000)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--min-existing-rows", type=int, default=180)
    return parser.parse_args()


def has_existing_history(db: Any, target: dict[str, str], start: date, end: date, min_rows: int) -> bool:
    stock = db.execute(select(Stock).where(Stock.code == target["code"])).scalar_one_or_none()
    if stock is None:
        return False
    count = db.execute(
        select(func.count())
        .select_from(KlineDaily)
        .where(KlineDaily.stock_id == stock.id, KlineDaily.trade_date >= start, KlineDaily.trade_date <= end)
    ).scalar_one()
    return count >= min_rows


def fetch_one(target: dict[str, str], start: date, end: date) -> tuple[dict[str, str], list[dict[str, Any]], str | None]:
    collector = AkshareCollector(request_interval_seconds=0, backoff_seconds=[1, 3])
    try:
        rows = collector._history_rows_for_target(target, start, end, prefer_bulk_daily=True)
        return target, rows, None
    except Exception as exc:
        return target, [], str(exc)


def flush_rows(db: Any, rows: list[dict[str, Any]]) -> dict[str, int]:
    if not rows:
        return {"inserted": 0, "updated": 0}
    return ingest_kline_payload(
        db,
        {
            "job_type": "full_market_daily_kline",
            "source": "akshare",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "items": rows,
            "failed_items": [],
        },
    )


def main() -> None:
    args = parse_args()
    start_time = time.perf_counter()
    end = date.today()
    start = end - timedelta(days=args.days)

    collector = AkshareCollector(request_interval_seconds=0, backoff_seconds=[1, 3])
    targets = collector._full_market_stock_targets()
    if args.limit is not None:
        targets = targets[: args.limit]

    with SessionLocal() as db:
        if args.skip_existing:
            before = len(targets)
            targets = [target for target in targets if not has_existing_history(db, target, start, end, args.min_existing_rows)]
            print(f"skip_existing={before - len(targets)} remaining={len(targets)}", flush=True)

        print(f"targets={len(targets)} days={args.days} workers={args.workers} range={start}..{end}", flush=True)
        buffer: list[dict[str, Any]] = []
        failed_items: list[dict[str, str]] = []
        inserted = 0
        updated = 0
        processed = 0

        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(fetch_one, target, start, end) for target in targets]
            for future in as_completed(futures):
                target, rows, error = future.result()
                processed += 1
                if error:
                    failed_items.append({"code": target["code"], "name": target["name"], "error": error})
                else:
                    buffer.extend(rows)

                if len(buffer) >= args.batch_rows:
                    summary = flush_rows(db, buffer)
                    inserted += int(summary.get("inserted", 0))
                    updated += int(summary.get("updated", 0))
                    buffer = []

                if processed == len(targets) or processed % 25 == 0:
                    elapsed = time.perf_counter() - start_time
                    print(
                        f"progress={processed}/{len(targets)} inserted={inserted} updated={updated} "
                        f"buffer={len(buffer)} failed={len(failed_items)} elapsed={elapsed:.1f}s",
                        flush=True,
                    )

        summary = flush_rows(db, buffer)
        inserted += int(summary.get("inserted", 0))
        updated += int(summary.get("updated", 0))
        result = {
            "total_targets": len(targets),
            "processed": processed,
            "inserted": inserted,
            "updated": updated,
            "failed": len(failed_items),
        }
        record_collection_job(
            db,
            "full_market_daily_kline",
            "akshare",
            "success" if not failed_items else "partial_failed",
            result,
            {"days": args.days, "workers": args.workers, "batch_rows": args.batch_rows, "skip_existing": args.skip_existing},
            None if not failed_items else f"{len(failed_items)} targets failed",
        )
        db.commit()

    print(result, flush=True)
    if failed_items:
        print("failed_samples=", failed_items[:10], flush=True)


if __name__ == "__main__":
    try:
        main()
    finally:
        engine.dispose()
