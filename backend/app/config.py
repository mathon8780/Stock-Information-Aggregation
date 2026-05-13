from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BASE_DIR.parent
load_dotenv(PROJECT_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "local")
    app_port: int = _int("APP_PORT", 8000)
    auto_seed_demo_data: bool = _bool("AUTO_SEED_DEMO_DATA", False)
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://market:change_me@localhost:5432/market_agent",
    ) or "postgresql+psycopg://market:change_me@localhost:5432/market_agent"

    backend_base_url: str = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")
    openclaw_local_token: str = os.getenv("OPENCLAW_LOCAL_TOKEN", "change_me")

    qqbot_target: str = os.getenv("QQBOT_TARGET", "configured_qqbot_default")
    qqbot_enable_price_alert: bool = _bool("QQBOT_ENABLE_PRICE_ALERT", True)
    qqbot_enable_strategy_alert: bool = _bool("QQBOT_ENABLE_STRATEGY_ALERT", True)
    qqbot_enable_daily_summary: bool = _bool("QQBOT_ENABLE_DAILY_SUMMARY", True)
    qqbot_enable_job_failed_alert: bool = _bool("QQBOT_ENABLE_JOB_FAILED_ALERT", True)

    market_snapshot_interval_seconds: int = _int("MARKET_SNAPSHOT_INTERVAL_SECONDS", 300)
    watch_snapshot_interval_seconds: int = _int("WATCH_SNAPSHOT_INTERVAL_SECONDS", 60)
    news_interval_seconds: int = _int("NEWS_INTERVAL_SECONDS", 900)
    advice_interval_seconds: int = _int("ADVICE_INTERVAL_SECONDS", 900)

    request_min_interval_seconds: int = _int("REQUEST_MIN_INTERVAL_SECONDS", 3)
    fetch_failure_downgrade_threshold: int = _int("FETCH_FAILURE_DOWNGRADE_THRESHOLD", 3)
    max_watchlist_size: int = _int("MAX_WATCHLIST_SIZE", 50)

    market_data_primary: str = os.getenv("MARKET_DATA_PRIMARY", "akshare")
    market_data_fallback: str = os.getenv("MARKET_DATA_FALLBACK", "public_web")
    analysis_engine: str = os.getenv("ANALYSIS_ENGINE", "rule_engine")
    local_llm_enabled: bool = _bool("LOCAL_LLM_ENABLED", False)
    local_llm_base_url: str = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434")
    local_llm_model: str = os.getenv("LOCAL_LLM_MODEL", "")


settings = Settings()
