import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import { useBackendEvents } from '../../hooks/useBackendEvents';
import type { CollectionJob, NewsItem, Snapshot, WatchItem } from '../../types';

type RankingGroup = { strong: Snapshot[]; weak: Snapshot[] };
type DashboardData = {
  market: Snapshot[];
  rankings: { up: RankingGroup; down: RankingGroup };
  watchlist: WatchItem[];
  watchlistMaxSize: number;
  news: NewsItem[];
  jobs: CollectionJob[];
  total: number | null;
  upTotal: number | null;
  downTotal: number | null;
};
const empty: DashboardData = {
  market: [],
  rankings: { up: { strong: [], weak: [] }, down: { strong: [], weak: [] } },
  watchlist: [],
  watchlistMaxSize: 0,
  news: [],
  jobs: [],
  total: null,
  upTotal: null,
  downTotal: null,
};
let dashboardCache: DashboardData | null = null;

export function useDashboardData() {
  const [data, setData] = useState(dashboardCache || empty);
  const [loading, setLoading] = useState(!dashboardCache);
  const [errors, setErrors] = useState<string[]>([]);
  const requestId = useRef(0);
  const load = useCallback(async (showSpinner = false) => {
    const id = ++requestId.current;
    if (showSpinner) setLoading(true);
    const rank = (direction: string, sort: string) =>
      api.market(
        new URLSearchParams({
          page_size: '50',
          [direction === 'up' ? 'change_min' : 'change_max']: direction === 'up' ? '0.01' : '-0.01',
          sort_by: 'change_pct',
          sort_order: sort,
        }),
      );
    const results = await Promise.allSettled([
      rank('up', 'desc'),
      rank('up', 'asc'),
      rank('down', 'desc'),
      rank('down', 'asc'),
      api.market(new URLSearchParams({ page_size: '10', market: 'INDEX', sort_by: 'code', sort_order: 'asc' })),
      api.watchlist(),
      api.news(new URLSearchParams({ limit: '40' })),
      api.jobs(20),
      api.market(new URLSearchParams({ page_size: '100', sort_by: 'change_pct', sort_order: 'desc' })),
    ] as const);
    if (id !== requestId.current) return;
    const [upStrong, upWeak, downStrong, downWeak, indices, watch, news, jobs, market] = results;
    setData((previous) => {
      const next = { ...previous, rankings: { up: { ...previous.rankings.up }, down: { ...previous.rankings.down } } };
      if (upStrong.status === 'fulfilled') {
        next.rankings.up.strong = upStrong.value.items;
        next.upTotal = upStrong.value.total;
      }
      if (upWeak.status === 'fulfilled') next.rankings.up.weak = upWeak.value.items;
      if (downStrong.status === 'fulfilled') next.rankings.down.strong = downStrong.value.items;
      if (downWeak.status === 'fulfilled') {
        next.rankings.down.weak = downWeak.value.items;
        next.downTotal = downWeak.value.total;
      }
      if (watch.status === 'fulfilled') {
        next.watchlist = watch.value.items;
        next.watchlistMaxSize = watch.value.max_size;
      }
      if (news.status === 'fulfilled') next.news = news.value.items;
      if (jobs.status === 'fulfilled') next.jobs = jobs.value.items;
      const merged = new Map(previous.market.map((item) => [item.code, item]));
      if (market.status === 'fulfilled') {
        merged.clear();
        market.value.items.forEach((item) => merged.set(item.code, item));
        next.total = market.value.total;
      }
      if (indices.status === 'fulfilled') indices.value.items.forEach((item) => merged.set(item.code, item));
      next.market = [...merged.values()];
      dashboardCache = next;
      return next;
    });
    const labels = [
      '上涨强势榜',
      '上涨弱势榜',
      '下跌强势榜',
      '下跌弱势榜',
      '指数',
      '自选',
      '资讯',
      '任务记录',
      '全市场行情',
    ];
    setErrors(results.flatMap((result, index) => (result.status === 'rejected' ? [labels[index]] : [])));
    setLoading(false);
  }, []);
  useEffect(() => {
    void load(!dashboardCache);
    return () => {
      requestId.current++;
    };
  }, [load]);
  useBackendEvents(['market.updated', 'watchlist.updated', 'news.updated', 'advice.updated', 'jobs.updated'], () =>
    load(false),
  );
  return { ...data, loading, errors, load };
}
