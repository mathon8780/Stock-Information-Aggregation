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
export interface NewsItem {
  id: number;
  scope: string;
  title: string;
  original_title?: string | null;
  summary?: string | null;
  content?: string | null;
  source: string;
  url?: string | null;
  sentiment: string;
  importance: number;
  published_at?: string | null;
  fetched_at?: string | null;
  simplification_status: 'pending' | 'simplified' | 'failed';
  simplified_at?: string | null;
  llm_provider?: string | null;
  llm_model?: string | null;
  prompt_name?: string | null;
  error_message?: string | null;
  code?: string;
  name?: string;
  stock?: Stock;
}
export interface NewsLlmConfig { provider: string; api_base_url: string; model: string; api_key_configured: boolean; prompt_preset: string; custom_prompt?: string | null; custom_prompt_configured: boolean; default_prompt: string; effective_prompt: string; updated_at?: string | null; }
export interface NewsLlmKeyStatus { provider: string; model: string; api_base_url: string; api_key_configured: boolean; ok: boolean; status: 'missing' | 'valid' | 'invalid'; message: string; checked_at?: string | null; }
export interface NewsLlmConfigPayload { provider: string; api_base_url: string; model: string; api_key?: string | null; clear_api_key?: boolean; prompt_preset: string; custom_prompt?: string | null; }
export interface Advice { id: number; stock_id: number; code?: string; name?: string; industry?: string | null; signal: Signal; confidence: number; reasoning: string; strategy: string; risk_notes: string; indicators: Record<string, any>; news_summary: Record<string, any>; market_context: Record<string, any>; engine: string; created_at: string; stock?: Stock; }
export interface WatchItem { id: number; stock: Stock; display_order: number; alert_enabled: boolean; alert_threshold_pct: number; strategy_push_enabled: boolean; added_at: string; latest_snapshot?: Snapshot | null; latest_advice?: Advice | null; }
export interface CollectionJob { id: number; job_type: string; status: string; source: string; result_summary?: Record<string, any> | null; error_message?: string | null; started_at: string; finished_at?: string | null; }
export interface CollectorStartResult { status: 'started' | 'already_running'; job_type: string; days: number; batch_size: number; limit?: number | null; }
export interface NotificationItem { id: number; notification_type: string; target_channel: string; title: string; content: string; payload?: Record<string, any> | null; status: string; retry_count: number; error_message?: string | null; created_at: string; sent_at?: string | null; }
export interface PaperAccount { id: number; owner_name: string; initial_cash: number; cash_balance: number; cash_available: number; cash_frozen: number; status: string; created_at?: string | null; last_login_at?: string | null; reset_at?: string | null; }
export interface PaperSummary { account: PaperAccount; cash_balance: number; cash_available: number; cash_frozen: number; position_market_value: number; total_assets: number; position_count: number; open_order_count: number; trade_count: number; }
export interface PaperPerformanceSummary { initial_cash: number; current_total_assets: number; total_return_pct: number; total_trades: number; closed_trade_count: number; winning_trades: number; losing_trades: number; win_rate_pct: number; realized_pnl: number; average_pnl: number; average_profit: number; average_loss: number; max_single_profit: number; max_single_loss: number; }
export interface PaperStockPerformance { stock_id: number; code: string; name: string; buy_quantity: number; sell_quantity: number; current_quantity: number; buy_amount: number; sell_amount: number; fee_total: number; realized_pnl: number; floating_pnl: number; total_pnl: number; trade_count: number; }
export interface PaperPosition { stock_id: number; code: string; name: string; market: string; total_quantity: number; available_quantity: number; today_buy_quantity: number; frozen_quantity: number; avg_cost: number; market_price: number; market_value: number; floating_pnl: number; floating_pnl_pct: number; }
export interface PaperOrder { id: number; stock_id: number; code: string; name: string; market: string; side: 'buy' | 'sell'; order_type: 'market' | 'limit' | 'take_profit' | 'stop_loss'; status: string; quantity: number; filled_quantity: number; limit_price?: number | null; trigger_price?: number | null; avg_fill_price?: number | null; frozen_cash: number; frozen_quantity: number; fee_total: number; reject_reason?: string | null; created_at?: string | null; filled_at?: string | null; }
export interface PaperTrade { id: number; order_id: number; stock_id: number; code: string; name: string; side: 'buy' | 'sell'; quantity: number; price: number; amount: number; commission: number; stamp_tax: number; transfer_fee: number; fee_total: number; realized_pnl?: number | null; trade_time?: string | null; price_source: string; }
export interface PaperCashFlow { id: number; order_id?: number | null; trade_id?: number | null; flow_type: string; amount: number; cash_balance_after: number; remark?: string | null; created_at?: string | null; }
export interface PaperPerformanceCalendarDay { trade_date: string; realized_pnl: number; buy_amount: number; sell_amount: number; fee_total: number; trade_count: number; order_count: number; cash_flow_count: number; trades: PaperTrade[]; orders: PaperOrder[]; cash_flows: PaperCashFlow[]; }
export interface Paged<T> { items: T[]; total: number; page?: number; page_size?: number; }
