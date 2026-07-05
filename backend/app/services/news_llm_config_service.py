from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests
from sqlalchemy.orm import Session

from app.config import settings
from app.models import NewsLlmConfig


DEFAULT_PROMPT_PRESET = "default"
DEFAULT_NEWS_PROMPTS = {
    DEFAULT_PROMPT_PRESET: (
        "请把证券新闻简化为适合行情监控系统展示的中文内容。"
        "摘要不超过80字，正文只保留关键事实、相关标的、时间、来源和可能影响；"
        "不要给出买入、卖出、持仓等投资建议，不要编造输入中没有的信息。"
    )
}


@dataclass(frozen=True)
class EffectiveNewsLlmConfig:
    provider: str
    api_base_url: str
    model: str
    api_key: str
    prompt_preset: str
    prompt_text: str
    custom_prompt: str
    api_key_configured: bool


def get_news_llm_config_row(db: Session) -> NewsLlmConfig | None:
    return db.get(NewsLlmConfig, 1)


def get_effective_news_llm_config(db: Session) -> EffectiveNewsLlmConfig:
    row = get_news_llm_config_row(db)
    prompt_preset = (row.prompt_preset if row and row.prompt_preset else DEFAULT_PROMPT_PRESET).strip()
    default_prompt = DEFAULT_NEWS_PROMPTS.get(prompt_preset, DEFAULT_NEWS_PROMPTS[DEFAULT_PROMPT_PRESET])
    custom_prompt = (row.custom_prompt if row and row.custom_prompt else "").strip()
    prompt_text = custom_prompt or default_prompt
    api_key = (row.api_key if row and row.api_key else settings.news_llm_api_key).strip()
    return EffectiveNewsLlmConfig(
        provider=(row.provider if row and row.provider else settings.news_llm_provider).strip() or "deepseek",
        api_base_url=(row.api_base_url if row and row.api_base_url else settings.news_llm_api_base_url).strip(),
        model=(row.model if row and row.model else settings.news_llm_model).strip(),
        api_key=api_key,
        prompt_preset=prompt_preset,
        prompt_text=prompt_text,
        custom_prompt=custom_prompt,
        api_key_configured=bool(api_key),
    )


def news_llm_config_dict(db: Session) -> dict[str, Any]:
    row = get_news_llm_config_row(db)
    effective = get_effective_news_llm_config(db)
    return {
        "provider": effective.provider,
        "api_base_url": effective.api_base_url,
        "model": effective.model,
        "api_key_configured": effective.api_key_configured,
        "prompt_preset": effective.prompt_preset,
        "custom_prompt": effective.custom_prompt,
        "custom_prompt_configured": bool(effective.custom_prompt),
        "default_prompt": DEFAULT_NEWS_PROMPTS[DEFAULT_PROMPT_PRESET],
        "effective_prompt": effective.prompt_text,
        "updated_at": row.updated_at.isoformat() if row else None,
    }


def validate_news_llm_config_status(db: Session) -> dict[str, Any]:
    effective = get_effective_news_llm_config(db)
    checked_at = datetime.now(timezone.utc).isoformat()
    base = {
        "provider": effective.provider,
        "model": effective.model,
        "api_base_url": effective.api_base_url,
        "api_key_configured": effective.api_key_configured,
        "checked_at": checked_at,
    }
    if not effective.api_key_configured:
        return {**base, "ok": False, "status": "missing", "message": "API Key 未配置"}

    endpoint = effective.api_base_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint = f"{endpoint}/chat/completions"
    payload: dict[str, Any] = {
        "model": effective.model,
        "messages": [{"role": "user", "content": "ping"}],
        "temperature": 0,
        "max_tokens": 1,
    }
    if effective.provider.lower() == "deepseek" or "api.deepseek.com" in effective.api_base_url.lower():
        payload["thinking"] = {"type": "disabled"}

    try:
        response = requests.post(
            endpoint,
            timeout=min(settings.news_llm_timeout_seconds, 15),
            headers={"Authorization": f"Bearer {effective.api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        return {**base, "ok": False, "status": "invalid", "message": f"API Key 检测失败：{exc}"}

    choices = data.get("choices") if isinstance(data, dict) else None
    if not isinstance(choices, list) or not choices:
        return {**base, "ok": False, "status": "invalid", "message": "API Key 检测失败：响应缺少 choices"}
    return {**base, "ok": True, "status": "valid", "message": "API Key 可用"}


def save_news_llm_config(db: Session, payload: dict[str, Any]) -> NewsLlmConfig:
    row = get_news_llm_config_row(db)
    if row is None:
        row = NewsLlmConfig(id=1)
        db.add(row)
        db.flush()
    row.provider = str(payload.get("provider") or settings.news_llm_provider).strip() or "deepseek"
    row.api_base_url = str(payload.get("api_base_url") or settings.news_llm_api_base_url).strip()
    row.model = str(payload.get("model") or settings.news_llm_model).strip()
    row.prompt_preset = str(payload.get("prompt_preset") or DEFAULT_PROMPT_PRESET).strip() or DEFAULT_PROMPT_PRESET
    row.custom_prompt = (str(payload.get("custom_prompt")).strip() if payload.get("custom_prompt") is not None else None) or None
    if payload.get("clear_api_key"):
        row.api_key = None
    elif payload.get("api_key") is not None and str(payload.get("api_key")).strip():
        row.api_key = str(payload.get("api_key")).strip()
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row
