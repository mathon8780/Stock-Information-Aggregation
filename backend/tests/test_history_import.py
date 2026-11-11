from argparse import Namespace
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import KlineDaily
from app.services.market_history_lock import HistoryImportBusy, history_import_lock
from app.services.market_request_guard import RequestThrottle, SourceBlockedError
from app.services.real_collector_service import AkshareCollector
from tools import import_full_market_history as importer


TARGET = {"code": "000001.SZ", "name": "平安银行", "market": "SZ", "security_type": "stock"}
OTHER = {**TARGET, "code": "600000.SH", "market": "SH"}


def frame():
    return pd.DataFrame([{"日期": "2026-11-10", "开盘": 10, "收盘": 11, "最高": 12, "最低": 9, "成交量": 100}])


@pytest.fixture
def history_tmp():
    # Windows Python 3.14 的 mode=0700 临时目录在受限运行环境中可能无法再次访问。
    path = Path(__file__).resolve().parents[2] / "data/runtime" / f"history-test-{uuid4().hex}"
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        for child in path.iterdir():
            child.unlink()
        path.rmdir()


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_transport_limits_every_request_and_pauses_batches():
    now, sleeps = [0.0], []

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    throttle = RequestThrottle(interval=5, jitter=3, batch_size=2, batch_pause=60,
                               sleep=sleep, clock=lambda: now[0], uniform=lambda a, b: b)
    for _ in range(4):
        throttle.call(lambda: None)
    assert sleeps == [8, 60, 8]


@pytest.mark.parametrize("status", [403, 412, 429])
def test_transport_blocks_without_another_request(status):
    calls = []
    throttle = RequestThrottle(clock=lambda: 0)

    def request():
        calls.append(1)
        return SimpleNamespace(status_code=status)

    with pytest.raises(SourceBlockedError):
        throttle.call(request)
    with pytest.raises(SourceBlockedError):
        throttle.call(request)
    assert len(calls) == 1


def test_rate_limit_does_not_fallback_or_retry():
    calls = []

    def blocked(**kwargs):
        calls.append("eastmoney")
        raise SourceBlockedError("HTTP 429")

    def fallback(**kwargs):
        calls.append("fallback")
        return frame()

    fake = SimpleNamespace(stock_zh_a_hist=blocked, stock_zh_a_hist_tx=fallback, stock_zh_a_daily=fallback)
    collector = AkshareCollector(fake, sleep_fn=lambda _: pytest.fail("不应退避后重试风控异常"))
    with pytest.raises(SourceBlockedError):
        collector._call_with_backoff(lambda: collector._history_rows_for_target(
            TARGET, date(2025, 11, 11), date(2026, 11, 11), prefer_bulk_daily=True), "test")
    assert calls == ["eastmoney"]


def test_verification_page_stops_even_when_http_status_is_success():
    throttle = RequestThrottle(clock=lambda: 0)
    response = SimpleNamespace(status_code=200, headers={"Content-Type": "text/html"}, text="<html>安全验证 captcha</html>")
    with pytest.raises(SourceBlockedError, match="验证页面"):
        throttle.call(lambda: response)
    assert throttle.blocked_until == 2700


def test_server_retry_after_can_extend_cooldown():
    throttle = RequestThrottle(clock=lambda: 0)
    response = SimpleNamespace(status_code=429, headers={"Retry-After": "7200"})
    with pytest.raises(SourceBlockedError) as exc:
        throttle.call(lambda: response)
    assert exc.value.retry_after_seconds == 7200
    assert throttle.blocked_until == 7200


def test_exchange_universe_includes_star_and_rejects_partial_lists():
    symbols = []

    def sh(symbol):
        symbols.append(symbol)
        return pd.DataFrame([{"证券代码": "688001" if symbol == "科创板" else "600000", "证券简称": "测试"}])

    fake = SimpleNamespace(stock_info_sh_name_code=sh,
                           stock_info_sz_name_code=lambda: pd.DataFrame([{"A股代码": "000001", "A股简称": "测试"}]),
                           stock_info_bj_name_code=lambda: pd.DataFrame([{"证券代码": "920001", "证券简称": "测试"}]))
    collector = AkshareCollector(fake)
    targets = collector._full_market_stock_targets()
    assert symbols == ["主板A股", "科创板"]
    assert {target["code"] for target in targets} == {"600000.SH", "688001.SH", "000001.SZ", "920001.BJ"}
    fake.stock_info_bj_name_code = lambda: pd.DataFrame()
    with pytest.raises(RuntimeError, match="名单不完整"):
        collector._full_market_stock_targets()


def test_empty_response_is_not_success():
    collector = AkshareCollector(SimpleNamespace(stock_zh_a_hist=lambda **kw: pd.DataFrame()), backoff_seconds=[])
    with pytest.raises(RuntimeError, match="empty"):
        collector._history_rows_for_target(TARGET, date(2025, 11, 11), date(2026, 11, 11), True)


def test_market_snapshot_risk_error_does_not_fallback(monkeypatch):
    fake = SimpleNamespace(stock_zh_a_spot_em=lambda: (_ for _ in ()).throw(SourceBlockedError("限流")))
    collector = AkshareCollector(fake)
    monkeypatch.setattr(collector, "_sina_quote_rows_for_targets", lambda *args: pytest.fail("不应绕过风控切换来源"))
    monkeypatch.setattr(collector, "_eastmoney_a_spot_rows", lambda: pytest.fail("不应绕过风控调用公开接口"))
    with pytest.raises(SourceBlockedError):
        collector._build_stock_spot_items(importer.datetime.now(importer.timezone.utc), [TARGET])


def test_fallback_units_and_turnover_over_100_percent():
    fake = SimpleNamespace(stock_zh_a_hist_tx=lambda **kw: pd.DataFrame([
        {"date": "2026-11-10", "open": 10, "close": 11, "high": 12, "low": 9, "volume": 12300, "turnover": 1.2},
    ]))
    collector = AkshareCollector(fake)
    row = collector._history_rows_for_target(TARGET, date(2025, 11, 11), date(2026, 11, 11), True)[0]
    assert row["volume"] == 123
    assert row["turnover_rate"] == 120


def test_full_market_stops_on_first_risk_error_and_reports_remaining(db, monkeypatch):
    collector = AkshareCollector(SimpleNamespace(), sleep_fn=lambda _: None, backoff_seconds=[])
    monkeypatch.setattr(collector, "_full_market_stock_targets", lambda: [TARGET, OTHER])
    monkeypatch.setattr(collector, "_history_rows_for_target", lambda *a, **kw: (_ for _ in ()).throw(SourceBlockedError("限流")))
    result = collector.collect_full_market_history(db)
    assert result["processed"] == 1
    assert result["failed"] == 1
    assert result["unprocessed"] == 1


class FakeCollector(AkshareCollector):
    def __init__(self):
        super().__init__(SimpleNamespace(stock_zh_a_hist=lambda **kw: frame()), backoff_seconds=[])
        self.calls = []

    def _full_market_stock_targets(self):
        return [TARGET, OTHER]

    def _history_rows_for_target(self, target, *args, **kwargs):
        self.calls.append(target["code"])
        return super()._history_rows_for_target(target, *args, **kwargs)


def test_checkpoint_resume_and_deleted_database_rows_are_refetched(db, history_tmp):
    state = importer.new_state(365, date(2026, 11, 11))
    args = Namespace(state=history_tmp / "checkpoint.json", limit=1, interval=5)
    collector = FakeCollector()
    assert importer.run_import(args, collector, db, state) == 2
    assert len(state["completed"]) == 1
    args.limit = None
    assert importer.run_import(args, collector, db, state) == 0
    assert len(collector.calls) == 2
    assert db.query(KlineDaily).count() == 2
    db.query(KlineDaily).delete()
    db.commit()
    assert importer.run_import(args, collector, db, state) == 0
    assert len(collector.calls) == 4


def test_database_failure_does_not_mark_target_complete(db, history_tmp, monkeypatch):
    args = Namespace(state=history_tmp / "checkpoint.json", limit=1, interval=5)
    state = importer.new_state(365, date(2026, 11, 11))

    def fail(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(importer, "ingest_kline_payload", fail)
    with pytest.raises(RuntimeError, match="database unavailable"):
        importer.run_import(args, FakeCollector(), db, state)
    assert state["completed"] == {}
    assert state["status"] == "failed"


def test_checkpoint_rejects_different_ranges_and_databases(history_tmp):
    path = history_tmp / "state.json"
    state = importer.new_state(365, date(2026, 11, 11))
    importer.save_state(path, state)
    assert importer.load_state(path, 365, None)["end"] == "2026-11-11"
    with pytest.raises(ValueError, match="日期"):
        importer.load_state(path, 30, None)
    state["database"] = "another database"
    importer.save_state(path, state)
    with pytest.raises(ValueError, match="数据库"):
        importer.load_state(path, 365, None)


def test_import_lock_rejects_another_job_and_releases_after_exception(history_tmp):
    path = history_tmp / "history.lock"
    with pytest.raises(ValueError):
        with history_import_lock(path):
            with pytest.raises(HistoryImportBusy):
                with history_import_lock(path):
                    pytest.fail("应拒绝第二个采集任务")
            raise ValueError("interrupted")
    with history_import_lock(path):
        pass


@pytest.mark.parametrize("argv", [["--workers", "4"], ["--interval", "0"], ["--interval", "nan"], ["--days", "0"], ["--limit", "-1"]])
def test_cli_rejects_unsafe_arguments(argv):
    with pytest.raises(SystemExit):
        importer.parse_args(argv)


def test_tencent_only_does_not_call_other_sources_or_hide_errors():
    calls = []

    def other_source(**kwargs):
        pytest.fail("腾讯单源模式不能访问其他来源")

    def tencent(**kwargs):
        calls.append(kwargs)
        raise ConnectionError("tencent disconnected")

    fake = SimpleNamespace(stock_zh_a_hist=other_source, stock_zh_a_daily=other_source, stock_zh_a_hist_tx=tencent)
    collector = AkshareCollector(fake, daily_source="tencent", backoff_seconds=[])
    with pytest.raises(ConnectionError, match="tencent disconnected"):
        collector._history_rows_for_target(TARGET, date(2025, 11, 11), date(2026, 11, 11), True)
    assert len(calls) == 1
    assert calls[0]["symbol"] == "sz000001"
    assert calls[0]["adjust"] == "qfq"


def test_stop_on_first_error_does_not_retry_or_advance(db, history_tmp, monkeypatch):
    args = Namespace(state=history_tmp / "checkpoint.json", limit=None, interval=10, source="tencent", stop_on_error=True)
    state = importer.new_state(365, date(2026, 11, 11))
    state["targets"] = [TARGET, OTHER]
    collector = FakeCollector()
    calls = []

    def fail(target, *args, **kwargs):
        calls.append(target["code"])
        raise ConnectionError("tencent disconnected")

    monkeypatch.setattr(collector, "_history_rows_for_target", fail)
    monkeypatch.setattr(collector, "_call_with_backoff", lambda *args: pytest.fail("首次异常即停止模式不能重试"))
    assert importer.run_import(args, collector, db, state) == 2
    assert state["status"] == "stopped"
    assert calls == [TARGET["code"]]
    assert state["completed"] == {}
    assert state["failures"][TARGET["code"]]["source"] == "tencent"


def test_tencent_import_records_actual_source(db, history_tmp):
    args = Namespace(state=history_tmp / "checkpoint.json", limit=1, interval=10, source="tencent", stop_on_error=True)
    state = importer.new_state(365, date(2026, 11, 11))
    state["targets"] = [TARGET]
    fake = SimpleNamespace(stock_zh_a_hist_tx=lambda **kwargs: pd.DataFrame([
        {"date": "2026-11-10", "open": 10, "close": 11, "high": 12, "low": 9, "volume": 12300, "turnover": 0.01},
    ]))
    collector = AkshareCollector(fake, daily_source="tencent", backoff_seconds=[])
    assert importer.run_import(args, collector, db, state) == 0
    row = db.query(KlineDaily).one()
    assert row.source == "akshare_tencent"
    assert row.volume == 123
    assert state["completed"][TARGET["code"]]["source"] == "akshare_tencent"


def test_source_cooldowns_are_separate_and_old_failure_is_preserved():
    state = importer.new_state(365, date(2026, 11, 11))
    state.update(status="blocked", stop_reason="eastmoney blocked", retry_after="2999-01-01T00:00:00+00:00")
    importer.select_source(state, "tencent")
    assert state["source"] == "tencent"
    assert state["source_history"][0]["stop_reason"] == "eastmoney blocked"
    assert state["source_cooldowns"]["auto"] == "2999-01-01T00:00:00+00:00"
    with pytest.raises(RuntimeError, match="冷却"):
        importer.select_source(state, "auto")


def test_tencent_mode_requires_existing_roster(db, history_tmp):
    args = Namespace(state=history_tmp / "checkpoint.json", limit=1, interval=10, source="tencent", stop_on_error=True)
    state = importer.new_state(365, date(2026, 11, 11))
    with pytest.raises(ValueError, match="已有名单断点"):
        importer.run_import(args, FakeCollector(), db, state)
