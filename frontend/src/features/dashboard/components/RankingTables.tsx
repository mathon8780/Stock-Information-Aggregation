import { Card, Col, Row, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { changeColor, formatCompact, formatNumber } from '../../../api/client';
import StockLink from '../../../components/StockLink';
import type { Snapshot } from '../../../types';

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

export default function RankingTables({ topGainers, topLosers }: { topGainers: Snapshot[]; topLosers: Snapshot[] }) {
  return (
    <Card title="涨跌榜" className="table-card dashboard-panel">
      <Row gutter={16}>
        <Col xs={24} md={12}>
          <div className="table-section-title">强势排行</div>
          <Table<Snapshot> size="small" rowKey="code" pagination={false} dataSource={topGainers} columns={rankColumns} />
        </Col>
        <Col xs={24} md={12}>
          <div className="table-section-title">弱势排行</div>
          <Table<Snapshot> size="small" rowKey="code" pagination={false} dataSource={topLosers} columns={rankColumns} />
        </Col>
      </Row>
    </Card>
  );
}
