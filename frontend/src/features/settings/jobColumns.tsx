import { Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { formatTime } from '../../api/client';
import type { CollectionJob } from '../../types';

export const jobColumns: ColumnsType<CollectionJob> = [
  { title: '任务', dataIndex: 'job_type', width: 150 },
  { title: '状态', dataIndex: 'status', width: 100, render: (value: string) => <Tag color={value === 'success' ? 'green' : 'orange'}>{value}</Tag> },
  { title: '来源', dataIndex: 'source', width: 100 },
  { title: '结果', render: (_: unknown, row: CollectionJob) => <Typography.Text code>{JSON.stringify(row.result_summary ?? {})}</Typography.Text> },
  { title: '开始时间', width: 180, render: (_: unknown, row: CollectionJob) => formatTime(row.started_at) },
];
