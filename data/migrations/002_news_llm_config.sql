ALTER TABLE news ADD COLUMN IF NOT EXISTS original_title VARCHAR(240);
UPDATE news SET original_title = substr(title, 1, 240) WHERE original_title IS NULL OR original_title = '';
ALTER TABLE news ADD COLUMN IF NOT EXISTS simplification_status VARCHAR(16) NOT NULL DEFAULT 'pending';
ALTER TABLE news ADD COLUMN IF NOT EXISTS simplified_at TIMESTAMPTZ;
ALTER TABLE news ADD COLUMN IF NOT EXISTS llm_provider VARCHAR(64);
ALTER TABLE news ADD COLUMN IF NOT EXISTS llm_model VARCHAR(128);
ALTER TABLE news ADD COLUMN IF NOT EXISTS prompt_name VARCHAR(64);
ALTER TABLE news ADD COLUMN IF NOT EXISTS error_message TEXT;

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
