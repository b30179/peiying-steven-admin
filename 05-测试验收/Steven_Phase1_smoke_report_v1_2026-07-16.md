# Steven Phase 1 Smoke Report

日期：2026-07-16

## 结论

Phase 1 的工程骨架、FastAPI health/API/权限/审计 smoke、Next.js 路由与后端 mock 数据适配均已通过。Open Design 已产出 Steven Dashboard 的视觉、信息架构和交互原型，并已整合为运行中的 Next.js 页面；本结论不代表 S1/S2/S3 业务验收。

## 实际命令

```powershell
cd D:\ZM\AI工坊\某中学\04-开发实现
.\.venv\Scripts\python.exe -m pytest -q apps\api\tests
pnpm lint:web
pnpm build:web

cd apps\api
..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 9000

cd ..\web
..\node_modules\.bin\next.cmd dev --port 3000
```

`8000` 和 `8010` 位于本机 Windows TCP 保留范围，因此开发 API 使用 `9000`。这不是部署配置。

## 结果

- `pytest -q apps/api/tests`：6 passed，1 warning（FastAPI/Starlette TestClient 对 httpx 的弃用提示）。
- `pnpm lint:web`：通过。
- `pnpm build:web`：通过；`/dashboard/steven` 为动态路由。
- `GET /health`：200，统一成功 envelope。
- `GET /api/v1/steven/dashboard`（Steven）：200；4 指标、5 待办，`ai_enabled=false`，并含复核来源/规则数据。
- 同一端点（Apple）：403，`forbidden`。
- `GET /api/v1/audit/events`（Steven）：403，`forbidden`。
- `GET /api/v1/audit/events`（Admin）：200，含 `steven.smoke` 的 `dashboard.view` 审计事件。

结构化 API 证据：`phase1-api-smoke.json`。

## 页面证据

- 地址：`http://127.0.0.1:3000/dashboard/steven`
- 截图：`phase1-steven-dashboard-open-design.png`
- 页面通过 `STEVEN_API_BASE_URL`（默认 `http://127.0.0.1:9000`）经后端 mock adapter 取数；页面文件不内嵌业务 fixture。

## Open Design

- Brief：`../04-开发实现/docs/open-design-steven-dashboard-brief.md`。
- 成功 run：`0aa4823c-8ec2-42dd-89ef-cbe90a3a4508`，项目 `puiying-steven-dashboard-phase1`。
- 原始 artifact：`../04-开发实现/docs/open-design/steven-dashboard-prototype.html` 与 `steven-dashboard-components.md`。
- Next.js 落地对应关系：`../04-开发实现/docs/open-design/open-design-integration.md`。
- 首次失败 run 的 API key 401 已保留为历史排障证据：`open-design-run-009fa635-7512-4ed4-a320-2a6533f8c8e7.md`。

## 已知限制

Phase 1 仍未实现真实 PostgreSQL 连接、Word/Excel 输出、S1/S2/S3 业务写入、真实 AI/OCR、供应商搜索或任何自动审批/选商/下单/发信/库存确认能力。
## 前端交互回归（2026-07-16）

- **问题**：通过 `http://127.0.0.1:3000` 访问时，Next.js 开发服务器曾阻止来自 `127.0.0.1` 的 `/_next/webpack-hmr` 请求，导致客户端 hydration/HMR 异常，页面按钮看似无响应。
- **修复**：在 `04-开发实现/apps/web/next.config.ts` 的 `allowedDevOrigins` 中明确允许 `127.0.0.1`，随后重启前端开发服务器。
- **真实浏览器回归**：使用 Edge CDP 找到 5 个 `.review-button`；点击“继续处理”成功打开复核抽屉；点击“记录人工复核”成功打开确认对话框；确认后成功出现 Toast：`已记录人工复核`。
- **证据**：`05-测试验收/phase1-review-drawer.png`。
## 文档一致性收尾（2026-07-16）

- 已修正 `04-开发实现/docs/steven-module-design.md` 中过期的 Open Design 状态：当前事实为成功 run `0aa4823c-8ec2-42dd-89ef-cbe90a3a4508` 已产出原型与组件说明，并已落地 Next.js。
- 首次失败 run `009fa635-7512-4ed4-a320-2a6533f8c8e7` 继续保留在 `04-开发实现/docs/open-design/`，仅作为 API key 401 的历史排障证据。
- 验证方式：全文检索未发现过期的当前失败状态表述；成功 run、原型、组件说明、整合说明及失败 run 历史记录文件均存在。
