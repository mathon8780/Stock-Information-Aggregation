from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time as wall_time
from typing import Any

from common.client import post_json


PostFunc = Callable[[str, dict[str, Any] | None], dict[str, Any]]


@dataclass(frozen=True)
class ScheduledTask:
    name: str
    endpoint: str | None
    interval_seconds: int
    trading_hours_only: bool = False
    enabled: bool = True
    description: str = ""


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def default_tasks() -> list[ScheduledTask]:
    return [
        ScheduledTask(
            name="market-data-fetcher",
            endpoint="/api/v1/collector/real/market",
            interval_seconds=_env_int("MARKET_SNAPSHOT_INTERVAL_SECONDS", 300),
            trading_hours_only=True,
            description="refresh real market snapshot",
        ),
        ScheduledTask(
            name="market-analysis-trigger",
            endpoint="/api/v1/analysis/watchlist",
            interval_seconds=_env_int("ADVICE_INTERVAL_SECONDS", 900),
            trading_hours_only=True,
            description="analyze watchlist with rule engine",
        ),
        ScheduledTask(
            name="market-intraday-fetcher",
            endpoint="/api/v1/collector/real/intraday",
            interval_seconds=_env_int("INTRADAY_INTERVAL_SECONDS", 86400),
            description="refresh watchlist 5 minute kline at low frequency",
        ),
        ScheduledTask(
            name="market-history-fetcher",
            endpoint="/api/v1/collector/real/history",
            interval_seconds=_env_int("HISTORY_INTERVAL_SECONDS", 86400),
            description="refresh watchlist and index daily kline at low frequency",
        ),
        ScheduledTask(
            name="market-info-fetcher",
            endpoint="/api/v1/collector/real/news",
            interval_seconds=_env_int("NEWS_AUTO_SYNC_INTERVAL_SECONDS", _env_int("NEWS_INTERVAL_SECONDS", 60)),
            description="refresh real news through NewsNow and DeepSeek",
        ),
    ]


def get_task(name: str) -> ScheduledTask:
    for task in default_tasks():
        if task.name == name:
            return task
    raise KeyError(f"unknown task: {name}")


def is_trading_time(now: datetime | None = None) -> bool:
    current = now or datetime.now()
    if current.weekday() >= 5:
        return False
    current_time = current.time()
    return wall_time(9, 30) <= current_time <= wall_time(11, 30) or wall_time(13, 0) <= current_time <= wall_time(15, 0)


def run_task(
    name: str,
    post: PostFunc = post_json,
    enforce_trading_hours: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    task = get_task(name)
    if not task.enabled or task.endpoint is None:
        return {"task": task.name, "status": "skipped", "reason": task.description or "disabled"}
    if enforce_trading_hours and task.trading_hours_only and not is_trading_time(now):
        return {"task": task.name, "status": "skipped", "reason": "outside trading hours"}
    result = post(task.endpoint, None)
    return {"task": task.name, "status": "success", "endpoint": task.endpoint, "result": result}


def run_due_tasks(
    last_runs: dict[str, float],
    post: PostFunc = post_json,
    enforce_trading_hours: bool = True,
    now: datetime | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> list[dict[str, Any]]:
    current = clock()
    results: list[dict[str, Any]] = []
    for task in default_tasks():
        previous = last_runs.get(task.name, 0)
        if current - previous < task.interval_seconds:
            continue
        result = run_task(task.name, post=post, enforce_trading_hours=enforce_trading_hours, now=now)
        last_runs[task.name] = current
        results.append(result)
    return results


def run_forever(
    sleep: Callable[[float], None] = time.sleep,
    post: PostFunc = post_json,
    poll_seconds: int = 30,
) -> None:
    last_runs: dict[str, float] = {}
    while True:
        for result in run_due_tasks(last_runs, post=post):
            print(json.dumps(result, ensure_ascii=False, default=str), flush=True)
        sleep(poll_seconds)
