import { useCallback, useEffect, useState } from 'react';
import { message } from 'antd';
import { api } from '../../api/client';
import { useBackendEvents } from '../../hooks/useBackendEvents';
import type { CollectionJob, NewsItem, Snapshot, WatchItem } from '../../types';

type DashboardCache = {
  market: Snapshot[];
  watchlist: WatchItem[];
  news: NewsItem[];
  jobs: CollectionJob[];
};

let dashboardCache: DashboardCache | null = null;

export function useDashboardData() {
  const [loading, setLoading] = useState(!dashboardCache);
  const [market, setMarket] = useState<Snapshot[]>(dashboardCache?.market ?? []);
  const [watchlist, setWatchlist] = useState<WatchItem[]>(dashboardCache?.watchlist ?? []);
  const [news, setNews] = useState<NewsItem[]>(dashboardCache?.news ?? []);
  const [jobs, setJobs] = useState<CollectionJob[]>(dashboardCache?.jobs ?? []);

  const load = useCallback(async (showSpinner = !dashboardCache) => {
    setLoading(showSpinner);
    try {
      const [marketRes, indexRes, watchRes, newsRes, jobsRes] = await Promise.all([
        api.market(new URLSearchParams({ page_size: '200', sort_by: 'change_pct', sort_order: 'desc' })),
        api.market(new URLSearchParams({ page_size: '10', market: 'INDEX', sort_by: 'code', sort_order: 'asc' })),
        api.watchlist(),
        api.news(new URLSearchParams({ limit: '40' })),
        api.jobs(5),
      ]);
      const byCode = new Map<string, Snapshot>();
      [...indexRes.items, ...marketRes.items].forEach((item) => byCode.set(item.code, item));
      const next = {
        market: Array.from(byCode.values()),
        watchlist: watchRes.items,
        news: newsRes.items,
        jobs: jobsRes.items,
      };
      dashboardCache = next;
      setMarket(next.market);
      setWatchlist(next.watchlist);
      setNews(next.news);
      setJobs(next.jobs);
    } catch (error) {
      if (showSpinner) message.error(error instanceof Error ? error.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(!dashboardCache); }, [load]);
  useBackendEvents(['market.updated', 'watchlist.updated', 'news.updated', 'advice.updated', 'jobs.updated'], () => load(false));

  return { loading, market, watchlist, news, jobs, load };
}
