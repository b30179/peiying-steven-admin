# Steven Phase 1 实施记录

日期：2026-07-16

## 本轮目标

在 `04-开发实现/` 建立 Steven 单仓库 Phase 1 骨架，落实 Next.js + TypeScript、FastAPI、PostgreSQL migration 契约、统一 API envelope、权限、审计和 Dashboard mock 适配；不进入 S1/S2/S3 完整业务。

## 落实内容

- 初始化 `apps/web`、`apps/api`、`docs`、`infra`。
- FastAPI 按 `router.py / schemas.py / models.py / service.py / repository.py / permissions.py / tests/` 分层。
- 建立 `/health`、`/api/v1/steven/dashboard`、`/api/v1/audit/events`。
- 所有成功响应使用 `data / pagination / request_id`；权限错误使用 `error / code / message / details / request_id`。
- Phase 1 开发身份 seam 使用 `X-Role`/`X-Actor`；文件明确标注生产必须替换为 accounts/JWT，不能作为生产认证。
- Dashboard 读取产生 `dashboard.view` 审计事件，普通 Steven 无法读取审计数据。
- 采购迁移建立 `steven_quote_jobs -> steven_quote_items -> steven_quote_suppliers -> steven_quote_offer_lines`，并包含 `UNIQUE(quote_supplier_id, quote_item_id)`、`quantity > 0`、运费/税费/单价非负约束。
- DeepSeek 仅预留后端 `DeepSeekAdapter`，默认禁用，不发起任何网络调用、不写入密钥，并要求 `needs_review` 后人工确认。

## Open Design 记录

brief 已保存于 `04-开发实现/docs/open-design-steven-dashboard-brief.md`。初次 run 的 API key 401 已保留为历史证据；后续 run `0aa4823c-8ec2-42dd-89ef-cbe90a3a4508` 成功产出原型和组件说明，并已落地到 Next.js。对应关系与产物位于 `04-开发实现/docs/open-design/`。

## 变更边界

未实现真实 AI/OCR、供应商搜索、报价 OCR、自动选择供应商、自动审批、下单、邮件、实盘确认、真实 PostgreSQL 连接、文件导出或其他岗位页面。

未部署到外网或生产环境；未写入真实数据、Token 或密钥。
## 2026-07-16 前端交互修复

- 发现并修复 Next.js 开发模式下 `127.0.0.1` 的开发资源跨域限制。
- `next.config.ts` 新增 `allowedDevOrigins: ["127.0.0.1"]`。
- 已完成真实浏览器 Drawer、确认对话框和 Toast 交互回归验证；未涉及业务规则、权限或数据变更。
## 2026-07-16 文档一致性收尾

- 将模块设计文档中的 Open Design 当前状态统一为“成功产出并已落地 Next.js”。
- 保留失败 run `009fa635-7512-4ed4-a320-2a6533f8c8e7` 作为历史排障记录，不删除、不再作为当前阻塞。
- 本次仅修正文档事实与验收记录，未进入 S1/S2/S3，未接入真实 AI/OCR、数据库、外部服务或密钥。
- 验证方式为指定文档全文检索与 Open Design 产物路径存在性检查。
