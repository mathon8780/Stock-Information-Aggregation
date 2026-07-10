const TOKEN_KEY = 'market-agent.paper-trading.token';
const ACCOUNT_KEY = 'market-agent.paper-trading.account';

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

module.exports = {
  getSession,
  saveSession,
  clearSession,
  authHeader,
};
