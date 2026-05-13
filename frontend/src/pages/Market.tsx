import { ReloadOutlined } from '@ant-design/icons';
import { Button, Card, Table, message } from 'antd';
import type { TablePaginationConfig } from 'antd/es/table';
import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import PageHeader from '../components/PageHeader';
import MarketToolbar from '../features/market/components/MarketToolbar';
import { createMarketColumns } from '../features/market/tables/marketColumns';
import type { Snapshot } from '../types';

export default function Market() {
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<Snapshot[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState('');
  const [market, setMarket] = useState<string | undefined>();
  const [watchCodes, setWatchCodes] = useState<Set<string>>(new Set());

  const load = async (nextPage = page) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(nextPage), page_size: '20', sort_by: 'change_pct', sort_order: 'desc' });
      if (q.trim()) params.set('q', q.trim());
      if (market) params.set('market', market);
      const [marketRes, watchRes] = await Promise.all([api.market(params), api.watchlist()]);
      setItems(marketRes.items);
      setTotal(marketRes.total);
      setPage(nextPage);
      setWatchCodes(new Set(watchRes.items.map((item) => item.stock.code)));
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(1); }, []);

  const addWatch = async (code: string) => {
    try {
      await api.addWatch(code);
      message.success('已加入自选股');
      await load(page);
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
        extra={<Button icon={<ReloadOutlined />} onClick={() => load(page)}>刷新</Button>}
      />
      <Card className="data-surface">
        <MarketToolbar q={q} market={market} setQ={setQ} setMarket={setMarket} onApply={() => load(1)} />
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
