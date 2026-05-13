import { useEffect, useState } from 'react';
import { message } from 'antd';
import { api } from '../../api/client';
import type { Advice, CollectionJob, NewsItem, Snapshot, WatchItem } from '../../types';

export function useDashboardData() {
  const [loading, setLoading] = useState(true);
  const [market, setMarket] = useState<Snapshot[]>([]);
  const [watchlist, setWatchlist] = useState<WatchItem[]>([]);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [advice, setAdvice] = useState<Advice[]>([]);
  const [jobs, setJobs] = useState<CollectionJob[]>([]);

  const load = async () => {
    setLoading(true);
    try {
      const [marketRes, watchRes, newsRes, adviceRes, jobsRes] = await Promise.all([
        api.market(new URLSearchParams({ page_size: '200', sort_by: 'change_pct', sort_order: 'desc' })),
        api.watchlist(),
        api.news(new URLSearchParams({ limit: '6' })),
        api.advice(),
        api.jobs(5),
      ]);
      setMarket(marketRes.items);
      setWatchlist(watchRes.items);
      setNews(newsRes.items);
      setAdvice(adviceRes.items.slice(0, 6));
      setJobs(jobsRes.items);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  return { loading, market, watchlist, news, advice, jobs, load };
}
