# Steven v4.1 实施方案需求对照审查

**被审查文件**：`Steven岗位AI实施方案_整合版_v4.1_2026-07-15(1).docx`  
**对照基线**：`D:\ZM\AI工坊\04-项目提案\最终实施参考文档\design.md`（最高优先级）  
**审查日期**：2026-07-15

## 结论

**暂不建议把 v4.1 直接设为主版本。**

它较 v3.1 补强了平台共用表、统一组件、API envelope、权限码、异步任务、AI 结构化输出、批量 Word 导出和异常处理，方向正确；但仍有 5 个 P0 级冲突/遗漏与若干 P1 问题。修正后可作为新的主版本。

## 已对齐、可保留

| 项目 | 结果 |
|---|---|
| Steven 三模块范围、跨角色隔离、人工决策边界 | 通过 |
| Next.js + TypeScript、Python 3.11 + FastAPI、PostgreSQL | 通过 |
| 共用基础表、权限码格式、统一 API 成功/列表/错误 envelope | 基本通过 |
| 统一组件、文件白名单、审计不可删除、AI 结构化输出 | 基本通过 |
| 批量多供应商 Word 导出 | 可保留，但要纳入审批/版本/审计规则 |

## P0：必须修正后才能设为主版本

### P0-1 繁简切换方案与 Next.js 技术栈冲突

v4.1 第 6.2 节使用 **Vue 动态渲染 + Pinia locale store + MutationObserver**；平台前端是 Next.js + TypeScript（React），不是 Vue。

**修正**：改为 Next.js/React 的 locale context/store（或项目既有 i18n 方案）。不用 Pinia、不写 Vue。禁止 MutationObserver 对整页文本节点和输入内容做自动转换：这会改写用户输入、模板变量、金额说明或文件名。界面固定文案用 locale 字典；用户录入、附件、原始文本和正式文书内容不得被自动繁简转换。

### P0-2 任务状态与 design.md 不一致

v4.1 写 `pending -> running -> completed / failed`，但 design.md 统一状态是：`pending / running / succeeded / failed / needs_review / confirmed`。

**修正**：全文统一为 design.md 的六个状态；`completed` 改为 `succeeded`。AI/OCR 结果必须先 `needs_review`，人工确认后 `confirmed`。导出/导入任务也使用同一任务模型。

### P0-3 库存重复 SKU 的异常处理与 P0 验收冲突

v4.1 异常表写“库存导入含重复 SKU：标记重复项，要求人工确认”；但既定 P0 规则是“重复 SKU 不可保存”。

**修正**：导入预检可高亮重复行供用户修正，但确认导入时必须拒绝写入重复 SKU；不得以“人工确认”绕过唯一约束。数据库必须有唯一索引/约束（建议 SKU 全局唯一，或明确 `warehouse/location + sku` 联合唯一）。

### P0-4 审批闭环接口和 Phase 2 表述冲突

v4.1 有审批权限和 `pending_approval`，却没有 `POST /api/v1/steven/tenders/{id}/submit-approval`，且把“线上审批流程”列入 Phase 2。这会让 MVP 无法满足“提交、批准/退回、通知、审计、导出”的既定闭环。

**修正**：MVP 必须具备最小审批闭环：提交审批、审批人批准/退回、待审批通知、审计记录、本人不得批准本人。复杂流程引擎/多级会签可列 Phase 2，但不能把基本审批放到 Phase 2。

### P0-5 数据库结构仍不足以直接实施

v4.1 的业务表仅列少量字段，仍使用 `file_path`，缺少关键外键、数据类型、唯一/检查约束及平台共用表关系；`steven_quote_jobs / items` 合并写法也无法直接生成 migration。

**修正**：至少逐表明确：
- 全表基础字段：`id, created_at, updated_at, created_by, updated_by, status`；
- 金额字段为 PostgreSQL `numeric/decimal`，禁止 float；数量为 integer，日期/币种为结构化字段；
- `steven_templates.file_id -> files.id`，不存业务绝对 `file_path`；
- `steven_tender_jobs.template_id -> steven_templates.id`，并有 `source_file_id, last_reviewed_by, last_reviewed_at`；
- `steven_quote_jobs` 与 `steven_quote_items` 拆分建表，明细用 `quote_job_id` 外键；数量 `>0`、金额 `>=0`、币种一致；
- `steven_inventory_counts.inventory_item_id -> steven_inventory_items.id`；SKU 唯一约束；数量 `>=0`；
- 模板、导出、附件、审批、通知、任务、审计均关联 `files/tasks/approvals/notifications/audit_logs`，业务表不得重复造共用表。

## P1：建议一并修正

1. **Celery/RQ 二选一**：v4.1 写“Celery/RQ + Redis”，应在实现前基于现有工程选定 Celery 或 RQ，禁止双套队列。
2. **统一文件服务**：应明确 `/api/v1/files/upload`、文件下载/预览授权、`files.id` 关联和 storage adapter；不能只描述 NAS 路径。
3. **API error envelope**：错误返回需含 `details`，不是只写 code/message；列表应规定 pagination、过滤、排序。
4. **补齐 CRUD/审批接口**：v4.1 未列 `/api/v1/steven/quotes` GET/POST、`/api/v1/steven/inventory` GET/POST、submit-approval、审批人 approve/reject 动作及统一任务查询方式。
5. **权限语义统一**：审计读取应接平台共用 audit 权限语义；导出权限与审批流程必须一致，不能出现“Steven 可导出”与“审批后导出”定义互相矛盾。
6. **基础设施前提**：当前项目尚未证明登录/权限/files/audit/组件库已完成；排期不能假设已有基础设施。Day 1–2 应明确为“搭建或接入底座、数据模型、API 合同、mock 页面”，否则两周计划失真。
7. **安全补项**：明确 secrets 不进前端/源码/日志；外部 AI/API 经审批、字段白名单、脱敏与审计后才可启用。
8. **批量导出规则**：每个供应商输出须独立文件版本、独立文件记录/哈希、审批与审计关联；批量导出前所有供应商字段均需通过校验。
9. **修订标记处理**：`[v4.0 新增]` 等内部修订痕迹建议迁入“修订记录”附录，正文保持面向客户的干净表述。

## 建议决定

- **不直接用 v4.1 取代 v3.2。**
- 以 v4.1 的新增内容为底稿，按上面 5 项 P0 和 9 项 P1 修订生成 `v4.2`；修订后再做两轮独立对照检查。
- 特别是繁简切换、审批闭环、SKU 唯一约束、任务状态、数据库 migration 级结构，必须在进入 Codex 实施前冻结。
