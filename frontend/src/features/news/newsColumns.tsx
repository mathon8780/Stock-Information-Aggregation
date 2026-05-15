import { LinkOutlined } from '@ant-design/icons';
import { Button, Space, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { formatTime } from '../../api/client';
import SentimentTag from '../../components/SentimentTag';
import StockLink from '../../components/StockLink';
import type { NewsItem } from '../../types';

function statusTag(status: NewsItem['simplification_status']) {
  const map = {
    simplified: { color: 'green', label: '已简化' },
    pending: { color: 'gold', label: '待处理' },
    failed: { color: 'red', label: '失败' },
  } as const;
  const item = map[status] ?? map.pending;
  return <Tag color={item.color}>{item.label}</Tag>;
}

export const newsColumns: ColumnsType<NewsItem> = [
  { title: '标题', render: (_: unknown, row: NewsItem) => <Space direction="vertical" size={2}><span>{row.title}</span><span className="muted">{row.summary}</span></Space> },
  { title: '标的', width: 150, render: (_: unknown, row: NewsItem) => row.code ? <StockLink code={row.code} name={row.name} /> : <Tag>市场</Tag> },
  { title: '处理', width: 100, render: (_: unknown, row: NewsItem) => statusTag(row.simplification_status) },
  { title: '范围', width: 90, dataIndex: 'scope', render: (value: string) => <Tag>{value}</Tag> },
  { title: '情绪', width: 90, dataIndex: 'sentiment', render: (value: string) => <SentimentTag sentiment={value} /> },
  { title: '重要性', width: 90, dataIndex: 'importance', render: (value: number) => <Tag color={value >= 4 ? 'orange' : 'default'}>{value}</Tag> },
  { title: '来源', width: 130, dataIndex: 'source' },
  { title: '发布时间', width: 180, render: (_: unknown, row: NewsItem) => formatTime(row.published_at) },
  { title: '简化时间', width: 180, render: (_: unknown, row: NewsItem) => formatTime(row.simplified_at) },
  { title: '原文', width: 90, render: (_: unknown, row: NewsItem) => row.url ? <Button size="small" icon={<LinkOutlined />} href={row.url} target="_blank" rel="noreferrer" /> : '-' },
];
