import { Button, Select, Space } from 'antd';

export default function NotificationsToolbar({
  notificationType,
  setNotificationType,
  onApply,
}: {
  notificationType?: string;
  setNotificationType: (value?: string) => void;
  onApply: () => void;
}) {
  return (
    <div className="toolbar">
      <Space wrap>
        <Select
          allowClear
          aria-label="通知类型"
          placeholder="类型"
          value={notificationType}
          onChange={setNotificationType}
          style={{ width: 150 }}
          options={[
            { label: '策略变化', value: 'strategy_change' },
            { label: '行情异动', value: 'price_alert' },
            { label: '新闻摘要', value: 'news_digest' },
            { label: '重大事件', value: 'major_event' },
            { label: '模拟成交', value: 'paper_trade' },
            { label: '模拟委托', value: 'paper_order' },
            { label: '模拟风控', value: 'paper_risk' },
          ]}
        />
        <Button onClick={onApply}>应用筛选</Button>
      </Space>
    </div>
  );
}
