import { ReloadOutlined } from '@ant-design/icons';
import { Button, Spin } from 'antd';
import { formatTime } from '../api/client';
import MetricCard from '../components/MetricCard';
import PageHeader from '../components/PageHeader';
import RiskNotice from '../components/RiskNotice';
import LatestNewsCard from '../features/dashboard/components/LatestNewsCard';
import RankingTables from '../features/dashboard/components/RankingTables';
import WatchlistOverview from '../features/dashboard/components/WatchlistOverview';
import { useDashboardData } from '../features/dashboard/useDashboardData';

export default function Dashboard() {
  const { loading, market, watchlist, watchlistMaxSize, news, jobs, load } = useDashboardData();

  if (loading) return <Spin fullscreen tip="加载市场数据" />;

  const indexOrder = ['000001.SH', '399001.SZ', '399006.SZ', '000300.SH', '000905.SH'];
  const indices = market
    .filter((item) => item.security_type === 'index')
    .sort((a, b) => indexOrder.indexOf(a.code) - indexOrder.indexOf(b.code))
    .slice(0, 5);
  const stocks = market.filter((item) => item.security_type === 'stock');
  const topGainers = stocks.slice(0, 8);
  const topLosers = [...stocks].sort((a, b) => (a.change_pct ?? 0) - (b.change_pct ?? 0)).slice(0, 8);
  const latestJob = jobs[0];

  return (
    <>
      <PageHeader
        title="Dashboard"
        description={`最近采集：${latestJob ? `${latestJob.job_type} · ${formatTime(latestJob.finished_at)}` : '-'}`}
        extra={<Button icon={<ReloadOutlined />} onClick={() => load(true)}>刷新</Button>}
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
            <RankingTables topGainers={topGainers} topLosers={topLosers} />
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
