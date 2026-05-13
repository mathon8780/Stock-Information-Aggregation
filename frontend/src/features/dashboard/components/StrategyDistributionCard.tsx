import { Card } from 'antd';
import ReactECharts from 'echarts-for-react';
import { createStrategyDistributionOption } from '../charts/strategyDistribution';
import type { Advice } from '../../../types';

export default function StrategyDistributionCard({ advice }: { advice: Advice[] }) {
  return (
    <Card title="策略分布" className="dashboard-panel">
      <ReactECharts option={createStrategyDistributionOption(advice)} style={{ height: 280 }} />
    </Card>
  );
}
