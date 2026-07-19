# Steven 岗位 AI 行政助手：Codex 实施任务书（v2）

## 权威文件与优先级

1. `D:\ZM\AI工坊\04-项目提案\最终实施参考文档\design.md`：平台架构、统一 API、权限、安全与协作规范（最高优先级）。
2. `D:\ZM\AI工坊\培英\Steven岗位AI实施方案_整合版_v3.1_2026-07-15.docx`：Steven 业务方案。
3. `D:\ZM\AI工坊\培英\Steven需求对照审计_v1_2026-07-15.md`：对 design.md 的审计修订项与 Phase 1 门禁。
4. `D:\ZM\AI工坊\04-项目提案\最终实施参考文档\Steven整合实施设计_v3_2026-07-15.md`：历史设计细节，仅作参考。

所有新建、修改、代码、前端原型、测试、文档均写入：`D:\ZM\AI工坊\培英\`。历史 `04-项目提案` 只读，不写入新产出。

## 模块目标与不可突破边界

仅实现 Steven：`/dashboard/steven` 和 `/api/v1/steven/*`。

业务：标书/书面报价单、采购比价、消耗品库存。

不得：实现其他岗位业务；自动选供应商、审批、下单、发信或确认实盘；启用供应商网络搜索、OCR、语音或扫码作为 MVP；未经批准启用外部 LLM/OCR、部署、改系统环境或安装大依赖。

## 技术与平台统一约束

- 前端：Next.js + TypeScript。
- 后端：Python 3.11 + FastAPI。
- 数据：PostgreSQL；异步任务固定选择 **Celery + Redis 或 RQ + Redis 中的一种**，不得并存两套。
- 文件：共用 files 模块和存储 Adapter；开发可本地受控目录，生产可切 NAS/MinIO/S3。业务表禁止存绝对路径。
- 文书：docxtpl / python-docx；Excel：openpyxl。
- 共用底座最小接入：accounts、files、tasks、approvals、notifications、audit。
- API 使用统一 envelope、分页与结构化错误（详见 design.md 7.2）。

## Phase 1（先做，完成后停下汇报）

按此顺序，不要倒置：

1. 阅读权威文件、检查目录和现有工程。
2. 创建 `docs/steven-module-design.md`，包含：用户/痛点/MVP/非范围/页面、数据模型、API、AI/OCR、权限、审计、异常、验收。
3. 先定义数据模型、权限矩阵和 API contract；Steven 后端按 `router.py / schemas.py / models.py / service.py / repository.py / permissions.py / tests/` 分层。
4. 创建最小统一底座接入边界：accounts/files/tasks/approvals/notifications/audit；不实现其他岗位业务。
5. 选择并初始化 Celery+Redis 或 RQ+Redis 的统一任务接口。导出、批量导入校验以及未来 AI/OCR 都使用任务模型；任务状态：`pending/running/succeeded/failed/needs_review/confirmed`。
6. 直接调用 Open Design，生成 Steven Dashboard 设计和组件方案；将结果整合为真正运行的 Next.js 页面，而不是孤立 HTML/截图。
7. 页面必须有统一顶部栏（学校名称、当前用户、通知、退出）、Steven 专属侧边栏、`PageHeader`、`StatsCard`、`DataTable`、`FilterBar`、`UploadDropzone`、`TaskStatusBadge`、`AiReviewPanel`、`ConfirmDialog`、`AuditTimeline`、`FormSection`、`EmptyState` 或可复用等价组件。
8. Dashboard 首屏：3–4 张指标卡、最多 5 项优先待办、最近活动、三业务入口。必须包含空状态、加载状态、错误状态；先接 mock adapter，不要硬编码进页面。
9. Phase 1 smoke：前端启动、后端 health、Steven 路由、跨角色拒绝、统一 API 返回、审计事件样例。

### Phase 1 汇报格式

- 完成内容；新增/修改文件；启动命令；测试/截图；Open Design 调用结果；已知限制；下一步。
- Open Design 若报 daemon/Node/ABI 错：完整保留错误，停止环境修改，只汇报最小修复建议。

## 后续实施要求

### S1 标书/书面报价单

- 模板、字段、事项、预算、日期、地点、供应商、条款、附件、版本、审批。
- 校验：必填；截止日期不早于生成日+3天；预算非负且下限≤上限；供应商去重；残留 `{{...}}` 变量使任务为 `draft_error`，禁止正式导出。
- 状态：`draft → needs_review → pending_approval → approved → exported`。
- 提交/批准/退回/导出均写 approvals、notifications（待审批）和 audit；本人不可批准本人。
- 文件名：`YYYYMMDD_文书类型_事项简称_v{版本}.docx`；正式版本不覆盖历史。

### S2 采购比价

- 手工/Excel 导入；数量>0；单价/税/运费≥0；行总价=数量×单价；含税总价=行总价+运费+税费；币种不一致阻断。
- 推荐供应商默认空；非最低价必须有理由及审批意见；报价过期异常提示。
- 输出：`YYYYMMDD_采购比价_事项简称_v{版本}.xlsx`。

### S3 库存

- 表单/Excel 导入；SKU 唯一；盘点/安全/目标库存为非负整数；负数或重复 SKU 拒绝保存。
- 建议订货量=`max(0,target_qty-counted_qty)`；低于安全库存标红；人工确认实盘。
- 输出：`YYYYMMDD_库存盘点_库位_v{版本}.xlsx`。

## AI/OCR 约束

MVP 默认禁用 AI/OCR；但必须预留可关闭 Adapter 和结构化任务合同。

若后续启用：
- Prompt 只放 `modules/steven/prompts/`；包含模块、输入、JSON schema、安全限制、示例。
- 输出为 `{fields, confidence, warnings, raw_text}`，进入 `needs_review`，不得直接写正式记录。
- 敏感信息未经校方批准不得外发。

## P0 验收

1. 日期缺失阻止生成标书。
2. 残留模板变量禁止正式导出。
3. Word 输出可再次打开编辑。
4. 三供应商五品项的总价/税费/运费/排序正确。
5. 非最低价无理由或审批意见不可提交。
6. 负库存、重复 SKU 不可保存。
7. 低库存和订货建议正确。
8. 普通用户无权读审计。
9. Steven 无权访问其他岗位路由/API。
10. 导出、删除、提交/批准审批、AI 结果确认全部有审计事件；待审批有通知记录。
11. API 符合 response envelope；列表支持 pagination。
12. secrets 不进入前端、代码或日志。
