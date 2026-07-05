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
import type { CollectionJob, NewsLlmConfig, NewsLlmConfigPayload, NewsLlmKeyStatus } from '../types';

export default function Settings() {
  const [settings, setSettings] = useState<Record<string, any> | null>(null);
  const [newsLlmConfig, setNewsLlmConfig] = useState<NewsLlmConfig | null>(null);
  const [newsLlmKeyStatus, setNewsLlmKeyStatus] = useState<NewsLlmKeyStatus | null>(null);
  const [jobs, setJobs] = useState<CollectionJob[]>([]);
  const [loading, setLoading] = useState(false);
  const [validatingKey, setValidatingKey] = useState(false);

  const load = useCallback(async (showSpinner = true) => {
    if (showSpinner) setLoading(true);
    try {
      const [s, j, c] = await Promise.all([api.settings(), api.jobs(20), api.newsLlmConfig()]);
      setSettings(s);
      setJobs(j.items);
      setNewsLlmConfig(c);
      if (!c.api_key_configured) {
        setNewsLlmKeyStatus({
          provider: c.provider,
          model: c.model,
          api_base_url: c.api_base_url,
          api_key_configured: false,
          ok: false,
          status: 'missing',
          message: 'API Key 未配置',
        });
      } else {
        setNewsLlmKeyStatus((current) => (current?.api_key_configured ? current : null));
      }
    } catch (error) {
      if (showSpinner) message.error(error instanceof Error ? error.message : '加载失败');
    } finally {
      if (showSpinner) setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);
  useBackendEvents(['settings.updated', 'jobs.updated'], () => load(false));

  const runTask = async (task: 'bootstrap' | 'market' | 'history' | 'missingDailyKline' | 'intraday' | 'news' | 'simplifyNews') => {
    setLoading(true);
    try {
      let backgroundStatus: 'started' | 'already_running' | undefined;
      if (task === 'bootstrap') await api.collectBootstrap();
      if (task === 'market') await api.collectMarket();
      if (task === 'history') backgroundStatus = (await api.collectFullMarketHistory()).status;
      if (task === 'missingDailyKline') backgroundStatus = (await api.collectMissingDailyKline()).status;
      if (task === 'intraday') await api.collectIntraday();
      if (task === 'news') await api.collectNews();
      if (task === 'simplifyNews') await api.simplifyPendingNews(50);
      if (task === 'history' || task === 'missingDailyKline') {
        if (backgroundStatus === 'already_running') message.info('日 K 后台任务已在运行');
        else message.success('日 K 后台任务已启动');
      } else {
        message.success('任务执行完成');
      }
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
      if (next.api_key_configured) {
        try {
          const status = await api.validateNewsLlmConfig();
          setNewsLlmKeyStatus(status);
        } catch (error) {
          message.warning(error instanceof Error ? error.message : 'Key 检测失败');
        }
      } else {
        setNewsLlmKeyStatus({
          provider: next.provider,
          model: next.model,
          api_base_url: next.api_base_url,
          api_key_configured: false,
          ok: false,
          status: 'missing',
          message: 'API Key 未配置',
        });
      }
      await load(true);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存失败');
    } finally {
      setLoading(false);
    }
  };

  const validateNewsLlmKey = useCallback(async () => {
    setValidatingKey(true);
    try {
      const status = await api.validateNewsLlmConfig();
      setNewsLlmKeyStatus(status);
      if (status.ok) message.success(status.message);
      else message.warning(status.message);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '检测失败');
    } finally {
      setValidatingKey(false);
    }
  }, []);

  return (
    <>
      <PageHeader
        title="Settings"
        description="真实行情数据源、PostgreSQL 运行状态、采集风控和任务状态"
        extra={<Button icon={<ReloadOutlined />} onClick={() => load(true)}>刷新</Button>}
      />
      <SettingsCards settings={settings} />
      <NewsLlmConfigCard
        config={newsLlmConfig}
        keyStatus={newsLlmKeyStatus}
        loading={loading}
        validating={validatingKey}
        onSave={saveNewsLlmConfig}
        onValidate={validateNewsLlmKey}
      />
      <TaskActions loading={loading} runTask={runTask} />
      <Card title="任务记录" className="table-card section-gap">
        <Table<CollectionJob> rowKey="id" loading={loading} dataSource={jobs} columns={jobColumns} pagination={{ pageSize: 8 }} />
      </Card>
    </>
  );
}
