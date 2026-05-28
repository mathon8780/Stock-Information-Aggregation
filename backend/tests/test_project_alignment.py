from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_sql_migration_includes_intraday_kline_table() -> None:
    sql = (PROJECT_ROOT / "data" / "migrations" / "001_init.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS kline_intraday" in sql
    assert "period_minutes INTEGER NOT NULL" in sql
    assert "bar_time TIMESTAMP NOT NULL" in sql
    assert "PRIMARY KEY (stock_id, period_minutes, bar_time)" in sql
