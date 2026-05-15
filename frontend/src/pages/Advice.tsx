import { PlayCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, Card, Table, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import PageHeader from '../components/PageHeader';
import RiskNotice from '../components/RiskNotice';
import AdviceToolbar from '../features/advice/AdviceToolbar';
import { adviceColumns } from '../features/advice/adviceColumns';
import { useBackendEvents } from '../hooks/useBackendEvents';
import type { Advice as AdviceType } from '../types';

export default function Advice() {
  const [loading, setLoading] = useState(false);
  const [signal, setSignal] = useState<string | undefined>();
  const [items, setItems] = useState<AdviceType[]>([]);

  const load = useCallback(async (showSpinner = true) => {
    if (showSpinner) setLoading(true);
    try {
      setItems((await api.advice(signal)).items);
    } catch (error) {
      if (showSpinner) message.error(error instanceof Error ? error.message : '加载失败');
    } finally {
      if (showSpinner) setLoading(false);
    }
  }, [signal]);

  useEffect(() => { void load(); }, []);
  useBackendEvents(['advice.updated'], () => load(false));

  const analyzeWatchlist = async () => {
    try {
      await api.analyzeWatchlist();
      message.success('自选股分析完成');
      await load(true);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '分析失败');
    }
  };

  return (
    <>
      <PageHeader
        title="Advice"
        description="关注股和全市场股票的最新策略建议"
        extra={(
          <>
            <Button icon={<PlayCircleOutlined />} type="primary" onClick={analyzeWatchlist}>分析自选股</Button>
            <Button icon={<ReloadOutlined />} onClick={() => load(true)}>刷新</Button>
          </>
        )}
      />
      <Card className="data-surface">
        <AdviceToolbar signal={signal} setSignal={setSignal} onApply={() => load(true)} />
        <Table<AdviceType> rowKey="id" loading={loading} columns={adviceColumns} dataSource={items} pagination={{ pageSize: 10 }} />
      </Card>
      <div className="section-gap"><RiskNotice /></div>
    </>
  );
}
