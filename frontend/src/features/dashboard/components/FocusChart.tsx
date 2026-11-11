import { Alert, Button, Empty, Modal, Segmented, Spin, Tag } from 'antd';
import ReactECharts from 'echarts-for-react';
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { api, formatCompact, formatNumber, formatTime } from '../../../api/client';
import SignalTag from '../../../components/SignalTag';
import { useBackendEvents } from '../../../hooks/useBackendEvents';
import { useThemeMode } from '../../../theme/ThemeModeContext';
import type { Advice, Snapshot } from '../../../types';
import { candleRows, rowsInRange, type CandleRow, type ChartPeriod } from '../dashboardData';

export default function FocusChart({
  snapshot,
  advice,
  refreshKey = 0,
}: {
  snapshot: Snapshot;
  advice?: Advice | null;
  refreshKey?: number;
}) {
  const isIndex = snapshot.security_type === 'index';
  const { mode } = useThemeMode();
  const [period, setPeriod] = useState<ChartPeriod>(isIndex ? 'daily' : 'minute');
  const [chartType, setChartType] = useState('candle');
  const [history, setHistory] = useState<Record<ChartPeriod, CandleRow[]>>({ daily: [], minute: [], fiveMinute: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [open, setOpen] = useState(false);
  const [info, setInfo] = useState(false);
  const [range, setRange] = useState<{ from: string; to: string; preset: string } | null>(null);
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [rangeError, setRangeError] = useState('');
  const [readout, setReadout] = useState<CandleRow>();
  const generation = useRef(0);
  const initialized = useRef(false);

  const load = useCallback(async () => {
    const id = ++generation.current;
    const results = await Promise.allSettled([
      api.kline(snapshot.code, 500),
      api.intraday(snapshot.code, 1, 1),
      api.intraday(snapshot.code, 5, 10),
    ] as const);
    if (id !== generation.current) return;
    const [daily, minute, fiveMinute] = results;
    const next = {
      daily: daily.status === 'fulfilled' ? candleRows(daily.value.items) : [],
      minute: minute.status === 'fulfilled' ? candleRows(minute.value.items) : [],
      fiveMinute: fiveMinute.status === 'fulfilled' ? candleRows(fiveMinute.value.items) : [],
    };
    setHistory((previous) => ({
      daily: daily.status === 'fulfilled' ? next.daily : previous.daily,
      minute: minute.status === 'fulfilled' ? next.minute : previous.minute,
      fiveMinute: fiveMinute.status === 'fulfilled' ? next.fiveMinute : previous.fiveMinute,
    }));
    if (!initialized.current) {
      setPeriod(isIndex ? 'daily' : next.minute.length ? 'minute' : next.fiveMinute.length ? 'fiveMinute' : 'daily');
      initialized.current = true;
    }
    setError(
      results.some((result) => result.status === 'rejected')
        ? '部分历史读取失败，可刷新重试；已读取的数据仍可查看。'
        : '',
    );
    setLoading(false);
  }, [snapshot.code, isIndex]);
  useEffect(() => {
    void load();
    return () => {
      generation.current++;
    };
  }, [load, refreshKey]);
  useBackendEvents(['kline.updated', 'intraday.updated'], () => load());
  const all = history[period];
  const rows = useMemo(() => (range ? rowsInRange(all, range.from, range.to) : all), [all, range]);
  useEffect(() => {
    setReadout(rows.at(-1));
  }, [rows]);
  const first = all[0]?.timeKey || '',
    last = all.at(-1)?.timeKey || '';
  const changePeriod = (value: ChartPeriod) => {
    setPeriod(value);
    setRange(null);
    setOpen(false);
    setRangeError('');
  };
  const toggleRange = () => {
    setFrom(range?.from || first);
    setTo(range?.to || last);
    setRangeError('');
    setOpen(!open);
  };
  const preset = (size: number) => {
    setRange(size ? { from: all[Math.max(0, all.length - size)].timeKey, to: last, preset: `最近 ${size} 根` } : null);
    setOpen(false);
    setRangeError('');
  };
  const apply = (event: FormEvent) => {
    event.preventDefault();
    if (from > to) {
      setRangeError('开始时间不能晚于结束时间。');
      return;
    }
    setRange({ from, to, preset: '自定义时段' });
    setOpen(false);
    setRangeError('');
  };
  const palette =
    mode === 'dark'
      ? { text: '#a5afbf', grid: '#384150', accent: '#eac276', up: '#ff8f9b', down: '#62d9b4' }
      : { text: '#65717e', grid: '#dce1e6', accent: '#876017', up: '#c73e50', down: '#168260' };
  const option = useMemo(
    () => ({
      animation: false,
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis', confine: true, axisPointer: { type: 'cross' } },
      axisPointer: { link: [{ xAxisIndex: 'all' }] },
      grid: [
        { left: 52, right: 16, top: 20, height: '61%' },
        { left: 52, right: 16, top: '76%', height: '12%' },
      ],
      xAxis: [0, 1].map((index) => ({
        type: 'category',
        gridIndex: index,
        data: rows.map((row) => row.timeKey.replace('T', ' ')),
        boundaryGap: true,
        axisLine: { lineStyle: { color: palette.grid } },
        axisLabel: {
          show: index === 1,
          color: palette.text,
          fontSize: 9,
          hideOverlap: true,
          formatter: (value: string) => (period === 'daily' ? value.slice(5) : value.slice(5, 16)),
        },
        axisTick: { show: false },
      })),
      yAxis: [0, 1].map((index) => ({
        scale: true,
        gridIndex: index,
        splitNumber: index ? 2 : 4,
        axisLabel: { show: index === 0, color: palette.text, fontSize: 9 },
        splitLine: { show: index === 0, lineStyle: { color: palette.grid, type: 'dashed' } },
      })),
      dataZoom: [{ type: 'inside', xAxisIndex: [0, 1] }],
      series: [
        chartType === 'candle'
          ? {
              name: 'K线',
              type: 'candlestick',
              data: rows.map((row) => [row.open, row.close, row.low, row.high]),
              itemStyle: {
                color: palette.up,
                color0: palette.down,
                borderColor: palette.up,
                borderColor0: palette.down,
              },
            }
          : {
              name: '收盘',
              type: 'line',
              data: rows.map((row) => row.close),
              symbol: rows.length === 1 ? 'circle' : 'none',
              lineStyle: { color: palette.accent, width: 1.6 },
              itemStyle: { color: palette.accent },
            },
        {
          name: '成交量',
          type: 'bar',
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: rows.map((row) => ({
            value: row.volume ?? null,
            itemStyle: { color: row.close >= row.open ? palette.up : palette.down, opacity: 0.55 },
          })),
        },
      ],
    }),
    [rows, chartType, period, mode],
  );
  const direction = (snapshot.change_pct || 0) > 0 ? 'positive' : (snapshot.change_pct || 0) < 0 ? 'negative' : '';
  const metrics = [
    ['今开', formatNumber(snapshot.open)],
    ['最高', formatNumber(snapshot.high)],
    ['最低', formatNumber(snapshot.low)],
    ['成交额', formatCompact(snapshot.amount)],
    [
      isIndex ? '涨跌额' : '换手率',
      isIndex
        ? formatNumber(snapshot.change_amount)
        : snapshot.turnover_rate == null
          ? '—'
          : `${formatNumber(snapshot.turnover_rate)}%`,
    ],
    ['行情时间', formatTime(snapshot.snapshot_time)],
  ];

  return (
    <section className="quant-panel focus-panel" aria-label="标的行情图">
      <div className="focus-quote">
        <div className="focus-quote-top">
          <div className="focus-heading">
            <h2>
              {snapshot.name}
              <small>{snapshot.code}</small>
            </h2>
            <strong className={`focus-price ${direction}`}>{formatNumber(snapshot.price)}</strong>
            <span className={`mono ${direction}`}>
              {snapshot.change_pct == null
                ? '—'
                : `${snapshot.change_pct > 0 ? '+' : ''}${formatNumber(snapshot.change_pct)}%`}
            </span>
          </div>
          {isIndex ? <Tag>指数 / 点</Tag> : <Link to={`/stock/${snapshot.code}`}>详情 ↗</Link>}
        </div>
        <div className="focus-metrics">
          {metrics.map(([label, value]) => (
            <span key={label}>
              {label}
              <b>{value}</b>
            </span>
          ))}
        </div>
      </div>
      <div className="focus-tools">
        <Segmented
          size="small"
          aria-label="图表周期"
          value={period}
          onChange={(value) => changePeriod(value as ChartPeriod)}
          options={[
            { label: '当前1分', value: 'minute', disabled: isIndex && !history.minute.length },
            { label: '10日5分', value: 'fiveMinute', disabled: isIndex && !history.fiveMinute.length },
            { label: '日 K', value: 'daily' },
          ]}
        />
        <div className="focus-tools-right">
          <Segmented
            size="small"
            aria-label="图表类型"
            value={chartType}
            onChange={(value) => setChartType(String(value))}
            options={[
              { label: '走势', value: 'line' },
              { label: '蜡烛', value: 'candle' },
            ]}
          />
          <Button
            size="small"
            className={range ? 'range-active' : ''}
            disabled={!all.length}
            aria-expanded={open}
            aria-controls="chart-range"
            onClick={toggleRange}
          >
            {range?.preset || '时间范围'}
          </Button>
        </div>
      </div>
      {open && (
        <form id="chart-range" className="focus-range" onSubmit={apply}>
          <div className="range-presets">
            <Button size="small" onClick={() => preset(0)}>
              全部
            </Button>
            <Button size="small" onClick={() => preset(20)}>
              最近 20 根
            </Button>
            <Button size="small" onClick={() => preset(60)}>
              最近 60 根
            </Button>
            <small>
              可选 {first.replace('T', ' ')} 至 {last.replace('T', ' ')}
            </small>
          </div>
          <div className="range-fields">
            <label>
              从
              <input
                aria-label="开始时间"
                type={period === 'daily' ? 'date' : 'datetime-local'}
                value={from}
                min={first}
                max={last}
                required
                onChange={(event) => {
                  setFrom(event.target.value);
                  setRangeError('');
                }}
              />
            </label>
            <label>
              至
              <input
                aria-label="结束时间"
                type={period === 'daily' ? 'date' : 'datetime-local'}
                value={to}
                min={first}
                max={last}
                required
                onChange={(event) => {
                  setTo(event.target.value);
                  setRangeError('');
                }}
              />
            </label>
            <Button size="small" type="primary" htmlType="submit">
              应用时段
            </Button>
          </div>
          {rangeError && (
            <p className="positive" role="alert">
              {rangeError}
            </p>
          )}
        </form>
      )}
      {error && (
        <Alert
          type="warning"
          message={error}
          action={
            <Button size="small" onClick={() => void load()}>
              重试
            </Button>
          }
        />
      )}
      <Spin spinning={loading}>
        {rows.length ? (
          <div
            tabIndex={0}
            role="group"
            aria-label="K线图，左右方向键读取行情"
            onKeyDown={(event) => {
              if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
              event.preventDefault();
              const index = readout ? rows.indexOf(readout) : rows.length - 1;
              setReadout(
                rows[
                  event.key === 'Home'
                    ? 0
                    : event.key === 'End'
                      ? rows.length - 1
                      : Math.max(0, Math.min(rows.length - 1, index + (event.key === 'ArrowRight' ? 1 : -1)))
                ],
              );
            }}
          >
            <ReactECharts
              option={option}
              notMerge
              className="overview-chart"
              onEvents={{
                updateAxisPointer: (event: { axesInfo?: { value: number }[] }) => {
                  const index = Number(event.axesInfo?.[0]?.value);
                  if (Number.isInteger(index) && rows[index]) setReadout(rows[index]);
                },
              }}
            />
          </div>
        ) : (
          <div className="chart-empty">
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={loading ? '读取历史行情' : range ? '所选时段没有已捕获的行情' : '此周期暂无历史数据'}
            />
            {range ? (
              <Button size="small" onClick={() => setRange(null)}>
                显示全部数据
              </Button>
            ) : period !== 'daily' ? (
              <Button size="small" onClick={() => changePeriod('daily')}>
                查看日 K
              </Button>
            ) : null}
          </div>
        )}
      </Spin>
      <div className="focus-chart-status">
        <span className="chart-readout">
          {readout
            ? `${readout.timeKey.replace('T', ' ')}　开 ${formatNumber(readout.open)}　高 ${formatNumber(readout.high)}　低 ${formatNumber(readout.low)}　收 ${formatNumber(readout.close)}`
            : '暂无可读取的数据'}
        </span>
        <span>
          {rows.length} / {all.length} 根{' '}
          <Button type="link" size="small" onClick={() => setInfo(true)}>
            数据说明
          </Button>
        </span>
      </div>
      {!isIndex && (
        <div className="focus-strategy">
          <SignalTag signal={advice?.signal} />
          <div>
            {advice?.reasoning || '该标的暂无策略记录。'}
            {advice && (
              <small>
                置信度 {formatNumber(advice.confidence, 0)}% · {formatTime(advice.created_at)}
              </small>
            )}
          </div>
        </div>
      )}
      <Modal
        title="图表数据说明"
        open={info}
        onCancel={() => setInfo(false)}
        footer={<Button onClick={() => setInfo(false)}>关闭</Button>}
      >
        <p>{isIndex ? '指数单位为点' : '价格单位为人民币元'}，成交量沿用接口原始单位。</p>
        <p>
          可用历史：{first.replace('T', ' ')} 至 {last.replace('T', ' ')}，共 {all.length} 根。
        </p>
        <p>
          指定时段包含开始和结束时刻，只过滤已经读取的历史。日 K 最多读取最近 500
          条，分钟数据按当前周期读取最近交易日。行情卡片与历史使用各自的记录时间，缺失历史不会补造。
        </p>
      </Modal>
    </section>
  );
}
