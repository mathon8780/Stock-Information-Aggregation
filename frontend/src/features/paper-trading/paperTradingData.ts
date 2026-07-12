import type { IntradayKline, PaperTrade, PaperWatchItem, Stock } from '../../types';

type BackendEventLike = {
  type: string;
  payload?: Record<string, unknown>;
};

export const PAPER_INTRADAY_POLL_INTERVAL_MS = 60_000;

export interface StockSearchOption {
  value: string;
  code: string;
  name: string;
  market: string;
  industry?: string | null;
  label: string;
  keywords: string[];
}

export interface PaperTradeMarker {
  barIndex: number;
  barTime: string;
  price: number;
  side: PaperTrade['side'];
  quantity: number;
  amount: number;
  tradeTime?: string | null;
}

export type PaperIntradayRefreshMode = 'switch' | 'manual' | 'poll' | 'event';

export interface PaperIntradayRefreshPlan {
  readCacheFirst: boolean;
  refreshSourceInBackground: boolean;
  clearOnError: boolean;
}

export function paperIntradayRefreshPlan(mode: PaperIntradayRefreshMode): PaperIntradayRefreshPlan {
  if (mode === 'switch' || mode === 'manual') {
    return { readCacheFirst: true, refreshSourceInBackground: true, clearOnError: false };
  }
  if (mode === 'poll') {
    return { readCacheFirst: false, refreshSourceInBackground: true, clearOnError: false };
  }
  return { readCacheFirst: true, refreshSourceInBackground: false, clearOnError: false };
}

export function selectLatestTradingDayIntraday(rows: IntradayKline[]): IntradayKline[] {
  const latestDate = rows.at(-1)?.bar_time.slice(0, 10);
  return latestDate ? rows.filter((item) => item.bar_time.startsWith(latestDate)) : [];
}

export function buildStockSearchOptions(stocks: Stock[]): StockSearchOption[] {
  return stocks.map((stock) => ({
    value: stock.code,
    code: stock.code,
    name: stock.name,
    market: stock.market,
    industry: stock.industry,
    label: `${stock.name} ${stock.code}`,
    keywords: [stock.code, stock.name, stock.industry].filter((item): item is string => Boolean(item)),
  }));
}

export function createPaperCaptcha(random: () => number = Math.random, length = 6): string {
  const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  return Array.from({ length }, () => alphabet[Math.floor(random() * alphabet.length) % alphabet.length]).join('');
}

export function isPaperCaptchaMatch(input: string | undefined, expected: string): boolean {
  return Boolean(expected) && input?.trim().toUpperCase() === expected.toUpperCase();
}

export function normalizePaperPhone(value: string | undefined): string {
  return String(value ?? '').replace(/\D/g, '');
}

export function isReasonablePaperPhone(value: string | undefined): boolean {
  return /^1[3-9]\d{9}$/.test(normalizePaperPhone(value));
}

export function createPaperTradeMarkers(kline: IntradayKline[], trades: PaperTrade[], code: string): PaperTradeMarker[] {
  const normalizedCode = code.trim().toUpperCase();
  if (!normalizedCode || !kline.length) return [];
  const barTimes = kline.map((bar) => parseMarketTimestamp(bar.bar_time));
  if (barTimes.some((barTime) => !Number.isFinite(barTime))) return [];
  const maxDistanceMs = Math.max(inferIntradayIntervalMs(kline, barTimes), 60_000);
  const markers: PaperTradeMarker[] = [];
  trades.forEach((trade) => {
    if (trade.code.toUpperCase() !== normalizedCode || !trade.trade_time) return;
    const tradeTime = parseMarketTimestamp(trade.trade_time);
    if (!Number.isFinite(tradeTime)) return;
    let nearestIndex = 0;
    let nearestDistance = Number.POSITIVE_INFINITY;
    barTimes.forEach((barTime, index) => {
      const distance = Math.abs(barTime - tradeTime);
      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearestIndex = index;
      }
    });
    if (nearestDistance > maxDistanceMs) return;
    markers.push({
      barIndex: nearestIndex,
      barTime: kline[nearestIndex].bar_time,
      price: trade.price,
      side: trade.side,
      quantity: trade.quantity,
      amount: trade.amount,
      tradeTime: trade.trade_time,
    });
  });
  return markers;
}

function parseMarketTimestamp(value: string): number {
  if (/[zZ]|[+-]\d{2}:\d{2}$/.test(value)) return new Date(value).getTime();
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})[T\s](\d{2}):(\d{2})(?::(\d{2}))?/);
  if (!match) return Number.NaN;
  const [, year, month, day, hour, minute, second = '0'] = match;
  return Date.UTC(Number(year), Number(month) - 1, Number(day), Number(hour) - 8, Number(minute), Number(second));
}

function inferIntradayIntervalMs(kline: IntradayKline[], barTimes: number[]): number {
  const explicitPeriod = kline.find((bar) => Number.isFinite(bar.period_minutes) && bar.period_minutes > 0)?.period_minutes;
  if (explicitPeriod) return explicitPeriod * 60_000;
  const diffs = barTimes
    .slice(1)
    .map((barTime, index) => barTime - barTimes[index])
    .filter((diff) => diff > 0);
  return Math.min(...diffs, 60_000);
}

export function stockCodeFromBackendEvent(event: BackendEventLike): string {
  const code = event.payload?.code;
  return typeof code === 'string' ? code.toUpperCase() : '';
}

export function stockCodesFromBackendEvent(event: BackendEventLike): string[] {
  const single = stockCodeFromBackendEvent(event);
  if (single) return [single];
  const codes = event.payload?.codes;
  if (!Array.isArray(codes)) return [];
  return codes.filter((code): code is string => typeof code === 'string').map((code) => code.toUpperCase());
}

export function backendEventTouchesStock(event: BackendEventLike, code: string): boolean {
  const normalizedCode = code.trim().toUpperCase();
  if (!normalizedCode) return true;
  const codes = stockCodesFromBackendEvent(event);
  return codes.length === 0 || codes.includes(normalizedCode);
}

export function backendEventTouchesAnyStock(event: BackendEventLike, targetCodes: Set<string>): boolean {
  const codes = stockCodesFromBackendEvent(event);
  if (codes.length === 0) return true;
  return codes.some((code) => targetCodes.has(code));
}

export function shouldRefreshPaperIntraday(event: BackendEventLike): boolean {
  if (event.type === 'paper_watchlist.updated') {
    return event.payload?.action === 'synced';
  }
  if (event.type === 'watchlist.updated') {
    return event.payload?.action === 'synced';
  }
  return event.type === 'intraday.updated' || event.type === 'visibility.resumed';
}

export function paperIntradayRefreshCode(event: BackendEventLike, selectedCode: string): string {
  const normalizedSelectedCode = selectedCode.trim().toUpperCase();
  if (!normalizedSelectedCode) return '';
  return backendEventTouchesStock(event, normalizedSelectedCode) ? normalizedSelectedCode : '';
}

export function upsertPaperWatchItem(items: PaperWatchItem[], item: PaperWatchItem): PaperWatchItem[] {
  const exists = items.some((current) => current.stock.code === item.stock.code);
  if (!exists) return [...items, item];
  return items.map((current) => (current.stock.code === item.stock.code ? item : current));
}

export function canApplyPaperIntradayResult(
  requestId: number,
  latestRequestId: number,
  selectedCode: string,
  resultCode: string,
): boolean {
  return requestId === latestRequestId && selectedCode.trim().toUpperCase() === resultCode.trim().toUpperCase();
}
