import { Card, Empty, Typography } from 'antd';
import type { CSSProperties } from 'react';
import { formatTime } from '../../../api/client';
import type { NewsItem } from '../../../types';

type SourceTheme = {
  accent: string;
  tint: string;
  label: string;
};

const sourceThemes: Record<string, SourceTheme> = {
  财联社: { accent: '#0f766e', tint: '#eef8f6', label: '财联社' },
  华尔街见闻: { accent: '#2563eb', tint: '#eef4ff', label: '华尔街见闻' },
  格隆汇: { accent: '#b45309', tint: '#fff6e8', label: '格隆汇' },
  雪球: { accent: '#7c3aed', tint: '#f5f0ff', label: '雪球' },
  金十数据: { accent: '#c2410c', tint: '#fff1ea', label: '金十数据' },
  MKTNews: { accent: '#334155', tint: '#f3f6f8', label: 'MKTNews' },
};

function sourceName(source: string) {
  return source.replace(/^newsnow:/, '') || '未知来源';
}

function sourceTheme(source: string) {
  const name = sourceName(source);
  return sourceThemes[name] ?? { accent: '#60707b', tint: '#f4f7f9', label: name };
}

function newsTimestamp(item: NewsItem) {
  return Date.parse(item.published_at || item.fetched_at || '') || 0;
}

function displayTitle(item: NewsItem) {
  const original = item.original_title || item.title;
  if (item.simplification_status === 'simplified') return item.title || original;
  return original;
}

function displayCopy(item: NewsItem) {
  if (item.simplification_status === 'simplified') return item.summary || item.content || item.title;
  return item.original_title || item.title;
}

export default function LatestNewsCard({ news }: { news: NewsItem[] }) {
  const items = [...news].sort((a, b) => newsTimestamp(b) - newsTimestamp(a));

  return (
    <Card title="最新资讯" className="latest-news-card">
      {items.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无新闻数据" />
      ) : (
        <div className="news-feed-list">
          {items.map((item) => {
            const theme = sourceTheme(item.source);
            const isSimplified = item.simplification_status === 'simplified';
            const title = displayTitle(item);
            const copy = displayCopy(item);
            return (
              <a
                key={item.id}
                className={`news-feed-item news-feed-item-${item.simplification_status}`}
                href={item.url || undefined}
                target="_blank"
                rel="noreferrer"
                style={{ '--source-accent': theme.accent, '--source-tint': theme.tint } as CSSProperties}
                aria-label={`打开原文：${title}`}
              >
                <div className="news-feed-topline">
                  <span className="news-feed-source-mark">{theme.label}</span>
                  <span className="news-feed-time">{formatTime(item.published_at || item.fetched_at)}</span>
                </div>
                <Typography.Text className="news-feed-title">{title}</Typography.Text>
                {isSimplified ? (
                  <Typography.Paragraph ellipsis={{ rows: 3 }} className="news-feed-copy">
                    {copy}
                  </Typography.Paragraph>
                ) : null}
              </a>
            );
          })}
        </div>
      )}
    </Card>
  );
}
