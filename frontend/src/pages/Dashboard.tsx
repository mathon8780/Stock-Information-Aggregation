import { DatabaseOutlined, ReloadOutlined } from '@ant-design/icons';
import { Alert, Button, Empty, Spin, Tabs } from 'antd';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api, formatNumber, formatTime } from '../api/client';
import PageHeader from '../components/PageHeader';
import RankingTables from '../features/dashboard/components/RankingTables';
import WatchlistOverview from '../features/dashboard/components/WatchlistOverview';
import FocusChart from '../features/dashboard/components/FocusChart';
import MarketMonitor from '../features/dashboard/components/MarketMonitor';
import BoardHeatmap from '../features/dashboard/components/BoardHeatmap';
import AdviceCards from '../features/advice/AdviceCards';
import NewsReader from '../features/news/NewsReader';
import { signalCounts, signalOrder } from '../features/dashboard/dashboardData';
import { useDashboardData } from '../features/dashboard/useDashboardData';
import type { MarketBoard, Snapshot } from '../types';

export default function Dashboard() {
  const data = useDashboardData();
  const [focused, setFocused] = useState<Snapshot | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [board, setBoard] = useState<MarketBoard | null>(null);
  const [collecting, setCollecting] = useState(false);
  const [taskMessage, setTaskMessage] = useState('');
  const order = ['000001.SH', '399001.SZ', '399006.SZ', '000300.SH', '000905.SH'];
  const indices = data.market
    .filter((item) => item.security_type === 'index')
    .sort((a, b) => order.indexOf(a.code) - order.indexOf(b.code))
    .slice(0, 5);
  const fallback = data.watchlist.find((item) => item.latest_snapshot)?.latest_snapshot || indices[0] || data.market[0];
  const selected = focused
    ? data.watchlist.find((item) => item.stock.code === focused.code)?.latest_snapshot ||
      data.market.find((item) => item.code === focused.code) ||
      focused
    : fallback;
  const advices = data.watchlist.flatMap((item) => (item.latest_advice ? [item.latest_advice] : []));
  const advice = advices.find(
    (item) => item.code === selected?.code || (item.stock_id === selected?.stock_id && selected?.stock_id !== 0),
  );
  const counts = signalCounts(advices);
  const quoted = data.watchlist.flatMap((item) =>
    item.latest_snapshot?.change_pct != null ? [item.latest_snapshot.change_pct] : [],
  );
  const average = quoted.length ? quoted.reduce((a, b) => a + b, 0) / quoted.length : null;
  const ratio =
    data.upTotal != null && data.downTotal != null && data.upTotal + data.downTotal
      ? (data.upTotal / (data.upTotal + data.downTotal)) * 100
      : null;
  const pct = (value: number | null | undefined) =>
    value == null ? '—' : `${value > 0 ? '+' : ''}${formatNumber(value)}%`;
  const collect = async () => {
    setCollecting(true);
    try {
      const result = await api.collectMissingDailyKline();
      setTaskMessage(result.status === 'already_running' ? '缺失日 K 补齐任务已在运行' : '缺失日 K 补齐任务已启动');
      await data.load(false);
    } catch (error) {
      setTaskMessage(error instanceof Error ? error.message : '任务启动失败');
    } finally {
      setCollecting(false);
    }
  };
  return (
    <div className="quant-dashboard">
      <PageHeader
        title="市场总览"
        description={indices[0] ? `行情 ${formatTime(indices[0].snapshot_time)}` : '等待行情数据'}
        extra={
          <>
            <Button icon={<DatabaseOutlined />} loading={collecting} onClick={() => void collect()}>
              补全缺失日 K
            </Button>
            <Button
              icon={<ReloadOutlined />}
              loading={data.loading}
              onClick={() => {
                setRefreshKey((value) => value + 1);
                void data.load(true);
              }}
            >
              刷新
            </Button>
          </>
        }
      />
      {data.errors.length > 0 && (
        <Alert type="warning" showIcon message={`${data.errors.join('、')}读取失败，保留已读取内容，可刷新重试。`} />
      )}
      {taskMessage && <Alert type="info" closable message={taskMessage} onClose={() => setTaskMessage('')} />}
      <Spin spinning={data.loading && !data.market.length && !data.watchlist.length}>
        <section className="overview-stats" aria-label="整体数据概览">
          <div className="overview-stat breadth-stat">
            <div className="stat-label">
              市场宽度 <small>全市场行情（含指数）</small>
            </div>
            <div className="breadth-values">
              <strong className="positive">
                {formatNumber(data.upTotal, 0)}
                <small>上涨</small>
              </strong>
              <strong className="negative">
                {formatNumber(data.downTotal, 0)}
                <small>下跌</small>
              </strong>
            </div>
            <div className="breadth-track">
              <i style={{ flex: data.upTotal || 0 }} />
              <i style={{ flex: data.downTotal || 0 }} />
            </div>
            <small>上涨占 {ratio == null ? '—' : formatNumber(ratio, 1) + '%'} · 涨跌幅绝对值 ≥0.01%</small>
          </div>
          <div className="overview-stat">
            <div className="stat-label">
              自选平均涨跌 <small>{quoted.length} 只有行情</small>
            </div>
            <strong className={`stat-value ${(average || 0) > 0 ? 'positive' : (average || 0) < 0 ? 'negative' : ''}`}>
              {pct(average)}
            </strong>
            <small>
              {quoted.filter((value) => value > 0).length} 只上涨 / {quoted.filter((value) => value < 0).length} 只下跌
              · 简单均值，非组合收益
            </small>
          </div>
          <div className="overview-stat">
            <div className="stat-label">
              策略覆盖 <Link to="/advice">查看策略</Link>
            </div>
            <strong className="stat-value">
              {advices.length}
              <small>/ {data.watchlist.length} 只自选</small>
            </strong>
            <small>
              {data.watchlist.filter((item) => item.alert_enabled).length} 只开启预警 ·{' '}
              {data.watchlist.filter((item) => item.strategy_push_enabled).length} 只开启推送
            </small>
          </div>
          <div className="overview-stat">
            <div className="stat-label">
              行情覆盖 <Link to="/market">查看行情</Link>
            </div>
            <strong className="stat-value">
              {formatNumber(data.total, 0)}
              <small>条最新行情</small>
            </strong>
            <small>
              {data.news.length} 条近期资讯 · {data.jobs.length} 条近期采集记录
            </small>
          </div>
        </section>
        <section className="quant-index-strip" aria-label="主要指数">
          {indices.map((item) => {
            const position =
              item.high != null && item.low != null && item.price != null && item.high > item.low
                ? Math.max(0, Math.min(100, ((item.price - item.low) / (item.high - item.low)) * 100))
                : 50;
            return (
              <button
                key={item.code}
                className={`quant-index ${selected?.code === item.code ? 'active' : ''}`}
                aria-pressed={selected?.code === item.code}
                aria-label={`查看${item.name}日K`}
                onClick={() => setFocused(item)}
              >
                <span>
                  {item.name}
                  <small>{item.code}</small>
                </span>
                <strong className={(item.change_pct || 0) >= 0 ? 'positive' : 'negative'}>
                  {formatNumber(item.price)}
                </strong>
                <span className="index-change">
                  <b className={(item.change_pct || 0) >= 0 ? 'positive' : 'negative'}>{pct(item.change_pct)}</b>
                  <small>{formatNumber(item.change_amount)}</small>
                </span>
                <span className="index-range">
                  <small>{formatNumber(item.low)}</small>
                  <i>
                    <em style={{ left: `${position}%` }} />
                  </i>
                  <small>{formatNumber(item.high)}</small>
                </span>
              </button>
            );
          })}
          {!indices.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无指数行情" />}
        </section>
        <div className="quant-workspace">
          <aside className="quant-workspace-left">
            <MarketMonitor
              watchlist={data.watchlist}
              selectedCode={selected?.code || ''}
              onSelect={setFocused}
              onChanged={() => void data.load(false)}
              board={board}
              clearBoard={() => setBoard(null)}
            />
            <BoardHeatmap refreshKey={refreshKey} selected={board?.code} onSelect={setBoard} />
          </aside>
          <div className="quant-workspace-center">
            {selected ? (
              <FocusChart refreshKey={refreshKey} key={selected.code} snapshot={selected} advice={advice} />
            ) : (
              <section className="quant-panel chart-empty">
                <Empty description="选择标的查看行情" />
              </section>
            )}
          </div>
          <aside className="quant-workspace-right">
            <section className="quant-panel">
              <div className="quant-panel-head">
                <h2>策略概况</h2>
                <small>自选范围</small>
              </div>
              <div className="strategy-counts">
                {signalOrder.map((signal) => (
                  <div key={signal}>
                    <strong>{counts[signal]}</strong>
                    <span>{signal}</span>
                  </div>
                ))}
              </div>
              <div className="strategy-overview-meta">
                <span>
                  平均置信度
                  <b>
                    {advices.length
                      ? formatNumber(advices.reduce((sum, item) => sum + item.confidence, 0) / advices.length, 0) + '%'
                      : '—'}
                  </b>
                </span>
                <span>
                  分析范围<b>{advices.length} 只自选股</b>
                </span>
              </div>
              <div className="quant-panel-foot">
                规则信号不代表实际成交<Link to="/advice">全部策略</Link>
              </div>
            </section>
            <section className="quant-panel market-brief">
              <div className="quant-panel-head">
                <h2>市场简报</h2>
                <small>最新 3 条</small>
              </div>
              <NewsReader
                items={[...data.news]
                  .sort(
                    (a, b) =>
                      Date.parse(b.published_at || b.fetched_at || '') -
                      Date.parse(a.published_at || a.fetched_at || ''),
                  )
                  .slice(0, 3)}
                compact
              />
              <div className="quant-panel-foot">
                <span>近期 {data.news.length} 条资讯</span>
                <Link to="/news">全部资讯</Link>
              </div>
            </section>
          </aside>
        </div>
        <section className="dashboard-base">
          <div className="base-heading">
            <div>
              <h2>基础数据</h2>
              <small>完整列表与管理操作，按需查看。</small>
            </div>
            <Link to="/market">进入全市场行情 ↗</Link>
          </div>
          <Tabs
            items={[
              {
                key: 'watch',
                label: `自选管理 ${data.watchlist.length}`,
                children: (
                  <WatchlistOverview
                    watchlist={data.watchlist}
                    maxSize={data.watchlistMaxSize}
                    onChanged={() => void data.load(false)}
                  />
                ),
              },
              {
                key: 'rank',
                label: '涨跌排行',
                children: (
                  <RankingTables
                    upRanks={{
                      strong: data.rankings.up.strong.filter((item) => item.security_type === 'stock').slice(0, 8),
                      weak: data.rankings.up.weak.filter((item) => item.security_type === 'stock').slice(0, 8),
                    }}
                    downRanks={{
                      strong: data.rankings.down.strong.filter((item) => item.security_type === 'stock').slice(0, 8),
                      weak: data.rankings.down.weak.filter((item) => item.security_type === 'stock').slice(0, 8),
                    }}
                  />
                ),
              },
              { key: 'advice', label: `策略明细 ${advices.length}`, children: <AdviceCards items={advices} /> },
            ]}
          />
        </section>
      </Spin>
    </div>
  );
}
