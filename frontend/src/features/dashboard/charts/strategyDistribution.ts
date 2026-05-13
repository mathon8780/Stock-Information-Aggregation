import type { Advice } from '../../../types';

export function createStrategyDistributionOption(advice: Advice[]) {
  const grouped = advice.reduce<Record<string, number>>((acc, item) => {
    acc[item.signal] = (acc[item.signal] ?? 0) + 1;
    return acc;
  }, {});

  return {
    color: ['#0f766e', '#2563eb', '#d97706', '#8b5cf6', '#64748b'],
    tooltip: { trigger: 'item' },
    legend: {
      bottom: 0,
      itemWidth: 10,
      itemHeight: 10,
      textStyle: { color: '#60707b' },
    },
    series: [
      {
        type: 'pie',
        radius: ['52%', '74%'],
        center: ['50%', '45%'],
        label: { formatter: '{b}: {c}', color: '#42515c' },
        data: Object.entries(grouped).map(([name, value]) => ({ name, value })),
      },
    ],
  };
}
