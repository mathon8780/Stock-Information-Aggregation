import { ReloadOutlined } from '@ant-design/icons';
import { Button, Card, Empty, Modal, Pagination, Spin, Tag, message } from 'antd';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api, formatTime } from '../api/client';
import PageHeader from '../components/PageHeader';
import NotificationsToolbar from '../features/notifications/NotificationsToolbar';
import { useBackendEvents } from '../hooks/useBackendEvents';
import type { NotificationItem } from '../types';

const statusLabels: Record<string, string> = {
  sent: '已发送',
  failed: '发送失败',
  pending: '待发送',
  skipped: '已跳过',
};
export default function Notifications() {
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [notificationType, setNotificationType] = useState<string>();
  const [applied, setApplied] = useState<string>();
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<NotificationItem | null>(null);
  const [loading, setLoading] = useState(false);
  const generation = useRef(0);
  const load = useCallback(
    async (showSpinner = true) => {
      const id = ++generation.current;
      if (showSpinner) setLoading(true);
      try {
        const result = await api.notifications(applied);
        if (id === generation.current) {
          setItems(result.items);
          setPage(1);
        }
      } catch (error) {
        if (id === generation.current) message.error(error instanceof Error ? error.message : '加载失败');
      } finally {
        if (id === generation.current) setLoading(false);
      }
    },
    [applied],
  );
  useEffect(() => {
    void load();
    return () => {
      generation.current++;
    };
  }, [load]);
  useBackendEvents(['notifications.updated'], () => load(false));
  return (
    <>
      <PageHeader
        title="通知中心"
        description="查看策略、资讯、行情异动与模拟交易的推送记录"
        extra={
          <Button icon={<ReloadOutlined />} onClick={() => void load()}>
            刷新
          </Button>
        }
      />
      <Card className="data-surface">
        <NotificationsToolbar
          notificationType={notificationType}
          setNotificationType={setNotificationType}
          onApply={() => {
            setPage(1);
            if (applied === notificationType) void load();
            else setApplied(notificationType);
          }}
        />
        <p className="muted">最近读取 {items.length} 条通知</p>
        <Spin spinning={loading}>
          <div className="notification-list">
            {items.slice((page - 1) * 10, page * 10).map((item) => (
              <article key={item.id} className="notification-item">
                <div className={`notification-state ${item.status}`} />
                <div className="notification-copy">
                  <div className="news-reading-meta">
                    <Tag>{item.notification_type}</Tag>
                    <time>{formatTime(item.created_at)}</time>
                  </div>
                  <button className="news-reading-title" onClick={() => setSelected(item)}>
                    {item.title}
                  </button>
                  <p>{item.content}</p>
                  <small className="muted">
                    {item.target_channel} · 重试 {item.retry_count} 次{' '}
                    {item.sent_at ? `· 发送于 ${formatTime(item.sent_at)}` : ''}
                  </small>
                  {item.error_message && <p className="positive">{item.error_message}</p>}
                </div>
                <Tag color={item.status === 'sent' ? 'green' : item.status === 'failed' ? 'red' : 'default'}>
                  {statusLabels[item.status] || item.status}
                </Tag>
              </article>
            ))}
          </div>
          {!items.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无通知记录" />}
        </Spin>
        <Pagination current={page} pageSize={10} total={items.length} showSizeChanger={false} onChange={setPage} />
      </Card>
      <Modal
        title={selected?.title || '通知详情'}
        open={Boolean(selected)}
        onCancel={() => setSelected(null)}
        footer={<Button onClick={() => setSelected(null)}>关闭</Button>}
      >
        <p className="news-detail-copy">{selected?.content}</p>
        {selected?.error_message && <p className="positive">{selected.error_message}</p>}
        {selected?.payload && (
          <details>
            <summary>查看通知数据</summary>
            <pre className="record-json">{JSON.stringify(selected.payload, null, 2)}</pre>
          </details>
        )}
      </Modal>
    </>
  );
}
