import { ReloadOutlined } from '@ant-design/icons';
import { Button, Card, Input, Pagination, Spin, message } from 'antd';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import PageHeader from '../components/PageHeader';
import NewsToolbar from '../features/news/NewsToolbar';
import NewsReader from '../features/news/NewsReader';
import { useBackendEvents } from '../hooks/useBackendEvents';
import type { NewsItem } from '../types';

export default function News() {
  const [items, setItems] = useState<NewsItem[]>([]);
  const [scope, setScope] = useState<string>();
  const [sentiment, setSentiment] = useState<string>();
  const [applied, setApplied] = useState<{ scope?: string; sentiment?: string }>({});
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const generation = useRef(0);
  const load = useCallback(
    async (showSpinner = true) => {
      const id = ++generation.current;
      if (showSpinner) setLoading(true);
      try {
        const params = new URLSearchParams({ limit: '100' });
        if (applied.scope) params.set('scope', applied.scope);
        if (applied.sentiment) params.set('sentiment', applied.sentiment);
        const result = await api.news(params);
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
  useBackendEvents(['news.updated'], () => load(false));
  const filtered = items.filter((item) =>
    `${item.title} ${item.original_title || ''} ${item.summary || ''}`.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <>
      <PageHeader
        title="新闻资讯"
        description="阅读市场与个股动态，查看来源和摘要整理状态"
        extra={
          <Button icon={<ReloadOutlined />} onClick={() => void load()}>
            刷新
          </Button>
        }
      />
      <Card className="data-surface">
        <div className="reading-toolbar">
          <NewsToolbar
            scope={scope}
            sentiment={sentiment}
            setScope={setScope}
            setSentiment={setSentiment}
            onApply={() => {
              if (applied.scope === scope && applied.sentiment === sentiment) void load();
              else setApplied({ scope, sentiment });
            }}
          />
          <Input
            type="search"
            aria-label="搜索已读取资讯"
            placeholder="搜索已读取资讯"
            value={query}
            allowClear
            onChange={(event) => {
              setQuery(event.target.value);
              setPage(1);
            }}
          />
        </div>
        <p className="muted">
          最近读取 {items.length} 条 · 匹配 {filtered.length} 条
        </p>
        <Spin spinning={loading}>
          <NewsReader items={filtered.slice((page - 1) * 12, page * 12)} />
        </Spin>
        <Pagination current={page} pageSize={12} total={filtered.length} showSizeChanger={false} onChange={setPage} />
      </Card>
    </>
  );
}
