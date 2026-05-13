import { ArrowDownOutlined, ArrowUpOutlined } from '@ant-design/icons';
import { Card, Space, Typography } from 'antd';
import { changeColor, formatNumber } from '../api/client';

export default function MetricCard({ title, value, suffix, change, extra }: { title: string; value?: number | string | null; suffix?: string; change?: number | null; extra?: string }) {
  const color = changeColor(change);
  return (
    <Card className="metric-card" size="small">
      <Typography.Text type="secondary" className="metric-title">{title}</Typography.Text>
      <div className="metric-value">{typeof value === 'number' ? formatNumber(value, 2) : value ?? '-'}{suffix ? <span>{suffix}</span> : null}</div>
      <Space size={6} className="metric-change" style={{ color }}>
        {change !== undefined && change !== null ? change >= 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined /> : null}
        {change !== undefined && change !== null ? `${formatNumber(change, 2)}%` : extra || '-'}
      </Space>
    </Card>
  );
}
