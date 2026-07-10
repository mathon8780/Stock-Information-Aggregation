# 微信小程序端

## 登录门禁

小程序首屏是 `pages/login/index`。用户必须先使用模拟交易用户账号登录或创建账号，登录成功后才会进入 `Dashboard`、`News` 和 `模拟交易` 三个 tab 页面。三个内容页也会在 `onShow` 做登录守卫，未登录或账号 token 失效时会回到登录页。

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

3. 如需绑定真实微信小程序 AppID，请复制 `project.private.config.example.json` 为 `project.private.config.json`，并只在这个本地私有文件里填写真实 AppID。`project.config.json` 固定使用 `touristappid`，避免把真实 AppID 提交到公开仓库。

4. 如果真机预览无法访问 `127.0.0.1`，在登录页把“后端 API 地址”改为电脑的局域网地址，例如：

```js
http://192.168.1.10:8000/api/v1
```

真机访问局域网地址时，后端需要监听 `0.0.0.0`：

```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload
```

开发者工具中本地调试可以保留 `urlCheck: false`。

## 安全说明

`project.private.config.json` 是本地私有配置，已被忽略，不应提交。GitHub secret scanning 已经标记过的 AppID 需要在腾讯侧撤销或更换；代码仓库只能移除当前和后续提交中的暴露，不能撤销已经公开过的凭据。

## 校验

```powershell
node .\miniprogram\tests\validate-miniprogram.mjs
```
