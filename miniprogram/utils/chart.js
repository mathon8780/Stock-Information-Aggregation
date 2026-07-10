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

function drawGrid(ctx, width, height) {
  ctx.setStrokeStyle('#edf1f7');
  ctx.setLineWidth(1);
  [0.25, 0.5, 0.75].forEach((ratio) => {
    const y = height * ratio;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();
  });
}

function drawLineChart(page, canvasId, points, options = {}) {
  const width = options.width || 340;
  const height = options.height || 160;
  const ctx = wx.createCanvasContext(canvasId, page);
  ctx.clearRect(0, 0, width, height);
  drawGrid(ctx, width, height);
  if (!points || points.length < 2) {
    ctx.setFillStyle('#98a2b3');
    ctx.setFontSize(12);
    ctx.fillText('暂无走势', width / 2 - 28, height / 2);
    ctx.draw();
    return;
  }

  const values = points.map((item) => numberValue(item.value));
  const bounds = range(values);
  const padding = 10;
  const plotHeight = height - padding * 2;
  const step = width / Math.max(points.length - 1, 1);

  ctx.setStrokeStyle(options.color || '#d12f2f');
  ctx.setLineWidth(2);
  ctx.beginPath();
  points.forEach((point, index) => {
    const x = index * step;
    const y = yFor(numberValue(point.value), bounds.min, bounds.max, padding, plotHeight);
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
  drawGrid(ctx, width, height);
  if (!bars || !bars.length) {
    ctx.setFillStyle('#98a2b3');
    ctx.setFontSize(12);
    ctx.fillText('暂无分钟K', width / 2 - 32, height / 2);
    ctx.draw();
    return;
  }

  const lows = bars.map((bar) => numberValue(bar.low));
  const highs = bars.map((bar) => numberValue(bar.high));
  const bounds = range(lows.concat(highs));
  const top = 12;
  const plotHeight = height - 28;
  const step = width / Math.max(bars.length, 1);
  const bodyWidth = Math.max(3, Math.min(10, step * 0.58));

  bars.forEach((bar, index) => {
    const open = numberValue(bar.open);
    const close = numberValue(bar.close);
    const high = numberValue(bar.high);
    const low = numberValue(bar.low);
    const x = index * step + step / 2;
    const highY = yFor(high, bounds.min, bounds.max, top, plotHeight);
    const lowY = yFor(low, bounds.min, bounds.max, top, plotHeight);
    const openY = yFor(open, bounds.min, bounds.max, top, plotHeight);
    const closeY = yFor(close, bounds.min, bounds.max, top, plotHeight);
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
    const x = nearestIndex * step + step / 2;
    const y = yFor(numberValue(trade.price), bounds.min, bounds.max, top, plotHeight);
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
};
