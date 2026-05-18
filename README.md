# 智能证券市场监视、提醒与策略建议系统

本项目按 `GPTPlan` 的计划书实现，代码全部放在 `Project` 目录下。当前版本使用 AKShare 免费真实数据源、本机 PostgreSQL、FastAPI 后端和 React/Vite 前端；东方财富接口优先，网络不可用时切换到 AKShare 的其他真实行情接口，不写入伪造数据。

## 功能范围

- 行情：AKShare 全市场快照、自选股快照、全市场近一年日 K、主要指数、自选股当日 1 分钟 K 与最近 10 个交易日 5 分钟 K。
- 自选股：CPO + AI 算力五只，默认 `300308.SZ`、`300502.SZ`、`300394.SZ`、`601138.SH`、`000977.SZ`。
- 资讯：NewsNow 真实新闻源 + 用户可配置的 OpenAI 兼容 LLM 整理，默认 DeepSeek，入库保存文本内容和原文地址。
- 策略：MA、MACD、RSI、BOLL、KDJ、量能、区间位置和新闻聚合的本地规则引擎。
- 前端：Dashboard、Market、StockDetail、News、Advice、Settings、Notifications。
- OpenClaw/QQBot：OpenClaw 脚本已接真实接口并提供本地 scheduler；QQBot 仍默认 dry-run。
- 成本：默认不依赖付费 API、在线 LLM、云服务器或云数据库。

## 本地运行

后端默认使用本机 PostgreSQL。SQLite 仅用于测试。

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e .\backend
.\.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

首次真实数据初始化：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/collector/real/bootstrap
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/api/v1/collector/real/full-market-history/start?days=365"
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/collector/real/intraday
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/collector/real/news
```

新闻整理的 LLM 在 `.env` 中配置，不在前端回显 key：

```env
NEWS_LLM_PROVIDER=deepseek
NEWS_LLM_API_KEY=your_key_here
NEWS_LLM_API_BASE_URL=https://api.deepseek.com
NEWS_LLM_MODEL=deepseek-v4-flash
NEWS_LLM_TIMEOUT_SECONDS=40
NEWS_LLM_MAX_CONCURRENCY=50
```

前端：

```powershell
Set-Location frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

打开 `http://127.0.0.1:5173`。

## PostgreSQL

```powershell
$env:PGPASSWORD='change_me'
& 'C:\Program Files\PostgreSQL\16\bin\psql.exe' -U market -h localhost -p 5432 -d market_agent -c 'select current_database();'
```

本机 PostgreSQL 默认连接串：`postgresql+psycopg://market:change_me@localhost:5432/market_agent`。

## OpenClaw 脚本

OpenClaw 脚本已切换到真实后端接口，不再调用 demo 采集端点。新闻采集通过 NewsNow + 可配置 LLM；QQBot 仍默认 dry-run。

```powershell
.\.venv\Scripts\python openclaw\market-data-fetcher\run.py
.\.venv\Scripts\python openclaw\market-intraday-fetcher\run.py
.\.venv\Scripts\python openclaw\market-history-fetcher\run.py
.\.venv\Scripts\python openclaw\market-info-fetcher\run.py
.\.venv\Scripts\python openclaw\market-analysis-trigger\run.py
.\.venv\Scripts\python openclaw\market-alert-publisher\run.py
```

本机长期运行可使用轻量调度入口：

```powershell
.\.venv\Scripts\python openclaw\local-scheduler\run.py
```

默认频率：全市场快照 300 秒、策略分析 900 秒且仅交易时段执行；新闻同步 300 秒；全市场近一年日 K 和 10 日 5 分钟 K 默认 86400 秒，避免高频抓取。

## 验证

```powershell
.\.venv\Scripts\python -m pytest .\backend\tests
Set-Location frontend
npm run build
```

## 风险提示

本系统生成的交易建议仅用于课程项目、学习研究和辅助分析，不构成任何投资建议，不承诺收益，也不替代用户独立判断。
