import { ReloadOutlined } from '@ant-design/icons';
import { Button, Col, Row, Spin } from 'antd';
import { formatTime } from '../api/client';
import MetricCard from '../components/MetricCard';
import PageHeader from '../components/PageHeader';
import RiskNotice from '../components/RiskNotice';
import LatestNewsCard from '../features/dashboard/components/LatestNewsCard';
import RankingTables from '../features/dashboard/components/RankingTables';
import StrategyDistributionCard from '../features/dashboard/components/StrategyDistributionCard';
import WatchlistOverview from '../features/dashboard/components/WatchlistOverview';
import { useDashboardData } from '../features/dashboard/useDashboardData';

export default function Dashboard() {
  const { loading, market, watchlist, news, advice, jobs, load } = useDashboardData();

  if (loading) return <Spin fullscreen tip="加载市场数据" />;

  const indices = market.filter((item) => item.security_type === 'index').slice(0, 5);
  const stocks = market.filter((item) => item.security_type === 'stock');
  const topGainers = stocks.slice(0, 8);
  const topLosers = [...stocks].sort((a, b) => (a.change_pct ?? 0) - (b.change_pct ?? 0)).slice(0, 8);
  const latestJob = jobs[0];

  return (
    <>
      <PageHeader
        title="Dashboard"
        description={`最近采集：${latestJob ? `${latestJob.job_type} · ${formatTime(latestJob.finished_at)}` : '-'}`}
        extra={<Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>}
      />

      <Row gutter={[16, 16]}>
        {indices.slice(0, 3).map((item) => (
          <Col xs={24} md={8} key={item.code}>
            <MetricCard title={`${item.name} ${item.code}`} value={item.price} change={item.change_pct} />
          </Col>
        ))}
      </Row>

      <Row gutter={[16, 16]} className="section-gap">
        <Col xs={24} lg={16}><RankingTables topGainers={topGainers} topLosers={topLosers} /></Col>
        <Col xs={24} lg={8}><StrategyDistributionCard advice={advice} /></Col>
      </Row>

      <Row gutter={[16, 16]} className="section-gap">
        <Col xs={24} lg={14}><WatchlistOverview watchlist={watchlist} /></Col>
        <Col xs={24} lg={10}><LatestNewsCard news={news} /></Col>
      </Row>

      <div className="section-gap"><RiskNotice /></div>
    </>
  );
}
