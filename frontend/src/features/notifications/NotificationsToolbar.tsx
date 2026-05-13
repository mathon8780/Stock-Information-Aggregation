import { Button, Select, Space } from 'antd';

export default function NotificationsToolbar({ status, setStatus, onApply }: { status?: string; setStatus: (value?: string) => void; onApply: () => void }) {
  return (
    <div className="toolbar">
      <Space wrap>
        <Select
          allowClear
          aria-label="推送状态"
          placeholder="状态"
          value={status}
          onChange={setStatus}
          style={{ width: 150 }}
          options={[{ label: 'pending', value: 'pending' }, { label: 'sent', value: 'sent' }, { label: 'failed', value: 'failed' }]}
        />
        <Button onClick={onApply}>应用筛选</Button>
      </Space>
    </div>
  );
}
