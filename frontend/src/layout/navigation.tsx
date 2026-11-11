export const pageNavigation = [
  { path: '/', label: '工作概览' },
  { path: '/market', label: '市场行情' },
  { path: '/news', label: '新闻资讯' },
  { path: '/advice', label: '策略观察' },
  { path: '/paper-trading', label: '模拟交易' },
  { path: '/notifications', label: '通知中心' },
  { path: '/settings', label: '系统设置' },
];

export function selectedMenuKey(pathname: string) {
  if (pageNavigation.some((item) => item.path === pathname)) return pathname;
  if (pathname.startsWith('/stock')) return '/market';
  if (pathname.startsWith('/paper-admin')) return '/paper-trading';
  return '/';
}
