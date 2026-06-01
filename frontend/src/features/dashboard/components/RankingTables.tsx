import { useState } from 'react';
import { Card, Col, Row, Segmented, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { changeColor, formatCompact, formatNumber } from '../../../api/client';
import StockLink from '../../../components/StockLink';
import type { Snapshot } from '../../../types';

type RankingMode = 'up' | 'down';

type RankingGroup = {
  strong: Snapshot[];
  weak: Snapshot[];
};

const rankColumns: ColumnsType<Snapshot> = [
  { title: '股票', render: (_: unknown, row: Snapshot) => <StockLink code={row.code} name={row.name} /> },
  { title: '价格', align: 'right', render: (_: unknown, row: Snapshot) => <span className="number-cell">{formatNumber(row.price, 2)}</span> },
  {
    title: '涨跌幅',
    align: 'right',
    render: (_: unknown, row: Snapshot) => (
      <span style={{ color: changeColor(row.change_pct), fontVariantNumeric: 'tabular-nums' }}>{formatNumber(row.change_pct, 2)}%</span>
    ),
  },
  { title: '成交额', align: 'right', render: (_: unknown, row: Snapshot) => formatCompact(row.amount) },
];

export default function RankingTables({ upRanks, downRanks }: { upRanks: RankingGroup; downRanks: RankingGroup }) {
  const [mode, setMode] = useState<RankingMode>('up');
  const activeRanks = mode === 'up' ? upRanks : downRanks;
  const emptyText = mode === 'up' ? '暂无上涨股票' : '暂无下跌股票';

  return (
    <Card
      title="涨跌榜"
      className="table-card dashboard-panel ranking-card"
      extra={(
        <Segmented
          size="small"
          value={mode}
          onChange={(value) => setMode(value as RankingMode)}
          options={[
            { label: '涨榜', value: 'up' },
            { label: '跌榜', value: 'down' },
          ]}
        />
      )}
    >
      <Row gutter={16}>
        <Col xs={24} md={12}>
          <div className="table-section-title">强势排行</div>
          <Table<Snapshot> size="small" rowKey="code" pagination={false} dataSource={activeRanks.strong} columns={rankColumns} locale={{ emptyText }} />
        </Col>
        <Col xs={24} md={12}>
          <div className="table-section-title">弱势排行</div>
          <Table<Snapshot> size="small" rowKey="code" pagination={false} dataSource={activeRanks.weak} columns={rankColumns} locale={{ emptyText }} />
        </Col>
      </Row>
    </Card>
  );
}
