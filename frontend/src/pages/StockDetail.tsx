import { CloudDownloadOutlined, PlayCircleOutlined, ReloadOutlined, StarFilled, StarOutlined } from '@ant-design/icons';
import { Button, Card, Col, Row, Segmented, Space, Spin, Typography, message } from 'antd';
import ReactECharts from 'echarts-for-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api, formatTime } from '../api/client';
import PageHeader from '../components/PageHeader';
import RiskNotice from '../components/RiskNotice';
import { createIntradayKlineOption, createKlineOption, createSnapshotOption } from '../features/stock-detail/charts/stockCharts';
import AdviceHistory from '../features/stock-detail/components/AdviceHistory';
import QuoteOverview from '../features/stock-detail/components/QuoteOverview';
import RelatedNews from '../features/stock-detail/components/RelatedNews';
import StrategySummary from '../features/stock-detail/components/StrategySummary';
import { selectDefaultKlineMode, type KlineMode } from '../features/stock-detail/klineMode';
import TechnicalIndicators from '../features/stock-detail/components/TechnicalIndicators';
import { useBackendEvents } from '../hooks/useBackendEvents';
import { useThemeMode } from '../theme/ThemeModeContext';
import type { Advice, IntradayKline, Kline, NewsItem, Snapshot, Stock } from '../types';

type StockDetailData = Stock & { latest_snapshot?: Snapshot | null; latest_advice?: Advice | null; is_watched: boolean };
const INTRADAY_REFRESH_MS = 60_000;

export default function StockDetail() {
  const { code = '' } = useParams();
  const [loading, setLoading] = useState(true);
  const [stock, setStock] = useState<StockDetailData | null>(null);
  const [kline, setKline] = useState<Kline[]>([]);
  const [intraday1m, setIntraday1m] = useState<IntradayKline[]>([]);
  const [intraday5m, setIntraday5m] = useState<IntradayKline[]>([]);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [history, setHistory] = useState<Advice[]>([]);
  const [klineMode, setKlineMode] = useState<KlineMode>('latest_intraday');
  const [intradayRefreshing, setIntradayRefreshing] = useState(false);
  const [dailyKlineRefreshing, setDailyKlineRefreshing] = useState(false);
  const [lastIntradayRefresh, setLastIntradayRefresh] = useState<string | null>(null);
  const intradayRefreshInFlight = useRef(false);
  const defaultModeCodeRef = useRef<string | null>(null);
  const { mode: themeMode } = useThemeMode();

  const load = useCallback(async (showSpinner = true) => {
    if (!code) return;
    if (showSpinner) setLoading(true);
    try {
      const [stockRes, klineRes, currentIntradayRes, tenDayIntradayRes, snapshotRes, newsRes, historyRes] = await Promise.all([
        api.stock(code),
        api.kline(code, 90),
        api.intraday(code, 1, 1),
        api.intraday(code, 5, 10),
        api.stockSnapshots(code, 160),
        api.stockNews(code, 10),
        api.adviceHistory(code, 20),
      ]);
      if (defaultModeCodeRef.current !== stockRes.code) {
        setKlineMode(selectDefaultKlineMode(stockRes.is_watched));
        defaultModeCodeRef.current = stockRes.code;
      }
      setStock(stockRes);
      setKline(klineRes.items);
      setIntraday1m(currentIntradayRes.items);
      setIntraday5m(tenDayIntradayRes.items);
      setSnapshots(snapshotRes.items);
      setNews(newsRes.items);
      setHistory(historyRes.items);
    } catch (error) {
      if (showSpinner) message.error(error instanceof Error ? error.message : '加载失败');
    } finally {
      if (showSpinner) setLoading(false);
    }
  }, [code]);

  const refreshIntraday = useCallback(async (showMessage = false) => {
    if (!code || intradayRefreshInFlight.current) return;
    intradayRefreshInFlight.current = true;
    setIntradayRefreshing(true);
    try {
      await api.collectStockIntraday(code, 1, 1);
      setLastIntradayRefresh(new Date().toISOString());
      await load(false);
      if (showMessage) message.success('分钟 K 已更新');
    } catch (error) {
      if (showMessage) message.error(error instanceof Error ? error.message : '分钟 K 更新失败');
    } finally {
      intradayRefreshInFlight.current = false;
      setIntradayRefreshing(false);
    }
  }, [code, load]);

  const completeDailyKline = useCallback(async () => {
    if (!code) return;
    setDailyKlineRefreshing(true);
    try {
      const result = await api.collectStockDailyKline(code, 365);
      const inserted = Number(result.inserted ?? 0);
      const updated = Number(result.updated ?? 0);
      const failed = Number(result.failed ?? 0);
      setKlineMode('daily');
      await load(false);
      if (failed > 0) {
        message.warning(`日 K 补全完成，失败 ${failed} 条`);
      } else {
        message.success(`日 K 补全完成，新增 ${inserted} 条，更新 ${updated} 条`);
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : '日 K 补全失败');
    } finally {
      setDailyKlineRefreshing(false);
    }
  }, [code, load]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!stock?.is_watched || stock.code.toUpperCase() !== code.toUpperCase()) return undefined;
    void refreshIntraday(false);
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void refreshIntraday(false);
    }, INTRADAY_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [refreshIntraday, stock?.is_watched]);

  useBackendEvents(['market.updated', 'watchlist.updated', 'news.updated', 'advice.updated', 'kline.updated', 'intraday.updated'], () => load(false));

  const analyze = async () => {
    try {
      await api.analyze(code);
      message.success('分析完成');
      await load(true);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '分析失败');
    }
  };

  const toggleWatch = async () => {
    if (!stock) return;
    try {
      stock.is_watched ? await api.removeWatch(stock.code) : await api.addWatch(stock.code);
      message.success(stock.is_watched ? '已移出自选股' : '已加入自选股');
      await load(true);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '操作失败');
    }
  };

  const klineOption = useMemo(() => createKlineOption(kline, themeMode), [kline, themeMode]);
  const latestIntraday = useMemo(() => {
    const latestDate = intraday1m.at(-1)?.bar_time.slice(0, 10);
    return latestDate ? intraday1m.filter((item) => item.bar_time.startsWith(latestDate)) : [];
  }, [intraday1m]);
  const intradayOption = useMemo(() => createIntradayKlineOption(intraday5m, themeMode), [intraday5m, themeMode]);
  const latestIntradayOption = useMemo(() => createIntradayKlineOption(latestIntraday, themeMode), [latestIntraday, themeMode]);
  const snapshotOption = useMemo(() => createSnapshotOption(snapshots, themeMode), [snapshots, themeMode]);

  if (loading) return <Spin fullscreen tip="加载个股详情" />;
  if (!stock) return null;

  const advice = history[0] ?? stock.latest_advice;
  const indicators = advice?.indicators ?? {};
  const latestIntradayTime = klineMode === 'intraday'
    ? intraday5m.at(-1)?.bar_time
    : latestIntraday.at(-1)?.bar_time || intraday1m.at(-1)?.bar_time;
  const klineTitle = klineMode === 'daily' ? '历史日 K 与均线' : klineMode === 'intraday' ? '10 日 5 分钟 K 与均线' : '当前交易日 1 分钟 K 与均线';

  return (
    <>
      <PageHeader
        title={`${stock.name} ${stock.code}`}
        description={`${stock.market} · ${stock.industry ?? '未分类'}`}
        extra={(
          <>
            <Button icon={stock.is_watched ? <StarFilled /> : <StarOutlined />} onClick={toggleWatch}>{stock.is_watched ? '取消关注' : '加入关注'}</Button>
            <Button icon={<PlayCircleOutlined />} type="primary" onClick={analyze}>触发分析</Button>
            <Button icon={<CloudDownloadOutlined />} loading={dailyKlineRefreshing} onClick={completeDailyKline}>补全近一年日 K</Button>
            <Button icon={<ReloadOutlined />} loading={intradayRefreshing} disabled={!stock.is_watched} onClick={() => refreshIntraday(true)}>更新分钟 K</Button>
            <Button icon={<ReloadOutlined />} onClick={() => load(true)}>刷新页面</Button>
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
            title={klineTitle}
            extra={(
              <Space size={10} wrap>
                {klineMode !== 'daily' ? (
                  <Typography.Text className="muted">
                    {latestIntradayTime ? `最新 ${formatTime(latestIntradayTime)}` : '暂无分钟 K'}
                    {lastIntradayRefresh ? ` · 更新 ${formatTime(lastIntradayRefresh)}` : ''}
                  </Typography.Text>
                ) : null}
                <Segmented
                  size="small"
                  value={klineMode}
                  onChange={(value) => setKlineMode(value as KlineMode)}
                  options={[
                    { label: '当前1分', value: 'latest_intraday' },
                    { label: '10日5分', value: 'intraday' },
                    { label: '日 K', value: 'daily' },
                  ]}
                />
              </Space>
            )}
          >
            <ReactECharts
              option={klineMode === 'daily' ? klineOption : klineMode === 'intraday' ? intradayOption : latestIntradayOption}
              className="chart-panel"
            />
          </Card>
        </Col>
        <Col xs={24} xl={9}>
          <Card title="关注股快照走势"><ReactECharts option={snapshotOption} className="chart-panel" /></Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} className="section-gap">
        <Col xs={24} lg={6} xl={5}><TechnicalIndicators indicators={indicators} /></Col>
        <Col xs={24} lg={6} xl={7}><RelatedNews news={news} /></Col>
        <Col xs={24} lg={12}><AdviceHistory history={history} /></Col>
      </Row>

      <div className="section-gap"><RiskNotice /></div>
    </>
  );
}
