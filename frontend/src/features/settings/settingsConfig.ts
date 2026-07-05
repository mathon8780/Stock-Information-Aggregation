export const FRONTEND_SETTINGS_STORAGE_KEY = 'market-agent.frontend-settings.v1';

export const COLLECTION_INTERVAL_DEFAULTS = {
  market_snapshot_seconds: 300,
  watch_snapshot_seconds: 60,
  news_seconds: 300,
  news_auto_sync_seconds: 300,
  advice_seconds: 900,
} as const;

export const ANALYSIS_ENGINE_OPTIONS = [
  { label: '规则引擎', value: 'rule_engine' },
  { label: '本地 LLM', value: 'local_llm' },
  { label: '新闻 LLM', value: 'news_llm' },
  { label: '技术指标', value: 'technical_indicators' },
];

export type CollectionIntervalKey = keyof typeof COLLECTION_INTERVAL_DEFAULTS;

export interface FrontendSettingsConfig {
  analysis_engine: string;
  collection_intervals: Record<CollectionIntervalKey, number>;
  risk_control: {
    request_min_interval_seconds: number;
    fetch_failure_downgrade_threshold: number;
    max_watchlist_size: number;
  };
}

function toPositiveInteger(value: unknown, fallback: number): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(1, Math.floor(parsed));
}

export function createDefaultFrontendSettings(settings: Record<string, any> | null): FrontendSettingsConfig {
  const analysisEngine = String(settings?.analysis_engine || 'rule_engine');
  return {
    analysis_engine: analysisEngine,
    collection_intervals: { ...COLLECTION_INTERVAL_DEFAULTS },
    risk_control: {
      request_min_interval_seconds: toPositiveInteger(settings?.risk_control?.request_min_interval_seconds, 3),
      fetch_failure_downgrade_threshold: toPositiveInteger(settings?.risk_control?.fetch_failure_downgrade_threshold, 3),
      max_watchlist_size: toPositiveInteger(settings?.risk_control?.max_watchlist_size, 20),
    },
  };
}

export function normalizeFrontendSettingsConfig(
  value: (Partial<FrontendSettingsConfig> & { analysis_engines?: string[] }) | null | undefined,
  defaults: FrontendSettingsConfig,
): FrontendSettingsConfig {
  const intervals = Object.entries(COLLECTION_INTERVAL_DEFAULTS).reduce(
    (next, [key, minimum]) => {
      const intervalKey = key as CollectionIntervalKey;
      next[intervalKey] = Math.max(
        minimum,
        toPositiveInteger(value?.collection_intervals?.[intervalKey], defaults.collection_intervals[intervalKey]),
      );
      return next;
    },
    {} as Record<CollectionIntervalKey, number>,
  );

  const storedEngine = typeof value?.analysis_engine === 'string' && value.analysis_engine.trim()
    ? value.analysis_engine
    : undefined;
  const migratedEngine = Array.isArray(value?.analysis_engines)
    ? value.analysis_engines.map(String).find(Boolean)
    : undefined;

  return {
    analysis_engine: storedEngine ?? migratedEngine ?? defaults.analysis_engine,
    collection_intervals: intervals,
    risk_control: {
      request_min_interval_seconds: toPositiveInteger(
        value?.risk_control?.request_min_interval_seconds,
        defaults.risk_control.request_min_interval_seconds,
      ),
      fetch_failure_downgrade_threshold: toPositiveInteger(
        value?.risk_control?.fetch_failure_downgrade_threshold,
        defaults.risk_control.fetch_failure_downgrade_threshold,
      ),
      max_watchlist_size: toPositiveInteger(value?.risk_control?.max_watchlist_size, defaults.risk_control.max_watchlist_size),
    },
  };
}
