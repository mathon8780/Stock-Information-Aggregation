import { PlusOutlined, StarOutlined } from '@ant-design/icons';
import { Button, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { formatCompact, formatNumber } from '../../../api/client';
import PriceText from '../../../components/PriceText';
import StockLink from '../../../components/StockLink';
import type { Snapshot } from '../../../types';

export function createMarketColumns(watchCodes: Set<string>, addWatch: (code: string) => void): ColumnsType<Snapshot> {
  return [
    { title: '股票', fixed: 'left', render: (_: unknown, row: Snapshot) => <StockLink code={row.code} name={row.name} /> },
    { title: '市场', dataIndex: 'market', width: 80, render: (value: string) => <Tag>{value}</Tag> },
    { title: '行业', dataIndex: 'industry', width: 110, ellipsis: true },
    { title: '最新价', align: 'right', render: (_: unknown, row: Snapshot) => formatNumber(row.price, 2) },
    { title: '涨跌幅', align: 'right', render: (_: unknown, row: Snapshot) => <PriceText value={row.change_pct} suffix="%" /> },
    { title: '成交量', align: 'right', render: (_: unknown, row: Snapshot) => formatCompact(row.volume) },
    { title: '成交额', align: 'right', render: (_: unknown, row: Snapshot) => formatCompact(row.amount) },
    { title: '换手率', align: 'right', render: (_: unknown, row: Snapshot) => `${formatNumber(row.turnover_rate, 2)}%` },
    { title: '量比', align: 'right', render: (_: unknown, row: Snapshot) => formatNumber(row.volume_ratio, 2) },
    { title: 'PE', align: 'right', render: (_: unknown, row: Snapshot) => formatNumber(row.pe, 2) },
    { title: 'PB', align: 'right', render: (_: unknown, row: Snapshot) => formatNumber(row.pb, 2) },
    {
      title: '关注',
      width: 92,
      render: (_: unknown, row: Snapshot) => (
        <Button
          aria-label={watchCodes.has(row.code) ? '已关注' : '加入关注'}
          size="small"
          icon={watchCodes.has(row.code) ? <StarOutlined /> : <PlusOutlined />}
          disabled={watchCodes.has(row.code)}
          onClick={() => addWatch(row.code)}
        />
      ),
    },
  ];
}
