import { Button, Empty, Modal, Tag } from 'antd';
import { useState } from 'react';
import { formatTime } from '../../api/client';
import SentimentTag from '../../components/SentimentTag';
import StockLink from '../../components/StockLink';
import type { NewsItem } from '../../types';

export function safeNewsUrl(value?: string | null) {
  try {
    const url = new URL(value || '');
    return ['http:', 'https:'].includes(url.protocol) ? url.href : undefined;
  } catch {
    return undefined;
  }
}

export default function NewsReader({ items, compact = false }: { items: NewsItem[]; compact?: boolean }) {
  const [selected, setSelected] = useState<NewsItem | null>(null);
  const title = (item: NewsItem) =>
    item.simplification_status === 'simplified' ? item.title : item.original_title || item.title;
  return (
    <>
      <div className={compact ? 'brief-list' : 'news-reading-list'}>
        {items.map((item) => (
          <article key={item.id} className="news-reading-item">
            <div className="news-reading-meta">
              <span className="news-source">{item.source.replace(/^newsnow:/, '')}</span>
              <time>{formatTime(item.published_at || item.fetched_at)}</time>
            </div>
            <button className="news-reading-title" onClick={() => setSelected(item)}>
              {title(item)}
            </button>
            {!compact && (item.code || item.stock?.code) && (
              <StockLink code={item.code || item.stock!.code} name={item.name || item.stock?.name} />
            )}
            {!compact && (
              <p>
                {item.simplification_status === 'simplified'
                  ? item.summary || '暂无摘要'
                  : item.simplification_status === 'failed'
                    ? '摘要整理失败，可展开查看原始内容。'
                    : '等待摘要整理，可展开查看原始标题。'}
              </p>
            )}
            <div className="news-reading-footer">
              <div>
                <Tag>{{ simplified: '已整理', pending: '待整理', failed: '整理失败' }[item.simplification_status]}</Tag>
                <SentimentTag sentiment={item.sentiment} />
                {!compact && (
                  <small>
                    重要性 {item.importance} · {item.scope === 'stock' ? '个股' : '市场'}
                  </small>
                )}
              </div>
              {!compact && (
                <Button type="link" size="small" onClick={() => setSelected(item)}>
                  阅读摘要
                </Button>
              )}
            </div>
          </article>
        ))}
      </div>
      {!items.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无匹配资讯" />}
      <Modal
        title={selected ? title(selected) : '新闻摘要'}
        open={Boolean(selected)}
        onCancel={() => setSelected(null)}
        footer={
          <>
            {safeNewsUrl(selected?.url) && (
              <a href={safeNewsUrl(selected?.url)} target="_blank" rel="noopener noreferrer">
                打开原文 ↗
              </a>
            )}
            <Button onClick={() => setSelected(null)}>关闭</Button>
          </>
        }
      >
        <p className="news-detail-copy">
          {selected?.content || selected?.summary || selected?.original_title || selected?.title}
        </p>
        <div className="news-detail-meta">
          {(selected?.code || selected?.stock?.code) && (
            <p>
              <StockLink code={selected.code || selected.stock!.code} name={selected.name || selected.stock?.name} />
            </p>
          )}
          <p>来源：{selected?.source.replace(/^newsnow:/, '')}</p>
          <p>
            发布：{formatTime(selected?.published_at)} · 整理：{formatTime(selected?.simplified_at)}
          </p>
          {selected?.llm_model && (
            <p>
              整理模型：{selected.llm_provider} / {selected.llm_model}
            </p>
          )}
          {selected?.error_message && <p className="positive">{selected.error_message}</p>}
        </div>
      </Modal>
    </>
  );
}
