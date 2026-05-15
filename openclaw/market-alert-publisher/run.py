from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1]))

from common.client import get_json, post_json


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _mark_result(notification_id: int, status: str, error_message: str | None = None) -> None:
    post_json(
        "/api/v1/ingest/openclaw/notification-result",
        {"notification_id": notification_id, "status": status, "error_message": error_message},
    )


def _post_qqbot_webhook(webhook_url: str, item: dict[str, Any]) -> None:
    payload = {
        "target": item.get("target_channel"),
        "title": item.get("title"),
        "content": item.get("content"),
        "notification_id": item.get("id"),
        "notification_type": item.get("notification_type"),
        "payload": item.get("payload") or {},
    }
    request = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status >= 400:
                raise RuntimeError(f"QQBot webhook returned HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"QQBot webhook failed: HTTP {exc.code} {detail}") from exc


def publish_pending_notifications(
    dry_run: bool | None = None,
    webhook_url: str | None = None,
    batch_size: int | None = None,
    max_retry: int | None = None,
) -> dict[str, Any]:
    dry_run = _env_bool("QQBOT_DRY_RUN", True) if dry_run is None else dry_run
    webhook_url = os.getenv("QQBOT_WEBHOOK_URL", "") if webhook_url is None else webhook_url
    batch_size = _env_int("QQBOT_BATCH_SIZE", 10) if batch_size is None else batch_size
    max_retry = _env_int("QQBOT_MAX_RETRY", 3) if max_retry is None else max_retry

    pending = get_json(f"/api/v1/notifications?status=pending&limit={max(1, batch_size)}").get("items", [])
    sent = failed = skipped = 0
    for item in pending:
        notification_id = int(item["id"])
        if int(item.get("retry_count") or 0) >= max_retry:
            _mark_result(notification_id, "failed", f"max retry reached: {max_retry}")
            skipped += 1
            continue
        try:
            if dry_run:
                print(f"[QQBot dry-run] {item['title']}: {item['content']}", flush=True)
            else:
                if not webhook_url:
                    raise RuntimeError("QQBOT_WEBHOOK_URL is not configured")
                _post_qqbot_webhook(webhook_url, item)
        except Exception as exc:
            _mark_result(notification_id, "failed", str(exc)[:1000])
            failed += 1
        else:
            _mark_result(notification_id, "sent")
            sent += 1
    result = {"published": sent, "failed": failed, "skipped": skipped, "dry_run": dry_run}
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


def main() -> None:
    publish_pending_notifications()


if __name__ == "__main__":
    main()
