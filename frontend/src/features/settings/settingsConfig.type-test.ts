import { createDefaultFrontendSettings, normalizeFrontendSettingsConfig } from './settingsConfig';

const defaults = createDefaultFrontendSettings({ analysis_engine: 'rule_engine' });

const normalized = normalizeFrontendSettingsConfig(
  {
    analysis_engines: ['news_llm'],
    collection_intervals: {
      market_snapshot_seconds: 1,
      watch_snapshot_seconds: 1,
      news_seconds: 1,
      news_auto_sync_seconds: 1,
      advice_seconds: 1,
    },
  },
  defaults,
);

const selectedEngine: string = normalized.analysis_engine;
const clampedMarketInterval: number = normalized.collection_intervals.market_snapshot_seconds;

void selectedEngine;
void clampedMarketInterval;
