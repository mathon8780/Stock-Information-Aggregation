const { api } = require('../../services/api');
const { getSession, goLogin, requirePaperLogin } = require('../../services/session');
const { polling } = require('../../config');
const {
  decorateNews,
  decoratePaperSummary,
  decorateSnapshot,
  formatTime,
  priceClass,
  signalClass,
} = require('../../utils/format');

const preferredIndexOrder = ['000001.SH', '399001.SZ', '399006.SZ', '000300.SH', '000905.SH'];

function decorateWatchItem(item) {
  const snapshot = item.latest_snapshot || {};
  const advice = item.latest_advice || {};
  return {
    ...item,
    code: item.stock.code,
    name: item.stock.name,
    priceText: snapshot.price === null || snapshot.price === undefined ? '-' : Number(snapshot.price).toFixed(2),
    changePctText: snapshot.change_pct === null || snapshot.change_pct === undefined ? '-' : `${Number(snapshot.change_pct).toFixed(2)}%`,
    changeClass: priceClass(snapshot.change_pct),
    signal: advice.signal || '-',
    signalClass: signalClass(advice.signal),
    confidenceText: advice.confidence === null || advice.confidence === undefined ? '-' : `${Number(advice.confidence).toFixed(0)}%`,
  };
}

Page({
  data: {
    loading: true,
    lastUpdated: '-',
    accountSummary: null,
    indices: [],
    topGainers: [],
    topLosers: [],
    watchlist: [],
    news: [],
  },

  onShow() {
    const session = requirePaperLogin();
    if (!session) {
      this.stopPolling();
      return;
    }
    this.loadDashboard(false);
    this.startPolling();
  },

  onHide() {
    this.stopPolling();
  },

  onUnload() {
    this.stopPolling();
  },

  onPullDownRefresh() {
    this.loadDashboard(true).finally(() => wx.stopPullDownRefresh());
  },

  startPolling() {
    this.stopPolling();
    this.pollTimer = setInterval(() => {
      this.loadDashboard(false);
    }, polling.dashboardMs);
  },

  stopPolling() {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  },

  async loadDashboard(showToast) {
    const session = getSession();
    if (!session.token) return;
    this.setData({ loading: true });
    try {
      const tasks = [
        api.market({ page: 1, page_size: 300, sort_by: 'change_pct', sort_order: 'desc' }),
        api.market({ page: 1, page_size: 30, sort_by: 'change_pct', sort_order: 'asc' }),
        api.market({ page: 1, page_size: 20, market: 'INDEX', sort_by: 'code', sort_order: 'asc' }),
        api.watchlist(),
        api.news({ limit: 8 }),
      ];
      tasks.push(api.paperSummary(session.token));

      const [marketRes, loserRes, indexRes, watchRes, newsRes, summaryRes] = await Promise.all(tasks);
      const marketItems = (marketRes.items || []).map(decorateSnapshot);
      const loserItems = (loserRes.items || []).map(decorateSnapshot);
      const indexItems = (indexRes.items || []).map(decorateSnapshot);
      const stocks = marketItems.filter((item) => item.security_type === 'stock');
      const indexByCode = new Map(indexItems.map((item) => [item.code, item]));
      const preferredCodeSet = new Set(preferredIndexOrder);
      const preferredIndices = preferredIndexOrder.map((code) => indexByCode.get(code)).filter(Boolean);
      const fallbackIndices = indexItems.filter((item) => !preferredCodeSet.has(item.code));
      const indices = [...preferredIndices, ...fallbackIndices].slice(0, 4);

      this.setData({
        loading: false,
        lastUpdated: formatTime(new Date().toISOString()),
        accountSummary: summaryRes ? decoratePaperSummary(summaryRes) : null,
        indices,
        topGainers: stocks.slice(0, 6),
        topLosers: loserItems.filter((item) => item.security_type === 'stock').slice(0, 6),
        watchlist: (watchRes.items || []).map(decorateWatchItem).slice(0, 8),
        news: (newsRes.items || []).map(decorateNews).slice(0, 6),
      });
    } catch (error) {
      this.setData({ loading: false });
      if (error.status === 401) {
        getApp().clearPaperSession();
        goLogin();
        return;
      }
      if (showToast) {
        wx.showToast({ title: error.message || '加载失败', icon: 'none' });
      }
    }
  },

  openNews() {
    wx.switchTab({ url: '/pages/news/index' });
  },

  openPaper() {
    wx.switchTab({ url: '/pages/paper/index' });
  },
});
