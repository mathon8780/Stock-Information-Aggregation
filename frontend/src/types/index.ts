export type Signal = '重点关注' | '谨慎买入' | '持有' | '减仓' | '回避';

export interface Stock {
  id: number;
  code: string;
  name: string;
  market: string;
  security_type: 'stock' | 'index';
  industry?: string | null;
  is_active?: boolean;
}

export interface Snapshot {
  id: number;
  snapshot_time: string;
  stock_id: number;
  code: string;
  name: string;
  market: string;
  security_type: 'stock' | 'index';
  industry?: string | null;
  price?: number | null;
  change_pct?: number | null;
  change_amount?: number | null;
  volume?: number | null;
  amount?: number | null;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  turnover_rate?: number | null;
  volume_ratio?: number | null;
  pe?: number | null;
  pb?: number | null;
}

export interface Kline { trade_date: string; open: number; high: number; low: number; close: number; volume?: number | null; }
export interface IntradayKline { bar_time: string; period_minutes: number; open: number; high: number; low: number; close: number; volume?: number | null; amount?: number | null; source: string; }
export interface NewsItem { id: number; scope: string; title: string; summary?: string | null; content?: string | null; source: string; url?: string | null; sentiment: string; importance: number; published_at?: string | null; code?: string; name?: string; stock?: Stock; }
export interface Advice { id: number; stock_id: number; code?: string; name?: string; industry?: string | null; signal: Signal; confidence: number; reasoning: string; strategy: string; risk_notes: string; indicators: Record<string, any>; news_summary: Record<string, any>; market_context: Record<string, any>; engine: string; created_at: string; stock?: Stock; }
export interface WatchItem { id: number; stock: Stock; display_order: number; alert_enabled: boolean; alert_threshold_pct: number; strategy_push_enabled: boolean; added_at: string; latest_snapshot?: Snapshot | null; latest_advice?: Advice | null; }
export interface CollectionJob { id: number; job_type: string; status: string; source: string; result_summary?: Record<string, any> | null; error_message?: string | null; started_at: string; finished_at?: string | null; }
export interface NotificationItem { id: number; notification_type: string; target_channel: string; title: string; content: string; payload?: Record<string, any> | null; status: string; retry_count: number; error_message?: string | null; created_at: string; sent_at?: string | null; }
export interface Paged<T> { items: T[]; total: number; page?: number; page_size?: number; }
