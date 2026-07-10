const { apiBaseUrl, apiBaseUrlStorageKey, defaultApiBaseUrl } = require('../config');
const { authHeader } = require('./session');

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

function buildQuery(params) {
  const pairs = [];
  Object.keys(params || {}).forEach((key) => {
    const value = params[key];
    if (value === undefined || value === null || value === '') return;
    pairs.push(`${encodeURIComponent(key)}=${encodeURIComponent(value)}`);
  });
  return pairs.length ? `?${pairs.join('&')}` : '';
}

function normalizeApiBaseUrl(value) {
  const fallback = defaultApiBaseUrl || apiBaseUrl;
  const normalized = String(value || fallback || '').trim().replace(/\/+$/, '');
  return normalized || fallback;
}

function getConfiguredApiBaseUrl() {
  try {
    return normalizeApiBaseUrl(wx.getStorageSync(apiBaseUrlStorageKey) || apiBaseUrl);
  } catch (error) {
    return normalizeApiBaseUrl(apiBaseUrl);
  }
}

function saveApiBaseUrl(value) {
  const normalized = normalizeApiBaseUrl(value);
  wx.setStorageSync(apiBaseUrlStorageKey, normalized);
  return normalized;
}

function formatRequestFailure(error, url) {
  const code = error && (error.errCode || error.errno || error.code);
  const reason = (error && (error.errMsg || error.message)) || '网络请求失败';
  const codeText = code === undefined || code === null || code === '' ? '' : `（${code}）`;
  let message = `网络请求失败${codeText}：${reason}；请求地址：${url}`;
  if (/\/\/(127\.0\.0\.1|localhost)(:|\/)/.test(url)) {
    message += '。如果在真机预览，请把后端 API 地址改为电脑局域网 IP，并用 0.0.0.0 启动后端';
  }
  return message;
}

function request(path, options = {}) {
  return new Promise((resolve, reject) => {
    const url = `${getConfiguredApiBaseUrl()}${path}`;
    wx.request({
      url,
      method: options.method || 'GET',
      data: options.data,
      header: {
        'Content-Type': 'application/json',
        ...(options.header || {}),
      },
      success(response) {
        const status = response.statusCode || 0;
        if (status >= 200 && status < 300) {
          resolve(response.data);
          return;
        }
        const data = response.data || {};
        const detail = data.detail || data.message;
        const message = typeof detail === 'string' ? detail : `HTTP ${status}`;
        reject(new ApiError(message, status));
      },
      fail(error) {
        const status = Number(error && (error.errCode || error.errno || error.code)) || 0;
        reject(new ApiError(formatRequestFailure(error, url), status));
      },
    });
  });
}

function paperRequest(token, path, options = {}) {
  return request(path, {
    ...options,
    header: {
      ...authHeader(token),
      ...(options.header || {}),
    },
  });
}

const api = {
  health() {
    return request('/health');
  },
  market(params = {}) {
    return request(`/market/snapshot${buildQuery(params)}`);
  },
  watchlist() {
    return request('/watchlist');
  },
  stocks(keyword) {
    return request(`/stocks${buildQuery({ q: keyword, security_type: 'stock' })}`);
  },
  news(params = {}) {
    return request(`/news${buildQuery(params)}`);
  },
  intraday(code, period = 1, days = 1) {
    return request(`/stocks/${encodeURIComponent(code)}/intraday${buildQuery({ period, days })}`);
  },
  collectStockIntraday(code, period = 1, tradingDays = 1) {
    return request(`/collector/real/intraday/${encodeURIComponent(code)}${buildQuery({ period, trading_days: tradingDays })}`, { method: 'POST' });
  },
  createPaperAccount(payload) {
    return request('/paper/accounts', { method: 'POST', data: payload });
  },
  loginPaperAccount(payload) {
    return request('/paper/sessions', { method: 'POST', data: payload });
  },
  logoutPaperAccount(token) {
    return paperRequest(token, '/paper/sessions/current', { method: 'DELETE' });
  },
  paperSummary(token) {
    return paperRequest(token, '/paper/summary');
  },
  paperPerformanceSummary(token) {
    return paperRequest(token, '/paper/performance/summary');
  },
  paperEquity(token) {
    return paperRequest(token, '/paper/equity');
  },
  paperWatchlist(token) {
    return paperRequest(token, '/paper/watchlist');
  },
  addPaperWatch(token, code) {
    return paperRequest(token, '/paper/watchlist', { method: 'POST', data: { code } });
  },
  removePaperWatch(token, code) {
    return paperRequest(token, `/paper/watchlist/${encodeURIComponent(code)}`, { method: 'DELETE' });
  },
  paperQuote(token, code) {
    return paperRequest(token, `/paper/quote${buildQuery({ code })}`);
  },
  paperPositions(token) {
    return paperRequest(token, '/paper/positions');
  },
  paperOrders(token, params = {}) {
    return paperRequest(token, `/paper/orders${buildQuery({ page_size: 50, ...params })}`);
  },
  createPaperOrder(token, payload) {
    return paperRequest(token, '/paper/orders', { method: 'POST', data: payload });
  },
  cancelPaperOrder(token, orderId) {
    return paperRequest(token, `/paper/orders/${orderId}/cancel`, { method: 'POST' });
  },
  runPaperMatching(token) {
    return paperRequest(token, '/paper/match/run', { method: 'POST' });
  },
  paperTrades(token) {
    return paperRequest(token, '/paper/trades');
  },
  paperCashFlows(token, params = {}) {
    return paperRequest(token, `/paper/cash-flows${buildQuery({ page_size: 50, ...params })}`);
  },
};

module.exports = {
  ApiError,
  api,
  apiBaseUrlStorageKey,
  formatRequestFailure,
  getConfiguredApiBaseUrl,
  normalizeApiBaseUrl,
  saveApiBaseUrl,
};
