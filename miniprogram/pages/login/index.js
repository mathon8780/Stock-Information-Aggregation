const { api, getConfiguredApiBaseUrl, saveApiBaseUrl } = require('../../services/api');
const { getSession, goHome } = require('../../services/session');

function normalizePhone(value) {
  return String(value || '').replace(/\D/g, '');
}

function isReasonablePhone(value) {
  return /^1[3-9]\d{9}$/.test(normalizePhone(value));
}

Page({
  data: {
    mode: 'login',
    submitting: false,
    loginOwnerName: '',
    loginPassword: '',
    createOwnerName: '',
    createPhone: '',
    createPassword: '',
    createCaptchaId: '',
    createCaptchaPhone: '',
    createCaptchaCode: '',
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

  async requestCreateCaptcha() {
    const phone = normalizePhone(this.data.createPhone);
    if (!isReasonablePhone(phone)) {
      wx.showToast({ title: '请输入正确手机号', icon: 'none' });
      return;
    }
    this.saveBackendUrl();
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
      wx.showModal({ title: '获取失败', content: error.message || '获取验证码失败', showCancel: false });
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
    this.saveBackendUrl();
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
      wx.showToast({ title: '账户已创建', icon: 'success' });
      goHome();
    } catch (error) {
      wx.showModal({ title: '创建失败', content: error.message || '创建失败', showCancel: false });
    } finally {
      this.setData({ submitting: false });
    }
  },
});
