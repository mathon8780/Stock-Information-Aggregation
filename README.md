# 智能证券市场监视、提醒与策略建议系统

本项目是一个本地运行的 A 股市场监控与辅助分析系统，代码位于 `Project` 目录。当前版本使用 FastAPI 后端、React/Vite 前端、本地 PostgreSQL、AKShare 免费真实行情数据源、NewsNow 新闻源，以及用户可配置的 OpenAI 兼容 LLM。

系统不写入伪造行情数据。当真实数据源不可用时，采集任务会记录失败状态，便于在前端 Settings 页面和 `collection_jobs` 表中排查。

## 功能范围

- 行情数据：支持 AKShare 全市场快照、主要指数、自选股快照、全市场近一年日 K、自选股当日 1 分钟 K、最近 10 个交易日 5 分钟 K。
- 自选股管理：支持搜索股票、加入自选、移出自选、配置价格预警、配置策略推送，并限制最大自选股数量。
- 个股数据补全：个股详情页可手动补全指定股票近一年日 K，也可手动更新指定股票分钟 K。
- 策略分析：规则引擎基于 MA、MACD、RSI、BOLL、KDJ、量能、区间位置、新闻聚合和指数环境生成本地策略建议。
- 手动策略触发：个股详情页可触发指定股票分析，Advice 页面可触发自选股批量分析。
- 新闻资讯：NewsNow 拉取真实新闻元数据；配置 LLM 后抓取原文并在内存中简化，只保存标题、来源、URL、时间、简化结果和处理状态。
- 通知与推送：系统会生成行情异动、策略变化、新闻摘要、重大事件通知记录，并可同步写入本地 Markdown 推送文件。
- 实时刷新：前端通过后端 SSE 事件流监听行情、新闻、策略、自选股和任务状态变化。

## 技术栈

- 后端：FastAPI、SQLAlchemy、PostgreSQL、Pydantic、pytest
- 前端：React、Vite、TypeScript、Ant Design、ECharts
- 数据源：AKShare、NewsNow
- LLM：OpenAI 兼容 Chat Completions API，默认 DeepSeek `deepseek-v4-flash`
- 调度：后端内置启动同步和新闻自动同步；行情、K 线、新闻和策略任务可通过 Settings 页面或后端 API 手动触发

## 本地运行

后端默认使用本机 PostgreSQL；SQLite 仅用于测试。

```powershell
Copy-Item .env.example .env

python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e .\backend

.\.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

前端：

```powershell
Set-Location .\frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

访问地址：

- 前端：`http://127.0.0.1:5173`
- 后端 API：`http://127.0.0.1:8000/api/v1`
- 后端文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/api/v1/health`

## 关键配置

`.env.example` 提供了本地运行的默认配置。复制为 `.env` 后再按需修改；`.env` 已被 git 忽略，不应提交真实密钥或本机私有路径。

数据库默认连接：

```env
DATABASE_URL=postgresql+psycopg://market:change_me@localhost:5432/market_agent
```

新闻 LLM fallback 配置：

```env
NEWS_LLM_PROVIDER=deepseek
NEWS_LLM_API_KEY=your_key_here
NEWS_LLM_API_BASE_URL=https://api.deepseek.com
NEWS_LLM_MODEL=deepseek-v4-flash
NEWS_LLM_TIMEOUT_SECONDS=40
NEWS_LLM_MAX_CONCURRENCY=50
```

Markdown 推送输出配置：

```env
PUSH_MESSAGE_ENABLED=true
PUSH_MESSAGE_DIR=<your-output-dir>
```

`PUSH_MESSAGE_DIR` 是本地推送文件输出目录，请按自己的机器路径配置。`.env.example` 中给出的 `C:\File\PushMessage` 只是 Windows 示例。

启动同步配置：

```env
STARTUP_SYNC_ENABLED=true
STARTUP_SYNC_WATCHLIST_ENABLED=true
STARTUP_SYNC_MARKET_ENABLED=true
STARTUP_SYNC_HISTORY_ENABLED=true
STARTUP_SYNC_INTRADAY_ENABLED=true
STARTUP_SYNC_NEWS_ENABLED=true
STARTUP_SYNC_ANALYSIS_ENABLED=true
STARTUP_SYNC_FULL_MARKET_HISTORY_ENABLED=false
```

`STARTUP_SYNC_FULL_MARKET_HISTORY_ENABLED` 默认关闭，因为全市场近一年日 K 同步耗时较长，并且可能触发免费数据源风控。

## 初始化真实数据

后端启动后，可手动触发基础数据采集：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/collector/real/bootstrap
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/api/v1/collector/real/missing-daily-kline/start?days=365"
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/collector/real/intraday
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/collector/real/news
```

常用采集接口：

- `POST /api/v1/collector/real/bootstrap`：拉取市场快照、默认自选股、基础日 K 和一次策略分析。
- `POST /api/v1/collector/real/market`：刷新全市场快照。
- `POST /api/v1/collector/real/missing-daily-kline/start?days=365`：后台补全缺失日 K。
- `POST /api/v1/collector/real/full-market-history/start?days=365`：后台同步全市场近一年日 K。
- `POST /api/v1/collector/real/daily-kline/{code}?days=365`：补全指定股票近一年日 K。
- `POST /api/v1/collector/real/intraday`：同步自选股最近 10 个交易日 5 分钟 K。
- `POST /api/v1/collector/real/intraday/{code}?trading_days=1&period=1`：更新指定股票当日 1 分钟 K。
- `POST /api/v1/collector/real/news`：同步新闻元数据，若 LLM 已配置会尝试简化。
- `POST /api/v1/news/simplify-pending?limit=50`：处理历史 `pending/failed` 新闻。

策略接口：

- `POST /api/v1/analysis/{code}`：手动触发指定股票策略分析。
- `POST /api/v1/analysis/watchlist`：手动触发全部自选股策略分析。
- `GET /api/v1/advice`：查看各股票最新策略。
- `GET /api/v1/advice/{code}/history`：查看指定股票策略历史。

## 前端页面

- Dashboard：查看大盘、自选股、涨跌排行、最新资讯和关键概览。
- Market：查看全市场快照，支持搜索、排序、筛选，并可从行情表加入自选股。
- StockDetail：查看个股快照、日 K、当日 1 分钟 K、10 日 5 分钟 K、相关新闻和策略历史；可触发指定股票分析、补全近一年日 K、更新分钟 K。
- News：查看新闻处理状态、简化内容、来源、发布时间和原文 URL。
- Advice：查看最新策略，可手动触发自选股批量分析。
- Settings：配置新闻 LLM、查看运行配置、触发真实数据同步、查看采集任务记录。
- Notifications：查看行情、策略、新闻和重大事件通知状态。

## 推送文件输出

启用 `PUSH_MESSAGE_ENABLED=true` 后，通知和策略分析会同步写入 `PUSH_MESSAGE_DIR`：

- 行情异动、策略变化、重大事件：按单条通知生成 Markdown 文件。
- 新闻摘要：按 15 分钟时间窗口聚合到同一个 Markdown 文件，不限制正文长度。
- 策略建议：每次分析按策略专属模板单独生成 Markdown 文件，文件名形如 `20260528_101630_strategy_300308_SZ_101.md`。
- 写入失败时不会中断主流程，错误会写入通知 payload 或策略 indicators 中的 `push_message_error`。

## 数据库

快速检查 PostgreSQL：

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
- `notifications`：行情、策略、新闻和重大事件通知记录
- `collection_jobs`：采集任务记录

## 自动更新与调度

后端启动后会执行一次启动同步，用于补齐页面所需数据：默认自选股、全市场快照、默认自选股和指数日 K、自选股分时 K、新闻和策略分析。

新闻自动同步由后端周期任务继续执行：

```env
NEWS_AUTO_SYNC_ENABLED=true
NEWS_AUTO_SYNC_INTERVAL_SECONDS=300
NEWS_AUTO_SYNC_LIMIT=30
NEWS_AUTO_SIMPLIFY_LIMIT=50
```

行情、分钟 K、缺失日 K、全市场日 K、新闻和策略分析都可以在 Settings 页面手动触发，也可以直接调用后端 API。

## 验证

后端测试：

```powershell
.\.venv\Scripts\python -m pytest .\backend\tests
```

前端构建：

```powershell
Set-Location .\frontend
npm run build
```

## 风险提示

本系统生成的交易建议仅用于课程项目、学习研究和辅助分析，不构成任何投资建议，不承诺收益，也不替代用户独立判断。
