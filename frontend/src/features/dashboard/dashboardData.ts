import type { Advice, IntradayKline, Kline, Signal } from '../../types';

export type ChartPeriod = 'minute' | 'fiveMinute' | 'daily';
export type CandleRow = (Kline | IntradayKline) & { timeKey: string };
export const signalOrder: Signal[] = ['重点关注', '谨慎买入', '持有', '减仓', '回避'];
export function signalCounts(items: Advice[]) {
  return Object.fromEntries(
    signalOrder.map((signal) => [signal, items.filter((item) => item.signal === signal).length]),
  ) as Record<Signal, number>;
}
export function marketTimeKey(value: string): string {
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/.test(value) ? value : `${value}+08:00`;
  const date = new Date(normalized);
  if (!Number.isFinite(date.getTime())) return '';
  const parts = new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date);
  const part = (name: string) => parts.find((item) => item.type === name)?.value || '';
  return `${part('year')}-${part('month')}-${part('day')}T${part('hour')}:${part('minute')}`;
}
export function candleRows(items: (Kline | IntradayKline)[]): CandleRow[] {
  return items
    .filter((row) => [row.open, row.close, row.high, row.low].every((value) => value != null && Number.isFinite(value)))
    .map((row) => ({
      ...row,
      timeKey: 'trade_date' in row ? row.trade_date.slice(0, 10) : marketTimeKey(row.bar_time),
    }))
    .filter((row) => row.timeKey)
    .sort((a, b) => a.timeKey.localeCompare(b.timeKey));
}
export function rowsInRange(rows: CandleRow[], from: string, to: string): CandleRow[] {
  return rows.filter((row) => (!from || row.timeKey >= from) && (!to || row.timeKey <= to));
}
