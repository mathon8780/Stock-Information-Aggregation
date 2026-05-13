import { Progress, Space, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { formatTime } from '../../api/client';
import SignalTag from '../../components/SignalTag';
import StockLink from '../../components/StockLink';
import type { Advice } from '../../types';

export const adviceColumns: ColumnsType<Advice> = [
  { title: '股票', width: 150, render: (_: unknown, row: Advice) => row.code ? <StockLink code={row.code} name={row.name} /> : '-' },
  { title: '策略', width: 110, dataIndex: 'signal', render: (value: string) => <SignalTag signal={value} /> },
  { title: '置信度', width: 160, dataIndex: 'confidence', render: (value: number) => <Progress percent={Math.round(value)} size="small" /> },
  {
    title: '理由',
    render: (_: unknown, row: Advice) => (
      <Space direction="vertical" size={2}>
        <Typography.Text>{row.reasoning}</Typography.Text>
        <Typography.Text type="secondary">{row.strategy}</Typography.Text>
      </Space>
    ),
  },
  { title: '生成时间', width: 180, render: (_: unknown, row: Advice) => formatTime(row.created_at) },
];
