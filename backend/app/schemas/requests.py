from __future__ import annotations

from pydantic import BaseModel, Field


class AddWatchRequest(BaseModel):
    code: str = Field(..., examples=["300308.SZ"])
    alert_enabled: bool = True
    alert_threshold_pct: float = 3.0
    strategy_push_enabled: bool = True


class UpdateWatchRequest(BaseModel):
    alert_enabled: bool | None = None
    alert_threshold_pct: float | None = None
    strategy_push_enabled: bool | None = None
    display_order: int | None = None


class NewsLlmConfigRequest(BaseModel):
    provider: str = Field("deepseek", min_length=1, max_length=64)
    api_base_url: str = Field("https://api.deepseek.com", min_length=1)
    model: str = Field("deepseek-v4-flash", min_length=1, max_length=128)
    api_key: str | None = None
    clear_api_key: bool = False
    prompt_preset: str = Field("default", min_length=1, max_length=64)
    custom_prompt: str | None = None
