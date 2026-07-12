import assert from 'node:assert/strict';
import test from 'node:test';
import * as paperTradingData from '../src/features/paper-trading/paperTradingData.ts';

test('paper intraday refreshes for completed syncs and page visibility recovery', () => {
  assert.equal(paperTradingData.shouldRefreshPaperIntraday({ type: 'paper_watchlist.updated', payload: { action: 'synced' } }), true);
  assert.equal(paperTradingData.shouldRefreshPaperIntraday({ type: 'paper_watchlist.updated', payload: { action: 'created' } }), false);
  assert.equal(paperTradingData.shouldRefreshPaperIntraday({ type: 'intraday.updated' }), true);
  assert.equal(paperTradingData.shouldRefreshPaperIntraday({ type: 'paper_watchlist.updated', payload: { action: 'deleted' } }), false);
  assert.equal(paperTradingData.shouldRefreshPaperIntraday({ type: 'news.updated' }), false);
  assert.equal(paperTradingData.shouldRefreshPaperIntraday({ type: 'visibility.resumed' }), true);
});

test('paper intraday events only refresh the selected watch stock', () => {
  const refreshCode = paperTradingData.paperIntradayRefreshCode;
  assert.equal(typeof refreshCode, 'function');
  assert.equal(refreshCode({ type: 'paper_watchlist.updated', payload: { code: '000002.sz', action: 'synced' } }, '000002.SZ'), '000002.SZ');
  assert.equal(refreshCode({ type: 'paper_watchlist.updated', payload: { code: '000001.SZ', action: 'synced' } }, '000002.SZ'), '');
  assert.equal(refreshCode({ type: 'visibility.resumed' }, '000002.SZ'), '000002.SZ');
});

test('new paper watch item is available before its tab is selected', () => {
  const upsert = paperTradingData.upsertPaperWatchItem;
  assert.equal(typeof upsert, 'function');
  const existing = { id: 1, stock: { id: 1, code: '000001.SZ', name: '平安银行', market: 'SZ', security_type: 'stock' } };
  const added = { id: 2, stock: { id: 2, code: '000002.SZ', name: '万 科Ａ', market: 'SZ', security_type: 'stock' } };
  assert.deepEqual(upsert([existing], added).map((item) => item.stock.code), ['000001.SZ', '000002.SZ']);
  assert.deepEqual(upsert([existing, added], { ...added, display_order: 2 }).map((item) => item.stock.code), ['000001.SZ', '000002.SZ']);
});

test('minute K polling runs every minute and ignores stale tab responses', () => {
  assert.equal(paperTradingData.PAPER_INTRADAY_POLL_INTERVAL_MS, 60_000);
  const canApply = paperTradingData.canApplyPaperIntradayResult;
  assert.equal(typeof canApply, 'function');
  assert.equal(canApply(2, 2, '000002.SZ', '000002.SZ'), true);
  assert.equal(canApply(1, 2, '000002.SZ', '000002.SZ'), false);
  assert.equal(canApply(2, 2, '000002.SZ', '000001.SZ'), false);
});

test('paper trade markers stay on the selected stock and current intraday session', () => {
  const kline = [
    { bar_time: '2026-07-10T09:30:00', period_minutes: 1, open: 10, high: 10.2, low: 9.9, close: 10.1, source: 'test' },
    { bar_time: '2026-07-10T09:31:00', period_minutes: 1, open: 10.1, high: 10.4, low: 10, close: 10.3, source: 'test' },
    { bar_time: '2026-07-10T09:32:00', period_minutes: 1, open: 10.3, high: 10.5, low: 10.2, close: 10.4, source: 'test' },
  ];
  const markers = paperTradingData.createPaperTradeMarkers(kline, [
    { id: 1, order_id: 1, stock_id: 1, code: '300308.SZ', name: '中际旭创', side: 'buy', quantity: 100, price: 10.35, amount: 1035, commission: 1, stamp_tax: 0, transfer_fee: 0.1, fee_total: 1.1, trade_time: '2026-07-10T09:31:30+08:00', price_source: 'test' },
    { id: 2, order_id: 2, stock_id: 2, code: '603867.SH', name: '新化股份', side: 'buy', quantity: 100, price: 31.2, amount: 3120, commission: 1, stamp_tax: 0, transfer_fee: 0.1, fee_total: 1.1, trade_time: '2026-07-10T09:31:00+08:00', price_source: 'test' },
    { id: 3, order_id: 3, stock_id: 1, code: '300308.SZ', name: '中际旭创', side: 'sell', quantity: 100, price: 10.8, amount: 1080, commission: 1, stamp_tax: 1, transfer_fee: 0.1, fee_total: 2.1, trade_time: '2026-07-09T15:00:00+08:00', price_source: 'test' },
  ], '300308.SZ');

  assert.equal(markers.length, 1);
  assert.equal(markers[0].barIndex, 1);
  assert.equal(markers[0].side, 'buy');
});
