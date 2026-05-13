import { ReloadOutlined } from '@ant-design/icons';
import { Button, Card, Table, message } from 'antd';
import { useEffect, useState } from 'react';
import { api } from '../api/client';
import PageHeader from '../components/PageHeader';
import NotificationsToolbar from '../features/notifications/NotificationsToolbar';
import { notificationColumns } from '../features/notifications/notificationColumns';
import type { NotificationItem } from '../types';

export default function Notifications() {
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [status, setStatus] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      setItems((await api.notifications(status)).items);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  return (
    <>
      <PageHeader
        title="Notifications"
        description="QQBot 推送任务、发送结果和失败重试记录"
        extra={<Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>}
      />
      <Card className="data-surface">
        <NotificationsToolbar status={status} setStatus={setStatus} onApply={load} />
        <Table<NotificationItem> rowKey="id" loading={loading} dataSource={items} columns={notificationColumns} pagination={{ pageSize: 10 }} />
      </Card>
    </>
  );
}
