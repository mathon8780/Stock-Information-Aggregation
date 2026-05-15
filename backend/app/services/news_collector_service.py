from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import News
from app.services.event_bus import publish_event
from app.services.ingest_service import content_hash, get_or_create_stock, ingest_news_payload, record_collection_job, truncate_news_original_title
from app.services.news_llm_config_service import EffectiveNewsLlmConfig, get_effective_news_llm_config
from app.services.notification_service import create_news_notification_if_needed
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
                }
            )
        return normalized


class ArticleContentFetcher:
    def __init__(self, timeout: float = 20.0, max_chars: int = 12000) -> None:
        self.timeout = timeout
        self.max_chars = max_chars

    def fetch(self, url: str) -> str:
        response = requests.get(
            url,
            timeout=self.timeout,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            },
        )
        response.raise_for_status()
        response.encoding = response.encoding or response.apparent_encoding
        soup = BeautifulSoup(response.text, "html.parser")
        for node in soup(["script", "style", "noscript", "svg"]):
            node.decompose()
        root = soup.find("article") or soup.find("main") or soup.body or soup
        parts = [
            node.get_text(" ", strip=True)
            for node in root.find_all(["h1", "h2", "h3", "p", "li"])
            if node.get_text(" ", strip=True)
        ]
        text = " ".join(parts) if parts else root.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            raise RuntimeError("article body is empty")
        return text[: self.max_chars]


class OpenAICompatibleNewsFormatter:
    def __init__(
        self,
        config: EffectiveNewsLlmConfig | None = None,
        api_key: str | None = None,
        api_base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.provider = config.provider if config else settings.news_llm_provider
        self.api_key = api_key if api_key is not None else (config.api_key if config else settings.news_llm_api_key)
        self.api_base_url = (api_base_url or (config.api_base_url if config else settings.news_llm_api_base_url)).rstrip("/")
        self.model = model or (config.model if config else settings.news_llm_model)
        self.prompt_preset = config.prompt_preset if config else "default"
        self.prompt_text = config.prompt_text if config else ""
        self.timeout = settings.news_llm_timeout_seconds if timeout is None else timeout

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
                        "task": f"使用 {self.provider} 整理证券市场新闻，输出适合课程系统入库的简化文本。",
                        "user_prompt": self.prompt_text,
                        "watchlist": watchlist,
                        "schema": {
                            "items": [
                                {
                                    "source_item_id": "输入中的 source_item_id",
                                    "title": "简洁中文标题",
                                    "summary": "80字以内中文摘要",
                                    "content": "只包含简化正文，列出关键事实和可能影响，不写买卖建议",
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
                                "source_item_id": str(item["source_item_id"]),
                                "source": item["source"],
                                "title": item["title"],
                                "url": item["url"],
                                "published_at": item["published_at"],
                                "article_text": item.get("article_text", ""),
                            }
                            for item in items
                        ],
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        payload: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": 0.1}
        if self._is_deepseek_provider():
            payload["thinking"] = {"type": "disabled"}
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

    def _is_deepseek_provider(self) -> bool:
        provider = self.provider.lower()
        base_url = self.api_base_url.lower()
        return provider == "deepseek" or "api.deepseek.com" in base_url


class NewsCollector:
    def __init__(
        self,
        fetcher: Any | None = None,
        formatter: Any | None = None,
        article_fetcher: Any | None = None,
        source_ids: list[tuple[str, str]] | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.fetcher = fetcher or NewsNowFetcher()
        self.formatter = formatter
        self.formatter_provided = formatter is not None
        self.article_fetcher = article_fetcher or ArticleContentFetcher()
        self.source_ids = source_ids or NEWSNOW_SOURCES
        self.sleep = sleep_fn

    def collect(self, db: Session, limit: int = 30) -> dict[str, Any]:
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

        ingest_items = [self._metadata_item(item) for item in raw_items]
        payload = {
            "job_type": "news",
            "source": "newsnow",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "items": ingest_items,
            "failed_items": failed_items,
        }
        summary = ingest_news_payload(db, payload)
        summary["failed_items"] = failed_items

        config = get_effective_news_llm_config(db)
        if self.formatter_provided or config.api_key_configured:
            summary["simplify"] = self.simplify_pending(
                db,
                limit=limit,
                content_hashes=[item["content_hash"] for item in ingest_items],
                record_job=True,
            )
        else:
            summary["simplify"] = {"processed": 0, "simplified": 0, "failed": 0, "skipped": len(ingest_items), "reason": "NEWS_LLM_API_KEY is not configured"}
        return summary

    def simplify_pending(
        self,
        db: Session,
        limit: int = 30,
        content_hashes: list[str] | None = None,
        record_job: bool = True,
    ) -> dict[str, Any]:
        config = get_effective_news_llm_config(db)
        if not self.formatter_provided and not config.api_key_configured:
            summary = {"processed": 0, "simplified": 0, "failed": 0, "skipped": 0, "reason": "NEWS_LLM_API_KEY is not configured"}
            if record_job:
                record_collection_job(db, "news_simplify", "newsnow", "skipped", summary, {"limit": limit})
                db.commit()
                publish_event("jobs.updated", {"job_type": "news_simplify"})
            return summary

        stmt = select(News).where(News.url.is_not(None), News.simplification_status.in_(["pending", "failed"]))
        if content_hashes:
            stmt = stmt.where(News.content_hash.in_(content_hashes))
        rows = db.execute(stmt.order_by(desc(News.fetched_at), desc(News.id)).limit(limit)).scalars().all()
        if not rows:
            summary = {"processed": 0, "simplified": 0, "failed": 0, "skipped": 0}
            if record_job:
                record_collection_job(db, "news_simplify", f"newsnow+{config.provider}", "success", summary, {"limit": limit})
                db.commit()
                publish_event("jobs.updated", {"job_type": "news_simplify"})
            return summary

        formatter = self._formatter_for(config)
        row_by_id = {str(row.id): row for row in rows}
        simplify_inputs = [
            {
                "source_item_id": str(row.id),
                "source": row.source,
                "title": row.original_title or row.title,
                "url": row.url,
                "published_at": row.published_at.isoformat() if row.published_at else row.fetched_at.isoformat(),
            }
            for row in rows
        ]
        simplified = 0
        failed_ids: set[int] = set()
        max_workers = min(settings.news_llm_max_concurrency, 50, len(simplify_inputs))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_row_id = {
                executor.submit(self._fetch_and_simplify_item, item, formatter): str(item["source_item_id"])
                for item in simplify_inputs
            }
            for future in as_completed(future_to_row_id):
                row_id = future_to_row_id[future]
                row = row_by_id.get(row_id)
                if row is None:
                    continue
                try:
                    item = future.result()
                except Exception as exc:
                    self._mark_failed(row, str(exc))
                    failed_ids.add(row.id)
                    continue
                self._apply_simplified_item(db, row, item, config, formatter)
                simplified += 1

        summary = {"processed": len(rows), "simplified": simplified, "failed": len(failed_ids), "skipped": max(0, len(rows) - simplified - len(failed_ids))}
        db.commit()
        publish_event("news.updated", summary)
        if simplified:
            publish_event("notifications.updated", {"source": "news_digest", "created": simplified})
        if record_job:
            record_collection_job(db, "news_simplify", f"newsnow+{config.provider}", "success" if not failed_ids else "partial_failed", summary, {"limit": limit, "content_hashes": content_hashes})
            db.commit()
            publish_event("jobs.updated", {"job_type": "news_simplify"})
        return summary

    def _fetch_and_simplify_item(self, item: dict[str, Any], formatter: Any) -> dict[str, Any]:
        original_title = str(item.get("title") or "").strip()
        try:
            article_text = self.article_fetcher.fetch(str(item["url"]))
        except Exception as exc:
            article_text = f"{original_title}\n来源：{item.get('source')}\n原文地址：{item.get('url')}\n正文抓取失败：{exc}"

        source_item_id = str(item["source_item_id"])
        formatted_items = formatter.format_items(
            [
                {
                    "source_item_id": source_item_id,
                    "source": item.get("source"),
                    "title": original_title,
                    "url": item.get("url"),
                    "published_at": item.get("published_at"),
                    "article_text": article_text,
                }
            ],
            DEFAULT_WATCHLIST,
        )
        for formatted_item in formatted_items:
            returned_id = str(formatted_item.get("source_item_id") or formatted_item.get("id") or "")
            if returned_id == source_item_id:
                return formatted_item
        if formatted_items:
            formatted_items[0]["source_item_id"] = source_item_id
            return formatted_items[0]
        raise RuntimeError("LLM did not return this news item")

    def _formatter_for(self, config: EffectiveNewsLlmConfig) -> Any:
        return self.formatter or OpenAICompatibleNewsFormatter(config=config)

    def _metadata_item(self, raw: dict[str, Any]) -> dict[str, Any]:
        digest = content_hash("newsnow", raw["source_id"], raw["id"], raw["url"])
        original_title = truncate_news_original_title(raw["title"])
        return {
            "scope": "market",
            "title": str(raw["title"]).strip(),
            "original_title": original_title,
            "summary": "",
            "content": None,
            "source": f"newsnow:{raw['source_name']}",
            "url": str(raw["url"]),
            "published_at": raw["published_at"],
            "sentiment": "neutral",
            "importance": 3,
            "content_hash": digest,
            "simplification_status": "pending",
            "raw_payload": {
                "source_id": raw["source_id"],
                "source_name": raw["source_name"],
                "source_item_id": raw["id"],
                "original_title": original_title,
                "original_url": raw["url"],
            },
        }

    def _apply_simplified_item(
        self,
        db: Session,
        row: News,
        item: dict[str, Any],
        config: EffectiveNewsLlmConfig,
        formatter: Any,
    ) -> None:
        code = str(item.get("code") or "").strip().upper() or _infer_watch_code(f"{item.get('title', '')} {item.get('summary', '')} {item.get('content', '')}", DEFAULT_WATCHLIST)
        if code:
            stock_meta = next((stock for stock in DEFAULT_WATCHLIST if stock["code"].upper() == code), {"code": code, "name": code})
            stock = get_or_create_stock(db, stock_meta)
            row.stock_id = stock.id
        if not row.original_title:
            row.original_title = truncate_news_original_title(row.title)
        row.scope = _safe_choice(str(item.get("scope") or ("stock" if code else row.scope or "market")), {"market", "stock", "security"}, "market")
        row.title = str(item.get("title") or row.title).strip()
        row.summary = str(item.get("summary") or row.title).strip()
        row.content = str(item.get("content") or row.summary or row.title).strip()
        row.source = str(item.get("source") or row.source).strip()
        row.url = str(item.get("url") or row.url).strip() or row.url
        row.sentiment = _safe_choice(str(item.get("sentiment") or "neutral"), {"positive", "neutral", "negative"}, "neutral")
        row.importance = _safe_importance(item.get("importance"))
        row.simplification_status = "simplified"
        row.simplified_at = datetime.now(timezone.utc)
        row.llm_provider = config.provider
        row.llm_model = getattr(formatter, "model", config.model)
        row.prompt_name = config.prompt_preset
        row.error_message = None
        payload = dict(row.raw_payload or {})
        payload.update({"llm_provider": row.llm_provider, "llm_model": row.llm_model, "prompt_name": row.prompt_name})
        row.raw_payload = payload
        create_news_notification_if_needed(db, row)

    def _mark_failed(self, row: News, error_message: str) -> None:
        row.simplification_status = "failed"
        row.error_message = error_message[:1000]

    def _record_failure(self, db: Session, failed_items: list[dict[str, Any]], error_message: str) -> dict[str, Any]:
        summary = {"inserted": 0, "skipped": 0, "failed": max(1, len(failed_items)), "failed_items": failed_items, "error_message": error_message}
        record_collection_job(db, "news", "newsnow", "failed", summary, {"sources": [source_id for source_id, _ in self.source_ids]}, error_message)
        db.commit()
        publish_event("jobs.updated", {"job_type": "news"})
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
