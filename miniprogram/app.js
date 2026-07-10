const session = require('./services/session');

App({
  globalData: {
    token: '',
    account: null,
  },

  onLaunch() {
    const stored = session.getSession();
    this.globalData.token = stored.token;
    this.globalData.account = stored.account;
  },

  setPaperSession(nextSession) {
    session.saveSession(nextSession);
    this.globalData.token = nextSession.token;
    this.globalData.account = nextSession.account;
  },

  clearPaperSession() {
    session.clearSession();
    this.globalData.token = '';
    this.globalData.account = null;
  },
});
