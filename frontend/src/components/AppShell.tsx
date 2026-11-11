import { LineChartOutlined } from '@ant-design/icons';
import { Layout, Switch } from 'antd';
import { Link, Outlet, useLocation } from 'react-router-dom';
import { pageNavigation, selectedMenuKey } from '../layout/navigation';
import { useThemeMode } from '../theme/ThemeModeContext';

export default function AppShell() {
  const selected = selectedMenuKey(useLocation().pathname);
  const { mode, setMode } = useThemeMode();
  return (
    <Layout className="app-shell quant-app-shell">
      <header className="quant-topbar">
        <Link to="/" className="quant-brand">
          <span className="quant-brand-mark">
            <LineChartOutlined />
          </span>
          <span>
            <strong>Market Agent</strong>
            <small>本地证券监控</small>
          </span>
        </Link>
        <nav className="quant-navigation" aria-label="主要页面">
          {pageNavigation.map((item) => (
            <Link
              key={item.path}
              to={item.path}
              className={selected === item.path ? 'active' : ''}
              aria-current={selected === item.path ? 'page' : undefined}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="quant-header-tools">
          <span>本地工作区</span>
          <Switch
            aria-label="切换暗黑模式"
            checked={mode === 'dark'}
            checkedChildren="暗"
            unCheckedChildren="亮"
            onChange={(checked) => setMode(checked ? 'dark' : 'light')}
          />
        </div>
      </header>
      <Layout.Content className="app-content">
        <Outlet />
      </Layout.Content>
      <footer className="quant-footer">
        <span>Market Agent / 市场监视与策略研究</span>
        <span>行情以记录时间为准</span>
      </footer>
    </Layout>
  );
}
