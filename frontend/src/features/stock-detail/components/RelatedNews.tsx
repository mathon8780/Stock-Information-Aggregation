import { Card, List, Space, Typography } from 'antd';
import { formatTime } from '../../../api/client';
import SentimentTag from '../../../components/SentimentTag';
import type { NewsItem } from '../../../types';

export default function RelatedNews({ news }: { news: NewsItem[] }) {
  return (
    <Card title="相关新闻">
      <List
        className="compact-list"
        dataSource={news}
        renderItem={(item: NewsItem) => (
          <List.Item>
            <List.Item.Meta
              title={<Space><SentimentTag sentiment={item.sentiment} /><Typography.Text>{item.title}</Typography.Text></Space>}
              description={<Typography.Text type="secondary">{item.source} · {formatTime(item.published_at)}</Typography.Text>}
            />
          </List.Item>
        )}
      />
    </Card>
  );
}
