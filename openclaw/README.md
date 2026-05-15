# OpenClaw 任务脚本

这些脚本面向 OpenClaw 或本机任务编排使用。当前版本只调用后端真实数据接口，不再调用 demo 采集端点。新闻采集使用 NewsNow + 用户可配置的 OpenAI 兼容 LLM；QQBot 发送仍默认 dry-run。

## 任务映射

| OpenClaw 任务 | 脚本 | 后端动作 |
| --- | --- | --- |
| `market-data-fetcher` | `market-data-fetcher/run.py` | 调用 `/api/v1/collector/real/market` 采集全市场快照和关注股快照 |
| `market-intraday-fetcher` | `market-intraday-fetcher/run.py` | 调用 `/api/v1/collector/real/intraday` 低频同步自选股 1 分钟 K |
| `market-history-fetcher` | `market-history-fetcher/run.py` | 调用 `/api/v1/collector/real/history` 低频同步日 K |
| `market-info-fetcher` | `market-info-fetcher/run.py` | 调用 `/api/v1/collector/real/news` 采集真实新闻并用配置的 LLM 整理 |
| `market-analysis-trigger` | `market-analysis-trigger/run.py` | 触发自选股策略分析 |
| `market-alert-publisher` | `market-alert-publisher/run.py` | 发布 pending 通知并回写状态 |
| `local-scheduler` | `local-scheduler/run.py` | 本地循环执行真实采集与分析任务 |

## 环境变量

- `BACKEND_BASE_URL`：默认 `http://localhost:8000`。
- `MARKET_SNAPSHOT_INTERVAL_SECONDS`：默认 `300`，只建议交易时段执行。
- `ADVICE_INTERVAL_SECONDS`：默认 `900`，只建议交易时段执行。
- `INTRADAY_INTERVAL_SECONDS`：默认 `86400`，避免高频抓取 1 分钟 K。
- `HISTORY_INTERVAL_SECONDS`：默认 `86400`，避免高频抓取历史日 K。
- `NEWS_INTERVAL_SECONDS`：默认 `900`，控制新闻同步频率。
- `NEWS_LLM_PROVIDER`：默认 `deepseek`。
- `NEWS_LLM_API_KEY`：新闻整理 LLM API Key，必需。
- `NEWS_LLM_API_BASE_URL`：默认 `https://api.deepseek.com`。
- `NEWS_LLM_MODEL`：默认 `deepseek-v4-flash`。
- `NEWS_LLM_TIMEOUT_SECONDS`：新闻简化 LLM 请求超时，默认 `40`。
- `NEWS_LLM_MAX_CONCURRENCY`：新闻简化并发上限，默认 `50`，代码会硬性限制最高 50。
- `QQBOT_DRY_RUN`：默认 `true`，只在控制台打印并将通知标记为 sent。
- `QQBOT_WEBHOOK_URL`：`QQBOT_DRY_RUN=false` 时必填，publisher 会向该地址 POST 通知 JSON。
- `QQBOT_BATCH_SIZE`：每轮最多推送通知数，默认 `10`。
- `QQBOT_MAX_RETRY`：通知失败后最多重试次数，默认 `3`。
- `QQBOT_ENABLE_NEWS_DIGEST`：是否为 LLM 简化后的新闻生成 QQBot 通知，默认 `true`。

## 本地调度

后端启动后，可以运行：

```powershell
.\.venv\Scripts\python openclaw\local-scheduler\run.py
```

该脚本会按 `common/scheduler.py` 中的任务表循环执行。全市场快照和策略分析默认限制在交易时段；日 K 和 1 分钟 K 默认一天一次，避免触发数据源风控。
