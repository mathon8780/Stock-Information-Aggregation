import { Space, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { formatTime } from '../../api/client';
import type { NotificationItem } from '../../types';

export const notificationColumns: ColumnsType<NotificationItem> = [
  { title: '类型', dataIndex: 'notification_type', width: 150, render: (value: string) => <Tag>{value}</Tag> },
  {
    title: '内容',
    render: (_: unknown, row: NotificationItem) => (
      <Space direction="vertical" size={2}>
        <Typography.Text strong>{row.title}</Typography.Text>
        <Typography.Text type="secondary">{row.content}</Typography.Text>
      </Space>
    ),
  },
  { title: '目标', dataIndex: 'target_channel', width: 180 },
  { title: '状态', dataIndex: 'status', width: 110, render: (value: string) => <Tag color={value === 'sent' ? 'green' : value === 'failed' ? 'red' : 'orange'}>{value}</Tag> },
  { title: '重试', dataIndex: 'retry_count', width: 80 },
  { title: '创建时间', width: 180, render: (_: unknown, row: NotificationItem) => formatTime(row.created_at) },
  { title: '发送时间', width: 180, render: (_: unknown, row: NotificationItem) => formatTime(row.sent_at) },
];
