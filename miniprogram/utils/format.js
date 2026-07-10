function isValidNumber(value) {
  return value !== null && value !== undefined && !Number.isNaN(Number(value));
}

function formatNumber(value, digits = 2) {
  if (!isValidNumber(value)) return '-';
  return Number(value).toLocaleString('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatCompact(value) {
  if (!isValidNumber(value)) return '-';
  const number = Number(value);
  const abs = Math.abs(number);
  if (abs >= 100000000) return `${formatNumber(number / 100000000, 2)}亿`;
  if (abs >= 10000) return `${formatNumber(number / 10000, 2)}万`;
  return formatNumber(number, 0);
}

function formatPct(value, digits = 2) {
  if (!isValidNumber(value)) return '-';
  return `${formatNumber(value, digits)}%`;
}

function formatTime(value) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  const pad = (number) => String(number).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function priceClass(value) {
  if (!isValidNumber(value)) return 'price-flat';
  if (Number(value) > 0) return 'price-up';
  if (Number(value) < 0) return 'price-down';
  return 'price-flat';
}

function signalClass(signal) {
  if (signal === '重点关注' || signal === '谨慎买入') return 'signal-buy';
  if (signal === '减仓' || signal === '回避') return 'signal-risk';
  return 'signal-hold';
}

function sideText(side) {
  return side === 'sell' ? '卖出' : '买入';
}

function orderTypeText(type) {
  const labels = {
    market: '市价',
    limit: '限价',
    take_profit: '止盈',
    stop_loss: '止损',
  };
  return labels[type] || type || '-';
}

function normalizeCode(value) {
  return String(value || '').trim().toUpperCase();
}

function decorateSnapshot(item) {
  return {
    ...item,
    priceText: formatNumber(item.price, 2),
    changePctText: formatPct(item.change_pct, 2),
    changeClass: priceClass(item.change_pct),
    amountText: formatCompact(item.amount),
  };
}

function newsSentimentClass(sentiment) {
  if (sentiment === 'positive') return 'news-sentiment-positive';
  if (sentiment === 'negative') return 'news-sentiment-negative';
  return 'news-sentiment-neutral';
}

function decorateNews(item) {
  return {
    ...item,
    timeText: formatTime(item.published_at || item.fetched_at),
    sentimentText: item.sentiment === 'positive' ? '积极' : item.sentiment === 'negative' ? '消极' : '中性',
    sentimentClass: newsSentimentClass(item.sentiment),
  };
}

function decoratePaperSummary(summary) {
  if (!summary) return null;
  return {
    ...summary,
    totalAssetsText: formatNumber(summary.total_assets, 2),
    cashAvailableText: formatNumber(summary.cash_available, 2),
    cashFrozenText: formatNumber(summary.cash_frozen, 2),
    marketValueText: formatNumber(summary.position_market_value, 2),
  };
}

module.exports = {
  decorateNews,
  decoratePaperSummary,
  decorateSnapshot,
  formatCompact,
  formatNumber,
  formatPct,
  formatTime,
  normalizeCode,
  orderTypeText,
  priceClass,
  sideText,
  signalClass,
};
