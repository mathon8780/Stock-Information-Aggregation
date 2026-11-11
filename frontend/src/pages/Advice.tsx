import { PlayCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, Card, Pagination, Segmented, Spin, message } from 'antd';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import PageHeader from '../components/PageHeader';
import AdviceCards from '../features/advice/AdviceCards';
import { signalCounts, signalOrder } from '../features/dashboard/dashboardData';
import { useBackendEvents } from '../hooks/useBackendEvents';
import type { Advice as AdviceType } from '../types';

export default function Advice() {
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [signal, setSignal] = useState('全部');
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<AdviceType[]>([]);
  const generation = useRef(0);
  const load = useCallback(async (showSpinner = true) => {
    const id = ++generation.current;
    if (showSpinner) setLoading(true);
    try {
      const result = await api.advice();
      if (id === generation.current) setItems(result.items);
    } catch (error) {
      if (id === generation.current) message.error(error instanceof Error ? error.message : '加载失败');
    } finally {
      if (id === generation.current) setLoading(false);
    }
  }, []);
  useEffect(() => {
    void load();
    return () => {
      generation.current++;
    };
  }, [load]);
  useBackendEvents(['advice.updated'], () => load(false));
  const analyzeWatchlist = async () => {
    setAnalyzing(true);
    try {
      await api.analyzeWatchlist();
      message.success('自选股分析完成');
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '分析失败');
    } finally {
      setAnalyzing(false);
    }
  };
  const counts = signalCounts(items);
  const filtered = signal === '全部' ? items : items.filter((item) => item.signal === signal);
  return (
    <>
      <PageHeader
        title="策略观察"
        description="查看最新信号、判断依据与风险；策略不代表实际交易"
        extra={
          <>
            <Button
              icon={<PlayCircleOutlined />}
              type="primary"
              loading={analyzing}
              onClick={() => void analyzeWatchlist()}
            >
              分析自选股
            </Button>
            <Button icon={<ReloadOutlined />} onClick={() => void load()}>
              刷新
            </Button>
          </>
        }
      />
      <div className="signal-summary">
        {signalOrder.map((value) => (
          <button
            key={value}
            onClick={() => {
              setSignal(value);
              setPage(1);
            }}
            className={signal === value ? 'active' : ''}
          >
            <strong className="mono">{counts[value]}</strong>
            <span>{value}</span>
          </button>
        ))}
      </div>
      <Card className="data-surface">
        <div className="toolbar">
          <Segmented
            aria-label="策略信号"
            value={signal}
            options={['全部', ...signalOrder]}
            onChange={(value) => {
              setSignal(String(value));
              setPage(1);
            }}
          />
          <small className="muted">当前读取 {items.length} 条最新策略</small>
        </div>
        <Spin spinning={loading}>
          <AdviceCards items={filtered.slice((page - 1) * 9, page * 9)} />
        </Spin>
        <Pagination current={page} pageSize={9} total={filtered.length} showSizeChanger={false} onChange={setPage} />
      </Card>
    </>
  );
}
