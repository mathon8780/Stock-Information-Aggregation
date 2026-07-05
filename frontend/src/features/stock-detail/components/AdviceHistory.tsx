import { Card, Empty } from 'antd';
import ReactECharts from 'echarts-for-react';
import { useMemo } from 'react';
import { createAdviceTrendOption } from '../charts/stockCharts';
import { useThemeMode } from '../../../theme/ThemeModeContext';
import type { Advice } from '../../../types';

export default function AdviceHistory({ history }: { history: Advice[] }) {
  const { mode: themeMode } = useThemeMode();
  const option = useMemo(() => createAdviceTrendOption(history, themeMode), [history, themeMode]);

  return (
    <Card title="历史建议">
      {history.length > 0 ? (
        <ReactECharts option={option} className="advice-trend-chart" style={{ height: 280 }} />
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无历史建议" />
      )}
    </Card>
  );
}
