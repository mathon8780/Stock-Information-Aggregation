const { api } = require('../../services/api');
const { goLogin, requirePaperLogin } = require('../../services/session');
const { polling } = require('../../config');
const { drawKlineChart, drawLineChart } = require('../../utils/chart');
const {
  decoratePaperSummary,
  formatNumber,
  formatPct,
  formatTime,
  normalizeCode,
  orderTypeText,
  priceClass,
  sideText,
  signalClass,
} = require('../../utils/format');

function latestTradingDayBars(items) {
  const bars = [...(items || [])].sort((a, b) => new Date(a.bar_time).getTime() - new Date(b.bar_time).getTime());
  const last = bars[bars.length - 1];
  if (!last) return [];
  const day = String(last.bar_time).slice(0, 10);
  return bars.filter((item) => String(item.bar_time).slice(0, 10) === day);
}

function formatShareQuantity(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '-';
  const abs = Math.abs(number);
  if (abs >= 1000000) return `${formatNumber(number / 1000000, 1)}m`;
  if (abs >= 1000) return `${formatNumber(number / 1000, 1)}k`;
  return formatNumber(number, 0);
}

function normalizePhone(value) {
  return String(value || '').replace(/\D/g, '');
}

function isReasonablePhone(value) {
  return /^1[3-9]\d{9}$/.test(normalizePhone(value));
}

function decorateWatchItem(item) {
  const snapshot = item.latest_snapshot || {};
  const advice = item.latest_advice || {};
  return {
    ...item,
    code: item.stock.code,
    name: item.stock.name,
    priceText: snapshot.price === null || snapshot.price === undefined ? '-' : formatNumber(snapshot.price, 2),
    changePctText: snapshot.change_pct === null || snapshot.change_pct === undefined ? '-' : formatPct(snapshot.change_pct, 2),
    changeClass: priceClass(snapshot.change_pct),
    signal: advice.signal || '-',
    signalClass: signalClass(advice.signal),
  };
}

function decoratePosition(item) {
  return {
    ...item,
    marketValueText: formatNumber(item.market_value, 2),
    availableQuantityText: formatShareQuantity(item.available_quantity),
    totalQuantityText: formatShareQuantity(item.total_quantity),
    frozenQuantityText: formatShareQuantity(item.frozen_quantity),
    todayBuyQuantityText: formatShareQuantity(item.today_buy_quantity),
    pnlText: formatNumber(item.floating_pnl, 2),
    pnlPctText: formatPct(item.floating_pnl_pct, 2),
    pnlClass: priceClass(item.floating_pnl),
    priceText: formatNumber(item.market_price, 2),
    costText: formatNumber(item.avg_cost, 4),
    assetRatioText: formatPct(item.asset_ratio_pct, 2),
  };
}

function decorateOrder(item) {
  return {
    ...item,
    sideText: sideText(item.side),
    sideClass: item.side === 'sell' ? 'price-down' : 'price-up',
    typeText: orderTypeText(item.order_type),
    createdText: formatTime(item.created_at),
    priceText: formatNumber(item.avg_fill_price || item.limit_price || item.trigger_price, 2),
    progressText: `${item.filled_quantity}/${item.quantity}`,
  };
}

function decorateTrade(item) {
  return {
    ...item,
    sideText: sideText(item.side),
    sideClass: item.side === 'sell' ? 'price-down' : 'price-up',
    priceText: formatNumber(item.price, 2),
    amountText: formatNumber(item.amount, 2),
    feeText: formatNumber(item.fee_total, 2),
    timeText: formatTime(item.trade_time),
  };
}

function decorateFlow(item) {
  const labels = {
    buy_cost: '买入扣款',
    sell_income: '卖出入账',
    fee: '手续费',
    reset: '账户重置',
    freeze: '冻结资金',
    unfreeze: '释放冻结',
  };
  return {
    ...item,
    typeText: labels[item.flow_type] || item.flow_type,
    amountText: formatNumber(item.amount, 2),
    amountClass: priceClass(item.amount),
    balanceText: formatNumber(item.cash_balance_after, 2),
    timeText: formatTime(item.created_at),
  };
}

Page({
  data: {
    authReady: false,
    loggedIn: false,
    loading: false,
    submitting: false,
    authMode: 'login',
    loginOwnerName: '',
    loginPassword: '',
    createOwnerName: '',
    createPhone: '',
    createPassword: '',
    createCaptchaId: '',
    createCaptchaPhone: '',
    createCaptchaCode: '',
    summary: null,
    performance: null,
    equity: [],
    watchlist: [],
    selectedCode: '',
    quote: null,
    intraday: [],
    positions: [],
    orders: [],
    trades: [],
    flows: [],
    searchKeyword: '',
    stockCandidates: [],
    orderCode: '',
    orderSide: 'buy',
    orderType: 'market',
    quantity: 100,
    limitPrice: '',
    triggerPrice: '',
    recordTab: 'orders',
    assetChartSize: { width: 340, height: 160 },
    intradayChartSize: { width: 340, height: 220 },
  },

  onShow() {
    const session = requirePaperLogin();
    if (!session) {
      this.stopPolling();
      this.setData({ authReady: false, loggedIn: false });
      return;
    }
    this.token = session.token;
    this.setData({ authReady: true, loggedIn: true }, () => {
      this.syncChartSize().finally(() => {
        this.loadPaper(false);
        this.startPolling();
      });
    });
  },

  onHide() {
    this.stopPolling();
  },

  syncChartSize() {
    return new Promise((resolve) => {
      const query = wx.createSelectorQuery().in(this);
      query.select('.asset-chart').boundingClientRect();
      query.select('.kline-chart').boundingClientRect();
      query.exec((rects) => {
        const [assetRect, intradayRect] = rects || [];
        const patch = {};
        if (assetRect && assetRect.width && assetRect.height) {
          patch.assetChartSize = { width: Math.floor(assetRect.width), height: Math.floor(assetRect.height) };
        }
        if (intradayRect && intradayRect.width && intradayRect.height) {
          patch.intradayChartSize = { width: Math.floor(intradayRect.width), height: Math.floor(intradayRect.height) };
        }
        if (Object.keys(patch).length) {
          this.setData(patch, resolve);
        } else {
          resolve();
        }
      });
    });
  },

  onUnload() {
    this.stopPolling();
  },

  onPullDownRefresh() {
    this.loadPaper(true).finally(() => wx.stopPullDownRefresh());
  },

  startPolling() {
    this.stopPolling();
    this.pollTimer = setInterval(() => {
      this.loadPaper(false);
    }, polling.paperMs);
    this.intradayTimer = setInterval(() => {
      if (this.data.selectedCode) this.loadIntraday(this.data.selectedCode, false);
    }, polling.intradayMs);
  },

  stopPolling() {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
    if (this.intradayTimer) {
      clearInterval(this.intradayTimer);
      this.intradayTimer = null;
    }
  },

  async loadPaper(showToast) {
    if (!this.token) return;
    this.setData({ loading: true });
    try {
      const [summaryRes, perfRes, equityRes, watchRes, positionRes, orderRes, tradeRes, flowRes] = await Promise.all([
        api.paperSummary(this.token),
        api.paperPerformanceSummary(this.token),
        api.paperEquity(this.token),
        api.paperWatchlist(this.token),
        api.paperPositions(this.token),
        api.paperOrders(this.token),
        api.paperTrades(this.token),
        api.paperCashFlows(this.token),
      ]);
      const watchlist = (watchRes.items || []).map(decorateWatchItem);
      const selectedCode = this.data.selectedCode || (watchlist[0] && watchlist[0].code) || '';
      this.setData({
        loading: false,
        loggedIn: true,
        summary: decoratePaperSummary(summaryRes),
        performance: {
          totalReturnText: formatPct(perfRes.total_return_pct, 2),
          winRateText: formatPct(perfRes.win_rate_pct, 2),
          realizedText: formatNumber(perfRes.realized_pnl, 2),
          drawdownText: formatPct(perfRes.max_drawdown_pct, 2),
        },
        equity: equityRes.items || [],
        watchlist,
        selectedCode,
        positions: (positionRes.items || []).map(decoratePosition),
        orders: (orderRes.items || []).map(decorateOrder),
        trades: (tradeRes.items || []).map(decorateTrade),
        flows: (flowRes.items || []).map(decorateFlow),
      });
      this.drawAssetChart();
      if (selectedCode) {
        this.loadQuote(selectedCode);
        this.loadIntraday(selectedCode, false);
      }
    } catch (error) {
      this.setData({ loading: false });
      if (error.status === 401) {
        getApp().clearPaperSession();
        this.token = '';
        this.stopPolling();
        this.setData({ authReady: false, loggedIn: false, summary: null });
        goLogin();
      }
      if (showToast) wx.showToast({ title: error.message || '加载失败', icon: 'none' });
    }
  },

  drawAssetChart() {
    const points = (this.data.equity || []).map((item) => ({
      time: item.snapshot_time,
      value: item.total_assets,
    }));
    setTimeout(() => drawLineChart(this, 'assetChart', points, { ...this.data.assetChartSize, color: '#d12f2f' }), 30);
  },

  drawIntradayChart() {
    const trades = (this.data.trades || []).filter((item) => item.code === this.data.selectedCode);
    setTimeout(() => drawKlineChart(this, 'intradayChart', this.data.intraday, trades, this.data.intradayChartSize), 30);
  },

  setAuthMode(event) {
    this.setData({ authMode: event.currentTarget.dataset.mode });
  },

  bindInput(event) {
    const field = event.currentTarget.dataset.field;
    if (field === 'createPhone') {
      this.setData({
        createPhone: event.detail.value,
        createCaptchaId: '',
        createCaptchaPhone: '',
        createCaptchaCode: '',
      });
      return;
    }
    this.setData({ [field]: event.detail.value });
  },

  async loginPaperAccount() {
    const ownerName = this.data.loginOwnerName.trim();
    const password = this.data.loginPassword;
    if (!ownerName || !password) {
      wx.showToast({ title: '请输入账号和密码', icon: 'none' });
      return;
    }
    this.setData({ submitting: true });
    try {
      const result = await api.loginPaperAccount({ owner_name: ownerName, password });
      getApp().setPaperSession(result);
      this.token = result.token;
      this.setData({ submitting: false, loggedIn: true });
      wx.showToast({ title: '已登录', icon: 'success' });
      this.loadPaper(true);
      this.startPolling();
    } catch (error) {
      this.setData({ submitting: false });
      wx.showToast({ title: error.message || '登录失败', icon: 'none' });
    }
  },

  async requestCreateCaptcha() {
    const phone = normalizePhone(this.data.createPhone);
    if (!isReasonablePhone(phone)) {
      wx.showToast({ title: '请输入正确手机号', icon: 'none' });
      return;
    }
    this.setData({ submitting: true });
    try {
      const result = await api.createPaperAccountCaptcha({ phone });
      this.setData({
        createPhone: result.phone,
        createCaptchaId: result.captcha_id,
        createCaptchaPhone: result.phone,
        createCaptchaCode: '',
      });
      wx.showModal({
        title: '模拟验证码',
        content: `手机号：${result.phone}\n验证码：${result.captcha_code}`,
        showCancel: false,
      });
    } catch (error) {
      wx.showToast({ title: error.message || '获取失败', icon: 'none' });
    } finally {
      this.setData({ submitting: false });
    }
  },

  async createPaperAccount() {
    const ownerName = this.data.createOwnerName.trim();
    const password = this.data.createPassword;
    const phone = normalizePhone(this.data.createPhone);
    const captchaCode = String(this.data.createCaptchaCode || '').trim();
    if (!ownerName || password.length < 6) {
      wx.showToast({ title: '账号不能为空，密码至少 6 位', icon: 'none' });
      return;
    }
    if (!isReasonablePhone(phone)) {
      wx.showToast({ title: '请输入正确手机号', icon: 'none' });
      return;
    }
    if (!this.data.createCaptchaId || this.data.createCaptchaPhone !== phone) {
      wx.showToast({ title: '请先获取当前手机号验证码', icon: 'none' });
      return;
    }
    if (!captchaCode) {
      wx.showToast({ title: '请输入验证码', icon: 'none' });
      return;
    }
    this.setData({ submitting: true });
    try {
      await api.createPaperAccount({
        owner_name: ownerName,
        password,
        phone,
        captcha_id: this.data.createCaptchaId,
        captcha_code: captchaCode,
      });
      const result = await api.loginPaperAccount({ owner_name: ownerName, password });
      getApp().setPaperSession(result);
      this.token = result.token;
      this.setData({
        submitting: false,
        loggedIn: true,
        createOwnerName: '',
        createPhone: '',
        createPassword: '',
        createCaptchaId: '',
        createCaptchaPhone: '',
        createCaptchaCode: '',
      });
      wx.showToast({ title: '账户已创建', icon: 'success' });
      this.loadPaper(true);
      this.startPolling();
    } catch (error) {
      this.setData({ submitting: false });
      wx.showToast({ title: error.message || '创建失败', icon: 'none' });
    }
  },

  async logoutPaperAccount() {
    if (this.token) {
      try {
        await api.logoutPaperAccount(this.token);
      } catch (error) {
        // Local logout is still valid if the token has expired.
      }
    }
    getApp().clearPaperSession();
    this.token = '';
    this.stopPolling();
    this.setData({
      loggedIn: false,
      summary: null,
      performance: null,
      watchlist: [],
      positions: [],
      orders: [],
      trades: [],
      flows: [],
      intraday: [],
    });
    goLogin();
  },

  async searchStocks() {
    const keyword = this.data.searchKeyword.trim();
    if (!keyword) return;
    try {
      const result = await api.stocks(keyword);
      this.setData({
        stockCandidates: (result.items || []).slice(0, 8).map((item) => ({
          ...item,
          label: `${item.name} ${item.code}`,
        })),
      });
    } catch (error) {
      wx.showToast({ title: error.message || '搜索失败', icon: 'none' });
    }
  },

  selectCandidate(event) {
    const code = event.currentTarget.dataset.code;
    this.setData({ orderCode: code, searchKeyword: code, stockCandidates: [] });
    this.loadQuote(code);
  },

  async loadQuote(code) {
    const normalized = normalizeCode(code);
    if (!this.token || !normalized) return;
    try {
      const quote = await api.paperQuote(this.token, normalized);
      this.setData({
        quote: {
          ...quote,
          priceText: formatNumber(quote.price, 2),
          limitText: quote.limit_down !== null && quote.limit_down !== undefined && quote.limit_up !== null && quote.limit_up !== undefined
            ? `${formatNumber(quote.limit_down, 2)} - ${formatNumber(quote.limit_up, 2)}`
            : '-',
          signal: quote.strategy_signal || '-',
          signalClass: signalClass(quote.strategy_signal),
        },
      });
    } catch (error) {
      this.setData({ quote: null });
    }
  },

  async loadIntraday(code, collectIfEmpty) {
    const normalized = normalizeCode(code);
    if (!normalized) return;
    try {
      let result = await api.intraday(normalized, 1, 1);
      let bars = latestTradingDayBars(result.items || []);
      if (!bars.length && collectIfEmpty) {
        await api.collectStockIntraday(normalized, 1, 1);
        result = await api.intraday(normalized, 1, 1);
        bars = latestTradingDayBars(result.items || []);
      }
      this.setData({ intraday: bars });
      this.drawIntradayChart();
    } catch (error) {
      this.setData({ intraday: [] });
      this.drawIntradayChart();
    }
  },

  selectWatch(event) {
    const code = event.currentTarget.dataset.code;
    this.setData({ selectedCode: code, orderCode: code, searchKeyword: code });
    this.loadQuote(code);
    this.loadIntraday(code, true);
  },

  async addWatch() {
    const code = normalizeCode(this.data.orderCode || this.data.searchKeyword);
    if (!code) {
      wx.showToast({ title: '请输入股票代码', icon: 'none' });
      return;
    }
    try {
      await api.addPaperWatch(this.token, code);
      wx.showToast({ title: '已加入自选', icon: 'success' });
      this.setData({ selectedCode: code, orderCode: code, searchKeyword: code });
      this.loadPaper(false);
      this.loadIntraday(code, true);
    } catch (error) {
      wx.showToast({ title: error.message || '加入失败', icon: 'none' });
    }
  },

  async removeWatch(event) {
    const code = event.currentTarget.dataset.code;
    try {
      await api.removePaperWatch(this.token, code);
      wx.showToast({ title: '已移出', icon: 'none' });
      this.setData({ selectedCode: '', intraday: [] });
      this.loadPaper(false);
    } catch (error) {
      wx.showToast({ title: error.message || '移出失败', icon: 'none' });
    }
  },

  setOrderSide(event) {
    this.setData({ orderSide: event.currentTarget.dataset.side });
  },

  setOrderType(event) {
    this.setData({ orderType: event.currentTarget.dataset.type });
  },

  async submitOrder() {
    const code = normalizeCode(this.data.orderCode || this.data.searchKeyword || this.data.selectedCode);
    const quantity = Number(this.data.quantity);
    if (!code || !quantity || quantity < 100) {
      wx.showToast({ title: '请输入股票代码和不少于 100 股的数量', icon: 'none' });
      return;
    }
    const payload = {
      code,
      side: this.data.orderSide,
      order_type: this.data.orderType,
      quantity,
      limit_price: null,
      trigger_price: null,
    };
    if (payload.order_type === 'limit') {
      payload.limit_price = Number(this.data.limitPrice);
      if (!payload.limit_price) {
        wx.showToast({ title: '请输入限价', icon: 'none' });
        return;
      }
    }
    if (payload.order_type === 'take_profit' || payload.order_type === 'stop_loss') {
      payload.trigger_price = Number(this.data.triggerPrice);
      if (!payload.trigger_price) {
        wx.showToast({ title: '请输入触发价', icon: 'none' });
        return;
      }
    }

    this.setData({ submitting: true });
    try {
      await api.createPaperOrder(this.token, payload);
      this.setData({ submitting: false, selectedCode: code });
      wx.showToast({ title: '委托已提交', icon: 'success' });
      this.loadPaper(false);
      this.loadIntraday(code, true);
    } catch (error) {
      this.setData({ submitting: false });
      wx.showToast({ title: error.message || '提交失败', icon: 'none' });
    }
  },

  async runMatching() {
    try {
      const result = await api.runPaperMatching(this.token);
      wx.showToast({ title: `成交 ${result.filled || 0} 笔`, icon: 'none' });
      this.loadPaper(false);
    } catch (error) {
      wx.showToast({ title: error.message || '撮合失败', icon: 'none' });
    }
  },

  async cancelOrder(event) {
    const id = event.currentTarget.dataset.id;
    try {
      await api.cancelPaperOrder(this.token, id);
      wx.showToast({ title: '已撤单', icon: 'none' });
      this.loadPaper(false);
    } catch (error) {
      wx.showToast({ title: error.message || '撤单失败', icon: 'none' });
    }
  },

  setRecordTab(event) {
    this.setData({ recordTab: event.currentTarget.dataset.tab });
  },
});
