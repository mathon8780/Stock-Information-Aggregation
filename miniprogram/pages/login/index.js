const { api, getConfiguredApiBaseUrl, saveApiBaseUrl } = require('../../services/api');
const { getSession, goHome } = require('../../services/session');

Page({
  data: {
    mode: 'login',
    submitting: false,
    loginOwnerName: '',
    loginPassword: '',
    createOwnerName: '',
    createPassword: '',
    apiBaseUrl: getConfiguredApiBaseUrl(),
  },

  onShow() {
    const session = getSession();
    if (session.token) goHome();
  },

  setMode(event) {
    this.setData({ mode: event.currentTarget.dataset.mode });
  },

  bindInput(event) {
    const field = event.currentTarget.dataset.field;
    this.setData({ [field]: event.detail.value });
  },

  saveBackendUrl() {
    const apiBaseUrl = saveApiBaseUrl(this.data.apiBaseUrl);
    this.setData({ apiBaseUrl });
    return apiBaseUrl;
  },

  async checkBackend() {
    this.saveBackendUrl();
    this.setData({ submitting: true });
    try {
      await api.health();
      wx.showToast({ title: '后端连接正常', icon: 'success' });
    } catch (error) {
      wx.showModal({
        title: '后端连接失败',
        content: error.message || '请检查后端 API 地址',
        showCancel: false,
      });
    } finally {
      this.setData({ submitting: false });
    }
  },

  async loginPaperAccount() {
    const ownerName = this.data.loginOwnerName.trim();
    const password = this.data.loginPassword;
    if (!ownerName || !password) {
      wx.showToast({ title: '请输入账号和密码', icon: 'none' });
      return;
    }
    this.saveBackendUrl();
    this.setData({ submitting: true });
    try {
      const result = await api.loginPaperAccount({ owner_name: ownerName, password });
      getApp().setPaperSession(result);
      wx.showToast({ title: '已登录', icon: 'success' });
      goHome();
    } catch (error) {
      wx.showModal({ title: '登录失败', content: error.message || '登录失败', showCancel: false });
    } finally {
      this.setData({ submitting: false });
    }
  },

  async createPaperAccount() {
    const ownerName = this.data.createOwnerName.trim();
    const password = this.data.createPassword;
    if (!ownerName || password.length < 6) {
      wx.showToast({ title: '账号不能为空，密码至少 6 位', icon: 'none' });
      return;
    }
    this.saveBackendUrl();
    this.setData({ submitting: true });
    try {
      await api.createPaperAccount({ owner_name: ownerName, password });
      const result = await api.loginPaperAccount({ owner_name: ownerName, password });
      getApp().setPaperSession(result);
      wx.showToast({ title: '账户已创建', icon: 'success' });
      goHome();
    } catch (error) {
      wx.showModal({ title: '创建失败', content: error.message || '创建失败', showCancel: false });
    } finally {
      this.setData({ submitting: false });
    }
  },
});
