import { LineChartOutlined } from '@ant-design/icons';
import { Layout, Menu, Typography } from 'antd';
import { Outlet, useLocation } from 'react-router-dom';
import { menuItems, selectedMenuKey } from '../layout/navigation';

const { Header, Sider, Content } = Layout;

export default function AppShell() {
  const location = useLocation();
  const selected = selectedMenuKey(location.pathname);
  return (
    <Layout className="app-shell">
      <Sider width={224} className="app-sider">
        <div className="brand">
          <LineChartOutlined />
          <div><Typography.Text strong>Market Agent</Typography.Text><span>本地证券监控</span></div>
        </div>
        <Menu theme="dark" mode="inline" selectedKeys={[selected]} items={menuItems} />
      </Sider>
      <Layout>
        <Header className="app-header">
          <div>
            <Typography.Text strong>智能证券市场监视、提醒与策略建议系统</Typography.Text>
            <Typography.Text type="secondary">HTTP 轮询 · 本地规则引擎 · OpenClaw 编排</Typography.Text>
          </div>
          <span className="header-status">Local MVP</span>
        </Header>
        <Content className="app-content"><Outlet /></Content>
      </Layout>
    </Layout>
  );
}
