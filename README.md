# 智能证券市场监视、提醒与策略建议系统

本项目是一个本地运行的 A 股市场监控与辅助分析系统，代码位于 `Project` 目录。当前版本使用 FastAPI 后端、React/Vite 前端、本地 PostgreSQL、AKShare 免费真实行情数据源、NewsNow 新闻源，以及用户可配置的 OpenAI 兼容 LLM。

系统不写入伪造行情数据；当真实数据源不可用时，采集任务会记录失败状态，便于在前端和任务记录中排查。

## 功能范围

- 行情数据：AKShare 全市场快照、主要指数、自选股快照、全市场近一年日 K、自选股当日 1 分钟 K、最近 10 个交易日 5 分钟 K。
- 自选股管理：默认关注 CPO + AI 算力方向股票；前端支持搜索股票、加入自选、移出自选、配置价格预警与策略推送。
- 自动分析：新增自选股后，后端会立即触发一次规则引擎分析并写入 `trading_advice`。
- 策略引擎：基于 MA、MACD、RSI、BOLL、KDJ、量能、区间位置、新闻聚合和指数环境生成本地规则策略。
- 新闻资讯：NewsNow 拉取真实新闻元数据；若配置 LLM，则抓取原文、在内存中简化，不保存原始正文，只保存标题、来源、URL、时间、简化结果和处理状态。
- 新闻自动同步：后端启动后默认每 300 秒自动获取新闻；配置 LLM 后会自动处理待简化新闻。
- 前端页面：Dashboard、Market、StockDetail、News、Advice、Settings、Notifications。
- 实时刷新：前端通过后端事件流监听数据变化，新闻、策略、自选股、任务状态更新后会刷新对应模块。
- OpenClaw/QQBot：OpenClaw 脚本已接入真实后端接口；QQBot 默认 dry-run，可通过 webhook 配置推送。

## 技术栈

- 后端：FastAPI、SQLAlchemy、PostgreSQL、Pydantic、pytest
- 前端：React、Vite、TypeScript、Ant Design、ECharts
- 数据源：AKShare、NewsNow
- LLM：OpenAI 兼容 Chat Completions API，默认 DeepSeek `deepseek-v4-flash`
- 调度：后端内置新闻自动同步，OpenClaw 本地 scheduler 负责行情、K 线、策略和推送任务

## 本地运行

后端默认使用本机 PostgreSQL；SQLite 仅用于测试。

```powershell
Set-Location "C:\Users\Matho\Desktop\Class\Engineering Practice\Project"
Copy-Item .env.example .env

python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e .\backend

.\.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

前端：

```powershell
Set-Location "C:\Users\Matho\Desktop\Class\Engineering Practice\Project\frontend"
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

访问地址：

- 前端：`http://127.0.0.1:5173`
- 后端 API：`http://127.0.0.1:8000`
- 后端文档：`http://127.0.0.1:8000/docs`

## 初始化真实数据

后端启动后，可手动触发一次基础数据采集：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/collector/real/bootstrap
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/api/v1/collector/real/full-market-history/start?days=365"
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/collector/real/intraday
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/collector/real/news
```

说明：

- `bootstrap` 会拉取市场快照、默认自选股、基础日 K 和一次策略分析。
- `full-market-history/start` 会在后端后台同步全市场近一年日 K，避免接口长时间阻塞。
- `intraday` 默认同步自选股最近 10 个交易日 5 分钟 K。
- `news` 会拉取新闻；若 LLM 已配置，则立即尝试简化。

## LLM 新闻配置

推荐在 Settings 页面填写新闻 LLM 配置；API Key 只保存到后端数据库，前端不会回显明文。

也可以在 `.env` 中配置默认 fallback：

```env
NEWS_LLM_PROVIDER=deepseek
NEWS_LLM_API_KEY=your_key_here
NEWS_LLM_API_BASE_URL=https://api.deepseek.com
NEWS_LLM_MODEL=deepseek-v4-flash
NEWS_LLM_TIMEOUT_SECONDS=40
NEWS_LLM_MAX_CONCURRENCY=50
```

当前行为：

- 未配置 API Key：新闻只保存元数据，状态为 `pending`。
- 配置 API Key：新新闻会自动简化；历史 `pending/failed` 新闻可通过 Settings 的“简化未处理新闻”按钮处理。
- LLM 返回异常或非法 JSON：新闻标记为 `failed`，错误写入 `error_message`，采集任务不会整体崩溃。

## 数据库

默认连接：

```text
postgresql+psycopg://market:change_me@localhost:5432/market_agent
```

快速检查：

```powershell
$env:PGPASSWORD='change_me'
& 'C:\Program Files\PostgreSQL\16\bin\psql.exe' -U market -h localhost -p 5432 -d market_agent -c 'select current_database();'
```

核心表包括：

- `stocks`：股票与指数基础信息
- `market_snapshot` / `watch_snapshot`：行情快照
- `kline_daily` / `kline_intraday`：日 K 与分钟 K
- `watchlist`：自选股配置
- `trading_advice`：策略分析结果
- `news`：新闻元数据、简化内容和处理状态
- `news_llm_config`：新闻 LLM 配置
- `notifications`：QQBot 等推送任务
- `collection_jobs`：采集任务记录

## 自动更新与调度

后端启动后会自动启动新闻同步任务：

- `NEWS_AUTO_SYNC_ENABLED=true`
- `NEWS_AUTO_SYNC_INTERVAL_SECONDS=300`
- `NEWS_AUTO_SYNC_LIMIT=30`
- `NEWS_AUTO_SIMPLIFY_LIMIT=50`

行情、分钟 K、全市场日 K、策略分析和通知推送由 OpenClaw 本地调度器负责：

```powershell
Set-Location "C:\Users\Matho\Desktop\Class\Engineering Practice\Project"
.\.venv\Scripts\python openclaw\local-scheduler\run.py
```

默认频率：

- 全市场快照：300 秒，仅交易时段执行
- 新闻同步：300 秒
- 策略分析：900 秒，仅交易时段执行
- 全市场近一年日 K：86400 秒
- 自选股 10 日 5 分钟 K：86400 秒

也可以单独运行某个 OpenClaw 任务：

```powershell
.\.venv\Scripts\python openclaw\market-data-fetcher\run.py
.\.venv\Scripts\python openclaw\market-intraday-fetcher\run.py
.\.venv\Scripts\python openclaw\market-history-fetcher\run.py
.\.venv\Scripts\python openclaw\market-info-fetcher\run.py
.\.venv\Scripts\python openclaw\market-analysis-trigger\run.py
.\.venv\Scripts\python openclaw\market-alert-publisher\run.py
```

## 前端操作说明

- Dashboard：查看大盘、自选股管理、涨跌排行和最新资讯。
- Market：查看全市场快照，可从行情表加入自选股。
- StockDetail：查看个股快照、日 K、当日 1 分钟 K、10 日 5 分钟 K、相关新闻和策略历史。
- News：查看新闻处理状态、简化内容、来源、发布时间和原文 URL。
- Advice：查看最新策略，可手动触发自选股分析。
- Settings：配置 LLM、触发真实数据同步、查看采集任务。
- Notifications：查看 QQBot 等推送任务状态。

## 验证

后端测试：

```powershell
.\.venv\Scripts\python -m pytest .\backend\tests
```

前端构建：

```powershell
Set-Location frontend
npm run build
```

## 风险提示

本系统生成的交易建议仅用于课程项目、学习研究和辅助分析，不构成任何投资建议，不承诺收益，也不替代用户独立判断。

## 启动自动同步

后端启动后会在后台执行一次启动同步，用于把页面所需数据补到最新：默认自选股、全市场快照、默认自选股/指数日 K、自选股分时 K、新闻和策略分析。新闻周期同步仍由后端自动任务继续执行。

可通过 `.env` 中的 `STARTUP_SYNC_*` 配置控制同步范围。`STARTUP_SYNC_FULL_MARKET_HISTORY_ENABLED` 默认关闭，因为全市场近一年日 K 同步耗时较长，并且可能触发免费数据源风控；需要全市场历史数据时再手动开启。
