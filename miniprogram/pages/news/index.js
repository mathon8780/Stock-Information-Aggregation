const { api } = require('../../services/api');
const { requirePaperLogin } = require('../../services/session');
const { polling } = require('../../config');
const { decorateNews } = require('../../utils/format');

const scopeOptions = [
  { label: '全部', value: '' },
  { label: '市场', value: 'market' },
  { label: '个股', value: 'stock' },
];

const sentimentOptions = [
  { label: '全部', value: '' },
  { label: '积极', value: 'positive' },
  { label: '中性', value: 'neutral' },
  { label: '负面', value: 'negative' },
];

Page({
  data: {
    loading: true,
    scope: '',
    sentiment: '',
    scopeOptions,
    sentimentOptions,
    items: [],
    expandedId: 0,
  },

  onShow() {
    const session = requirePaperLogin();
    if (!session) {
      this.stopPolling();
      return;
    }
    this.loadNews(false);
    this.startPolling();
  },

  onHide() {
    this.stopPolling();
  },

  onUnload() {
    this.stopPolling();
  },

  onPullDownRefresh() {
    this.loadNews(true).finally(() => wx.stopPullDownRefresh());
  },

  startPolling() {
    this.stopPolling();
    this.pollTimer = setInterval(() => {
      this.loadNews(false);
    }, polling.newsMs);
  },

  stopPolling() {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  },

  async loadNews(showToast) {
    this.setData({ loading: true });
    try {
      const response = await api.news({
        limit: 100,
        scope: this.data.scope,
        sentiment: this.data.sentiment,
      });
      this.setData({
        loading: false,
        items: (response.items || []).map((item) => ({
          ...decorateNews(item),
          isExpanded: item.id === this.data.expandedId,
          body: item.content || item.summary || item.title,
          stockName: item.name || (item.stock && item.stock.name) || '',
          stockCode: item.code || (item.stock && item.stock.code) || '',
        })),
      });
    } catch (error) {
      this.setData({ loading: false });
      if (showToast) wx.showToast({ title: error.message || '加载失败', icon: 'none' });
    }
  },

  selectScope(event) {
    this.setData({ scope: event.currentTarget.dataset.value || '' });
    this.loadNews(true);
  },

  selectSentiment(event) {
    this.setData({ sentiment: event.currentTarget.dataset.value || '' });
    this.loadNews(true);
  },

  toggleNews(event) {
    const id = Number(event.currentTarget.dataset.id);
    const expandedId = this.data.expandedId === id ? 0 : id;
    this.setData({
      expandedId,
      items: this.data.items.map((item) => ({ ...item, isExpanded: item.id === expandedId })),
    });
  },

  copyUrl(event) {
    const url = event.currentTarget.dataset.url;
    if (!url) return;
    wx.setClipboardData({
      data: url,
      success: () => wx.showToast({ title: '原文链接已复制', icon: 'none' }),
    });
  },
});
