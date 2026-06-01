import { useCallback, useEffect, useState } from 'react';
import { message } from 'antd';
import { api } from '../../api/client';
import { useBackendEvents } from '../../hooks/useBackendEvents';
import type { CollectionJob, NewsItem, Snapshot, WatchItem } from '../../types';

type RankingGroup = {
  strong: Snapshot[];
  weak: Snapshot[];
};

type DashboardRankings = {
  up: RankingGroup;
  down: RankingGroup;
};

const emptyRankings: DashboardRankings = {
  up: { strong: [], weak: [] },
  down: { strong: [], weak: [] },
};

type DashboardCache = {
  market: Snapshot[];
  rankings: DashboardRankings;
  watchlist: WatchItem[];
  watchlistMaxSize: number;
  news: NewsItem[];
  jobs: CollectionJob[];
};

let dashboardCache: DashboardCache | null = null;

export function useDashboardData() {
  const [loading, setLoading] = useState(!dashboardCache);
  const [market, setMarket] = useState<Snapshot[]>(dashboardCache?.market ?? []);
  const [rankings, setRankings] = useState<DashboardRankings>(dashboardCache?.rankings ?? emptyRankings);
  const [watchlist, setWatchlist] = useState<WatchItem[]>(dashboardCache?.watchlist ?? []);
  const [watchlistMaxSize, setWatchlistMaxSize] = useState(dashboardCache?.watchlistMaxSize ?? 0);
  const [news, setNews] = useState<NewsItem[]>(dashboardCache?.news ?? []);
  const [jobs, setJobs] = useState<CollectionJob[]>(dashboardCache?.jobs ?? []);

  const load = useCallback(async (showSpinner = !dashboardCache) => {
    setLoading(showSpinner);
    try {
      const [upStrongRes, upWeakRes, downStrongRes, downWeakRes, indexRes, watchRes, newsRes, jobsRes] = await Promise.all([
        api.market(new URLSearchParams({ page_size: '50', change_min: '0.01', sort_by: 'change_pct', sort_order: 'desc' })),
        api.market(new URLSearchParams({ page_size: '50', change_min: '0.01', sort_by: 'change_pct', sort_order: 'asc' })),
        api.market(new URLSearchParams({ page_size: '50', change_max: '-0.01', sort_by: 'change_pct', sort_order: 'desc' })),
        api.market(new URLSearchParams({ page_size: '50', change_max: '-0.01', sort_by: 'change_pct', sort_order: 'asc' })),
        api.market(new URLSearchParams({ page_size: '10', market: 'INDEX', sort_by: 'code', sort_order: 'asc' })),
        api.watchlist(),
        api.news(new URLSearchParams({ limit: '40' })),
        api.jobs(5),
      ]);
      const byCode = new Map<string, Snapshot>();
      [...indexRes.items, ...upStrongRes.items].forEach((item) => byCode.set(item.code, item));
      const next = {
        market: Array.from(byCode.values()),
        rankings: {
          up: { strong: upStrongRes.items, weak: upWeakRes.items },
          down: { strong: downStrongRes.items, weak: downWeakRes.items },
        },
        watchlist: watchRes.items,
        watchlistMaxSize: watchRes.max_size,
        news: newsRes.items,
        jobs: jobsRes.items,
      };
      dashboardCache = next;
      setMarket(next.market);
      setRankings(next.rankings);
      setWatchlist(next.watchlist);
      setWatchlistMaxSize(next.watchlistMaxSize);
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

  return { loading, market, rankings, watchlist, watchlistMaxSize, news, jobs, load };
}
