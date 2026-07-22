# Steven Phase 2 分阶段实施计划（v1）

- 制定日期：2026-07-16
- Phase 1 基线标识：`Steven-Phase1-BL-2026-07-16`
- 规划状态：待项目负责人选择先实施 S1、S2 或 S3
- 适用目录：`D:\ZM\AI工坊\某中学\`

## 1. 规划依据与优先级

1. `00-项目规范/design.md`：平台架构、路由、API、权限、审计、安全和 UI 规范，最高优先级。
2. `01-当前方案/Steven岗位AI实施方案_整合版_v4.6_2026-07-16.docx`：Steven 当前业务、数据模型和验收基线。
3. `02-实施任务/Steven_Codex实施任务书_v3_2026-07-16.md`：开发边界、采购比价硬约束和 Phase 1 已落实的工程合同。

如后续出现冲突，按上述优先级处理；无法合理推断的业务规则集中提交最少问题，不自行编造。

## 2. Phase 1 基线锁定

`Steven-Phase1-BL-2026-07-16` 作为后续实施起点，包含：

- `/dashboard/steven` Dashboard、Steven 专属导航和 Open Design 已落地视觉/交互。
- FastAPI health、统一 API envelope、开发身份 seam、跨角色拒绝和审计读取权限。
- `router.py / schemas.py / models.py / service.py / repository.py / permissions.py / tests/` 分层骨架。
- 报价明细 `UNIQUE(quote_supplier_id, quote_item_id)` migration 约束。
- DeepSeek 后端 Adapter 占位，默认关闭；未接真实 AI/OCR、数据库、外部服务或密钥。

后续阶段不得回写或重新定义 Phase 1 验收事实；若发现基线缺陷，应单独提出变更申请和回归范围。

## 3. 全阶段共同实施约束

### 3.1 技术与范围

- 前端：Next.js + TypeScript；仅新增 `/dashboard/steven/*` 页面。
- 后端：Python 3.11 + FastAPI；仅新增 `/api/v1/steven/*` API。
- 数据模型按 PostgreSQL 设计 migration，但规划阶段及获准实施阶段默认不连接真实业务数据库；使用内存 repository、mock adapter 或隔离测试环境验证合同。
- 文件、任务、审批、通知、审计优先复用平台共用边界，不在 Steven 模块重复建设平台底座。
- 每一业务阶段独立实现、独立验收、独立停下汇报；未经确认不顺带进入下一业务模块。

### 3.2 绝对业务边界

- 不自动选择或推荐供应商；推荐供应商字段默认空白，由人工填写。
- 不自动审批、不自动下单、不自动发送邮件、不自动确认实物库存。
- 不做供应商网络搜索、报价 OCR、语音录入、条码扫码。
- AI/OCR 默认禁用；DeepSeek 只保留服务端 Adapter 计划，不连接真实服务、不配置密钥。
- AI 未来只能产生结构化候选或说明，状态必须先进入 `needs_review`，经人工确认后才可进入 `confirmed`；关闭 AI 时模板和规则流程必须完整可用。
- 正式 Word/Excel 每次导出创建新版本，不覆盖草稿或历史版本。
- 前端隐藏不等于权限控制，所有 API 必须执行角色/权限校验。

### 3.3 通用交付门槛

每个阶段必须同时完成：

1. Open Design 先产出对应页面的视觉、信息架构和交互方案，保存至 `04-开发实现/docs/open-design/`。
2. Codex 将设计整合为真正运行的 Next.js 页面，不保留孤立 HTML 或截图。
3. 后端 API 使用统一成功/错误 envelope，并为写操作记录审计事件。
4. migration 仅作为 PostgreSQL 数据合同提交和离线检查，不连接或修改真实数据库。
5. 测试数据脱敏；自动化测试优先，无法自动化的项目提供稳定复现步骤和截图。
6. 每阶段完成后停止，提交文件清单、启动方式、测试结果、截图、限制和下一步建议。

---

## 4. 阶段 S1：标书 / 书面报价单

### 4.1 阶段目标

交付从已启用模板选择、字段填写、规则校验、Draft Word 生成、人工复核、提交审批到批准后版本化导出的完整受控流程。AI 关闭时仍可完全运行。

### 4.2 用户流程

1. Steven 进入“标书与报价单”列表。
2. 点击“新建文书”，选择已启用模板并查看模板变量、必填标识和示例。
3. 填写事项名称、截止日期、预算上下限、供应商、交付地点和特殊条款。
4. 系统执行字段校验；错误定位到具体字段，不创建正式文件。
5. 校验通过后创建生成任务，输出独立的 Draft v1 Word。
6. Steven 下载/打开草稿，进行人工复核；系统记录复核人、时间和备注。
7. Steven 提交审批；提交人不得审批本人任务。
8. 审批人批准或退回；退回后返回人工修改/复核。
9. 批准后由获授权角色正式导出；单次或批量供应商版本均创建新文件版本，不覆盖历史。

### 4.3 页面清单

- `/dashboard/steven/tenders`：文书事项列表、状态 Badge、截止日期、模板、当前版本、最多两个行内动作。
- 新建/编辑宽抽屉：模板选择、基本信息、供应商与条款、校验摘要。
- 复核抽屉：字段来源、模板变量、异常位置、草稿版本、人工复核动作。
- 版本抽屉：Draft/正式版本、供应商、操作人、时间、任务编号、文件哈希和下载入口。
- 审批确认弹窗：提交、批准、退回和正式导出的显式确认。
- loading、empty、error、`draft_error`、`needs_review`、`pending_approval`、`approved`、`exported` 状态。

### 4.4 API 清单

- `GET /api/v1/steven/templates`：已启用模板和变量定义。
- `GET /api/v1/steven/tenders`：分页列表。
- `POST /api/v1/steven/tenders`：创建草稿事项。
- `GET /api/v1/steven/tenders/{id}`：详情。
- `PATCH /api/v1/steven/tenders/{id}`：仅允许可编辑状态修改。
- `POST /api/v1/steven/tenders/{id}/generate`：创建 Word 草稿任务。
- `POST /api/v1/steven/tenders/{id}/confirm-review`：记录人工复核，不代表审批。
- `POST /api/v1/steven/tenders/{id}/submit-approval`：提交审批。
- `POST /api/v1/steven/approvals/{id}/approve`：审批人批准。
- `POST /api/v1/steven/approvals/{id}/reject`：审批人退回并填写意见。
- `POST /api/v1/steven/tenders/{id}/export`：批准后正式导出。
- `POST /api/v1/steven/tenders/{id}/batch-export`：批准后按多个供应商生成独立版本。
- `GET /api/v1/steven/tenders/{id}/versions`：版本记录。
- `GET /api/v1/steven/tasks/{task_id}`：生成任务状态。

### 4.5 数据表与 migration 计划

- `steven_templates`：`id/type/version/file_id/fields_json/is_active/status/created_at/updated_at/created_by/updated_by`；`type + version` 唯一；`file_id -> files.id`。
- `steven_tender_jobs`：`template_id/payload_json/status/source_file_id/last_reviewed_by/last_reviewed_at` 及通用追溯字段。
- 平台 `files`：记录模板、草稿、正式版本的相对存储键、哈希、文件类型和版本；Steven 表不保存绝对路径。
- 平台 `tasks`：记录 Word 生成任务及 `pending/running/succeeded/failed` 状态。
- 平台 `approvals`：记录提交人、审批人、状态、意见和时间；禁止提交人自审。
- migration 计划：新增 S1 表、外键、`type + version` 唯一约束和必要索引；不修改 Phase 1 报价唯一约束。
- migration 验证：离线 SQL、SQLAlchemy metadata/约束测试；不连接真实 PostgreSQL。

### 4.6 后端规则与 AI 边界

- 必填字段不可缺失。
- 截止日期不得早于生成日加 3 天。
- 预算金额使用 Decimal/numeric；非负且下限不得大于上限。
- 至少 1 家供应商；供应商名称按标准化后去重。
- 生成后检查所有 `{{...}}` 变量；存在未替换变量时标记 `draft_error`。
- `draft_error`、未人工复核或未审批状态不得正式导出。
- 每次生成/导出从版本服务取得新版本号；文件名遵循 `YYYYMMDD_文书类型_事项简称_v{版本}.docx`。
- Word 必须可由 Microsoft Word/兼容软件重新打开和编辑。
- DeepSeek 未来仅可辅助润色获批准的特殊条款或异常说明；不得改变金额、日期、供应商、审批状态或模板变量；本阶段默认关闭，仅保留 Adapter 合同和人工复核 UI 位置。

### 4.7 权限、审计与人工确认

- `steven:tenders:read/write/submit`：Steven。
- `steven:tenders:export`、`steven:approvals:approve`：审批人或明确授权角色。
- `steven:audit:read`：IT/管理员；普通 Steven 用户不得读取完整审计数据。
- 审计事件：`tender.create/update/generate/review/submit/approve/reject/export/batch_export`。
- 人工确认点：草稿复核、提交审批、批准/退回、正式导出、批量导出供应商选择。
- 提交人自审必须返回 403，并保留审批与审计记录。

### 4.8 验收数据与测试用例

- 3 个脱敏可维护 Word 模板；每个模板包含变量字典、必填标识和示例。
- 1 个正常文书事项，含 3 家供应商，用于 Draft、审批和批量导出。
- 1 个含未替换变量的测试模板/副本，仅用于 T02。
- P0：缺截止日期不能生成；截止日期不足 3 天被阻止；预算非法被阻止；重复供应商被阻止。
- P0：未替换变量进入 `draft_error`，不能提交或正式导出。
- P0：Word 输出可重新打开、修改并保存。
- P0：批量导出 3 个供应商版本，生成 3 个独立文件且字段不串数据。
- P0：正式导出不覆盖草稿或历史版本。
- P0：提交人自审被拒绝；跨角色访问被拒绝；写操作均有审计。
- P1：AI 关闭时纯模板流程完整通过。

### 4.9 完成标准

- 页面、API、状态机、Word 生成、审批接口和版本记录端到端可演示。
- S1 自动化测试全部通过，P0 无阻断缺陷。
- 至少提供 1 次完整正常流程和 1 次 `draft_error` 流程截图/记录。
- 无真实 AI/OCR、数据库、外部服务或密钥调用。
- 阶段报告明确已完成能力与未部署/未接入能力。

### 4.10 风险、依赖与非范围

- 依赖：校方确认的 3 份 Word 范本、变量字典、审批角色和文件存储规则。
- 风险：Word 模板 run 拆分、复杂表格和页眉页脚可能导致变量识别遗漏；需模板扫描和重新打开测试。
- 风险：审批角色未确认会影响正式导出权限；未确认前使用脱敏角色假设并标注。
- 不实现：真实邮件发送、电子签署、复杂多级审批、外部 AI 润色、供应商搜索、OCR。

---

## 5. 阶段 S2：采购比价

### 5.1 阶段目标

交付采购事项、标准品项、供应商报价单和报价明细的结构化录入/导入、规则计算、异常阻断、人工填写推荐与审批意见、可编辑 Excel 导出。系统只计算和提示，不自动选择供应商。

### 5.2 用户流程

1. Steven 创建采购事项，设置事项名称和统一币种。
2. 录入 5 个标准采购品项及数量，或导入标准 Excel/CSV 草稿。
3. 为 3 家供应商分别录入报价单级资料：有效期、运费、税费、附件引用。
4. 为每家供应商录入 5 条报价明细，共 15 条完整明细。
5. 系统校验数量、金额、重复明细、缺报价、币种和有效期。
6. 仅当报价完整且币种一致时计算小计、含税总价和价格排序。
7. 推荐供应商字段保持空白，由人工选择；非最低价时必须填写理由和审批意见。
8. 人工提交审批/确认后导出可编辑 Excel，新建版本且不覆盖历史。

### 5.3 页面清单

- `/dashboard/steven/quotes`：采购事项列表、供应商数、品项数、完整性、币种、有效期、推荐状态。
- 采购事项详情：标准品项表、供应商报价单卡片、15 格报价矩阵或分供应商明细表。
- 导入抽屉：模板下载、文件选择、预检结果、行号错误、确认写入。
- 异常抽屉：缺报价、币种不一致、过期报价、负数/非数字和重复明细。
- 人工推荐/审批弹窗：推荐供应商、非最低价理由、审批意见，默认均为空。
- 版本/附件/审计抽屉；导出确认和 Toast。

### 5.4 API 清单

- `GET /api/v1/steven/quotes`、`POST /api/v1/steven/quotes`。
- `GET /api/v1/steven/quotes/{id}`、`PATCH /api/v1/steven/quotes/{id}`。
- `GET/POST /api/v1/steven/quotes/{id}/items`。
- `GET/POST /api/v1/steven/quotes/{id}/suppliers`。
- `GET/POST /api/v1/steven/quotes/{id}/offer-lines`。
- `POST /api/v1/steven/quotes/import`：预检并返回结构化错误，不因附件存在视为数据正确。
- `POST /api/v1/steven/quotes/{id}/confirm-import`：人工确认写入已通过预检的数据。
- `POST /api/v1/steven/quotes/{id}/recommendation`：人工保存推荐、理由和审批意见。
- `POST /api/v1/steven/quotes/{id}/submit-approval`：提交人工推荐审批。
- `POST /api/v1/steven/quotes/{id}/export`：导出可编辑 Excel 新版本。
- `GET /api/v1/steven/quotes/{id}/versions`。

### 5.5 数据表与 migration 计划

沿用并补全 Phase 1 已建立的关系：

```text
steven_quote_jobs
  -> steven_quote_items
  -> steven_quote_suppliers
  -> steven_quote_offer_lines
```

- `steven_quote_jobs`：补全 `subject/currency/recommended_supplier_id/source_file_id` 和通用追溯字段。
- `steven_quote_items`：`item/specification/qty/unit`；`qty > 0`。
- `steven_quote_suppliers`：`supplier_name/source_file_id/valid_until/freight/tax/subtotal/total/currency`；金额 numeric 且非负。
- `steven_quote_offer_lines`：`quote_supplier_id/quote_item_id/unit_price/line_total/remark`；保留并验证 `UNIQUE(quote_supplier_id, quote_item_id)`。
- 供应商级运费和税费只保存在 `steven_quote_suppliers`，不得复制到每个品项。
- 推荐供应商外键指向 `steven_quote_suppliers.id`，默认 `NULL`。
- migration 计划：在不破坏 Phase 1 migration 的前提下增量补列、外键、检查约束和索引；离线验证，不连接真实数据库。

### 5.6 后端规则与 AI 边界

- 数量 `> 0`；单价、运费、税费 `>= 0`；金额使用 Decimal/numeric，禁止 float。
- 行总价 = 数量 × 单价，由系统计算，不接受客户端覆盖。
- 供应商小计 = 该供应商所有行总价之和。
- 含税总价 = 小计 + 供应商级运费 + 供应商级税费；每家供应商费用只计算一次。
- 3 家 × 5 品项必须恰有 15 条唯一报价明细才视为全部完整。
- 任一供应商缺任一品项时标记 `incomplete`，不得进入完整价格比较或自动排序结论。
- 币种不一致时阻断比较；报价过期显示醒目异常。
- 推荐供应商默认空白；系统不得根据最低价自动写入推荐字段。
- 人工选择非最低价供应商时，非最低价理由和审批意见两项缺一不可。
- DeepSeek 未来仅可生成异常说明草稿或整理人工备注，不得推荐供应商、改变金额或作审批结论；本阶段不调用真实模型。

### 5.7 权限、审计与人工确认

- `steven:quotes:read/write/export`：Steven；审批动作由 `steven:quotes:approve` 或获授权审批角色执行。
- 审计事件：`quote.create/update/import_precheck/import_confirm/offer_line_write/calculate/recommend/submit/approve/reject/export`。
- 人工确认点：导入写入、异常修正、推荐供应商、非最低价理由、审批意见、提交审批、导出。
- 附件只作为留档来源；不得因附件存在跳过结构化数据校验。

### 5.8 验收数据与测试用例

标准验收数据：

- 1 个采购事项，统一币种 HKD。
- 5 个标准品项，每个数量均大于 0。
- 3 家供应商，每家 5 条报价明细，共 15 条。
- 每家供应商各自设置运费、税费和有效期。
- 预置可人工核对的行总价、小计、含税总价和排序结果。

异常数据：

- 删除 1 条报价明细形成 14 条：供应商报价不完整，阻断完整比较。
- 1 家供应商币种改为 USD：阻断比较。
- 1 家报价有效期早于当前日期：显示过期异常。
- 数量为 0、负单价、负运费、负税费：拒绝保存并定位字段/行号。
- 重复供应商+品项报价：触发复合唯一约束/服务层校验。
- 人工推荐非最低价但缺理由或审批意见：阻止提交。

完成测试：

- P0 T04、T05、T14、T15 全部通过。
- Excel 导出可重新打开和编辑，文件名为 `YYYYMMDD_采购比价_事项简称_v{版本}.xlsx`。
- 再次导出创建新版本，不覆盖历史。
- 普通用户无权读取完整审计；跨角色 API 返回 403。

### 5.9 完成标准

- 15 条标准报价的计算、完整性、币种、有效期和排序测试全部通过。
- 页面能明确区分“最低价排序结果”和“人工推荐”，推荐字段不会自动填充。
- 非最低价双字段校验、导入预检、人工确认和审计闭环可演示。
- Excel 输出可编辑、版本独立；无真实 OCR、AI、数据库或外部调用。

### 5.10 风险、依赖与非范围

- 依赖：校方确认的比价 Excel 列结构、币种处理口径、税费含义、审批角色。
- 风险：不同供应商报价口径不一致；MVP 仅接受标准结构化录入，不自行推断附件内容。
- 风险：税费可能是金额或税率；实施前必须确认，未确认时按方案中的“供应商级金额”处理并标注假设。
- 不实现：报价 OCR、供应商网络搜索、自动推荐、自动审批、自动下单、邮件询价、汇率换算。

---

## 6. 阶段 S3：消耗品库存

### 6.1 阶段目标

交付库存清单、网页单项录入、标准 Excel 批量盘点预检、盘点差异、低库存提示、建议订货量和人工确认记录。系统只提供建议，不确认实物库存或订货结果。

### 6.2 用户流程

1. Steven 进入库存列表，按库位、状态和低库存筛选。
2. 新建/编辑库存品项，填写唯一 SKU、名称、库位、账面量、安全库存和目标库存。
3. 通过网页录入本次盘点量，或上传标准 Excel 进行批量预检。
4. 系统检查负数、非整数、重复 SKU、缺失字段和目标库存规则。
5. 预检通过后由人工确认写入盘点记录；保留历史盘点，不覆盖旧记录。
6. 系统计算盘点差异和建议订货量，低于安全库存时标红。
7. Steven 现场核实后记录“已人工确认/需复查”，系统不改变实物事实。
8. 导出低库存或盘点清单，每次创建新文件版本。

### 6.3 页面清单

- `/dashboard/steven/inventory`：SKU、品项、库位、账面量、本次盘点量、安全库存、目标库存、建议订货量和状态。
- 单项录入/编辑抽屉。
- Excel 导入抽屉：模板、预检、重复行、负数、行号错误和人工确认写入。
- 差异/低库存抽屉：账面差异、规则说明、建议订货量和人工确认状态。
- 导出确认、历史盘点、附件和审计抽屉。
- loading、empty、error、low-stock、needs_review、confirmed 状态。

### 6.4 API 清单

- `GET /api/v1/steven/inventory`、`POST /api/v1/steven/inventory`。
- `GET /api/v1/steven/inventory/{id}`、`PATCH /api/v1/steven/inventory/{id}`。
- `POST /api/v1/steven/inventory/import`：Excel 预检。
- `POST /api/v1/steven/inventory/import/{task_id}/confirm`：人工确认写入通过预检的数据。
- `POST /api/v1/steven/inventory/{id}/counts`：新增盘点记录。
- `POST /api/v1/steven/inventory/counts/{id}/confirm-review`：记录人工核实状态，不代表系统确认实物。
- `GET /api/v1/steven/inventory/low-stock`：低库存清单。
- `GET /api/v1/steven/inventory/{id}/counts`：盘点历史。
- `POST /api/v1/steven/inventory/export`：导出盘点/低库存清单新版本。

### 6.5 数据表与 migration 计划

- `steven_inventory_items`：`id/sku/name/location/current_qty/safety_qty/target_qty/status` 及通用追溯字段。
- `steven_inventory_counts`：`inventory_item_id/count_qty/counted_at/source_file_id/last_reviewed_by/last_reviewed_at/status` 及通用追溯字段。
- `sku` 唯一；数量字段使用 integer 且 `>= 0`；`target_qty >= safety_qty`。
- 盘点记录只新增，不覆盖历史；批量导入附件通过 `source_file_id -> files.id` 关联。
- 建议订货量作为服务层计算结果或可重算字段，不把未经人工确认的建议写成订单事实。
- migration 计划：新增库存表、SKU 唯一约束、非负检查、目标库存检查、外键和查询索引；离线验证，不连接真实数据库。

### 6.6 后端规则与 AI 边界

- SKU 必须唯一；导入预检可高亮重复，确认写入时仍必须拒绝重复 SKU。
- 账面量、盘点量、安全库存和目标库存均为非负整数；负数或小数拒绝保存。
- 目标库存不得低于安全库存。
- 盘点差异 = 本次盘点量 - 账面量，仅提示差异，不判断实物对错。
- 建议订货量 = `max(0, 目标库存 - 本次盘点量)`。
- 本次盘点量低于安全库存时标红并进入低库存清单。
- DeepSeek 未来仅可整理异常说明或人工备注，不得确认盘点结果、生成订单或决定采购数量；本阶段不调用真实模型。

### 6.7 权限、审计与人工确认

- `steven:inventory:read/write`：Steven；完整审计仍仅 IT/管理员读取。
- 审计事件：`inventory.create/update/import_precheck/import_confirm/count_create/count_review/low_stock_view/export`。
- 人工确认点：批量导入写入、盘点差异复核、低库存现场核实、建议订货量接受/调整、导出。
- “已人工确认”只记录谁在何时核实了页面数据，不表示系统确认实物库存或已完成订货。

### 6.8 验收数据与测试用例

标准数据：

- 至少 20 个脱敏库存品项，覆盖多个库位。
- 至少 5 个低库存品项、3 个盘点差异品项、若干正常品项。
- 每项均有 SKU、账面量、盘点量、安全库存和目标库存。

异常数据：

- 重复 SKU 两行：预检高亮，确认写入拒绝。
- 负盘点量、负安全库存、负目标库存：拒绝并提示行号。
- 小数盘点量：拒绝整数校验。
- 目标库存低于安全库存：拒绝保存。

完成测试：

- P0 T07、T08、T14、T15 全部通过。
- 低库存清单与建议订货量逐项匹配公式。
- 历史盘点记录不被新盘点覆盖。
- 导出文件可编辑，命名为 `YYYYMMDD_库存盘点_库位_v{版本}.xlsx`，重复导出创建新版本。
- 跨角色访问和普通用户审计读取被拒绝。

### 6.9 完成标准

- 20 项标准导入、重复/负数拦截、盘点历史、低库存和建议订货量测试全部通过。
- 页面清楚区分系统计算建议与人工实物确认。
- 导入确认、差异复核、导出和审计链路可演示。
- 无条码、语音、真实 AI/OCR、数据库、订单或外部服务调用。

### 6.10 风险、依赖与非范围

- 依赖：校方确认的库存 Excel 列结构、SKU 规则、库位命名、安全库存和目标库存口径。
- 风险：历史表可能无 SKU 或 SKU 不唯一；MVP 不自动合并，须由人工清洗后导入。
- 风险：账面量与盘点量差异不能由系统判断原因，必须保留人工备注和复查状态。
- 不实现：条码扫码、语音盘点、自动确认实物、自动生成采购单、自动下单或供应商联动。

---

## 7. 建议的阶段选择与依赖关系

三个业务阶段可独立启动，但建议遵循以下判断：

- 先选 S1：适合优先验证 Word 模板、文件版本和审批边界；对 S2/S3 的计算模型依赖较少。
- 先选 S2：适合优先验证当前最明确的 3×5 数据模型和 Phase 1 已建立的报价唯一约束。
- 先选 S3：适合优先验证规则计算、Excel 导入预检和人工确认，业务链路相对独立。

无论选择哪一项，均先执行该阶段的“范围冻结 → Open Design → API/数据合同 → 实现 → 权限审计 → P0 验收 → 阶段汇报”，完成后停止，不自动进入下一项。

## 8. 启动前需确认的最少事项

选择具体阶段后，仅对该阶段确认以下材料：

- S1：至少 3 份脱敏 Word 范本、模板变量、审批角色和正式导出权限。
- S2：比价 Excel 样本、税费口径、统一币种规则、推荐/审批角色。
- S3：至少 20 项脱敏库存样本、SKU 和库位规则、安全/目标库存口径。

材料不足时可使用明确标注的脱敏演示数据，不宣称已满足真实业务。

## 9. 本规划明确不执行的事项

本文件仅为实施计划。本轮不编写业务代码、不修改 migration、不安装依赖、不连接真实数据库、不调用 Open Design 生成新页面、不接入 DeepSeek/AI/OCR、不配置密钥、不部署、不调用外部服务。