import { Empty } from 'antd';
import { Link } from 'react-router-dom';
import { formatNumber, formatTime } from '../../api/client';
import SignalTag from '../../components/SignalTag';
import StockLink from '../../components/StockLink';
import type { Advice } from '../../types';

export default function AdviceCards({ items }: { items: Advice[] }) {
  return items.length ? (
    <div className="advice-grid">
      {items.map((item) => (
        <article className="advice-card" key={item.id}>
          <header>
            {item.code || item.stock?.code ? (
              <StockLink code={item.code || item.stock!.code} name={item.name || item.stock?.name} />
            ) : (
              <span>未知标的</span>
            )}
            <SignalTag signal={item.signal} />
          </header>
          <div className="advice-confidence">
            <span style={{ width: `${Math.max(0, Math.min(100, item.confidence))}%` }} />
            <small>置信度 {formatNumber(item.confidence, 0)}%</small>
          </div>
          <h3>判断依据</h3>
          <p>{item.reasoning}</p>
          <h3>观察建议</h3>
          <p>{item.strategy || '暂无建议'}</p>
          <h3>风险提示</h3>
          <p className="muted">{item.risk_notes || '暂无风险说明'}</p>
          <footer>
            <time>{formatTime(item.created_at)}</time>
            {(item.code || item.stock?.code) && <Link to={`/stock/${item.code || item.stock?.code}`}>查看详情 ↗</Link>}
          </footer>
        </article>
      ))}
    </div>
  ) : (
    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配的策略" />
  );
}
