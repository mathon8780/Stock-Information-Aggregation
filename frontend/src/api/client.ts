import type { Advice, CollectionJob, IntradayKline, Kline, NewsItem, NotificationItem, Paged, Snapshot, Stock, WatchItem } from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) }, ...init });
  if (!response.ok) throw new Error((await response.text()) || `HTTP ${response.status}`);
  return (await response.json()) as T;
}

export const api = {
  settings: () => request<Record<string, any>>('/settings'),
  stock: (code: string) => request<Stock & { latest_snapshot?: Snapshot | null; latest_advice?: Advice | null; is_watched: boolean }>(`/stocks/${code}`),
  kline: (code: string, limit = 90) => request<Paged<Kline>>(`/stocks/${code}/kline?limit=${limit}`),
  intraday: (code: string, period = 5, days = 10) => request<Paged<IntradayKline>>(`/stocks/${code}/intraday?period=${period}&days=${days}`),
  stockSnapshots: (code: string, limit = 120) => request<Paged<Snapshot>>(`/stocks/${code}/snapshots?limit=${limit}`),
  stockNews: (code: string, limit = 20) => request<Paged<NewsItem>>(`/stocks/${code}/news?limit=${limit}`),
  market: (params: URLSearchParams) => request<Paged<Snapshot>>(`/market/snapshot?${params.toString()}`),
  news: (params: URLSearchParams) => request<Paged<NewsItem>>(`/news?${params.toString()}`),
  advice: (signal?: string) => request<Paged<Advice>>(`/advice${signal ? `?signal=${encodeURIComponent(signal)}` : ''}`),
  adviceHistory: (code: string, limit = 20) => request<Paged<Advice>>(`/advice/${code}/history?limit=${limit}`),
  analyze: (code: string) => request<Advice>(`/analysis/${code}`, { method: 'POST' }),
  analyzeWatchlist: () => request<Paged<Advice>>('/analysis/watchlist', { method: 'POST' }),
  watchlist: () => request<Paged<WatchItem> & { max_size: number }>('/watchlist'),
  addWatch: (code: string) => request('/watchlist', { method: 'POST', body: JSON.stringify({ code }) }),
  removeWatch: (code: string) => request(`/watchlist/${code}`, { method: 'DELETE' }),
  collectBootstrap: () => request('/collector/real/bootstrap', { method: 'POST' }),
  collectMarket: () => request('/collector/real/market', { method: 'POST' }),
  collectHistory: () => request('/collector/real/history', { method: 'POST' }),
  collectIntraday: () => request('/collector/real/intraday', { method: 'POST' }),
  jobs: (limit = 50) => request<Paged<CollectionJob>>(`/collection-jobs?limit=${limit}`),
  notifications: (status?: string) => request<Paged<NotificationItem>>(`/notifications?limit=100${status ? `&status=${status}` : ''}`),
};

export function formatNumber(value?: number | null, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-';
  return value.toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits });
}
export function formatCompact(value?: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-';
  if (Math.abs(value) >= 100000000) return `${formatNumber(value / 100000000, 2)} 亿`;
  if (Math.abs(value) >= 10000) return `${formatNumber(value / 10000, 2)} 万`;
  return formatNumber(value, 0);
}
export function formatTime(value?: string | null): string {
  if (!value) return '-';
  return new Date(value).toLocaleString('zh-CN', { hour12: false });
}
export function changeColor(value?: number | null): string {
  if (value === null || value === undefined) return '#57606a';
  if (value > 0) return '#cf222e';
  if (value < 0) return '#1a7f37';
  return '#57606a';
}
