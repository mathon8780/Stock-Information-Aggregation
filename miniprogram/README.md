# 微信小程序端

该目录是项目的微信小程序客户端，使用原生小程序 `WXML/WXSS/JS` 实现，直接复用现有 FastAPI 后端接口。

## 页面

- `Dashboard`：展示主要指数、涨跌排行、系统自选股、最新资讯；如果已登录模拟账户，同步展示账户资产摘要。
- `News`：展示新闻列表，支持按范围和情绪筛选，展开后可查看整理内容并复制原文链接。
- `模拟交易`：仅支持用户账号登录/创建，不提供管理员入口；展示账户概览、自选股分钟 K、持仓、委托、成交和资金流水，并支持下单、加入自选、撤单和运行撮合。

## 后端同步

小程序端与 Web 前端共用同一组后端 API：

- 行情：`GET /api/v1/market/snapshot`
- 系统自选：`GET /api/v1/watchlist`
- 新闻：`GET /api/v1/news`
- 模拟交易账号：`POST /api/v1/paper/sessions`
- 模拟交易数据：`GET /api/v1/paper/summary`、`/paper/watchlist`、`/paper/positions`、`/paper/orders`、`/paper/trades`、`/paper/cash-flows`
- 模拟交易操作：`POST /api/v1/paper/orders`、`POST /api/v1/paper/match/run`

小程序端通过页面 `onShow` 立即刷新，并用轮询保持和后端数据同步。当前未接入小程序原生 SSE，因为微信小程序环境与浏览器 `EventSource` 不一致。

## 本地运行

1. 启动后端：

```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

2. 用微信开发者工具打开 `Project/miniprogram`。

3. 如果真机预览无法访问 `127.0.0.1`，将 `config.js` 中的 `apiBaseUrl` 改为电脑的局域网地址，例如：

```js
apiBaseUrl: 'http://192.168.1.10:8000/api/v1'
```

开发者工具中本地调试可以保留 `urlCheck: false`。

## 校验

```powershell
node .\miniprogram\tests\validate-miniprogram.mjs
```
