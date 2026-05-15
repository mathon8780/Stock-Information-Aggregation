import { ReloadOutlined } from '@ant-design/icons';
import { Button, Card, Table, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import PageHeader from '../components/PageHeader';
import NewsLlmConfigCard from '../features/settings/NewsLlmConfigCard';
import SettingsCards from '../features/settings/SettingsCards';
import TaskActions from '../features/settings/TaskActions';
import { jobColumns } from '../features/settings/jobColumns';
import { useBackendEvents } from '../hooks/useBackendEvents';
import type { CollectionJob, NewsLlmConfig, NewsLlmConfigPayload } from '../types';

export default function Settings() {
  const [settings, setSettings] = useState<Record<string, any> | null>(null);
  const [newsLlmConfig, setNewsLlmConfig] = useState<NewsLlmConfig | null>(null);
  const [jobs, setJobs] = useState<CollectionJob[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (showSpinner = true) => {
    if (showSpinner) setLoading(true);
    try {
      const [s, j, c] = await Promise.all([api.settings(), api.jobs(20), api.newsLlmConfig()]);
      setSettings(s);
      setJobs(j.items);
      setNewsLlmConfig(c);
    } catch (error) {
      if (showSpinner) message.error(error instanceof Error ? error.message : '加载失败');
    } finally {
      if (showSpinner) setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);
  useBackendEvents(['settings.updated', 'jobs.updated'], () => load(false));

  const runTask = async (task: 'bootstrap' | 'market' | 'history' | 'intraday' | 'news' | 'simplifyNews') => {
    setLoading(true);
    try {
      if (task === 'bootstrap') await api.collectBootstrap();
      if (task === 'market') await api.collectMarket();
      if (task === 'history') await api.collectHistory();
      if (task === 'intraday') await api.collectIntraday();
      if (task === 'news') await api.collectNews();
      if (task === 'simplifyNews') await api.simplifyPendingNews(50);
      message.success('任务执行完成');
      await load(true);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '执行失败');
    } finally {
      setLoading(false);
    }
  };

  const saveNewsLlmConfig = async (payload: NewsLlmConfigPayload) => {
    setLoading(true);
    try {
      const next = await api.updateNewsLlmConfig(payload);
      setNewsLlmConfig(next);
      message.success('LLM 配置已保存');
      await load(true);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Settings"
        description="真实行情数据源、PostgreSQL 运行状态、采集风控和任务状态"
        extra={<Button icon={<ReloadOutlined />} onClick={() => load(true)}>刷新</Button>}
      />
      <SettingsCards settings={settings} />
      <NewsLlmConfigCard config={newsLlmConfig} loading={loading} onSave={saveNewsLlmConfig} />
      <TaskActions loading={loading} runTask={runTask} />
      <Card title="任务记录" className="table-card section-gap">
        <Table<CollectionJob> rowKey="id" loading={loading} dataSource={jobs} columns={jobColumns} pagination={{ pageSize: 8 }} />
      </Card>
    </>
  );
}
