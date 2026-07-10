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
