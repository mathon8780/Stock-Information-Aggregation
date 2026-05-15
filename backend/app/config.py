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


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, _int(name, default)))


def _database_url() -> str:
    return os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://market:change_me@localhost:5432/market_agent",
    ) or "postgresql+psycopg://market:change_me@localhost:5432/market_agent"


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "local")
    app_port: int = _int("APP_PORT", 8000)
    auto_seed_demo_data: bool = _bool("AUTO_SEED_DEMO_DATA", False)
    database_url: str = _database_url()

    backend_base_url: str = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")
    openclaw_local_token: str = os.getenv("OPENCLAW_LOCAL_TOKEN", "change_me")

    qqbot_target: str = os.getenv("QQBOT_TARGET", "configured_qqbot_default")
    qqbot_enable_price_alert: bool = _bool("QQBOT_ENABLE_PRICE_ALERT", True)
    qqbot_enable_strategy_alert: bool = _bool("QQBOT_ENABLE_STRATEGY_ALERT", True)
    qqbot_enable_news_digest: bool = _bool("QQBOT_ENABLE_NEWS_DIGEST", True)
    qqbot_enable_daily_summary: bool = _bool("QQBOT_ENABLE_DAILY_SUMMARY", True)
    qqbot_enable_job_failed_alert: bool = _bool("QQBOT_ENABLE_JOB_FAILED_ALERT", True)
    qqbot_webhook_url: str = os.getenv("QQBOT_WEBHOOK_URL", "")
    qqbot_batch_size: int = _int("QQBOT_BATCH_SIZE", 10)
    qqbot_max_retry: int = _int("QQBOT_MAX_RETRY", 3)

    market_snapshot_interval_seconds: int = _int("MARKET_SNAPSHOT_INTERVAL_SECONDS", 300)
    watch_snapshot_interval_seconds: int = _int("WATCH_SNAPSHOT_INTERVAL_SECONDS", 60)
    news_interval_seconds: int = _int("NEWS_INTERVAL_SECONDS", 900)
    news_auto_sync_enabled: bool = _bool("NEWS_AUTO_SYNC_ENABLED", not _database_url().startswith("sqlite"))
    news_auto_sync_interval_seconds: int = _int("NEWS_AUTO_SYNC_INTERVAL_SECONDS", 60)
    news_auto_sync_limit: int = _int("NEWS_AUTO_SYNC_LIMIT", 30)
    news_auto_simplify_limit: int = _int("NEWS_AUTO_SIMPLIFY_LIMIT", 50)
    advice_interval_seconds: int = _int("ADVICE_INTERVAL_SECONDS", 900)
    news_source_request_interval_seconds: int = _int("NEWS_SOURCE_REQUEST_INTERVAL_SECONDS", 2)

    request_min_interval_seconds: int = _int("REQUEST_MIN_INTERVAL_SECONDS", 3)
    fetch_failure_downgrade_threshold: int = _int("FETCH_FAILURE_DOWNGRADE_THRESHOLD", 3)
    max_watchlist_size: int = _int("MAX_WATCHLIST_SIZE", 20)

    market_data_primary: str = os.getenv("MARKET_DATA_PRIMARY", "akshare")
    market_data_fallback: str = os.getenv("MARKET_DATA_FALLBACK", "public_web")
    analysis_engine: str = os.getenv("ANALYSIS_ENGINE", "rule_engine")
    local_llm_enabled: bool = _bool("LOCAL_LLM_ENABLED", False)
    local_llm_base_url: str = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434")
    local_llm_model: str = os.getenv("LOCAL_LLM_MODEL", "")
    news_llm_provider: str = os.getenv("NEWS_LLM_PROVIDER", "deepseek")
    news_llm_api_key: str = os.getenv("NEWS_LLM_API_KEY", os.getenv("DEEPSEEK_API_KEY", ""))
    news_llm_api_base_url: str = os.getenv("NEWS_LLM_API_BASE_URL", os.getenv("DEEPSEEK_API_BASE_URL", "https://api.deepseek.com"))
    news_llm_model: str = os.getenv("NEWS_LLM_MODEL", os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"))
    news_llm_timeout_seconds: int = _bounded_int("NEWS_LLM_TIMEOUT_SECONDS", 40, 1, 300)
    news_llm_max_concurrency: int = _bounded_int("NEWS_LLM_MAX_CONCURRENCY", 50, 1, 50)
    newsnow_api_base_url: str = os.getenv("NEWSNOW_API_BASE_URL", "https://newsnow.busiyi.world/api")


settings = Settings()
