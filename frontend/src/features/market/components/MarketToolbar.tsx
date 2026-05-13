import { Button, Input, Select, Space } from 'antd';

interface MarketToolbarProps {
  q: string;
  market?: string;
  setQ: (value: string) => void;
  setMarket: (value?: string) => void;
  onApply: () => void;
}

export default function MarketToolbar({ q, market, setQ, setMarket, onApply }: MarketToolbarProps) {
  return (
    <div className="toolbar">
      <Space wrap>
        <Input.Search
          allowClear
          aria-label="搜索代码、名称、行业"
          placeholder="代码、名称、行业"
          value={q}
          onChange={(event) => setQ(event.target.value)}
          onSearch={onApply}
          style={{ width: 260 }}
        />
        <Select
          allowClear
          aria-label="市场筛选"
          placeholder="市场"
          value={market}
          onChange={setMarket}
          style={{ width: 140 }}
          options={[
            { label: '沪市', value: 'SH' },
            { label: '深市', value: 'SZ' },
            { label: '指数', value: 'INDEX' },
          ]}
        />
        <Button onClick={onApply}>应用筛选</Button>
      </Space>
    </div>
  );
}
