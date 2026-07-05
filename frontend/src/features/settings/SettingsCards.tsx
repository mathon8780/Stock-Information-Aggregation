import { ControlOutlined, DatabaseOutlined, FileSearchOutlined, SafetyOutlined, SettingOutlined } from '@ant-design/icons';
import { Button, Card, Descriptions, Form, InputNumber, Radio, Space, Tag, message } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import {
  ANALYSIS_ENGINE_OPTIONS,
  COLLECTION_INTERVAL_DEFAULTS,
  FRONTEND_SETTINGS_STORAGE_KEY,
  type CollectionIntervalKey,
  type FrontendSettingsConfig,
  createDefaultFrontendSettings,
  normalizeFrontendSettingsConfig,
} from './settingsConfig';

const intervalLabels: Record<CollectionIntervalKey, string> = {
  market_snapshot_seconds: '全市场',
  watch_snapshot_seconds: '关注股',
  news_seconds: '资讯',
  news_auto_sync_seconds: '自动资讯',
  advice_seconds: '策略',
};

function NumberItem({
  label,
  name,
  min,
  unit,
}: {
  label: string;
  name: (string | number)[];
  min: number;
  unit?: string;
}) {
  return (
    <div className="settings-number-row">
      <span className="settings-number-label">{label}</span>
      <div className="settings-number-control">
        <Form.Item name={name} noStyle>
          <InputNumber aria-label={label} min={min} precision={0} className="settings-number-input" />
        </Form.Item>
        {unit ? <span className="settings-input-unit">{unit}</span> : null}
      </div>
    </div>
  );
}

function readStoredConfig(): (Partial<FrontendSettingsConfig> & { analysis_engines?: string[] }) | null {
  try {
    const raw = localStorage.getItem(FRONTEND_SETTINGS_STORAGE_KEY);
    return raw ? JSON.parse(raw) as Partial<FrontendSettingsConfig> & { analysis_engines?: string[] } : null;
  } catch {
    return null;
  }
}

function writeStoredConfig(config: FrontendSettingsConfig): void {
  localStorage.setItem(FRONTEND_SETTINGS_STORAGE_KEY, JSON.stringify(config));
}

export default function SettingsCards({ settings }: { settings: Record<string, any> | null }) {
  const [form] = Form.useForm<FrontendSettingsConfig>();
  const defaults = useMemo(() => createDefaultFrontendSettings(settings), [settings]);
  const [hasStoredConfig, setHasStoredConfig] = useState(() => Boolean(readStoredConfig()));
  const [config, setConfig] = useState<FrontendSettingsConfig>(() => normalizeFrontendSettingsConfig(readStoredConfig(), defaults));

  const analysisOptions = useMemo(() => {
    const current = settings?.analysis_engine ? String(settings.analysis_engine) : '';
    if (!current || ANALYSIS_ENGINE_OPTIONS.some((item) => item.value === current)) return ANALYSIS_ENGINE_OPTIONS;
    return [{ label: current, value: current }, ...ANALYSIS_ENGINE_OPTIONS];
  }, [settings?.analysis_engine]);

  useEffect(() => {
    if (!hasStoredConfig) {
      setConfig(defaults);
      return;
    }
    setConfig((current) => normalizeFrontendSettingsConfig(current, defaults));
  }, [defaults, hasStoredConfig]);

  useEffect(() => {
    form.setFieldsValue(config);
  }, [config, form]);

  const saveConfig = (values: FrontendSettingsConfig) => {
    const next = normalizeFrontendSettingsConfig(values, defaults);
    setConfig(next);
    writeStoredConfig(next);
    setHasStoredConfig(true);
    message.success('前端配置已保存');
  };

  const resetConfig = () => {
    setConfig(defaults);
    localStorage.removeItem(FRONTEND_SETTINGS_STORAGE_KEY);
    setHasStoredConfig(false);
    form.setFieldsValue(defaults);
    message.success('已恢复默认值');
  };

  return (
    <Form<FrontendSettingsConfig> form={form} layout="vertical" onFinish={saveConfig}>
      <div className="settings-grid">
        <Card title={<Space><DatabaseOutlined />运行环境</Space>}>
          <Descriptions column={1} size="small">
            <Descriptions.Item label="环境">{settings?.app_env ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="数据库">{settings?.database ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="数据源">{settings?.market_data_primary ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="启动自动填充">{String(settings?.auto_seed_demo_data ?? false)}</Descriptions.Item>
            <Descriptions.Item label="新闻整理">{settings?.news?.llm_provider ?? '-'} / {settings?.news?.model ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="LLM 地址">{settings?.news?.api_base_url ?? '-'}</Descriptions.Item>
          </Descriptions>
        </Card>

        <Card title={<Space><ControlOutlined />分析引擎</Space>}>
          <Form.Item name="analysis_engine" rules={[{ required: true, message: '请选择分析引擎' }]}>
            <Radio.Group options={analysisOptions} className="settings-radio-group" />
          </Form.Item>
          <Space size={6} wrap>
            <Tag>{config.analysis_engine}</Tag>
          </Space>
        </Card>

        <Card title={<Space><FileSearchOutlined />采集间隔</Space>}>
          {(Object.keys(COLLECTION_INTERVAL_DEFAULTS) as CollectionIntervalKey[]).map((key) => (
            <NumberItem
              key={key}
              label={`${intervalLabels[key]}（≥${COLLECTION_INTERVAL_DEFAULTS[key]}s）`}
              name={['collection_intervals', key]}
              min={COLLECTION_INTERVAL_DEFAULTS[key]}
              unit="s"
            />
          ))}
        </Card>

        <Card title={<Space><SafetyOutlined />风控策略</Space>}>
          <NumberItem label="最小请求间隔" name={['risk_control', 'request_min_interval_seconds']} min={1} unit="s" />
          <NumberItem label="失败降频阈值" name={['risk_control', 'fetch_failure_downgrade_threshold']} min={1} />
          <NumberItem label="自选股上限" name={['risk_control', 'max_watchlist_size']} min={1} />
        </Card>
      </div>

      <div className="settings-actions">
        <Button type="primary" htmlType="submit" icon={<SettingOutlined />}>保存前端配置</Button>
        <Button onClick={resetConfig}>恢复默认值</Button>
      </div>
    </Form>
  );
}
