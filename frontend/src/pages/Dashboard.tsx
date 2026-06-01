import { DatabaseOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, message, Space, Spin } from 'antd';
import { useState } from 'react';
import { api, formatTime } from '../api/client';
import MetricCard from '../components/MetricCard';
import PageHeader from '../components/PageHeader';
import RiskNotice from '../components/RiskNotice';
import LatestNewsCard from '../features/dashboard/components/LatestNewsCard';
import RankingTables from '../features/dashboard/components/RankingTables';
import WatchlistOverview from '../features/dashboard/components/WatchlistOverview';
import { useDashboardData } from '../features/dashboard/useDashboardData';
import type { Snapshot } from '../types';

function stockRank(items: Snapshot[]) {
  return items.filter((item) => item.security_type === 'stock').slice(0, 8);
}

export default function Dashboard() {
  const { loading, market, rankings, watchlist, watchlistMaxSize, news, jobs, load } = useDashboardData();
  const [missingDailyLoading, setMissingDailyLoading] = useState(false);

  const triggerMissingDailyKline = async () => {
    setMissingDailyLoading(true);
    try {
      const result = await api.collectMissingDailyKline();
      if (result.status === 'already_running') message.info('缺失日 K 补齐任务已在运行');
      else message.success('缺失日 K 补齐任务已启动');
      await load(false);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '启动补齐任务失败');
    } finally {
      setMissingDailyLoading(false);
    }
  };

  if (loading) return <Spin fullscreen tip="加载市场数据" />;

  const indexOrder = ['000001.SH', '399001.SZ', '399006.SZ', '000300.SH', '000905.SH'];
  const indices = market
    .filter((item) => item.security_type === 'index')
    .sort((a, b) => indexOrder.indexOf(a.code) - indexOrder.indexOf(b.code))
    .slice(0, 5);
  const rankingGroups = {
    up: {
      strong: stockRank(rankings.up.strong),
      weak: stockRank(rankings.up.weak),
    },
    down: {
      strong: stockRank(rankings.down.strong),
      weak: stockRank(rankings.down.weak),
    },
  };
  const latestJob = jobs[0];

  return (
    <>
      <PageHeader
        title="Dashboard"
        description={`最近采集：${latestJob ? `${latestJob.job_type} · ${formatTime(latestJob.finished_at)}` : '-'}`}
        extra={(
          <Space wrap>
            <Button icon={<DatabaseOutlined />} loading={missingDailyLoading} onClick={triggerMissingDailyKline}>补全缺失日 K</Button>
            <Button icon={<ReloadOutlined />} onClick={() => load(true)}>刷新</Button>
          </Space>
        )}
      />

      <div className="dashboard-layout">
        <main className="dashboard-main">
          <section className="dashboard-panel">
            <div className="table-section-title">大盘数据</div>
            <div className="index-strip">
              {indices.map((item) => (
                <MetricCard key={item.code} title={`${item.name} ${item.code}`} value={item.price} change={item.change_pct} />
              ))}
            </div>
          </section>

          <div className="section-gap">
            <RankingTables upRanks={rankingGroups.up} downRanks={rankingGroups.down} />
          </div>

          <div className="section-gap">
            <WatchlistOverview watchlist={watchlist} maxSize={watchlistMaxSize} onChanged={() => load(false)} />
          </div>

          <div className="section-gap"><RiskNotice /></div>
        </main>

        <aside className="dashboard-news-rail">
          <LatestNewsCard news={news} />
        </aside>
      </div>
    </>
  );
}
