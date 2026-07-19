# Steven Demo D0：AI / OCR / PostgreSQL 合同冻结实施说明 v1

- 日期：2026-07-17
- 当前基线：`Steven-Phase1-BL-2026-07-16`、S2、P0-A / P0-A.1、P0-B / P0-B.1
- 当前状态：D0 合同、脱敏样本、代码接口与离线自动化验证完成
- 准入结论：不代表 Azure、DeepSeek 或 PostgreSQL 已真实接通，不代表可试运行或生产可用

## 1. 本轮目标与真实演示切片

D0 冻结的受控业务链为：

`脱敏报价文件 → OCR → AI 结构化候选 → 人工复核 → PostgreSQL 正式业务表 → 规则比价 → 人工推荐/审批 → Excel`

当前实际启用的业务切片仅为 S2：

`S2 报价 OCR → AI 候选 → 人工确认 → 既有 S2 比价/审批/Excel`

S1 标书/文书与 S3 消耗品库存尚未实现 OCR/AI 业务流程。本轮只为其保留可复用的平台合同，不能将其描述为已交付。

## 2. 边界更新

原“AI/OCR 永久禁用”调整为：

- OCR/AI 在 Demo profile 下可配置启用，但默认关闭。
- 未同时启用 Demo profile、OCR 和 AI structuring 时，文档处理 API 返回 `document_intelligence_disabled`。
- OCR/AI 结果只能进入 `needs_review` 候选层。
- OCR/AI 不得直接写入 `steven_quote_*`、未来 S1 或 S3 正式业务表。
- AI 不得推荐或选择供应商，不得计算金额或排序，不得审批、下单、发信或确认实物库存。
- 在线处理失败时必须记录 `failed`；只能明确标记数据来源为 `mock`、`cached_demo` 或 `live`，不得将 Mock/缓存伪装成实时成功。
- 本轮不实现 S1、S3、NAS、MinIO、Redis、队列集群、生产部署或真实外部服务连接。

## 3. 平台可复用文档智能合同

通用代码位于：

`04-开发实现/apps/api/app/modules/document_intelligence/`

核心路由键：

- `module`
- `document_type`
- `purpose`
- `schema_name`
- `schema_version`

统一状态机：

`pending → running → needs_review → confirmed/rejected/failed`

统一能力：

- 文件元数据与追加式文件存储接口。
- OCR 与 AI 任务记录。
- Provider、model、状态、输出、错误码和 `request_id`。
- 候选 JSON、人工修订 JSON、warnings 和 evidence。
- evidence 保存页码、原文、bbox 与置信度。
- reviewer、复核时间、目标业务对象及审计关联。
- 独立确认器负责将人工确认后的候选写入对应正式业务表。

当前 purpose 合同：

| 模块 | purpose | D0 状态 |
|---|---|---|
| S2 | `quotation_extraction` | 已启用并测试 |
| S2 | `quote_exception_explanation` | 仅预留合同，未启用 |
| S1 | `tender_source_extraction` | 仅预留合同，未启用 |
| S1 | `clause_draft` | 仅预留合同，未启用 |
| S3 | `inventory_sheet_extraction` | 仅预留合同，未启用 |
| S3 | `inventory_exception_explanation` | 仅预留合同，未启用 |

## 4. Migration

新增 Alembic revision：

`20260717_0007_document_intelligence_demo_contract.py`

完整链：

`20260716_0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 20260717_0007`

本轮未修改 `0001`–`0006`。

新增表：

- `files`
- `ocr_jobs`
- `ai_jobs`
- `review_candidates`
- `steven_quote_import_candidates`

关键约束与索引：

- 文件 `storage_key` 唯一，文件大小非负。
- job/candidate 状态使用固定检查约束。
- 文件、任务和候选均保存 `request_id`。
- 按文件、请求、模块、文档类型、用途、状态和目标业务对象建立查询索引。
- S2 通过扩展关联表连接通用 candidate 与 `steven_quote_jobs`，未将通用表写死为报价结构。

## 5. Adapter 合同

### 5.1 OCR

已实现：

- `OcrAdapter`
- `MockOcrAdapter`
- `AzureDocumentIntelligenceAdapter`

Azure 目标合同：

- 模型：Document Intelligence v4 `prebuilt-invoice`
- API mapper 目标版本：`2024-11-30`
- endpoint、model、timeout 和 Key 仅由服务端配置。
- 当前只验证 endpoint/model/timeout、请求 mapper、响应 mapper 和注入式 mock transport。
- 本轮没有发出真实 Azure 请求。

### 5.2 AI 结构化

已实现：

- `AiStructuringAdapter`
- `MockAiStructuringAdapter`
- `DeepSeekStructuringAdapter`

DeepSeek 合同：

- 服务端构造脱敏输入。
- 邮箱和香港电话号码在发送前替换为脱敏占位符。
- `request_id` 和 evidence 原文不进入 AI 输入。
- 返回值必须通过严格 Pydantic Schema 校验，额外字段被拒绝。
- 推荐、排序、审批、下单等决策字段被显式拒绝。
- 当前只验证配置、请求 mapper、严格 JSON 解析和注入式 mock transport。
- 本轮没有发出真实 DeepSeek 请求。

Key 不写入源码、前端、日志、审计、样本或 `.env.example`。

## 6. 脱敏演示数据合同

样本目录：

`04-开发实现/demo-data/steven-d0/`

正常样本：

1. 中文扫描 PDF。
2. 英文/中英混排数字 PDF。
3. 中英双语表格 PNG，并附 PDF。

异常样本：

1. 缺少品项。
2. USD/HKD 币种冲突。
3. 报价过期。

每份样本均有人工 ground truth，清单由 `manifest.json` 管理。全部数据标记为 `fully_sanitized_demo_data`，不含真实姓名、公司、电话、邮箱、地址、银行资料、校务或学生数据。

正常基线：

- 币种：HKD。
- 3 家脱敏供应商。
- 5 个标准品项。
- 人工确认后合计 15 条报价明细。

既有 S2 规则计算结果：

| 排名 | 供应商 | 品项小计 | 运费 | 税费 | 总价 |
|---|---|---:|---:|---:|---:|
| 1 | SUP-C | 2,393 | 90 | 100 | 2,583 |
| 2 | SUP-A | 2,405 | 120 | 80 | 2,605 |
| 3 | SUP-B | 2,367 | 180 | 75 | 2,622 |

以上排序是系统规则计算，不构成人工推荐。推荐字段保持空白。

## 7. 候选与人工确认流程

1. 有权限用户上传已脱敏 PDF、PNG 或 JPEG。
2. 系统保存文件 hash、大小、MIME、storage key、actor 和 `request_id`。
3. 创建 OCR job，执行配置的 OCR Adapter。
4. OCR 结果保存文本、warnings、来源和 evidence。
5. 创建 AI job，按 `schema_name` 执行结构化 Adapter。
6. AI 输出通过严格 Schema 和禁用决策字段校验。
7. Candidate 进入 `needs_review`，不得写正式报价。
8. 人工并排查看原件、OCR evidence、AI 候选和最终修订值。
9. 人工可修订、拒绝或确认候选。
10. `confirm_scan_candidate()` 在独立事务中锁定 candidate 与采购事项，重新校验：
    - 候选状态与目标事项。
    - Schema。
    - 币种一致性。
    - 标准品项集合。
    - 数量和金额规则。
    - 重复供应商/品项。
    - S2 完整性与权限边界。
11. 校验通过后，同一事务写入正式报价、将 candidate 置为 `confirmed` 并追加 S2 审计。
12. 任一步失败全部回滚，candidate 保持待复核或进入明确失败状态。

## 8. API 与 UI 合同

API 位于既有 `/api/v1/steven/*` 范围：

- `POST /api/v1/steven/files`
- `GET /api/v1/steven/files/{file_id}/content`
- `POST /api/v1/steven/scan-imports`
- `GET /api/v1/steven/document-jobs/{job_id}`
- `GET /api/v1/steven/review-candidates`
- `GET /api/v1/steven/review-candidates/{candidate_id}`
- `PATCH /api/v1/steven/review-candidates/{candidate_id}`
- `POST /api/v1/steven/review-candidates/{candidate_id}/confirm`
- `POST /api/v1/steven/review-candidates/{candidate_id}/reject`

复核页面：

`/dashboard/steven/quotes/{quoteId}/scan-review/{candidateId}`

页面明确显示：

- “OCR/AI 提取结果，必须人工确认”。
- “AI 不参与供应商推荐和审批”。
- “当前使用脱敏演示资料”。

## 9. PostgreSQL 18 plan-only 合同

目标环境建议：

- Windows 服务：`postgresql-x64-18`
- 独立数据库：`puiying_steven_demo`
- 最低权限账号：`puiying_steven_demo_app`

计划文件：

- `04-开发实现/scripts/plan_steven_demo_postgres18.ps1`
- `04-开发实现/docs/Steven_Demo_PostgreSQL18_原生空库验证计划_v1_2026-07-17.md`

脚本固定输出：

- `mode=plan-only`
- `execution_allowed=false`

本轮未启动 PostgreSQL 服务、未创建数据库或账号、未读取密码、未连接真实实例。真实 migration、重启恢复、数据库约束和并发 smoke 必须在 D1 获明确批准后执行。

## 10. 验证结果

| 项目 | 结果 |
|---|---|
| D0 专项测试 | 15 项通过，并包含于全量测试 |
| 后端全量测试 | `72 passed, 1 warning in 7.47s` |
| Python compileall | 通过 |
| Alembic offline SQL | 通过，head 为 `20260717_0007` |
| 前端 ESLint | 通过 |
| Next.js production build | 通过 |
| 脱敏样本完整性与视觉检查 | 通过 |

唯一 warning 为既有 Starlette `TestClient` / `httpx` 弃用提示。本轮没有安装或升级依赖。

## 11. 当前限制

- Azure Document Intelligence 未联网调用。
- DeepSeek 未联网调用。
- PostgreSQL 空库、重启恢复和真实并发 smoke 未执行。
- 当前运行切片只启用 S2 quotation extraction。
- S1/S3 仅完成复用架构映射，业务表、Schema、确认器、页面和规则尚未实现。
- 文件系统与数据库导出仍按可恢复一致性 Saga 管理，不宣称跨数据库与文件系统原子事务。
- Demo policy 中 `required_quote_count=3` 仅为演示假设；金额门槛、审批层级、记录保留期和云 OCR 许可待甲方确认。

## 12. D1 前置批准

D1 开始前至少需要项目负责人明确批准：

1. 启动并连接本机 PostgreSQL 18。
2. 创建独立 Demo 数据库与最低权限账号。
3. 执行 migration、bootstrap、脱敏 seed、重启与并发 smoke。
4. 是否允许配置 Azure Document Intelligence 测试 endpoint 与受管 Key。
5. 是否允许配置 DeepSeek 测试 endpoint、model 与受管 Key。
6. 云 OCR/AI 的数据地域、保留、日志、不用于训练及传输许可。

