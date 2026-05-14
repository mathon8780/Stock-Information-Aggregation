import { DatabaseOutlined, FileSearchOutlined } from '@ant-design/icons';
import { Card, Descriptions, Space } from 'antd';

export default function SettingsCards({ settings }: { settings: Record<string, any> | null }) {
  return (
    <div className="settings-grid">
      <Card title={<Space><DatabaseOutlined />运行环境</Space>}>
        <Descriptions column={1} size="small">
          <Descriptions.Item label="环境">{settings?.app_env}</Descriptions.Item>
          <Descriptions.Item label="数据库">{settings?.database}</Descriptions.Item>
          <Descriptions.Item label="数据源">{settings?.market_data_primary}</Descriptions.Item>
          <Descriptions.Item label="启动自动填充">{String(settings?.auto_seed_demo_data)}</Descriptions.Item>
          <Descriptions.Item label="分析引擎">{settings?.analysis_engine}</Descriptions.Item>
          <Descriptions.Item label="新闻整理">{settings?.news?.llm_provider} / {settings?.news?.model}</Descriptions.Item>
          <Descriptions.Item label="LLM 地址">{settings?.news?.api_base_url}</Descriptions.Item>
          <Descriptions.Item label="新闻 Key">{settings?.news?.api_key_configured ? '已配置' : '未配置'}</Descriptions.Item>
        </Descriptions>
      </Card>
      <Card title={<Space><FileSearchOutlined />采集间隔</Space>}>
        <Descriptions column={1} size="small">
          <Descriptions.Item label="全市场">{settings?.collector_intervals?.market_snapshot_seconds}s</Descriptions.Item>
          <Descriptions.Item label="关注股">{settings?.collector_intervals?.watch_snapshot_seconds}s</Descriptions.Item>
          <Descriptions.Item label="资讯">{settings?.collector_intervals?.news_seconds}s</Descriptions.Item>
          <Descriptions.Item label="策略">{settings?.collector_intervals?.advice_seconds}s</Descriptions.Item>
        </Descriptions>
      </Card>
      <Card title="风控与默认自选股">
        <Descriptions column={1} size="small">
          <Descriptions.Item label="最小请求间隔">{settings?.risk_control?.request_min_interval_seconds}s</Descriptions.Item>
          <Descriptions.Item label="失败降频阈值">{settings?.risk_control?.fetch_failure_downgrade_threshold}</Descriptions.Item>
          <Descriptions.Item label="自选股上限">{settings?.risk_control?.max_watchlist_size}</Descriptions.Item>
          <Descriptions.Item label="默认主题">CPO + AI 算力</Descriptions.Item>
        </Descriptions>
      </Card>
    </div>
  );
}
