import { Card, Table } from 'antd';
import { formatNumber } from '../../../api/client';
import PriceText from '../../../components/PriceText';
import SignalTag from '../../../components/SignalTag';
import StockLink from '../../../components/StockLink';
import type { WatchItem } from '../../../types';

export default function WatchlistOverview({ watchlist }: { watchlist: WatchItem[] }) {
  return (
    <Card title="自选股概览" className="table-card">
      <Table<WatchItem>
        size="small"
        rowKey={(row) => row.stock.code}
        pagination={false}
        dataSource={watchlist}
        columns={[
          { title: '股票', render: (_: unknown, row: WatchItem) => <StockLink code={row.stock.code} name={row.stock.name} /> },
          { title: '最新价', align: 'right', render: (_: unknown, row: WatchItem) => formatNumber(row.latest_snapshot?.price, 2) },
          { title: '涨跌幅', align: 'right', render: (_: unknown, row: WatchItem) => <PriceText value={row.latest_snapshot?.change_pct} suffix="%" /> },
          { title: '策略', render: (_: unknown, row: WatchItem) => <SignalTag signal={row.latest_advice?.signal} /> },
          { title: '置信度', align: 'right', render: (_: unknown, row: WatchItem) => row.latest_advice ? `${formatNumber(row.latest_advice.confidence, 0)}%` : '-' },
        ]}
      />
    </Card>
  );
}
