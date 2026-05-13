import { Card, Space, Timeline, Typography } from 'antd';
import { formatNumber, formatTime } from '../../../api/client';
import SignalTag from '../../../components/SignalTag';
import type { Advice } from '../../../types';

export default function AdviceHistory({ history }: { history: Advice[] }) {
  return (
    <Card title="历史建议">
      <Timeline
        items={history.map((item) => ({
          children: (
            <Space direction="vertical" size={2}>
              <Space><SignalTag signal={item.signal} /><span>{formatNumber(item.confidence, 0)}%</span></Space>
              <Typography.Text type="secondary">{formatTime(item.created_at)}</Typography.Text>
            </Space>
          ),
        }))}
      />
    </Card>
  );
}
