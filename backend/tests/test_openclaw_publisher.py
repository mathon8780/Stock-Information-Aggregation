from __future__ import annotations

import importlib.util
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[2]


def load_publisher_module():
    path = PROJECT_DIR / "openclaw" / "market-alert-publisher" / "run.py"
    spec = importlib.util.spec_from_file_location("market_alert_publisher_run", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_qqbot_publisher_posts_webhook_and_marks_sent(monkeypatch):
    publisher = load_publisher_module()
    posted: list[tuple[str, dict]] = []
    status_updates: list[tuple[str, dict]] = []

    monkeypatch.setattr(
        publisher,
        "get_json",
        lambda path: {
            "items": [
                {
                    "id": 7,
                    "notification_type": "news_digest",
                    "target_channel": "group-1",
                    "title": "财联社：新闻标题",
                    "content": "简化内容",
                    "payload": {"news_id": 3},
                    "retry_count": 0,
                }
            ]
        },
    )
    monkeypatch.setattr(publisher, "_post_qqbot_webhook", lambda url, item: posted.append((url, item)))
    monkeypatch.setattr(publisher, "post_json", lambda path, payload: status_updates.append((path, payload)) or {})

    result = publisher.publish_pending_notifications(dry_run=False, webhook_url="http://qqbot.local/send", batch_size=5)

    assert result == {"published": 1, "failed": 0, "skipped": 0, "dry_run": False}
    assert posted[0][0] == "http://qqbot.local/send"
    assert posted[0][1]["id"] == 7
    assert status_updates == [
        (
            "/api/v1/ingest/openclaw/notification-result",
            {"notification_id": 7, "status": "sent", "error_message": None},
        )
    ]


def test_qqbot_publisher_reports_webhook_failure(monkeypatch):
    publisher = load_publisher_module()
    status_updates: list[tuple[str, dict]] = []

    monkeypatch.setattr(
        publisher,
        "get_json",
        lambda path: {
            "items": [
                {
                    "id": 8,
                    "notification_type": "news_digest",
                    "target_channel": "group-1",
                    "title": "新闻标题",
                    "content": "简化内容",
                    "payload": {"news_id": 4},
                    "retry_count": 0,
                }
            ]
        },
    )
    monkeypatch.setattr(publisher, "_post_qqbot_webhook", lambda url, item: (_ for _ in ()).throw(RuntimeError("webhook down")))
    monkeypatch.setattr(publisher, "post_json", lambda path, payload: status_updates.append((path, payload)) or {})

    result = publisher.publish_pending_notifications(dry_run=False, webhook_url="http://qqbot.local/send", batch_size=5)

    assert result == {"published": 0, "failed": 1, "skipped": 0, "dry_run": False}
    assert status_updates[0][1]["notification_id"] == 8
    assert status_updates[0][1]["status"] == "failed"
    assert "webhook down" in status_updates[0][1]["error_message"]
