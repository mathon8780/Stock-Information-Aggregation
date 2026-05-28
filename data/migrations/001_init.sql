CREATE TABLE IF NOT EXISTS stocks (
  id BIGSERIAL PRIMARY KEY,
  code VARCHAR(32) NOT NULL UNIQUE,
  name VARCHAR(128) NOT NULL,
  market VARCHAR(16) NOT NULL,
  security_type VARCHAR(16) NOT NULL CHECK (security_type IN ('stock', 'index')),
  industry VARCHAR(128),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kline_daily (
  stock_id BIGINT NOT NULL REFERENCES stocks(id),
  trade_date DATE NOT NULL,
  open NUMERIC(18,4),
  high NUMERIC(18,4),
  low NUMERIC(18,4),
  close NUMERIC(18,4),
  volume BIGINT,
  amount NUMERIC(24,4),
  amplitude NUMERIC(10,4),
  change_pct NUMERIC(10,4),
  turnover_rate NUMERIC(10,4),
  source VARCHAR(64) NOT NULL DEFAULT 'akshare',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (stock_id, trade_date)
);

CREATE TABLE IF NOT EXISTS kline_intraday (
  stock_id BIGINT NOT NULL REFERENCES stocks(id),
  period_minutes INTEGER NOT NULL,
  bar_time TIMESTAMP NOT NULL,
  open NUMERIC(18,4),
  high NUMERIC(18,4),
  low NUMERIC(18,4),
  close NUMERIC(18,4),
  volume BIGINT,
  amount NUMERIC(24,4),
  amplitude NUMERIC(10,4),
  change_pct NUMERIC(10,4),
  change_amount NUMERIC(18,4),
  turnover_rate NUMERIC(10,4),
  source VARCHAR(64) NOT NULL DEFAULT 'akshare',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (stock_id, period_minutes, bar_time)
);

CREATE TABLE IF NOT EXISTS market_snapshot (
  id BIGSERIAL PRIMARY KEY,
  snapshot_time TIMESTAMPTZ NOT NULL,
  stock_id BIGINT NOT NULL REFERENCES stocks(id),
  price NUMERIC(18,4),
  change_pct NUMERIC(10,4),
  change_amount NUMERIC(18,4),
  volume BIGINT,
  amount NUMERIC(24,4),
  open NUMERIC(18,4),
  high NUMERIC(18,4),
  low NUMERIC(18,4),
  amplitude NUMERIC(10,4),
  turnover_rate NUMERIC(10,4),
  volume_ratio NUMERIC(10,4),
  pe NUMERIC(14,4),
  pb NUMERIC(14,4),
  total_mv NUMERIC(24,4),
  circ_mv NUMERIC(24,4),
  idempotency_key VARCHAR(160) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS watch_snapshot (
  id BIGSERIAL PRIMARY KEY,
  snapshot_time TIMESTAMPTZ NOT NULL,
  stock_id BIGINT NOT NULL REFERENCES stocks(id),
  source_snapshot_id BIGINT REFERENCES market_snapshot(id),
  price NUMERIC(18,4),
  change_pct NUMERIC(10,4),
  change_amount NUMERIC(18,4),
  volume BIGINT,
  amount NUMERIC(24,4),
  open NUMERIC(18,4),
  high NUMERIC(18,4),
  low NUMERIC(18,4),
  amplitude NUMERIC(10,4),
  turnover_rate NUMERIC(10,4),
  volume_ratio NUMERIC(10,4),
  pe NUMERIC(14,4),
  pb NUMERIC(14,4),
  total_mv NUMERIC(24,4),
  circ_mv NUMERIC(24,4),
  idempotency_key VARCHAR(160) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS news (
  id BIGSERIAL PRIMARY KEY,
  stock_id BIGINT REFERENCES stocks(id),
  scope VARCHAR(16) NOT NULL CHECK (scope IN ('market', 'stock', 'security')),
  title TEXT NOT NULL,
  original_title VARCHAR(240),
  summary TEXT,
  content TEXT,
  source VARCHAR(128) NOT NULL,
  url TEXT,
  content_hash VARCHAR(128) NOT NULL UNIQUE,
  sentiment VARCHAR(16) NOT NULL DEFAULT 'neutral',
  importance INTEGER NOT NULL DEFAULT 3,
  published_at TIMESTAMPTZ,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  raw_payload JSONB,
  simplification_status VARCHAR(16) NOT NULL DEFAULT 'pending' CHECK (simplification_status IN ('pending', 'simplified', 'failed')),
  simplified_at TIMESTAMPTZ,
  llm_provider VARCHAR(64),
  llm_model VARCHAR(128),
  prompt_name VARCHAR(64),
  error_message TEXT
);

CREATE TABLE IF NOT EXISTS news_llm_config (
  id INTEGER PRIMARY KEY DEFAULT 1,
  provider VARCHAR(64) NOT NULL DEFAULT 'deepseek',
  api_base_url TEXT NOT NULL DEFAULT 'https://api.deepseek.com',
  model VARCHAR(128) NOT NULL DEFAULT 'deepseek-v4-flash',
  api_key TEXT,
  prompt_preset VARCHAR(64) NOT NULL DEFAULT 'default',
  custom_prompt TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS trading_advice (
  id BIGSERIAL PRIMARY KEY,
  stock_id BIGINT NOT NULL REFERENCES stocks(id),
  signal VARCHAR(32) NOT NULL,
  confidence NUMERIC(5,2) NOT NULL,
  reasoning TEXT NOT NULL,
  strategy TEXT NOT NULL,
  risk_notes TEXT NOT NULL,
  indicators JSONB,
  news_summary JSONB,
  market_context JSONB,
  engine VARCHAR(32) NOT NULL DEFAULT 'rule_engine',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS watchlist (
  id BIGSERIAL PRIMARY KEY,
  stock_id BIGINT NOT NULL UNIQUE REFERENCES stocks(id),
  display_order INTEGER NOT NULL DEFAULT 0,
  alert_enabled BOOLEAN NOT NULL DEFAULT TRUE,
  alert_threshold_pct NUMERIC(8,4) NOT NULL DEFAULT 3,
  strategy_push_enabled BOOLEAN NOT NULL DEFAULT TRUE,
  added_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS collection_jobs (
  id BIGSERIAL PRIMARY KEY,
  job_type VARCHAR(32) NOT NULL,
  status VARCHAR(16) NOT NULL,
  source VARCHAR(64) NOT NULL DEFAULT 'system',
  requested_payload JSONB,
  result_summary JSONB,
  error_message TEXT,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS notifications (
  id BIGSERIAL PRIMARY KEY,
  notification_type VARCHAR(32) NOT NULL,
  target_channel VARCHAR(64) NOT NULL,
  title VARCHAR(256) NOT NULL,
  content TEXT NOT NULL,
  payload JSONB,
  status VARCHAR(16) NOT NULL DEFAULT 'pending',
  retry_count INTEGER NOT NULL DEFAULT 0,
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sent_at TIMESTAMPTZ
);
