export type KlineMode = 'daily' | 'intraday' | 'latest_intraday';

export function selectDefaultKlineMode<T extends boolean>(isWatched: T): T extends true ? 'latest_intraday' : 'daily' {
  return (isWatched ? 'latest_intraday' : 'daily') as T extends true ? 'latest_intraday' : 'daily';
}
