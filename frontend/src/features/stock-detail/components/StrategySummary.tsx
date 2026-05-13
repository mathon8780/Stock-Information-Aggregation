import { Card, Space, Typography } from 'antd';
import { formatNumber } from '../../../api/client';
import SignalTag from '../../../components/SignalTag';
import type { Advice } from '../../../types';

export default function StrategySummary({ advice }: { advice?: Advice | null }) {
  return (
    <Card title="当前策略" className="strategy-card">
      <Space direction="vertical" size={10}>
        <Space>
          <SignalTag signal={advice?.signal} />
          <Typography.Text strong>{formatNumber(advice?.confidence, 0)}%</Typography.Text>
        </Space>
        <Typography.Text>{advice?.reasoning ?? '暂无策略'}</Typography.Text>
        <Typography.Text type="secondary">{advice?.strategy}</Typography.Text>
      </Space>
    </Card>
  );
}
