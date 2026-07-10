import type { IntradayKline, PaperTrade, PaperWatchItem } from '../../types';
import { backendEventTouchesAnyStock, backendEventTouchesStock, buildStockSearchOptions, createPaperCaptcha, createPaperTradeMarkers, isPaperCaptchaMatch, isReasonablePaperPhone, normalizePaperPhone, paperIntradayRefreshCode, paperIntradayRefreshPlan, selectLatestTradingDayIntraday, shouldRefreshPaperIntraday, stockCodeFromBackendEvent, stockCodesFromBackendEvent } from './paperTradingData';

const rows: IntradayKline[] = [
  { bar_time: '2026-07-02T14:59:00', period_minutes: 1, open: 10, high: 10.2, low: 9.9, close: 10.1, source: 'test' },
  { bar_time: '2026-07-03T09:31:00', period_minutes: 1, open: 10.1, high: 10.3, low: 10.0, close: 10.2, source: 'test' },
];

const latestRows: IntradayKline[] = selectLatestTradingDayIntraday(rows);
const firstLatestRow: IntradayKline | undefined = latestRows[0];
const watchItem: PaperWatchItem = {
  id: 1,
  stock: { id: 1, code: '300308.SZ', name: '中际旭创', market: 'SZ', security_type: 'stock' },
  display_order: 1,
  added_at: '2026-07-03T09:31:00',
  latest_snapshot: null,
  latest_advice: null,
};
const stockOptions = buildStockSearchOptions([
  { id: 1, code: '300308.SZ', name: '中际旭创', market: 'SZ', security_type: 'stock' },
]);
const stockOptionValue: string = stockOptions[0]?.value ?? '';
const stockOptionKeywords: string[] = stockOptions[0]?.keywords ?? [];
const syncEventCode: string = stockCodeFromBackendEvent({ type: 'paper_watchlist.updated', payload: { code: '300308.sz' } });
const syncEventCodes: string[] = stockCodesFromBackendEvent({ type: 'intraday.updated', payload: { codes: ['300308.sz', '920000.bj'] } });
const touchesSelected: boolean = backendEventTouchesStock({ type: 'intraday.updated', payload: { codes: ['300308.SZ'] } }, '300308.SZ');
const touchesAny: boolean = backendEventTouchesAnyStock({ type: 'intraday.updated', payload: { codes: ['300308.SZ'] } }, new Set(['300308.SZ']));
const refreshCode: string = paperIntradayRefreshCode({ type: 'intraday.updated', payload: { codes: ['300308.SZ'] } }, '300308.SZ');
const switchRefreshPlan: { readCacheFirst: boolean; refreshSourceInBackground: boolean; clearOnError: boolean } = paperIntradayRefreshPlan('switch');
const manualRefreshPlan: { readCacheFirst: boolean; refreshSourceInBackground: boolean; clearOnError: boolean } = paperIntradayRefreshPlan('manual');
const shouldRefreshSync: boolean = shouldRefreshPaperIntraday({ type: 'paper_watchlist.updated', payload: { action: 'synced' } });
const shouldIgnoreDelete: boolean = shouldRefreshPaperIntraday({ type: 'paper_watchlist.updated', payload: { action: 'deleted' } });
const captcha: string = createPaperCaptcha(() => 0.1);
const captchaMatches: boolean = isPaperCaptchaMatch(' ab12 ', 'AB12');
const normalizedPhone: string = normalizePaperPhone(' 139-0000-0001 ');
const phoneValid: boolean = isReasonablePaperPhone(normalizedPhone);
const tradeMarkers = createPaperTradeMarkers(rows, [
  { id: 1, order_id: 1, stock_id: 1, code: '300308.SZ', name: '中际旭创', side: 'buy', quantity: 100, price: 10.2, amount: 1020, commission: 1, stamp_tax: 0, transfer_fee: 0.1, fee_total: 1.1, trade_time: '2026-07-03T09:31:30', price_source: 'test' } satisfies PaperTrade,
], '300308.SZ');

void firstLatestRow;
void watchItem;
void stockOptionValue;
void stockOptionKeywords;
void syncEventCode;
void syncEventCodes;
void touchesSelected;
void touchesAny;
void refreshCode;
void switchRefreshPlan;
void manualRefreshPlan;
void shouldRefreshSync;
void shouldIgnoreDelete;
void captcha;
void captchaMatches;
void normalizedPhone;
void phoneValid;
void tradeMarkers;
