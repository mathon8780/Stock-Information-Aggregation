import { formatTime } from '../../../api/client';
import type { IntradayKline, Kline, Snapshot } from '../../../types';

export function createKlineOption(kline: Kline[]) {
  const dates = kline.map((item) => item.trade_date);
  const candle = kline.map((item) => [item.open, item.close, item.low, item.high]);
  const closes = kline.map((item) => item.close);
  return createCandlestickOption(dates, candle, closes);
}

export function createIntradayKlineOption(kline: IntradayKline[]) {
  const labels = kline.map((item) => formatTime(item.bar_time).slice(5, 16));
  const candle = kline.map((item) => [item.open, item.close, item.low, item.high]);
  const closes = kline.map((item) => item.close);
  return createCandlestickOption(labels, candle, closes);
}

function createCandlestickOption(labels: string[], candle: number[][], closes: number[]) {
  const ma = (windowSize: number) => closes.map((_, index) => {
    const sample = closes.slice(Math.max(0, index - windowSize + 1), index + 1);
    return Number((sample.reduce((sum, value) => sum + value, 0) / sample.length).toFixed(2));
  });

  return {
    animation: false,
    color: ['#0f766e', '#2563eb', '#d97706', '#8b5cf6'],
    tooltip: { trigger: 'axis' },
    legend: { data: ['K线', 'MA5', 'MA20', 'MA60'], top: 0, textStyle: { color: '#60707b' } },
    grid: { left: 48, right: 24, top: 42, bottom: 42 },
    xAxis: { type: 'category', data: labels, boundaryGap: true, axisLine: { lineStyle: { color: '#cbd8df' } } },
    yAxis: { scale: true, splitLine: { lineStyle: { color: '#e7eef2' } } },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 8 }],
    series: [
      { name: 'K线', type: 'candlestick', data: candle },
      { name: 'MA5', type: 'line', data: ma(5), smooth: true, symbol: 'none' },
      { name: 'MA20', type: 'line', data: ma(20), smooth: true, symbol: 'none' },
      { name: 'MA60', type: 'line', data: ma(60), smooth: true, symbol: 'none' },
    ],
  };
}

export function createSnapshotOption(snapshots: Snapshot[]) {
  return {
    color: ['#0f766e'],
    tooltip: { trigger: 'axis' },
    grid: { left: 48, right: 24, top: 28, bottom: 32 },
    xAxis: {
      type: 'category',
      data: snapshots.map((item) => formatTime(item.snapshot_time).slice(5, 16)),
      axisLine: { lineStyle: { color: '#cbd8df' } },
    },
    yAxis: { type: 'value', scale: true, splitLine: { lineStyle: { color: '#e7eef2' } } },
    series: [
      {
        name: '最新价',
        type: 'line',
        data: snapshots.map((item) => item.price),
        smooth: true,
        symbol: 'none',
        areaStyle: { color: 'rgba(15, 118, 110, 0.12)' },
      },
    ],
  };
}
