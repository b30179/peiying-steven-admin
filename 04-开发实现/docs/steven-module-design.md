# Steven 模块设计（Phase 1）

## MVP 与非范围

范围仅限标书/书面报价单、采购比价、消耗品库存的项目骨架。Phase 1 不实现完整业务写入、文件生成、真实 AI/OCR、供应商搜索、自动采购决策、审批、下单、邮件或实盘库存确认。

## 页面与状态

- `/dashboard/steven`：Steven 专属 Dashboard；数据经 `lib/steven-dashboard-adapter.ts` 调用后端 mock repository，页面不内嵌业务 fixture。
- 页面具备 ready/error/loading/empty 状态，并按 Open Design artifact 落地 drawer/toast/confirm 交互。
- Open Design 项目 `puiying-steven-dashboard-phase1` 的成功 run `0aa4823c-8ec2-42dd-89ef-cbe90a3a4508` 已生成 Dashboard 原型与组件说明；Next.js 落地对应关系记录于 `docs/open-design/open-design-integration.md`。首次失败 run `009fa635-7512-4ed4-a320-2a6533f8c8e7` 仅保留为历史排障记录，不代表当前状态。平台 accounts/files/tasks/approvals/notifications/audit 通过 `modules/platform/boundaries.py` 的 Protocol 接口边界预留。

## 数据与 migration

采购关系：`steven_quote_jobs -> steven_quote_items -> steven_quote_suppliers -> steven_quote_offer_lines`。

首个 migration 建立 `uq_steven_quote_offer_lines_supplier_item`，即 `UNIQUE(quote_supplier_id, quote_item_id)`；还包含数量大于零、运费/税费/单价非负的数据库检查约束。供应商层记录运费和税费，避免复制至每一个品项。

## 权限矩阵

| 资源 | Steven | Admin | 其他岗位 |
|---|---|---|---|
| `GET /api/v1/steven/dashboard` | 允许 | 允许 | 拒绝 403 |
| `GET /api/v1/audit/events` | 拒绝 403 | 允许 | 拒绝 403 |

Phase 1 的 `X-Role` / `X-Actor` 是可替换的开发身份 seam；生产环境必须接入 accounts/JWT，不可把请求头模式视为生产认证。

## API 合同

成功：`{ data, pagination, request_id }`。

错误：`{ error: { code, message, details, request_id } }`。

当前端点：`GET /health`、`GET /api/v1/steven/dashboard`、`GET /api/v1/audit/events`。

## 审计与任务

Dashboard 读取会写入 `dashboard.view` 审计样例，字段包括 actor、action、object_type、object_id、timestamp 与 before_after。任务状态统一预留：`pending/running/succeeded/failed/needs_review/confirmed`。

## AI Adapter

`DeepSeekAdapter` 只在后端存在，默认 `DEEPSEEK_ENABLED=false`；不发起网络调用、不读取或记录密钥，候选结果状态为 `needs_review` 并要求人工确认。

## P0 映射

- T09/T12/T14：`tests/test_api.py` 验证审计拒绝、跨角色拒绝、统一 API envelope。
- T15：`tests/test_quote_constraints.py` 验证报价明细复合唯一约束；migration 还定义金额/数量检查约束。
- T16：Adapter 仅预留 `needs_review` + 人工确认合同，真实 AI 仍禁用。