import { ReloadOutlined } from '@ant-design/icons';
import { Button, Card, Table, message } from 'antd';
import { useEffect, useState } from 'react';
import { api } from '../api/client';
import PageHeader from '../components/PageHeader';
import SettingsCards from '../features/settings/SettingsCards';
import TaskActions from '../features/settings/TaskActions';
import { jobColumns } from '../features/settings/jobColumns';
import type { CollectionJob } from '../types';

export default function Settings() {
  const [settings, setSettings] = useState<Record<string, any> | null>(null);
  const [jobs, setJobs] = useState<CollectionJob[]>([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [s, j] = await Promise.all([api.settings(), api.jobs(20)]);
      setSettings(s);
      setJobs(j.items);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const runTask = async (task: 'bootstrap' | 'market' | 'history' | 'intraday') => {
    setLoading(true);
    try {
      if (task === 'bootstrap') await api.collectBootstrap();
      if (task === 'market') await api.collectMarket();
      if (task === 'history') await api.collectHistory();
      if (task === 'intraday') await api.collectIntraday();
      message.success('任务执行完成');
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '执行失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Settings"
        description="真实行情数据源、PostgreSQL 运行状态、采集风控和任务状态"
        extra={<Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>}
      />
      <SettingsCards settings={settings} />
      <TaskActions loading={loading} runTask={runTask} />
      <Card title="任务记录" className="table-card section-gap">
        <Table<CollectionJob> rowKey="id" loading={loading} dataSource={jobs} columns={jobColumns} pagination={{ pageSize: 8 }} />
      </Card>
    </>
  );
}
