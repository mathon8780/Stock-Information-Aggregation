import { Card, Descriptions } from 'antd';
import { formatNumber } from '../../../api/client';

export default function TechnicalIndicators({ indicators }: { indicators: Record<string, any> }) {
  return (
    <Card title="技术指标">
      <Descriptions column={1} size="small">
        <Descriptions.Item label="MA5 / MA20">{formatNumber(indicators.ma5, 2)} / {formatNumber(indicators.ma20, 2)}</Descriptions.Item>
        <Descriptions.Item label="MA60">{formatNumber(indicators.ma60, 2)}</Descriptions.Item>
        <Descriptions.Item label="MACD">{indicators.macd?.cross ?? '-'} · {formatNumber(indicators.macd?.histogram, 4)}</Descriptions.Item>
        <Descriptions.Item label="RSI14">{formatNumber(indicators.rsi14, 2)}</Descriptions.Item>
        <Descriptions.Item label="BOLL">{formatNumber(indicators.boll?.lower, 2)} - {formatNumber(indicators.boll?.upper, 2)}</Descriptions.Item>
        <Descriptions.Item label="KDJ">{formatNumber(indicators.kdj?.k, 2)} / {formatNumber(indicators.kdj?.d, 2)} / {formatNumber(indicators.kdj?.j, 2)}</Descriptions.Item>
      </Descriptions>
    </Card>
  );
}
