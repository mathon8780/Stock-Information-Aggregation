import { ReloadOutlined } from '@ant-design/icons';
import { Button, Card, Table, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import PageHeader from '../components/PageHeader';
import NotificationsToolbar from '../features/notifications/NotificationsToolbar';
import { notificationColumns } from '../features/notifications/notificationColumns';
import { useBackendEvents } from '../hooks/useBackendEvents';
import type { NotificationItem } from '../types';

export default function Notifications() {
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [status, setStatus] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (showSpinner = true) => {
    if (showSpinner) setLoading(true);
    try {
      setItems((await api.notifications(status)).items);
    } catch (error) {
      if (showSpinner) message.error(error instanceof Error ? error.message : '加载失败');
    } finally {
      if (showSpinner) setLoading(false);
    }
  }, [status]);

  useEffect(() => { void load(); }, []);
  useBackendEvents(['notifications.updated'], () => load(false));

  return (
    <>
      <PageHeader
        title="Notifications"
        description="策略、新闻、重大事件和行情异动通知记录"
        extra={<Button icon={<ReloadOutlined />} onClick={() => load(true)}>刷新</Button>}
      />
      <Card className="data-surface">
        <NotificationsToolbar status={status} setStatus={setStatus} onApply={() => load(true)} />
        <Table<NotificationItem> rowKey="id" loading={loading} dataSource={items} columns={notificationColumns} pagination={{ pageSize: 10 }} />
      </Card>
    </>
  );
}
