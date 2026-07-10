import {
  AlertOutlined,
  BarChartOutlined,
  BellOutlined,
  DashboardOutlined,
  FileTextOutlined,
  FundProjectionScreenOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import type { MenuProps } from 'antd';
import { Link } from 'react-router-dom';

export const menuItems: MenuProps['items'] = [
  { key: '/', icon: <DashboardOutlined />, label: <Link to="/">Dashboard</Link> },
  { key: '/market', icon: <BarChartOutlined />, label: <Link to="/market">Market</Link> },
  { key: '/news', icon: <FileTextOutlined />, label: <Link to="/news">News</Link> },
  { key: '/advice', icon: <AlertOutlined />, label: <Link to="/advice">Advice</Link> },
  { key: '/paper-trading', icon: <FundProjectionScreenOutlined />, label: <Link to="/paper-trading">Transaction</Link> },
  { key: '/notifications', icon: <BellOutlined />, label: <Link to="/notifications">Notifications</Link> },
  { key: '/settings', icon: <SettingOutlined />, label: <Link to="/settings">Settings</Link> },
];

export function selectedMenuKey(pathname: string) {
  if (menuItems?.some((item) => item?.key === pathname)) return pathname;
  if (pathname.startsWith('/stock')) return '/market';
  if (pathname.startsWith('/paper-admin')) return '/paper-trading';
  return '/';
}
