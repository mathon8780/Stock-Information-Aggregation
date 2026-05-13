import { Alert, Card, Empty } from 'antd';
import PageHeader from '../components/PageHeader';

export default function News() {
  return (
    <>
      <PageHeader
        title="News"
        description="新闻采集本轮未启用，当前系统只使用真实行情和历史 K 线进行策略分析"
      />
      <Card className="data-surface">
        <Alert
          showIcon
          type="info"
          message="暂不处理新闻内容"
          description="本轮暂不处理新闻数据源。后续接入真实新闻源时会重新启用该页面。"
        />
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无新闻数据" style={{ marginTop: 32 }} />
      </Card>
    </>
  );
}
