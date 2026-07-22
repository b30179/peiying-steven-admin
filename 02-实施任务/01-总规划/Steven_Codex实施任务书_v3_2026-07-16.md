# Steven 岗位 AI 行政助手：Codex 实施任务书（v3）

## 任务目标

以 `Steven岗位AI实施方案_整合版_v4.6_2026-07-16.docx` 为当前实施基线，建立可运行的 Steven 模块项目骨架。范围仅限 Steven：标书/书面报价单、采购比价、消耗品库存；不实现其他岗位业务。

## 权威文件与优先级

1. `D:\ZM\AI工坊\某中学\00-项目规范\design.md`：平台架构、路由、权限、安全、接口、UI 与协作规范，最高优先级。
2. `D:\ZM\AI工坊\某中学\01-当前方案\Steven岗位AI实施方案_整合版_v4.6_2026-07-16.docx`：当前业务与数据模型基线。
3. 本任务书：本阶段交付范围与验收要求。
4. `03-参考资料/`、`90-审计记录/`、`99-历史归档/`：仅供参考，不得覆盖前述规范。

所有新建、修改、代码、前端原型、测试与文档必须写入 `D:\ZM\AI工坊\某中学\`。历史 `D:\ZM\AI工坊\04-项目提案\` 只读，不写入新产出。

## 不可突破边界

- 路由仅可使用 `/dashboard/steven` 和 `/api/v1/steven/*`。
- 前端使用 Next.js + TypeScript；后端使用 Python 3.11 + FastAPI；数据库使用 PostgreSQL。
- 统一底座只接入 accounts、files、tasks、approvals、notifications、audit 的最小边界；不要实现其他岗位模块。
- AI/OCR 在 MVP 中默认禁用；只保留可关闭 Adapter、结构化任务合同与人工确认入口。后续经批准启用内嵌大模型时，默认提供商为 DeepSeek，且只能由 FastAPI 后端 Adapter 调用；密钥仅从服务端环境变量或受管密钥存储读取，前端不得直连或持有密钥。不得接入外部模型、OCR、供应商网络搜索或真实系统。
- 不得实现自动选供应商、审批、下单、发信或任何实盘确认。
- 不得写入密钥、Token、真实个人资料或真实业务数据；测试数据必须脱敏。
- 未经主人明确同意，不部署、不改系统环境、不安装大型依赖。

## v4.6 采购比价硬约束

数据关系必须为：

```text
steven_quote_jobs
  -> steven_quote_items
  -> steven_quote_suppliers
  -> steven_quote_offer_lines
```

- 运费和税费记录并汇总在供应商报价单层 `steven_quote_suppliers`，不能复制计入每个品项。
- 首个 migration 必须为 `steven_quote_offer_lines` 建立：`UNIQUE(quote_supplier_id, quote_item_id)`。
- T04 验收数据必须包含 3 家供应商 x 5 个品项 = 15 条报价明细。
- 任一供应商对任一品项缺报价，必须显式标记该供应商报价不完整，进入人工处理；不可当作完整报价自动比较。
- 数量必须大于 0；单价、税费、运费不得为负；币种不一致必须阻断计算。

## Phase 1：项目骨架与可运行 Dashboard

按顺序执行，完成后停止并汇报，不进入完整业务开发：

1. 阅读权威文件，检查 `04-开发实现/` 现状。
2. 在 `04-开发实现/` 初始化统一单仓库骨架：`apps/web`、`apps/api`、`docs`、`infra`；不要创建与规范冲突的平行架构。
3. 创建 `docs/steven-module-design.md`，明确 MVP、非范围、页面、数据模型、权限矩阵、API contract、审计事件、异常处理与 P0 验收映射。
4. 后端按 `router.py / schemas.py / models.py / service.py / repository.py / permissions.py / tests/` 分层建立 Steven 模块；创建 PostgreSQL migration 骨架，包含报价明细复合唯一约束。
5. 建立 accounts/files/tasks/approvals/notifications/audit 的最小接口边界和统一 API response envelope；任务状态统一使用 `pending/running/succeeded/failed/needs_review/confirmed`。
6. 先将页面需求、目标用户、页面清单、组件与状态整理为 Open Design 输入 brief，保存到 `04-开发实现/docs/open-design-steven-dashboard-brief.md`。前端视觉、信息架构和交互设计必须由 Open Design 产出；不要由 Codex 自行另起一套视觉设计。
7. 将 Open Design 产出的设计 artifact、截图或可复用组件说明保存到 `04-开发实现/docs/open-design/`；Codex 负责把该设计实现为真正运行的 Next.js 页面，而不是保留孤立 HTML 或截图。若 Open Design 当前不可用，只记录阻断和最小修复建议，继续完成不依赖视觉设计的后端与前端结构，不擅自替代其设计决策。
8. 实现可运行的 `/dashboard/steven`：统一顶部栏、Steven 侧边栏、PageHeader、3-4 张指标卡、最多 5 项优先待办、最近活动、三个业务入口。使用 mock adapter，禁止直接硬编码业务数据到页面。
9. 页面必须具备空、加载、错误状态；普通用户跨角色访问必须由后端拒绝。
10. 提供最小 smoke：前端启动、后端 health、Steven 路由、统一 API envelope、跨角色拒绝、审计事件样例。

## Phase 1 交付位置

- 源码、migration、配置样例与启动说明：`04-开发实现/`
- 设计说明：`04-开发实现/docs/`
- 测试用例、测试结果、截图与验收证据：`05-测试验收/`
- 本轮变更说明：`90-审计记录/`

## 完成汇报格式

提交以下内容后停下等待下一阶段指令：

1. 完成内容与新增/修改文件清单。
2. 启动命令及实际 smoke 结果。
3. 数据模型与 migration 中已落实的约束。
4. 页面截图或可访问地址。
5. Open Design 设计产物的路径、实现对应关系，或明确阻断证据。
6. 已知限制、尚未实现的业务与下一步建议。
7. 如 Open Design、Node、ABI 或依赖出现问题：保留完整错误与最小修复建议；不得自行修改系统环境。
