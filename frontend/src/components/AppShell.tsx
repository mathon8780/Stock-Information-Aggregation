import { LineChartOutlined } from '@ant-design/icons';
import { Layout, Menu, Switch, Tooltip, Typography } from 'antd';
import { Outlet, useLocation } from 'react-router-dom';
import { menuItems, selectedMenuKey } from '../layout/navigation';
import { useThemeMode } from '../theme/ThemeModeContext';

const { Sider, Content } = Layout;

export default function AppShell() {
  const location = useLocation();
  const selected = selectedMenuKey(location.pathname);
  const { mode, setMode } = useThemeMode();
  return (
    <Layout className="app-shell">
      <Sider width={224} className="app-sider">
        <div className="brand">
          <LineChartOutlined />
          <div><Typography.Text strong>Market Agent</Typography.Text><span>本地证券监控</span></div>
        </div>
        <Menu theme="dark" mode="inline" selectedKeys={[selected]} items={menuItems} />
        <div className="sider-footer">
          <Tooltip title="切换暗黑模式" placement="right">
            <Switch
              aria-label="切换暗黑模式"
              checked={mode === 'dark'}
              checkedChildren="暗"
              unCheckedChildren="亮"
              onChange={(checked) => setMode(checked ? 'dark' : 'light')}
            />
          </Tooltip>
        </div>
      </Sider>
      <Layout>
        <Content className="app-content"><Outlet /></Content>
      </Layout>
    </Layout>
  );
}
