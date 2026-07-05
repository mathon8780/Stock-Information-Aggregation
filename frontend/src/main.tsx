import React from 'react';
import ReactDOM from 'react-dom/client';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import 'antd/dist/reset.css';
import './styles.css';
import App from './App';
import { createAntdTheme } from './theme/antdTheme';
import { THEME_MODE_STORAGE_KEY, ThemeModeContext, type ThemeMode } from './theme/ThemeModeContext';

function readInitialThemeMode(): ThemeMode {
  const stored = localStorage.getItem(THEME_MODE_STORAGE_KEY);
  return stored === 'dark' ? 'dark' : 'light';
}

function MarketAgentRoot() {
  const [mode, setModeState] = React.useState<ThemeMode>(readInitialThemeMode);

  const setMode = React.useCallback((nextMode: ThemeMode) => {
    setModeState(nextMode);
    localStorage.setItem(THEME_MODE_STORAGE_KEY, nextMode);
    document.documentElement.dataset.theme = nextMode;
  }, []);

  React.useEffect(() => {
    document.documentElement.dataset.theme = mode;
  }, [mode]);

  const theme = React.useMemo(() => createAntdTheme(mode), [mode]);
  const contextValue = React.useMemo(() => ({
    mode,
    setMode,
    toggleMode: () => setMode(mode === 'dark' ? 'light' : 'dark'),
  }), [mode, setMode]);

  return (
    <ThemeModeContext.Provider value={contextValue}>
      <ConfigProvider locale={zhCN} theme={theme}>
        <App />
      </ConfigProvider>
    </ThemeModeContext.Provider>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <MarketAgentRoot />
  </React.StrictMode>,
);
