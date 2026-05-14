from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import requests
from sqlalchemy.orm import Session

from app.config import settings
from app.services.ingest_service import content_hash, ingest_news_payload, record_collection_job
from app.services.real_collector_service import DEFAULT_WATCHLIST


NEWSNOW_SOURCES: list[tuple[str, str]] = [
    ("cls-telegraph", "财联社"),
    ("wallstreetcn-quick", "华尔街见闻"),
    ("gelonghui", "格隆汇"),
    ("xueqiu-hotstock", "雪球"),
    ("jin10", "金十数据"),
    ("mktnews-flash", "MKTNews"),
]


class NewsNowFetcher:
    def __init__(self, base_url: str | None = None, timeout: float = 20.0) -> None:
        self.base_url = (base_url or settings.newsnow_api_base_url).rstrip("/")
        self.timeout = timeout

    def fetch_source(self, source_id: str, source_name: str, limit: int) -> list[dict[str, Any]]:
        url = f"{self.base_url}/s?{urlencode({'id': source_id})}"
        headers = {
            "Accept": "application/json",
            "Referer": "https://newsnow.busiyi.world/c/realtime",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        }
        response = requests.get(url, timeout=self.timeout, headers=headers)
        response.raise_for_status()
        data = response.json()
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise RuntimeError(f"NewsNow source {source_id} returned no items")
        normalized: list[dict[str, Any]] = []
        for item in items[:limit]:
            title = str(item.get("title") or "").strip()
            url_value = item.get("url") or item.get("mobileUrl") or ""
            if not title or not url_value:
                continue
            normalized.append(
                {
                    "source_id": source_id,
                    "source_name": source_name,
                    "id": str(item.get("id") or item.get("url") or title),
                    "title": title,
                    "url": str(url_value),
                    "published_at": _news_time(item, data.get("updatedTime")),
                    "raw": item,
                }
            )
        return normalized


class OpenAICompatibleNewsFormatter:
    def __init__(
        self,
        api_key: str | None = None,
        api_base_url: str | None = None,
        model: str | None = None,
        timeout: float = 45.0,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.news_llm_api_key
        self.api_base_url = (api_base_url or settings.news_llm_api_base_url).rstrip("/")
        self.model = model or settings.news_llm_model
        self.timeout = timeout

    def format_items(self, items: list[dict[str, Any]], watchlist: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not self.api_key:
            raise RuntimeError("NEWS_LLM_API_KEY is not configured")
        messages = [
            {
                "role": "system",
                "content": (
                    "你是证券资讯编辑，只做信息整理，不提供投资建议。"
                    "必须基于输入新闻，不编造事实。只返回 JSON，不要 Markdown。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                    "task": f"使用 {settings.news_llm_provider} 整理证券市场新闻，输出适合课程系统入库的文本。",
                        "watchlist": watchlist,
                        "schema": {
                            "items": [
                                {
                                    "source_item_id": "原始新闻 id",
                                    "title": "简洁中文标题",
                                    "summary": "80字以内中文摘要",
                                    "content": "只包含文本的整理正文，列出关键信息和可能影响，不写买卖建议",
                                    "source": "newsnow:来源名",
                                    "url": "原文地址",
                                    "published_at": "ISO时间",
                                    "scope": "market 或 stock",
                                    "code": "若明确关联自选股则给股票代码，否则为空",
                                    "sentiment": "positive/neutral/negative",
                                    "importance": "1到5的整数",
                                }
                            ]
                        },
                        "items": [
                            {
                                "source_item_id": item["id"],
                                "source": f"newsnow:{item['source_name']}",
                                "title": item["title"],
                                "url": item["url"],
                                "published_at": item["published_at"],
                            }
                            for item in items
                        ],
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        payload = {"model": self.model, "messages": messages, "temperature": 0.1}
        endpoint = self.api_base_url if self.api_base_url.endswith("/chat/completions") else f"{self.api_base_url}/chat/completions"
        response = requests.post(endpoint, timeout=self.timeout, headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}, json=payload)
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        parsed = _parse_llm_json(content)
        llm_items = parsed.get("items") if isinstance(parsed, dict) else parsed
        if not isinstance(llm_items, list):
            raise RuntimeError("LLM response did not contain an items array")
        return [item for item in llm_items if isinstance(item, dict)]


class NewsCollector:
    def __init__(
        self,
        fetcher: Any | None = None,
        formatter: Any | None = None,
        source_ids: list[tuple[str, str]] | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.fetcher = fetcher or NewsNowFetcher()
        self.formatter = formatter or OpenAICompatibleNewsFormatter()
        self.source_ids = source_ids or NEWSNOW_SOURCES
        self.sleep = sleep_fn

    def collect(self, db: Session, limit: int = 30) -> dict[str, Any]:
        watchlist = DEFAULT_WATCHLIST
        raw_items: list[dict[str, Any]] = []
        failed_items: list[dict[str, Any]] = []
        per_source_limit = max(2, min(10, (limit + len(self.source_ids) - 1) // len(self.source_ids)))
        for index, (source_id, source_name) in enumerate(self.source_ids):
            if index:
                self.sleep(settings.news_source_request_interval_seconds)
            try:
                raw_items.extend(self.fetcher.fetch_source(source_id, source_name, per_source_limit))
            except Exception as exc:
                failed_items.append({"source_id": source_id, "source_name": source_name, "error": str(exc)})
        raw_items = _dedupe_raw_items(raw_items)[:limit]
        if not raw_items:
            return self._record_failure(db, failed_items, "no news items returned")
        try:
            formatted_items = self.formatter.format_items(raw_items, watchlist)
        except Exception as exc:
            return self._record_failure(db, failed_items, str(exc))
        raw_by_id = {str(item["id"]): item for item in raw_items}
        ingest_items = [self._normalize_formatted_item(item, raw_by_id, watchlist) for item in formatted_items]
        ingest_items = [item for item in ingest_items if item is not None]
        if not ingest_items:
            return self._record_failure(db, failed_items, "LLM returned no usable news items")
        payload = {
            "job_type": "news",
            "source": "newsnow+deepseek",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "items": ingest_items,
            "failed_items": failed_items,
        }
        summary = ingest_news_payload(db, payload)
        summary["failed_items"] = failed_items
        return summary

    def _normalize_formatted_item(
        self,
        item: dict[str, Any],
        raw_by_id: dict[str, dict[str, Any]],
        watchlist: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        raw_id = str(item.get("source_item_id") or item.get("id") or "")
        raw = raw_by_id.get(raw_id)
        if raw is None:
            url = str(item.get("url") or "")
            raw = next((candidate for candidate in raw_by_id.values() if candidate["url"] == url), None)
        if raw is None:
            return None
        code = str(item.get("code") or "").strip().upper() or _infer_watch_code(f"{item.get('title', '')} {item.get('summary', '')} {raw.get('title', '')}", watchlist)
        source_name = raw["source_name"]
        title = str(item.get("title") or raw["title"]).strip()
        summary = str(item.get("summary") or title).strip()
        content = str(item.get("content") or summary).strip()
        return {
            "code": code or None,
            "scope": str(item.get("scope") or ("stock" if code else "market")),
            "title": title,
            "summary": summary,
            "content": content,
            "source": str(item.get("source") or f"newsnow:{source_name}"),
            "url": str(item.get("url") or raw["url"]),
            "published_at": item.get("published_at") or raw["published_at"],
            "sentiment": _safe_choice(str(item.get("sentiment") or "neutral"), {"positive", "neutral", "negative"}, "neutral"),
            "importance": _safe_importance(item.get("importance")),
            "content_hash": content_hash("newsnow", raw["source_id"], raw["id"], raw["url"]),
            "raw_payload": {
                "source_id": raw["source_id"],
                "source_name": raw["source_name"],
                "source_item_id": raw["id"],
                "original_title": raw["title"],
                "original_url": raw["url"],
                "llm_model": getattr(self.formatter, "model", None),
            },
        }

    def _record_failure(self, db: Session, failed_items: list[dict[str, Any]], error_message: str) -> dict[str, Any]:
        summary = {"inserted": 0, "skipped": 0, "failed": max(1, len(failed_items)), "failed_items": failed_items, "error_message": error_message}
        record_collection_job(db, "news", "newsnow+deepseek", "failed", summary, {"sources": [source_id for source_id, _ in self.source_ids]}, error_message)
        db.commit()
        return summary


def _dedupe_raw_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        key = f"{item.get('source_id')}:{item.get('id')}:{item.get('url')}"
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _news_time(item: dict[str, Any], fallback: Any = None) -> str:
    raw = item.get("pubDate") or item.get("date") or (item.get("extra") or {}).get("date") or fallback
    if isinstance(raw, (int, float)):
        seconds = raw / 1000 if raw > 10_000_000_000 else raw
        return datetime.fromtimestamp(seconds, timezone.utc).isoformat()
    if isinstance(raw, str) and raw.strip():
        text = raw.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone(timedelta(hours=8)))
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            pass
    return datetime.now(timezone.utc).isoformat()


def _parse_llm_json(content: str) -> Any:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()
    return json.loads(text)


def _infer_watch_code(text: str, watchlist: list[dict[str, Any]]) -> str:
    normalized = text.upper()
    for stock in watchlist:
        code = stock["code"].upper()
        compact = code.replace(".", "")
        if stock["name"] in text or code in normalized or compact in normalized:
            return code
    return ""


def _safe_choice(value: str, allowed: set[str], fallback: str) -> str:
    return value if value in allowed else fallback


def _safe_importance(value: Any) -> int:
    try:
        return max(1, min(5, int(value)))
    except (TypeError, ValueError):
        return 3
