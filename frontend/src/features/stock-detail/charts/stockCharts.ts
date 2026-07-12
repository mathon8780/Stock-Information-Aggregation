import { formatTime } from '../../../api/client';
import type { PaperTradeMarker } from '../../paper-trading/paperTradingData';
import type { ThemeMode } from '../../../theme/ThemeModeContext';
import type { Advice, IntradayKline, Kline, Signal, Snapshot } from '../../../types';

export function createKlineOption(kline: Kline[], themeMode: ThemeMode = 'light') {
  const dates = kline.map((item) => item.trade_date);
  const candle = kline.map((item) => [item.open, item.close, item.low, item.high]);
  const closes = kline.map((item) => item.close);
  return createCandlestickOption(dates, candle, closes, themeMode);
}

export function createIntradayKlineOption(kline: IntradayKline[], themeMode: ThemeMode = 'light', tradeMarkers: PaperTradeMarker[] = []) {
  const labels = kline.map((item) => formatTime(item.bar_time).slice(5, 16));
  const candle = kline.map((item) => [item.open, item.close, item.low, item.high]);
  const closes = kline.map((item) => item.close);
  return createCandlestickOption(labels, candle, closes, themeMode, tradeMarkers);
}

function chartPalette(themeMode: ThemeMode) {
  return themeMode === 'dark'
    ? { text: '#c7d2de', axis: '#33465f', split: '#1d2b3d', background: '#0f172a', area: 'rgba(45, 212, 191, 0.16)' }
    : { text: '#60707b', axis: '#cbd8df', split: '#e7eef2', background: '#ffffff', area: 'rgba(15, 118, 110, 0.12)' };
}

const signalStrength: Record<Signal, number> = {
  重点关注: 2,
  谨慎买入: 1,
  持有: 0,
  减仓: -1,
  回避: -2,
};

const signalColor: Record<Signal, string> = {
  重点关注: '#2563eb',
  谨慎买入: '#dc2626',
  持有: '#64748b',
  减仓: '#d97706',
  回避: '#7c3aed',
};

const strengthLabel: Record<number, Signal> = {
  2: '重点关注',
  1: '谨慎买入',
  0: '持有',
  [-1]: '减仓',
  [-2]: '回避',
};

function createCandlestickOption(labels: string[], candle: number[][], closes: number[], themeMode: ThemeMode, tradeMarkers: PaperTradeMarker[] = []) {
  const ma = (windowSize: number) => closes.map((_, index) => {
    const sample = closes.slice(Math.max(0, index - windowSize + 1), index + 1);
    return Number((sample.reduce((sum, value) => sum + value, 0) / sample.length).toFixed(2));
  });

  const palette = chartPalette(themeMode);
  const validTradeMarkers = tradeMarkers.filter((marker) => (
    marker.barIndex >= 0
    && marker.barIndex < labels.length
    && Number.isFinite(marker.price)
  ));
  const buyMarkers = validTradeMarkers.filter((marker) => marker.side === 'buy').map((marker) => ({
    value: [labels[marker.barIndex], marker.price],
    quantity: marker.quantity,
    amount: marker.amount,
    tradeTime: marker.tradeTime,
  }));
  const sellMarkers = validTradeMarkers.filter((marker) => marker.side === 'sell').map((marker) => ({
    value: [labels[marker.barIndex], marker.price],
    quantity: marker.quantity,
    amount: marker.amount,
    tradeTime: marker.tradeTime,
  }));
  const markerLegend = tradeMarkers.length ? ['买入', '卖出'] : [];

  return {
    animation: false,
    backgroundColor: palette.background,
    color: ['#0f766e', '#2563eb', '#d97706', '#8b5cf6'],
    tooltip: { trigger: 'axis', confine: true },
    legend: { data: ['K线', 'MA5', 'MA20', 'MA60', ...markerLegend], top: 0, textStyle: { color: palette.text } },
    grid: { left: 48, right: 24, top: 42, bottom: 42 },
    xAxis: { type: 'category', data: labels, boundaryGap: true, axisLine: { lineStyle: { color: palette.axis } }, axisLabel: { color: palette.text } },
    yAxis: { scale: true, axisLabel: { color: palette.text }, splitLine: { lineStyle: { color: palette.split } } },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 8 }],
    series: [
      { name: 'K线', type: 'candlestick', data: candle },
      { name: 'MA5', type: 'line', data: ma(5), smooth: true, symbol: 'none' },
      { name: 'MA20', type: 'line', data: ma(20), smooth: true, symbol: 'none' },
      { name: 'MA60', type: 'line', data: ma(60), smooth: true, symbol: 'none' },
      ...(buyMarkers.length ? [{
        name: '买入',
        type: 'scatter',
        data: buyMarkers,
        symbol: 'triangle',
        symbolSize: 14,
        symbolOffset: [0, -8],
        itemStyle: { color: '#dc2626', borderColor: '#ffffff', borderWidth: 1 },
        clip: true,
        z: 8,
      }] : []),
      ...(sellMarkers.length ? [{
        name: '卖出',
        type: 'scatter',
        data: sellMarkers,
        symbol: 'triangle',
        symbolRotate: 180,
        symbolSize: 14,
        symbolOffset: [0, 8],
        itemStyle: { color: '#16a34a', borderColor: '#ffffff', borderWidth: 1 },
        clip: true,
        z: 8,
      }] : []),
    ],
  };
}

export function createSnapshotOption(snapshots: Snapshot[], themeMode: ThemeMode = 'light') {
  const palette = chartPalette(themeMode);
  return {
    backgroundColor: palette.background,
    color: ['#0f766e'],
    tooltip: { trigger: 'axis' },
    grid: { left: 48, right: 24, top: 28, bottom: 32 },
    xAxis: {
      type: 'category',
      data: snapshots.map((item) => formatTime(item.snapshot_time).slice(5, 16)),
      axisLine: { lineStyle: { color: palette.axis } },
      axisLabel: { color: palette.text },
    },
    yAxis: { type: 'value', scale: true, axisLabel: { color: palette.text }, splitLine: { lineStyle: { color: palette.split } } },
    series: [
      {
        name: '最新价',
        type: 'line',
        data: snapshots.map((item) => item.price),
        smooth: true,
        symbol: 'none',
        areaStyle: { color: palette.area },
      },
    ],
  };
}

export function createAdviceTrendOption(history: Advice[], themeMode: ThemeMode = 'light') {
  const palette = chartPalette(themeMode);
  const items = [...history].sort((left, right) => new Date(left.created_at).getTime() - new Date(right.created_at).getTime());
  const labels = items.map((item) => formatTime(item.created_at).slice(5, 16));
  const strengthData = items.map((item) => {
    const signal = item.signal as Signal;
    const strength = signalStrength[signal] ?? 0;
    const confidence = Number.isFinite(item.confidence) ? item.confidence : 0;
    return {
      value: strength,
      symbolSize: Math.max(8, Math.min(18, 8 + confidence / 10)),
      itemStyle: { color: signalColor[signal] ?? '#64748b' },
      advice: item,
    };
  });

  return {
    animationDuration: 220,
    backgroundColor: palette.background,
    color: ['#2563eb', '#94a3b8'],
    tooltip: {
      trigger: 'axis',
      confine: true,
      formatter: (params: unknown) => {
        const entry = Array.isArray(params) ? params[0] : params;
        if (!entry || typeof entry !== 'object' || !('data' in entry)) return '';
        const data = entry.data as { advice?: Advice };
        const advice = data.advice;
        if (!advice) return '';
        const reasoning = advice.reasoning ? `<br/>${advice.reasoning}` : '';
        return `${formatTime(advice.created_at)}<br/>${advice.signal} · 置信度 ${Math.round(advice.confidence)}%${reasoning}`;
      },
    },
    grid: { left: 48, right: 42, top: 24, bottom: 46 },
    xAxis: {
      type: 'category',
      data: labels,
      boundaryGap: false,
      axisLine: { lineStyle: { color: palette.axis } },
      axisLabel: { color: palette.text, hideOverlap: true },
    },
    yAxis: [
      {
        type: 'value',
        min: -2,
        max: 2,
        interval: 1,
        axisLabel: {
          color: palette.text,
          formatter: (value: number) => strengthLabel[value] ?? '',
        },
        splitLine: { lineStyle: { color: palette.split } },
      },
      {
        type: 'value',
        min: 0,
        max: 100,
        axisLabel: { color: palette.text, formatter: '{value}%' },
        splitLine: { show: false },
      },
    ],
    dataZoom: items.length > 8 ? [{ type: 'inside' }, { type: 'slider', height: 16, bottom: 10 }] : [],
    series: [
      {
        name: '建议走势',
        type: 'line',
        data: strengthData,
        smooth: true,
        lineStyle: { width: 2, color: themeMode === 'dark' ? '#60a5fa' : '#2563eb' },
        areaStyle: { color: themeMode === 'dark' ? 'rgba(96, 165, 250, 0.12)' : 'rgba(37, 99, 235, 0.1)' },
      },
      {
        name: '置信度',
        type: 'bar',
        yAxisIndex: 1,
        data: items.map((item) => item.confidence),
        barMaxWidth: 10,
        itemStyle: { color: themeMode === 'dark' ? 'rgba(148, 163, 184, 0.2)' : 'rgba(100, 116, 139, 0.18)' },
      },
    ],
  };
}
