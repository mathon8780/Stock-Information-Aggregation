function numberValue(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function range(values) {
  const filtered = values.map(numberValue).filter((value) => Number.isFinite(value));
  if (!filtered.length) return { min: 0, max: 1 };
  const min = Math.min(...filtered);
  const max = Math.max(...filtered);
  if (min === max) return { min: min - 1, max: max + 1 };
  return { min, max };
}

function yFor(value, min, max, top, height) {
  return top + (max - value) / (max - min) * height;
}

function formatAxisValue(value) {
  const number = numberValue(value);
  const abs = Math.abs(number);
  if (abs >= 1000000) return `${(number / 1000000).toFixed(abs >= 10000000 ? 0 : 1)}m`;
  if (abs >= 1000) return `${(number / 1000).toFixed(abs >= 10000 ? 0 : 1)}k`;
  if (abs >= 100) return number.toFixed(0);
  if (abs >= 10) return number.toFixed(1);
  return number.toFixed(2);
}

function formatTimeLabel(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 5);
  const pad = (number) => String(number).padStart(2, '0');
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function drawAxes(ctx, width, height, bounds, labels = [], options = {}) {
  const left = options.left || 46;
  const right = options.right || 8;
  const top = options.top || 12;
  const bottom = options.bottom || 24;
  const plotWidth = Math.max(40, width - left - right);
  const plotHeight = Math.max(40, height - top - bottom);
  const x0 = left;
  const y0 = top;

  ctx.setStrokeStyle('#e4e9f2');
  ctx.setLineWidth(1);
  [0, 0.5, 1].forEach((ratio) => {
    const y = y0 + plotHeight * ratio;
    ctx.beginPath();
    ctx.moveTo(x0, y);
    ctx.lineTo(x0 + plotWidth, y);
    ctx.stroke();

    const value = bounds.max - (bounds.max - bounds.min) * ratio;
    ctx.setFillStyle('#667085');
    ctx.setFontSize(10);
    ctx.setTextAlign('right');
    ctx.fillText(formatAxisValue(value), x0 - 5, y + 3);
  });

  ctx.setStrokeStyle('#cfd8e6');
  ctx.beginPath();
  ctx.moveTo(x0, y0);
  ctx.lineTo(x0, y0 + plotHeight);
  ctx.lineTo(x0 + plotWidth, y0 + plotHeight);
  ctx.stroke();

  const first = labels[0];
  const middle = labels[Math.floor((labels.length - 1) / 2)];
  const last = labels[labels.length - 1];
  [
    { text: formatTimeLabel(first), x: x0, align: 'left' },
    { text: formatTimeLabel(middle), x: x0 + plotWidth / 2, align: 'center' },
    { text: formatTimeLabel(last), x: x0 + plotWidth, align: 'right' },
  ].forEach((label) => {
    if (!label.text) return;
    ctx.setFillStyle('#667085');
    ctx.setFontSize(10);
    ctx.setTextAlign(label.align);
    ctx.fillText(label.text, label.x, y0 + plotHeight + 17);
  });

  ctx.setTextAlign('left');
  return { left: x0, top: y0, width: plotWidth, height: plotHeight };
}

function drawLineChart(page, canvasId, points, options = {}) {
  const width = options.width || 340;
  const height = options.height || 160;
  const ctx = wx.createCanvasContext(canvasId, page);
  ctx.clearRect(0, 0, width, height);
  const values = (points || []).map((item) => numberValue(item.value));
  const bounds = range(values);
  const labels = (points || []).map((item) => item.time);
  const plot = drawAxes(ctx, width, height, bounds, labels);
  if (!points || points.length < 2) {
    ctx.setFillStyle('#98a2b3');
    ctx.setFontSize(12);
    ctx.fillText('暂无走势', width / 2 - 28, height / 2);
    ctx.draw();
    return;
  }

  const step = plot.width / Math.max(points.length - 1, 1);

  ctx.setStrokeStyle(options.color || '#d12f2f');
  ctx.setLineWidth(2);
  ctx.beginPath();
  points.forEach((point, index) => {
    const x = plot.left + index * step;
    const y = yFor(numberValue(point.value), bounds.min, bounds.max, plot.top, plot.height);
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
  ctx.draw();
}

function drawKlineChart(page, canvasId, bars, trades = [], options = {}) {
  const width = options.width || 340;
  const height = options.height || 220;
  const ctx = wx.createCanvasContext(canvasId, page);
  ctx.clearRect(0, 0, width, height);
  const lows = (bars || []).map((bar) => numberValue(bar.low));
  const highs = (bars || []).map((bar) => numberValue(bar.high));
  const bounds = range(lows.concat(highs));
  const labels = (bars || []).map((bar) => bar.bar_time);
  const plot = drawAxes(ctx, width, height, bounds, labels);
  if (!bars || !bars.length) {
    ctx.setFillStyle('#98a2b3');
    ctx.setFontSize(12);
    ctx.fillText('暂无分钟K', width / 2 - 32, height / 2);
    ctx.draw();
    return;
  }

  const step = plot.width / Math.max(bars.length, 1);
  const bodyWidth = Math.max(3, Math.min(10, step * 0.58));

  bars.forEach((bar, index) => {
    const open = numberValue(bar.open);
    const close = numberValue(bar.close);
    const high = numberValue(bar.high);
    const low = numberValue(bar.low);
    const x = plot.left + index * step + step / 2;
    const highY = yFor(high, bounds.min, bounds.max, plot.top, plot.height);
    const lowY = yFor(low, bounds.min, bounds.max, plot.top, plot.height);
    const openY = yFor(open, bounds.min, bounds.max, plot.top, plot.height);
    const closeY = yFor(close, bounds.min, bounds.max, plot.top, plot.height);
    const isUp = close >= open;

    ctx.setStrokeStyle(isUp ? '#d12f2f' : '#148f56');
    ctx.setFillStyle(isUp ? '#fff1f1' : '#e9f8ef');
    ctx.setLineWidth(1);
    ctx.beginPath();
    ctx.moveTo(x, highY);
    ctx.lineTo(x, lowY);
    ctx.stroke();
    ctx.fillRect(x - bodyWidth / 2, Math.min(openY, closeY), bodyWidth, Math.max(2, Math.abs(openY - closeY)));
    ctx.strokeRect(x - bodyWidth / 2, Math.min(openY, closeY), bodyWidth, Math.max(2, Math.abs(openY - closeY)));
  });

  trades.forEach((trade) => {
    const tradeTime = new Date(trade.trade_time || '').getTime();
    if (!Number.isFinite(tradeTime)) return;
    let nearestIndex = 0;
    let nearestDistance = Number.MAX_SAFE_INTEGER;
    bars.forEach((bar, index) => {
      const distance = Math.abs(new Date(bar.bar_time).getTime() - tradeTime);
      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearestIndex = index;
      }
    });
    const x = plot.left + nearestIndex * step + step / 2;
    const y = yFor(numberValue(trade.price), bounds.min, bounds.max, plot.top, plot.height);
    ctx.setFillStyle(trade.side === 'buy' ? '#d12f2f' : '#148f56');
    ctx.beginPath();
    if (trade.side === 'buy') {
      ctx.moveTo(x, y - 12);
      ctx.lineTo(x - 7, y + 2);
      ctx.lineTo(x + 7, y + 2);
    } else {
      ctx.moveTo(x, y + 12);
      ctx.lineTo(x - 7, y - 2);
      ctx.lineTo(x + 7, y - 2);
    }
    ctx.closePath();
    ctx.fill();
  });

  ctx.draw();
}

module.exports = {
  drawKlineChart,
  drawLineChart,
  formatAxisValue,
};
