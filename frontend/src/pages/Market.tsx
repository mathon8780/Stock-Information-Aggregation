import { ReloadOutlined } from '@ant-design/icons';
import { Button, Card, Table, message } from 'antd';
import type { TablePaginationConfig } from 'antd/es/table';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import PageHeader from '../components/PageHeader';
import MarketToolbar from '../features/market/components/MarketToolbar';
import { createMarketColumns } from '../features/market/tables/marketColumns';
import { useBackendEvents } from '../hooks/useBackendEvents';
import type { Snapshot } from '../types';

type MarketCacheEntry = {
  items: Snapshot[];
  total: number;
  page: number;
  watchCodes: Set<string>;
};

const marketCache = new Map<string, MarketCacheEntry>();

function cacheKey(page: number, q: string, market?: string) {
  return JSON.stringify({ page, q: q.trim(), market: market ?? '' });
}

export default function Market() {
  const [page, setPage] = useState(1);
  const [q, setQ] = useState('');
  const [market, setMarket] = useState<string | undefined>();
  const initialCache = marketCache.get(cacheKey(1, '', undefined));
  const [loading, setLoading] = useState(!initialCache);
  const [items, setItems] = useState<Snapshot[]>(initialCache?.items ?? []);
  const [total, setTotal] = useState(initialCache?.total ?? 0);
  const [watchCodes, setWatchCodes] = useState<Set<string>>(initialCache?.watchCodes ?? new Set());

  const load = useCallback(async (nextPage = page, showSpinner?: boolean) => {
    const key = cacheKey(nextPage, q, market);
    const cached = marketCache.get(key);
    const shouldShowSpinner = showSpinner ?? !cached;
    if (cached) {
      setItems(cached.items);
      setTotal(cached.total);
      setPage(cached.page);
      setWatchCodes(cached.watchCodes);
    }
    setLoading(shouldShowSpinner);
    try {
      const params = new URLSearchParams({ page: String(nextPage), page_size: '20', sort_by: 'change_pct', sort_order: 'desc' });
      if (q.trim()) params.set('q', q.trim());
      if (market) params.set('market', market);
      const [marketRes, watchRes] = await Promise.all([api.market(params), api.watchlist()]);
      const nextWatchCodes = new Set(watchRes.items.map((item) => item.stock.code));
      setItems(marketRes.items);
      setTotal(marketRes.total);
      setPage(nextPage);
      setWatchCodes(nextWatchCodes);
      marketCache.set(key, { items: marketRes.items, total: marketRes.total, page: nextPage, watchCodes: nextWatchCodes });
    } catch (error) {
      if (shouldShowSpinner) message.error(error instanceof Error ? error.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [market, page, q]);

  useEffect(() => { void load(1); }, []);
  useBackendEvents(['market.updated', 'watchlist.updated'], () => load(page, false));

  const addWatch = async (code: string) => {
    try {
      await api.addWatch(code);
      marketCache.clear();
      message.success('已加入自选股');
      await load(page, true);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '操作失败');
    }
  };

  const columns = useMemo(() => createMarketColumns(watchCodes, addWatch), [watchCodes]);
  const pagination: TablePaginationConfig = { current: page, pageSize: 20, total, showSizeChanger: false, onChange: (next) => load(next) };

  return (
    <>
      <PageHeader
        title="Market"
        description="全市场行情快照、筛选和自选股管理"
        extra={<Button icon={<ReloadOutlined />} onClick={() => load(page, true)}>刷新</Button>}
      />
      <Card className="data-surface">
        <MarketToolbar q={q} market={market} setQ={setQ} setMarket={setMarket} onApply={() => load(1, true)} />
        <Table<Snapshot>
          rowKey="code"
          loading={loading}
          dataSource={items}
          columns={columns}
          pagination={pagination}
          scroll={{ x: 1180 }}
          size="middle"
        />
      </Card>
    </>
  );
}
