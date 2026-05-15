import { ReloadOutlined } from '@ant-design/icons';
import { Button, Card, Empty, Space, Table, Typography, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { api, formatTime } from '../api/client';
import PageHeader from '../components/PageHeader';
import NewsToolbar from '../features/news/NewsToolbar';
import { newsColumns } from '../features/news/newsColumns';
import { useBackendEvents } from '../hooks/useBackendEvents';
import type { NewsItem } from '../types';

export default function News() {
  const [items, setItems] = useState<NewsItem[]>([]);
  const [scope, setScope] = useState<string | undefined>();
  const [sentiment, setSentiment] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (showSpinner = true) => {
    if (showSpinner) setLoading(true);
    try {
      const params = new URLSearchParams({ limit: '100' });
      if (scope) params.set('scope', scope);
      if (sentiment) params.set('sentiment', sentiment);
      const response = await api.news(params);
      setItems(response.items);
    } catch (error) {
      if (showSpinner) message.error(error instanceof Error ? error.message : '加载失败');
    } finally {
      if (showSpinner) setLoading(false);
    }
  }, [scope, sentiment]);

  useEffect(() => { void load(); }, []);
  useBackendEvents(['news.updated'], () => load(false));

  return (
    <>
      <PageHeader
        title="News"
        description="NewsNow 真实新闻源，配置的 LLM 整理后入库"
        extra={<Button icon={<ReloadOutlined />} onClick={() => load(true)}>刷新</Button>}
      />
      <Card className="table-card">
        <NewsToolbar scope={scope} sentiment={sentiment} setScope={setScope} setSentiment={setSentiment} onApply={() => load(true)} />
        <Table<NewsItem>
          rowKey="id"
          loading={loading}
          dataSource={items}
          columns={newsColumns}
          pagination={{ pageSize: 12 }}
          locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无新闻数据" /> }}
          expandable={{
            expandedRowRender: (row) => (
              <Space direction="vertical" size={8} style={{ maxWidth: 920 }}>
                <Typography.Text>{row.content || row.summary || (row.simplification_status === 'pending' ? '新闻已保存元数据，等待 LLM 简化。' : row.title)}</Typography.Text>
                {row.error_message ? <Typography.Text type="danger">{row.error_message}</Typography.Text> : null}
                <Typography.Text type="secondary">
                  {row.source} · {formatTime(row.published_at)}
                  {row.simplified_at ? <> · 简化于 {formatTime(row.simplified_at)}</> : null}
                  {row.llm_model ? <> · {row.llm_provider}/{row.llm_model}</> : null}
                  {row.url ? <> · <a href={row.url} target="_blank" rel="noreferrer">原文地址</a></> : null}
                </Typography.Text>
              </Space>
            ),
          }}
        />
      </Card>
    </>
  );
}
