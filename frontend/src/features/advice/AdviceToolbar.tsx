import { Button, Select, Space } from 'antd';

export default function AdviceToolbar({ signal, setSignal, onApply }: { signal?: string; setSignal: (value?: string) => void; onApply: () => void }) {
  return (
    <div className="toolbar">
      <Space wrap>
        <Select
          allowClear
          aria-label="策略类型"
          placeholder="策略类型"
          value={signal}
          onChange={setSignal}
          style={{ width: 160 }}
          options={['重点关注', '谨慎买入', '持有', '减仓', '回避'].map((value) => ({ label: value, value }))}
        />
        <Button onClick={onApply}>应用筛选</Button>
      </Space>
    </div>
  );
}
