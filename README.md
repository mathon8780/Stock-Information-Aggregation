# 智能证券市场监视、提醒与策略建议系统

这是一个本地运行的 A 股市场监控、新闻整理、策略分析与模拟交易系统。项目包含 FastAPI 后端、React/Vite Web 前端、原生微信小程序端、本地 PostgreSQL 数据库、AKShare/公开 Web 行情数据源、NewsNow 新闻源，以及可配置的 OpenAI 兼容 LLM 新闻简化能力。

系统定位为课程项目、学习研究和辅助分析工具。后端不会伪造行情数据；真实数据源不可用时，会在 `collection_jobs` 中记录失败状态，并通过 Settings 页面或通知列表展示，方便排查。

## 核心能力

- 行情监控：采集主要指数、全市场快照、自选股快照、日 K 与分钟 K 数据。
- 自选股管理：支持按代码或名称搜索股票，加入/移出系统自选股，配置价格预警和策略推送。
- 策略分析：基于 MA、MACD、RSI、BOLL、KDJ、量能、区间位置、新闻情绪和指数环境生成规则策略。
- 新闻资讯：从 NewsNow 获取新闻元数据；配置 LLM 后抓取原文并生成本地简化内容、情绪和重要性信息。
- 通知与推送：记录行情异动、策略变化、新闻摘要、重大事件、模拟交易成交和风控提醒；可输出 Markdown 推送文件。
- 模拟交易：支持用户注册/登录、账户自选股、买卖委托、撮合、T+1 持仓、费用计算、绩效统计和管理员总览。
- 多端访问：Web 前端提供完整工作台；微信小程序提供登录门禁、Dashboard、News 和模拟交易移动端。
- 实时刷新：Web 前端通过 SSE 订阅后端事件，小程序通过轮询保持同步。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 后端 | Python 3.11+、FastAPI、SQLAlchemy、Pydantic、psycopg、pytest |
| 前端 | React 18、Vite 5、TypeScript、Ant Design、ECharts |
| 小程序 | 微信小程序原生 WXML/WXSS/JS |
| 数据库 | PostgreSQL，本地测试使用 SQLite |
| 数据源 | AKShare、东方财富/新浪公开行情 fallback、NewsNow |
| LLM | OpenAI 兼容 Chat Completions API，默认配置 DeepSeek |

## 目录结构

```text
Project/
├─ backend/                    # FastAPI 后端
│  ├─ app/
│  │  ├─ api/router.py          # /api/v1 路由
│  │  ├─ analysis/              # 技术指标计算
│  │  ├─ models/entities.py     # SQLAlchemy 数据模型
│  │  ├─ schemas/requests.py    # 请求体模型
│  │  └─ services/              # 采集、新闻、策略、通知、模拟交易服务
│  ├─ tests/                    # pytest 测试
│  └─ pyproject.toml
├─ frontend/                    # React/Vite Web 前端
│  ├─ src/pages/                # Dashboard、Market、News、Advice、Transaction 等页面
│  ├─ src/features/             # 页面内表格、图表和业务组件
│  ├─ src/api/client.ts         # 前端 API client
│  └─ tests/                    # Node test 前端业务逻辑测试
├─ miniprogram/                 # 微信小程序端
│  ├─ pages/login               # 登录/注册门禁
│  ├─ pages/dashboard           # 移动端概览
│  ├─ pages/news                # 新闻列表
│  └─ pages/paper               # 模拟交易
├─ data/migrations/             # PostgreSQL 建表 SQL 参考
├─ docs/superpowers/            # 近期需求设计与计划文档
├─ tools/                       # 运维脚本，例如全市场日 K 导入
├─ .env.example                 # 本地环境变量模板
└─ README.md
```

## 环境要求

- Windows + PowerShell 示例命令已在文档中给出；Linux/macOS 可按等价命令执行。
- Python 3.11 或更高版本。后端 Dockerfile 使用 Python 3.12。
- Node.js 22 或兼容版本。前端 Dockerfile 使用 `node:22-alpine`。
- PostgreSQL 16 或兼容版本。默认数据库名为 `market_agent`。
- 微信开发者工具，用于打开 `miniprogram/`。

## 本地启动

### 1. 准备 PostgreSQL

如果本机还没有数据库，可用管理员账号进入 `psql` 后执行：

```sql
CREATE USER market WITH PASSWORD 'change_me';
CREATE DATABASE market_agent OWNER market;
GRANT ALL PRIVILEGES ON DATABASE market_agent TO market;
```

快速检查连接：

```powershell
$env:PGPASSWORD='change_me'
& 'C:\Program Files\PostgreSQL\16\bin\psql.exe' -U market -h localhost -p 5432 -d market_agent -c 'select current_database();'
```

### 2. 启动后端

```powershell
Copy-Item .env.example .env

python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e ".\backend[test]"

.\.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

后端启动时会执行 `init_db()`，按 SQLAlchemy 模型创建缺失表，并对旧库补充新闻简化字段和模拟账户手机号字段。

### 3. 启动 Web 前端

```powershell
Set-Location .\frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

访问地址：

- Web 前端：`http://127.0.0.1:5173`
- 后端 API：`http://127.0.0.1:8000/api/v1`
- Swagger 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/api/v1/health`

### 4. 启动微信小程序

1. 保持后端运行。
2. 用微信开发者工具打开 `Project/miniprogram`。
3. 开发者工具本地调试可使用默认 `http://127.0.0.1:8000/api/v1`。
4. 真机预览时，将登录页里的后端地址改为电脑局域网地址，例如 `http://192.168.1.10:8000/api/v1`，并用 `--host 0.0.0.0` 启动后端。

```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload
```

## 关键配置

`.env.example` 是本地配置模板，复制成 `.env` 后按需修改。`.env`、`.env.*`、小程序私有配置和本地运行日志均已在 `.gitignore` 中忽略。

### 数据库

```env
DATABASE_URL=postgresql+psycopg://market:change_me@localhost:5432/market_agent
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=market_agent
POSTGRES_USER=market
POSTGRES_PASSWORD=change_me
```

### 采集与启动同步

```env
MARKET_SNAPSHOT_INTERVAL_SECONDS=300
WATCH_SNAPSHOT_INTERVAL_SECONDS=60
NEWS_AUTO_SYNC_ENABLED=true
NEWS_AUTO_SYNC_INTERVAL_SECONDS=300
NEWS_AUTO_SYNC_LIMIT=30
NEWS_AUTO_SIMPLIFY_LIMIT=50

STARTUP_SYNC_ENABLED=true
STARTUP_SYNC_WATCHLIST_ENABLED=true
STARTUP_SYNC_MARKET_ENABLED=true
STARTUP_SYNC_HISTORY_ENABLED=true
STARTUP_SYNC_INTRADAY_ENABLED=true
STARTUP_SYNC_NEWS_ENABLED=true
STARTUP_SYNC_ANALYSIS_ENABLED=true
STARTUP_SYNC_FULL_MARKET_HISTORY_ENABLED=false
```

`STARTUP_SYNC_FULL_MARKET_HISTORY_ENABLED` 默认关闭，因为全市场近一年日 K 同步耗时较长，也可能触发免费数据源风控。

### 新闻 LLM

```env
NEWS_LLM_PROVIDER=deepseek
NEWS_LLM_API_KEY=
NEWS_LLM_API_BASE_URL=https://api.deepseek.com
NEWS_LLM_MODEL=deepseek-v4-flash
NEWS_LLM_TIMEOUT_SECONDS=40
NEWS_LLM_MAX_CONCURRENCY=50
NEWSNOW_API_BASE_URL=https://newsnow.busiyi.world/api
```

也可以在 Web `Settings` 页面配置 LLM provider、base URL、model、API Key、prompt preset 或自定义 prompt。数据库中的 `news_llm_config` 优先级高于环境变量。

### 推送输出

```env
PUSH_MESSAGE_ENABLED=true
PUSH_MESSAGE_DIR=C:\File\PushMessage
QQBOT_DRY_RUN=true
QQBOT_ENABLE_PRICE_ALERT=true
QQBOT_ENABLE_STRATEGY_ALERT=true
QQBOT_ENABLE_NEWS_DIGEST=true
QQBOT_ENABLE_JOB_FAILED_ALERT=true
```

启用后，通知和策略建议会写入本地 Markdown 文件。`PUSH_MESSAGE_DIR` 应改成自己机器上的路径，不要提交私人路径或真实 webhook。

### 前端与小程序 API 地址

Web 前端使用：

```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

小程序默认地址在 `miniprogram/config.js`：

```js
defaultApiBaseUrl: 'http://127.0.0.1:8000/api/v1'
```

小程序登录页支持临时修改 API 地址，并保存到本地 storage。

## 初始化真实数据

后端启动后，可以在 Web `Settings` 页面点击任务按钮，也可以直接调用 API。注意：`/collector/real/bootstrap` 的 `reset` 默认值为 `true`，会重建数据库表；已有数据时请显式加 `?reset=false`。

推荐首次初始化流程：

```powershell
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/api/v1/collector/real/bootstrap?reset=false"
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/api/v1/collector/real/missing-daily-kline/start?days=365"
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/api/v1/collector/real/intraday?trading_days=10&period=5"
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/api/v1/collector/real/news?limit=30"
```

常用采集接口：

- `POST /collector/real/bootstrap?reset=false`：创建默认自选股、采集市场快照、基础日 K、新闻和策略。
- `POST /collector/real/market`：刷新全市场快照。
- `POST /collector/real/history`：采集默认自选股和主要指数历史日 K。
- `POST /collector/real/daily-kline/{code}?days=365`：补全指定股票日 K。
- `POST /collector/real/full-market-history/start?days=365`：后台同步全市场日 K。
- `POST /collector/real/missing-daily-kline/start?days=365`：后台补齐缺失日 K。
- `POST /collector/real/intraday?trading_days=10&period=5`：同步自选股分钟 K。
- `POST /collector/real/intraday/{code}?trading_days=1&period=1`：同步指定股票当日 1 分钟 K。
- `POST /collector/real/news?limit=30`：采集新闻并按配置尝试简化。
- `POST /news/simplify-pending?limit=50`：处理历史 `pending` 或 `failed` 新闻。

全市场日 K 也可以用脚本导入：

```powershell
.\.venv\Scripts\python .\tools\import_full_market_history.py --days 365 --workers 4 --skip-existing
```

## 后端 API 概览

所有业务接口默认挂载在 `/api/v1`。

### 系统与实时事件

- `GET /health`：健康检查。
- `GET /settings`：运行配置、启动同步状态、LLM 状态、推送配置和风险参数。
- `GET /events`：SSE 事件流。Web 前端订阅 `watchlist.updated`、`jobs.updated`、`news.updated`、`paper_order.updated`、`paper_trade.filled` 等事件。

### 股票、行情与 K 线

- `GET /stocks?q=中际&security_type=stock`：搜索股票或指数。
- `GET /stocks/{code}`：股票详情、最新快照、最新策略和是否在系统自选中。
- `GET /stocks/{code}/kline?limit=90`：日 K。
- `GET /stocks/{code}/intraday?period=5&days=10`：分钟 K。
- `GET /stocks/{code}/snapshot`：最新快照。
- `GET /stocks/{code}/snapshots?limit=120`：快照历史。
- `GET /market/snapshot?page=1&page_size=50&sort_by=change_pct&sort_order=desc`：全市场快照，支持 `q`、`market`、`industry`、`change_min`、`change_max`。

### 新闻与策略

- `GET /news?scope=market&sentiment=positive&limit=50`：新闻列表。
- `GET /news/{news_id}`：新闻详情。
- `GET /stocks/{code}/news?limit=20`：个股相关新闻。
- `GET /news-llm-config` / `PUT /news-llm-config`：读取或保存新闻 LLM 配置。
- `POST /news-llm-config/validate`：验证当前 LLM Key。
- `GET /advice?signal=持有`：最新策略汇总。
- `GET /advice/{code}`：获取或即时生成指定股票策略。
- `GET /advice/{code}/history?limit=20`：策略历史。
- `POST /analysis/{code}`：手动触发个股策略分析。
- `POST /analysis/watchlist`：批量分析系统自选股。

### 系统自选、任务与通知

- `GET /watchlist`：系统自选股列表。
- `POST /watchlist`：加入自选股，请求体示例 `{"code":"300308.SZ"}`。
- `PATCH /watchlist/{code}`：更新预警、阈值、策略推送和排序。
- `DELETE /watchlist/{code}`：移出自选股。
- `GET /collection-jobs?limit=50`：采集任务记录。
- `GET /notifications?notification_type=paper_trade&limit=100`：通知记录。

## Web 前端页面

- `Dashboard`：主要指数、涨跌排行、系统自选股、最新新闻、最近采集任务和缺失日 K 补齐入口。
- `Market`：全市场行情表，支持搜索、筛选、排序和加入自选股。
- `StockDetail`：个股快照、日 K、分钟 K、技术指标、策略摘要、相关新闻和策略历史。
- `News`：新闻列表、简化状态、情绪、重要性、来源和原文 URL。
- `Advice`：最新策略列表，支持按策略信号筛选和批量分析自选股。
- `Transaction`：模拟交易用户端和管理员入口。
- `Notifications`：行情、策略、新闻、任务、模拟交易和风控通知。
- `Settings`：采集任务、运行配置、新闻 LLM 配置、Key 验证和任务记录。

Web 前端请求封装在 `frontend/src/api/client.ts`，页面状态使用普通 React state 和 Ant Design 组件组织。`frontend/src/hooks/useBackendEvents.ts` 负责 SSE 订阅。

## 模拟交易说明

模拟交易功能位于后端 `paper_trading_service.py`、Web 页面 `PaperTrading.tsx`、小程序 `pages/paper`。用户接口需要 `Authorization: Bearer <token>`。

### 账户与登录

用户创建账号需要先请求手机号验证码：

```powershell
$captcha = Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/paper/account-captchas `
  -ContentType 'application/json' `
  -Body '{"phone":"13900000001"}'

Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/paper/accounts `
  -ContentType 'application/json' `
  -Body (@{
    owner_name = 'demo'
    password = 'secret123'
    phone = $captcha.phone
    captcha_id = $captcha.captcha_id
    captcha_code = $captcha.captcha_code
  } | ConvertTo-Json)
```

登录后获得 token：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/paper/sessions `
  -ContentType 'application/json' `
  -Body '{"owner_name":"demo","password":"secret123"}'
```

本地演示管理员接口使用 `POST /paper/admin/sessions`。当前测试用默认账号为 `admin`，密码为 `admin...`；公开部署前应改造成环境变量或外部密钥，不要保留硬编码演示凭据。

### 交易规则

- 初始资金：`500000.0000`。
- 支持订单：`market` 市价单、`limit` 限价单、`take_profit` 止盈单、`stop_loss` 止损单。
- 买卖数量必须大于 0；前端默认按 100 股步进。
- 市价单仅允许在 A 股交易时间 `09:30-11:30`、`13:00-15:00` 执行。
- 买入执行 T+1 规则：当日买入形成 `today_buy_quantity`，下一个交易日才转为可卖数量。
- 限价买入冻结资金，限价卖出冻结可卖持仓；撤单释放冻结。
- 止盈/止损单进入 `monitoring` 状态，调用 `/paper/match/run` 后按最新价检查触发和成交。
- 费用：佣金 `0.00025`，过户费 `0.00001`，卖出印花税 `0.001`。
- 涨跌停：普通股票 10%，ST 5%，创业板/科创板 20%，北交所 30%。

常用接口：

- `GET /paper/summary`：账户资产摘要。
- `GET /paper/quote?code=300308.SZ`：下单报价、涨跌停和策略信号。
- `GET /paper/watchlist` / `POST /paper/watchlist`：账户级自选股。
- `POST /paper/orders`：提交委托。
- `POST /paper/orders/{order_id}/cancel`：撤单。
- `POST /paper/match/run`：运行撮合。
- `GET /paper/positions`、`/paper/orders`、`/paper/trades`、`/paper/cash-flows`：持仓、委托、成交和资金流水。
- `GET /paper/performance/summary`、`/paper/performance/by-stock`、`/paper/performance/calendar`、`/paper/equity`：绩效、个股盈亏、交易日历和净值曲线。
- `GET /paper/admin/overview`：管理员查看账户汇总和资金流水。

## 微信小程序端

小程序在 `miniprogram/`，使用原生 WXML/WXSS/JS。入口页是 `pages/login/index`，登录成功后才能进入三个 tab：

- `pages/dashboard/index`：主要指数、涨跌排行、系统自选股、最新资讯和账户资产摘要。
- `pages/news/index`：新闻列表，支持范围和情绪筛选，可复制原文链接。
- `pages/paper/index`：模拟交易账户概览、自选股分钟 K、下单、持仓、委托、成交和资金流水。

小程序不暴露管理员入口，不使用浏览器 `EventSource`，而是按配置轮询：

```js
polling: {
  dashboardMs: 30000,
  newsMs: 60000,
  paperMs: 15000,
  intradayMs: 60000,
}
```

`project.config.json` 固定使用 `touristappid`。如果需要真实 AppID，请复制 `miniprogram/project.private.config.example.json` 为 `project.private.config.json` 并只在本地填写，该文件已被忽略。

## 数据库表

核心行情与策略表：

- `stocks`：股票和指数基础信息。
- `market_snapshot` / `watch_snapshot`：全市场和自选股快照。
- `kline_daily` / `kline_intraday`：日 K 和分钟 K。
- `watchlist`：系统自选股。
- `news`：新闻元数据、简化内容、情绪、重要性和 LLM 状态。
- `news_llm_config`：新闻 LLM 配置。
- `trading_advice`：策略分析结果。
- `collection_jobs`：采集任务记录。
- `notifications`：通知记录和推送状态。

模拟交易表：

- `paper_accounts`、`paper_sessions`：模拟账户和登录会话。
- `paper_watchlist`：账户级自选股。
- `paper_orders`、`paper_trades`：委托和成交。
- `paper_positions`：账户持仓。
- `paper_cash_flows`：资金流水。
- `paper_equity_snapshots`：资产净值快照。

`data/migrations/001_init.sql` 是完整建表参考，`002_news_llm_config.sql` 用于旧库补充新闻 LLM 字段。当前应用启动时以 SQLAlchemy `create_all` 和轻量 schema upgrade 为主，没有接入 Alembic。

## 测试与校验

后端测试：

```powershell
.\.venv\Scripts\python -m pytest .\backend\tests
```

前端构建：

```powershell
Set-Location .\frontend
npm run build
```

前端业务逻辑测试：

```powershell
Set-Location .\frontend
node --test .\tests\paperTradingData.test.mjs
```

小程序结构与网络错误提示校验：

```powershell
node .\miniprogram\tests\validate-miniprogram.mjs
node .\miniprogram\tests\api-network-error.test.mjs
```

建议在提交前至少运行后端 pytest、前端 build，以及本次改动相关的小程序或前端 Node 测试。

## Docker 构建

后端镜像：

```powershell
docker build -t market-agent-backend .\backend
docker run --rm -p 8000:8000 --env-file .env market-agent-backend
```

前端镜像：

```powershell
docker build -t market-agent-frontend .\frontend --build-arg VITE_API_BASE_URL=http://localhost:8000/api/v1
docker run --rm -p 8080:80 market-agent-frontend
```

当前仓库没有提供 `docker-compose.yml`。容器化运行时仍需准备外部 PostgreSQL，并确保后端容器中的 `DATABASE_URL` 能访问该数据库。

## 运行与安全注意事项

- 不要提交 `.env`、真实 API Key、真实微信 AppID、数据库文件、运行日志或本机私有路径。
- `backend/backend-dev.log`、`frontend/frontend-dev.log`、`logs/`、`data/runtime/` 等运行产物应保持本地化。
- 免费数据源可能限流或字段变化；采集失败应先查看 `collection_jobs.error_message` 和 Settings 页面任务记录。
- `bootstrap` 默认会重建表，已有数据环境必须使用 `reset=false` 或改用单项采集接口。
- 新闻简化会调用外部 LLM 服务，注意 API Key 费用、并发限制和原文内容隐私。
- 交易建议、新闻摘要和模拟交易结果仅用于学习研究，不构成投资建议。

## 常见问题

### 前端提示接口不可用

确认后端在 `8000` 端口运行，并检查 `frontend/.env` 或根目录 `.env` 中的 `VITE_API_BASE_URL`。默认应指向 `http://localhost:8000/api/v1`。

### 小程序真机无法访问本机后端

真机不能访问电脑的 `127.0.0.1`。请把小程序登录页 API 地址改成电脑局域网 IP，并用 `--host 0.0.0.0` 启动后端。

### 新闻一直是 pending

检查 `NEWS_LLM_API_KEY` 或 Settings 页面中的 LLM Key 是否配置，并调用 `POST /api/v1/news-llm-config/validate` 验证。未配置 Key 时新闻元数据仍可保存，但不会完成 LLM 简化。

### 模拟交易下单失败

常见原因包括：未登录或 token 过期、无最新价格、非交易时间提交市价单、委托价格超出涨跌停、买入现金不足、卖出可用持仓不足，或当日买入数量受 T+1 限制。

### 全市场日 K 很慢

全市场历史数据量大，建议使用后台接口或 `tools/import_full_market_history.py --skip-existing` 分批导入。不要在频繁重启开发服务器时开启 `STARTUP_SYNC_FULL_MARKET_HISTORY_ENABLED`。
