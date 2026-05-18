import { PlayCircleOutlined } from '@ant-design/icons';
import { Button, Card, Space } from 'antd';

export default function TaskActions({ loading, runTask }: { loading: boolean; runTask: (task: 'bootstrap' | 'market' | 'history' | 'intraday' | 'news' | 'simplifyNews') => void }) {
  return (
    <Card title="真实数据同步" className="section-gap">
      <Space wrap>
        <Button icon={<PlayCircleOutlined />} loading={loading} type="primary" onClick={() => runTask('bootstrap')}>初始化真实数据</Button>
        <Button icon={<PlayCircleOutlined />} loading={loading} onClick={() => runTask('market')}>刷新全市场快照</Button>
        <Button icon={<PlayCircleOutlined />} loading={loading} onClick={() => runTask('history')}>启动全市场近一年日 K</Button>
        <Button icon={<PlayCircleOutlined />} loading={loading} onClick={() => runTask('intraday')}>同步自选股 10 日 5 分钟 K</Button>
        <Button icon={<PlayCircleOutlined />} loading={loading} onClick={() => runTask('news')}>同步新闻元数据</Button>
        <Button icon={<PlayCircleOutlined />} loading={loading} onClick={() => runTask('simplifyNews')}>简化未处理新闻</Button>
      </Space>
    </Card>
  );
}
