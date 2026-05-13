import { Button, Select, Space } from 'antd';

interface NewsToolbarProps {
  scope?: string;
  sentiment?: string;
  setScope: (value?: string) => void;
  setSentiment: (value?: string) => void;
  onApply: () => void;
}

export default function NewsToolbar({ scope, sentiment, setScope, setSentiment, onApply }: NewsToolbarProps) {
  return (
    <div className="toolbar">
      <Space wrap>
        <Select
          allowClear
          aria-label="新闻范围"
          placeholder="范围"
          value={scope}
          onChange={setScope}
          style={{ width: 140 }}
          options={[{ label: '市场', value: 'market' }, { label: '个股', value: 'stock' }]}
        />
        <Select
          allowClear
          aria-label="新闻情绪"
          placeholder="情绪"
          value={sentiment}
          onChange={setSentiment}
          style={{ width: 140 }}
          options={[{ label: '积极', value: 'positive' }, { label: '中性', value: 'neutral' }, { label: '负面', value: 'negative' }]}
        />
        <Button onClick={onApply}>应用筛选</Button>
      </Space>
    </div>
  );
}
