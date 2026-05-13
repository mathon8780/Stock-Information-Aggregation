import { Card, Descriptions } from 'antd';
import { formatCompact, formatNumber, formatTime } from '../../../api/client';
import PriceText from '../../../components/PriceText';
import type { Snapshot } from '../../../types';

export default function QuoteOverview({ snapshot }: { snapshot?: Snapshot | null }) {
  return (
    <Card title="行情概览">
      <Descriptions column={{ xs: 1, sm: 2, md: 4 }} size="small">
        <Descriptions.Item label="最新价">{formatNumber(snapshot?.price, 2)}</Descriptions.Item>
        <Descriptions.Item label="涨跌幅"><PriceText value={snapshot?.change_pct} suffix="%" /></Descriptions.Item>
        <Descriptions.Item label="涨跌额"><PriceText value={snapshot?.change_amount} /></Descriptions.Item>
        <Descriptions.Item label="成交量">{formatCompact(snapshot?.volume)}</Descriptions.Item>
        <Descriptions.Item label="今开">{formatNumber(snapshot?.open, 2)}</Descriptions.Item>
        <Descriptions.Item label="最高">{formatNumber(snapshot?.high, 2)}</Descriptions.Item>
        <Descriptions.Item label="最低">{formatNumber(snapshot?.low, 2)}</Descriptions.Item>
        <Descriptions.Item label="更新时间">{formatTime(snapshot?.snapshot_time)}</Descriptions.Item>
      </Descriptions>
    </Card>
  );
}
