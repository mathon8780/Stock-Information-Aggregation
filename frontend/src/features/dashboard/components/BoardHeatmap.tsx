import { Alert, Button, Empty, Segmented, Spin } from 'antd';
import { useEffect, useRef, useState } from 'react';
import { api, ApiError, formatNumber, formatTime } from '../../../api/client';
import type { BoardKind, BoardResult, MarketBoard } from '../../../types';

export default function BoardHeatmap({
  selected,
  onSelect,
  refreshKey = 0,
}: {
  refreshKey?: number;
  selected: string | undefined;
  onSelect: (board: MarketBoard) => void;
}) {
  const [kind, setKind] = useState<BoardKind>('industry');
  const [result, setResult] = useState<BoardResult<MarketBoard> | null>(null);
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  const generation = useRef(0);
  useEffect(() => {
    const id = ++generation.current;
    setLoading(true);
    setResult(null);
    api
      .boards(kind)
      .then((value) => {
        if (id === generation.current) setResult(value);
      })
      .catch((cause) => {
        if (id === generation.current)
          setResult({
            items: [],
            total: 0,
            source: 'eastmoney',
            fetched_at: null,
            stale: false,
            error:
              cause instanceof ApiError && cause.status === 404
                ? '板块接口尚未加载，请在数据导入结束后重新加载后端服务。'
                : '板块数据读取失败，请稍后重试。',
          });
      })
      .finally(() => {
        if (id === generation.current) setLoading(false);
      });
    return () => {
      generation.current++;
    };
  }, [kind, retry, refreshKey]);
  return (
    <section className="quant-panel board-panel">
      <div className="quant-panel-head">
        <h2>板块温度</h2>
        <Segmented
          size="small"
          aria-label="板块类别"
          value={kind}
          onChange={(value) => setKind(value as BoardKind)}
          options={[
            { label: '行业', value: 'industry' },
            { label: '概念', value: 'concept' },
          ]}
        />
      </div>
      {result?.error && <Alert message={result.error} type="warning" />}
      <Spin spinning={loading}>
        <div className="board-heatmap">
          {result?.items.map((board) => (
            <button
              key={board.code}
              className={`heat-cell ${(board.change_pct || 0) < 0 ? 'falling' : (board.change_pct || 0) > 0 ? 'rising' : 'flat'} ${selected === board.code ? 'selected' : ''}`}
              aria-pressed={selected === board.code}
              onClick={() => onSelect(board)}
            >
              <span>{board.name}</span>
              <strong>
                {board.change_pct != null && board.change_pct > 0 ? '+' : ''}
                {formatNumber(board.change_pct)}%
              </strong>
              <small>
                {board.up_count ?? '—'} 涨 / {board.down_count ?? '—'} 跌
              </small>
            </button>
          ))}
        </div>
        {!loading && !result?.items.length && (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无板块行情">
            <Button size="small" onClick={() => setRetry((value) => value + 1)}>
              重试
            </Button>
          </Empty>
        )}
      </Spin>
      <div className="board-foot">
        {result?.stale ? '上次缓存 · ' : ''}领涨 / 领跌各 4 个 · 东方财富
        {result?.items[0]?.quote_time ? (
          <small>行情 {formatTime(result.items[0].quote_time)}</small>
        ) : result?.fetched_at ? (
          <small>读取 {formatTime(result.fetched_at)}</small>
        ) : null}
      </div>
    </section>
  );
}
