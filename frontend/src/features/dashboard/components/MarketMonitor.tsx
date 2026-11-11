import { StarFilled, StarOutlined } from '@ant-design/icons';
import { Alert, Button, Empty, Input, Pagination, Popconfirm, Select, Spin, message } from 'antd';
import { useEffect, useMemo, useRef, useState } from 'react';
import { api, formatNumber, formatTime } from '../../../api/client';
import { useBackendEvents } from '../../../hooks/useBackendEvents';
import type { MarketBoard, Snapshot, WatchItem } from '../../../types';

export default function MarketMonitor({
  watchlist,
  selectedCode,
  onSelect,
  onChanged,
  board,
  clearBoard,
}: {
  watchlist: WatchItem[];
  selectedCode: string;
  onSelect: (item: Snapshot) => void;
  onChanged: () => void;
  board: MarketBoard | null;
  clearBoard: () => void;
}) {
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');
  const [descending, setDescending] = useState(true);
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<Snapshot[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [providerState, setProviderState] = useState({ stale: false, fetchedAt: '' });
  const [changing, setChanging] = useState('');
  const [refresh, setRefresh] = useState(0);
  const generation = useRef(0);
  const watched = useMemo(() => new Set(watchlist.map((item) => item.stock.code)), [watchlist]);
  useBackendEvents(['market.updated', 'watchlist.updated'], () => setRefresh((value) => value + 1));
  useEffect(() => {
    setQuery('');
    setPage(1);
    setFilter('all');
  }, [board?.code]);
  useEffect(() => {
    const id = ++generation.current;
    if (filter === 'saved' && !board) return;
    const timer = window.setTimeout(
      async () => {
        setLoading(true);
        setError('');
        try {
          const params = new URLSearchParams({
            page: String(page),
            page_size: '12',
            sort_by: 'change_pct',
            sort_order: descending ? 'desc' : 'asc',
          });
          if (query.trim()) params.set('q', query.trim());
          if (filter === 'up') params.set('change_min', '0.01');
          if (filter === 'down') params.set('change_max', '-0.01');
          const result = board
            ? await api.boardConstituents(board.code, page, descending ? 'desc' : 'asc')
            : await api.market(params);
          if (id !== generation.current) return;
          setItems(result.items);
          setTotal(result.total);
          setProviderState({
            stale: 'stale' in result && result.stale === true,
            fetchedAt: 'fetched_at' in result && typeof result.fetched_at === 'string' ? result.fetched_at : '',
          });
          if ('error' in result && typeof result.error === 'string') setError(result.error);
        } catch (cause) {
          if (id === generation.current) {
            setItems([]);
            setTotal(0);
            setError(cause instanceof Error ? cause.message : '行情读取失败');
          }
        } finally {
          if (id === generation.current) setLoading(false);
        }
      },
      query ? 300 : 0,
    );
    return () => {
      window.clearTimeout(timer);
      generation.current++;
    };
  }, [query, filter, descending, page, refresh, board?.code]);
  const allRows =
    filter === 'saved' && !board
      ? watchlist
          .flatMap((item) => (item.latest_snapshot ? [item.latest_snapshot] : []))
          .filter((item) => `${item.name} ${item.code}`.toLowerCase().includes(query.toLowerCase()))
          .sort((a, b) => ((a.change_pct ?? 0) - (b.change_pct ?? 0)) * (descending ? -1 : 1))
      : items;
  const rows = board
    ? allRows.filter(
        (item) =>
          `${item.name} ${item.code}`.toLowerCase().includes(query.toLowerCase()) &&
          (filter === 'all' ||
            (filter === 'saved'
              ? watched.has(item.code)
              : filter === 'up'
                ? (item.change_pct ?? 0) > 0
                : (item.change_pct ?? 0) < 0)),
      )
    : allRows;
  const toggle = async (item: Snapshot) => {
    setChanging(item.code);
    try {
      watched.has(item.code) ? await api.removeWatch(item.code) : await api.addWatch(item.code);
      onChanged();
      message.success(watched.has(item.code) ? '已移出自选' : '已加入自选');
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : '自选操作失败');
    } finally {
      setChanging('');
    }
  };
  return (
    <section className="quant-panel monitor-panel">
      <div className="quant-panel-head">
        <h2>标的监测</h2>
        <small>{filter === 'saved' && !board ? rows.length : total} 个标的</small>
      </div>
      {board && (
        <div className="monitor-board">
          <span>{board.name}</span>
          <Button type="link" size="small" onClick={clearBoard}>
            退出板块
          </Button>
        </div>
      )}
      <div className="monitor-search">
        <Input
          aria-label="搜索监测标的"
          type="search"
          allowClear
          placeholder={board ? '搜索本页成分股' : '搜索代码或名称'}
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setPage(1);
          }}
        />
        <Select
          aria-label="筛选监测标的"
          size="small"
          value={filter}
          onChange={(value) => {
            setFilter(value);
            setPage(1);
          }}
          options={[
            { label: '全部标的', value: 'all' },
            { label: '我的自选', value: 'saved' },
            { label: '上涨', value: 'up' },
            { label: '下跌', value: 'down' },
          ]}
        />
      </div>
      {error && <Alert message={error} type="warning" />}
      <Spin spinning={loading && (Boolean(board) || filter !== 'saved')}>
        <div className="monitor-table-wrap">
          <table className="monitor-table" aria-label="标的行情">
            <thead>
              <tr>
                <th>股票 / 代码</th>
                <th>现价</th>
                <th aria-sort={descending ? 'descending' : 'ascending'}>
                  <button
                    onClick={() => {
                      setDescending(!descending);
                      setPage(1);
                    }}
                  >
                    涨跌幅 {descending ? '↓' : '↑'}
                  </button>
                </th>
                <th>自选</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((item) => (
                <tr key={item.code} className={selectedCode === item.code ? 'selected' : ''}>
                  <td>
                    <button
                      className="monitor-symbol"
                      aria-label={`查看${item.name}行情`}
                      onClick={() => onSelect(item)}
                    >
                      {item.name}
                      <small>{item.code}</small>
                    </button>
                  </td>
                  <td className="mono">{formatNumber(item.price)}</td>
                  <td
                    className={`mono ${(item.change_pct || 0) > 0 ? 'positive' : (item.change_pct || 0) < 0 ? 'negative' : ''}`}
                  >
                    {item.change_pct != null && item.change_pct > 0 ? '+' : ''}
                    {item.change_pct == null ? '—' : `${formatNumber(item.change_pct)}%`}
                  </td>
                  <td>
                    {watched.has(item.code) ? (
                      <Popconfirm
                        title={`将${item.name}移出自选？`}
                        onConfirm={() => toggle(item)}
                        okText="移出"
                        cancelText="取消"
                      >
                        <Button
                          type="text"
                          size="small"
                          className="monitor-star saved"
                          aria-label={`移出自选：${item.name}`}
                          loading={changing === item.code}
                          icon={<StarFilled />}
                        />
                      </Popconfirm>
                    ) : (
                      <Button
                        type="text"
                        size="small"
                        className="monitor-star"
                        aria-label={`加入自选：${item.name}`}
                        disabled={item.security_type === 'index'}
                        loading={changing === item.code}
                        onClick={() => void toggle(item)}
                        icon={<StarOutlined />}
                      />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!rows.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配的标的" />}
        </div>
      </Spin>
      <div className="monitor-foot">
        {board
          ? `${providerState.stale ? '上次缓存 · ' : ''}搜索与涨跌筛选作用于本页成分股${providerState.fetchedAt ? ` · 读取 ${formatTime(providerState.fetchedAt)}` : ''}`
          : '点击标的切换中央图表；星标管理自选'}
      </div>
      {(board || filter !== 'saved') && total > (board ? 20 : 12) && (
        <Pagination
          size="small"
          showSizeChanger={false}
          simple
          current={page}
          pageSize={board ? 20 : 12}
          total={total}
          onChange={setPage}
        />
      )}
    </section>
  );
}
