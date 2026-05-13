import { Card, List, Space, Typography } from 'antd';
import { formatTime } from '../../../api/client';
import type { NewsItem } from '../../../types';

export default function LatestNewsCard({ news }: { news: NewsItem[] }) {
  return (
    <Card title="最新资讯">
      <List
        className="compact-list"
        dataSource={news}
        renderItem={(item: NewsItem) => (
          <List.Item>
            <List.Item.Meta
              title={<Typography.Text>{item.title}</Typography.Text>}
              description={(
                <Space direction="vertical" size={2}>
                  <Typography.Text type="secondary">{item.source} · {formatTime(item.published_at)}</Typography.Text>
                  <Typography.Text type="secondary">{item.summary}</Typography.Text>
                </Space>
              )}
            />
          </List.Item>
        )}
      />
    </Card>
  );
}
