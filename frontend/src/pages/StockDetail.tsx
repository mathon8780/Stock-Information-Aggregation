import { PlayCircleOutlined, ReloadOutlined, StarFilled, StarOutlined } from '@ant-design/icons';
import { Button, Card, Col, Row, Segmented, Spin, message } from 'antd';
import ReactECharts from 'echarts-for-react';
import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '../api/client';
import PageHeader from '../components/PageHeader';
import RiskNotice from '../components/RiskNotice';
import { createIntradayKlineOption, createKlineOption, createSnapshotOption } from '../features/stock-detail/charts/stockCharts';
import AdviceHistory from '../features/stock-detail/components/AdviceHistory';
import QuoteOverview from '../features/stock-detail/components/QuoteOverview';
import RelatedNews from '../features/stock-detail/components/RelatedNews';
import StrategySummary from '../features/stock-detail/components/StrategySummary';
import TechnicalIndicators from '../features/stock-detail/components/TechnicalIndicators';
import type { Advice, IntradayKline, Kline, NewsItem, Snapshot, Stock } from '../types';

type StockDetailData = Stock & { latest_snapshot?: Snapshot | null; latest_advice?: Advice | null; is_watched: boolean };
type KlineMode = 'daily' | 'intraday';

export default function StockDetail() {
  const { code = '' } = useParams();
  const [loading, setLoading] = useState(true);
  const [stock, setStock] = useState<StockDetailData | null>(null);
  const [kline, setKline] = useState<Kline[]>([]);
  const [intraday, setIntraday] = useState<IntradayKline[]>([]);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [history, setHistory] = useState<Advice[]>([]);
  const [klineMode, setKlineMode] = useState<KlineMode>('daily');

  const load = async () => {
    if (!code) return;
    setLoading(true);
    try {
      const [stockRes, klineRes, intradayRes, snapshotRes, newsRes, historyRes] = await Promise.all([
        api.stock(code),
        api.kline(code, 90),
        api.intraday(code, 5, 10),
        api.stockSnapshots(code, 160),
        api.stockNews(code, 10),
        api.adviceHistory(code, 20),
      ]);
      setStock(stockRes);
      setKline(klineRes.items);
      setIntraday(intradayRes.items);
      setSnapshots(snapshotRes.items);
      setNews(newsRes.items);
      setHistory(historyRes.items);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, [code]);

  const analyze = async () => {
    try {
      await api.analyze(code);
      message.success('分析完成');
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '分析失败');
    }
  };

  const toggleWatch = async () => {
    if (!stock) return;
    try {
      stock.is_watched ? await api.removeWatch(stock.code) : await api.addWatch(stock.code);
      message.success(stock.is_watched ? '已移出自选股' : '已加入自选股');
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '操作失败');
    }
  };

  const klineOption = useMemo(() => createKlineOption(kline), [kline]);
  const intradayOption = useMemo(() => createIntradayKlineOption(intraday), [intraday]);
  const snapshotOption = useMemo(() => createSnapshotOption(snapshots), [snapshots]);

  if (loading) return <Spin fullscreen tip="加载个股详情" />;
  if (!stock) return null;

  const advice = history[0] ?? stock.latest_advice;
  const indicators = advice?.indicators ?? {};

  return (
    <>
      <PageHeader
        title={`${stock.name} ${stock.code}`}
        description={`${stock.market} · ${stock.industry ?? '未分类'}`}
        extra={(
          <>
            <Button icon={stock.is_watched ? <StarFilled /> : <StarOutlined />} onClick={toggleWatch}>{stock.is_watched ? '取消关注' : '加入关注'}</Button>
            <Button icon={<PlayCircleOutlined />} type="primary" onClick={analyze}>触发分析</Button>
            <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
          </>
        )}
      />

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={16}><QuoteOverview snapshot={stock.latest_snapshot} /></Col>
        <Col xs={24} lg={8}><StrategySummary advice={advice} /></Col>
      </Row>

      <Row gutter={[16, 16]} className="section-gap">
        <Col xs={24} xl={15}>
          <Card
            title={klineMode === 'daily' ? '历史日 K 与均线' : '5 分钟 K 与均线'}
            extra={(
              <Segmented
                size="small"
                value={klineMode}
                onChange={(value) => setKlineMode(value as KlineMode)}
                options={[
                  { label: '日 K', value: 'daily' },
                  { label: '5 分钟', value: 'intraday' },
                ]}
              />
            )}
          >
            <ReactECharts option={klineMode === 'daily' ? klineOption : intradayOption} className="chart-panel" />
          </Card>
        </Col>
        <Col xs={24} xl={9}>
          <Card title="关注股快照走势"><ReactECharts option={snapshotOption} className="chart-panel" /></Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} className="section-gap">
        <Col xs={24} lg={8}><TechnicalIndicators indicators={indicators} /></Col>
        <Col xs={24} lg={8}><RelatedNews news={news} /></Col>
        <Col xs={24} lg={8}><AdviceHistory history={history} /></Col>
      </Row>

      <div className="section-gap"><RiskNotice /></div>
    </>
  );
}
