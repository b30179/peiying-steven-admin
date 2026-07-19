# Steven Demo D0 实施记录 v1

- 日期：2026-07-17
- 基线：`Steven-Phase1-BL-2026-07-16`、S2、P0-A / P0-A.1、P0-B / P0-B.1
- 状态：合同、脱敏样本、代码接口、离线 migration 与自动化回归完成
- 限制：未连接 Azure、DeepSeek 或 PostgreSQL，未进入 D1、S1 或 S3

## 1. 实施记录

1. 将 AI/OCR 边界调整为 Demo profile 可配置启用、默认关闭，并保留人工确认强制要求。
2. 新增通用 `document_intelligence` 模块，按 `module`、`document_type`、`purpose`、`schema_name` 和 `schema_version` 路由。
3. 建立统一 `pending → running → needs_review → confirmed/rejected/failed` 状态机。
4. 新增 OCR 与 AI Adapter 协议、Mock Adapter、Azure Document Intelligence Adapter 和 DeepSeek Adapter。
5. Azure/DeepSeek 仅实现配置校验、mapper 和 mock transport 测试，没有发出真实网络请求。
6. 对 AI 输入实施邮箱和香港电话号码脱敏；`request_id` 与 evidence 原文不发送给 AI。
7. 对 AI 输出实施严格 Schema、额外字段拒绝和决策字段拒绝。
8. 追加 migration `20260717_0007`，未修改 `0001`–`0006`。
9. 新增 `files`、`ocr_jobs`、`ai_jobs`、`review_candidates` 和 S2 扩展关联表。
10. 新增文件上传、任务查询、候选查询/修订/确认/拒绝 API。
11. 新增 S2 扫描候选确认 Unit of Work；正式报价、candidate 状态和业务审计同一事务提交，冲突映射为 409。
12. 新增 Next.js 三栏复核页面，展示原件、OCR evidence、AI 候选和人工最终值。
13. 生成 3 份正常脱敏报价样本、3 份异常副本、ground truth、manifest、hash/页数/尺寸与视觉预览证据。
14. 新增香港学校 Demo policy，明确 3 份报价仅为演示假设，其他门槛待甲方确认。
15. 新增 PostgreSQL 18 plan-only 脚本和空库验证计划，没有启动或连接数据库。
16. 新增全业务复用映射，明确 S1/S2/S3 共用文件、任务、候选、审批、审计、PostgreSQL 与版本化导出底座。

## 2. Migration 链

`20260716_0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 20260717_0007`

本轮只新增：

`04-开发实现/apps/api/alembic/versions/20260717_0007_document_intelligence_demo_contract.py`

## 3. 主要代码与配置

- `04-开发实现/apps/api/app/modules/document_intelligence/schemas.py`
- `04-开发实现/apps/api/app/modules/document_intelligence/adapters.py`
- `04-开发实现/apps/api/app/modules/document_intelligence/repository.py`
- `04-开发实现/apps/api/app/modules/document_intelligence/postgres_repository.py`
- `04-开发实现/apps/api/app/modules/document_intelligence/service.py`
- `04-开发实现/apps/api/app/modules/document_intelligence/router.py`
- `04-开发实现/apps/api/app/modules/document_intelligence/storage.py`
- `04-开发实现/apps/api/app/modules/steven/scan_import_application.py`
- `04-开发实现/apps/api/tests/test_demo_d0_document_intelligence.py`
- `04-开发实现/apps/web/components/steven/scan-review-workspace.tsx`
- `04-开发实现/apps/web/app/dashboard/steven/quotes/[quoteId]/scan-review/[candidateId]/page.tsx`
- `04-开发实现/config/demo-policy.json`
- `04-开发实现/scripts/generate_steven_d0_samples.py`
- `04-开发实现/scripts/plan_steven_demo_postgres18.ps1`
- `04-开发实现/docs/Steven_Demo_PostgreSQL18_原生空库验证计划_v1_2026-07-17.md`
- `04-开发实现/demo-data/steven-d0/`

## 4. 验证记录

- D0 专项：15 项通过，并包含在全量测试中。
- 后端全量：`72 passed, 1 warning in 7.47s`。
- Python compileall：通过。
- Alembic offline SQL：通过，head 为 `20260717_0007`。
- 前端 ESLint：通过。
- Next.js production build：通过，包含扫描复核动态路由。
- 样本完整性：manifest、ground truth、SHA-256、页数、尺寸均已记录。
- 样本视觉复核：无裁切、乱码、黑块或重叠。

唯一 warning 为既有 Starlette `TestClient` / `httpx` 弃用提示。本轮未安装或升级依赖。

## 5. 数据与安全边界记录

- 所有样本均为完全脱敏演示数据。
- 未使用真实姓名、公司、电话、邮箱、地址、银行、校务或学生资料。
- 未写入真实账号、密码、Token、数据库连接或密钥。
- Key 不进入源码、前端、日志、审计、样本或 `.env.example`。
- OCR/AI 只生成 `needs_review` 候选。
- AI 不推荐供应商、不计算金额/排序、不审批、不下单、不发信、不确认库存。
- Mock 和缓存必须明确标记来源，不得伪装实时成功。
- 文件系统与数据库导出保持可恢复一致性 Saga 表述，不宣称跨资源原子事务。

## 6. 未执行事项

- 未启动或连接 `postgresql-x64-18`。
- 未创建 `puiying_steven_demo` 或最低权限数据库账号。
- 未执行 PostgreSQL 空库 migration、bootstrap、重启恢复或并发 smoke。
- 未调用 Azure Document Intelligence。
- 未调用 DeepSeek。
- 未连接 NAS、MinIO、Redis、真实文件、真实账户或任何外部服务。
- 未实现 S1 或 S3。
- 未部署、未拉取镜像、未安装依赖、未修改宿主机服务。

## 7. 当前结论

D0 已完成受控合同冻结和离线验证。当前真实可展示切片是 S2 的脱敏报价候选复核流程；S1/S3 只具备复用设计，不得标记为已实现。

D1 必须在项目负责人明确批准 PostgreSQL 与外部 Provider 的环境、网络、受管密钥和数据传输边界后才能开始。
