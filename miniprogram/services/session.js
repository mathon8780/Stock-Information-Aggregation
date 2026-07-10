const TOKEN_KEY = 'market-agent.paper-trading.token';
const ACCOUNT_KEY = 'market-agent.paper-trading.account';
const LOGIN_PAGE = '/pages/login/index';
const HOME_PAGE = '/pages/dashboard/index';

function getSession() {
  return {
    token: wx.getStorageSync(TOKEN_KEY) || '',
    account: wx.getStorageSync(ACCOUNT_KEY) || null,
  };
}

function saveSession(session) {
  wx.setStorageSync(TOKEN_KEY, session.token || '');
  wx.setStorageSync(ACCOUNT_KEY, session.account || null);
}

function clearSession() {
  wx.removeStorageSync(TOKEN_KEY);
  wx.removeStorageSync(ACCOUNT_KEY);
}

function authHeader(token) {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function currentRoute() {
  const pages = typeof getCurrentPages === 'function' ? getCurrentPages() : [];
  const current = pages[pages.length - 1];
  return current ? current.route : '';
}

function goLogin() {
  if (currentRoute() === 'pages/login/index') return;
  wx.reLaunch({ url: LOGIN_PAGE });
}

function goHome() {
  wx.switchTab({ url: HOME_PAGE });
}

function requirePaperLogin() {
  const session = getSession();
  if (session.token) return session;
  goLogin();
  return null;
}

module.exports = {
  getSession,
  saveSession,
  clearSession,
  authHeader,
  goHome,
  goLogin,
  requirePaperLogin,
};
