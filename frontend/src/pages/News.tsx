import { ReloadOutlined } from '@ant-design/icons';
import { Button, Card, Empty, Space, Table, Typography, message } from 'antd';
import { useEffect, useState } from 'react';
import { api, formatTime } from '../api/client';
import PageHeader from '../components/PageHeader';
import NewsToolbar from '../features/news/NewsToolbar';
import { newsColumns } from '../features/news/newsColumns';
import type { NewsItem } from '../types';

export default function News() {
  const [items, setItems] = useState<NewsItem[]>([]);
  const [scope, setScope] = useState<string | undefined>();
  const [sentiment, setSentiment] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: '100' });
      if (scope) params.set('scope', scope);
      if (sentiment) params.set('sentiment', sentiment);
      const response = await api.news(params);
      setItems(response.items);
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
        title="News"
        description="NewsNow 真实新闻源，配置的 LLM 整理后入库"
        extra={<Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>}
      />
      <Card className="table-card">
        <NewsToolbar scope={scope} sentiment={sentiment} setScope={setScope} setSentiment={setSentiment} onApply={load} />
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
                <Typography.Text>{row.content || row.summary || row.title}</Typography.Text>
                <Typography.Text type="secondary">
                  {row.source} · {formatTime(row.published_at)}
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
