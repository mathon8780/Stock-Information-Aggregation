const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const ts = require('typescript');
const source = fs.readFileSync(path.join(__dirname, '../src/features/dashboard/dashboardData.ts'), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
});
const target = { exports: {} };
vm.runInNewContext(compiled.outputText, { exports: target.exports, module: target, Intl, Date });
const { marketTimeKey, candleRows, rowsInRange, signalCounts } = target.exports;
const daily = (day, close = 12) => ({ trade_date: `2026-11-${day}`, open: 10, high: 13, low: 9, close, volume: 100 });

test('minute boundaries use China market time across UTC midnight', () => {
  assert.equal(marketTimeKey('2026-11-10T16:00:00Z'), '2026-11-11T00:00');
  assert.equal(marketTimeKey('2026-11-11T01:30:59Z'), '2026-11-11T09:30');
  assert.equal(marketTimeKey('2026-11-11T09:30:00+08:00'), '2026-11-11T09:30');
  assert.equal(marketTimeKey('2026-11-11T09:30:00'), '2026-11-11T09:30');
  assert.equal(marketTimeKey('invalid'), '');
});
test('custom daily range is inclusive and can reach the oldest loaded candle', () => {
  const rows = candleRows([daily('11'), daily('09'), daily('10')]);
  const filtered = rowsInRange(rows, '2026-11-09', '2026-11-10');
  assert.equal(filtered.length, 2);
  assert.equal(filtered[0].timeKey, '2026-11-09');
  assert.equal(filtered[1].timeKey, '2026-11-10');
  assert.equal(rowsInRange(rows, '2026-11-10', '2026-11-10').length, 1);
  assert.equal(rowsInRange(rows, '2026-12-01', '2026-12-02').length, 0);
});
test('minute endpoint includes exactly the selected minute without other days', () => {
  const rows = candleRows(
    ['2026-11-10T09:30:00+08:00', '2026-11-11T09:30:00+08:00', '2026-11-11T09:31:00+08:00'].map((bar_time) => ({
      bar_time,
      period_minutes: 1,
      open: 10,
      high: 11,
      low: 9,
      close: 10,
    })),
  );
  assert.equal(rowsInRange(rows, '2026-11-11T09:30', '2026-11-11T09:30').length, 1);
});
test('invalid OHLC rows are omitted without creating replacement prices', () => {
  assert.equal(candleRows([daily('09'), daily('10', NaN), daily('11', null)]).length, 1);
});
test('all five real signal categories remain distinct', () => {
  const counts = signalCounts(
    ['重点关注', '谨慎买入', '持有', '减仓', '回避', '重点关注'].map((signal) => ({ signal })),
  );
  assert.equal(Object.keys(counts).length, 5);
  assert.equal(counts['重点关注'], 2);
  assert.equal(counts['回避'], 1);
  assert.equal(
    Object.values(counts).reduce((sum, value) => sum + value, 0),
    6,
  );
});
