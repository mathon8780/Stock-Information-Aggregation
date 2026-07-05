import { selectDefaultKlineMode, type KlineMode } from './klineMode';

const watchedMode: 'latest_intraday' = selectDefaultKlineMode(true);
const unwatchedMode: 'daily' = selectDefaultKlineMode(false);
const explicitMode: KlineMode = selectDefaultKlineMode(true);

void watchedMode;
void unwatchedMode;
void explicitMode;
