# Steven AI 行政助手：本机脱敏 Demo

本单仓库仅承载 Steven 模块，路由为 `/dashboard/steven` 与 `/api/v1/steven/*`。

## 目录

- `apps/web`：Next.js + TypeScript 前端结构。
- `apps/api`：FastAPI、权限、审计、任务与 Steven 模块分层。
- `apps/api/alembic`：PostgreSQL migration 骨架。
- `docs`：模块设计、Open Design brief/产物与启动说明。
- `infra`：仅本地 PostgreSQL 示例，不代表部署配置。

OCR/AI 在受控 Demo profile 下由服务端配置开关管理；输出只进入 `review_candidates(needs_review)` 候选层，必须人工确认后才能写入业务表。2026-07-18 本轮 D2 已批准并完成 S1/S2 的本机脱敏链路：项目内 PaddleOCR 负责 PNG/JPG/PDF 文字提取，DeepSeek 仅用于 S1 校对与 S2 报价结构化；AI 不决定供应商、预算、推荐、审批、下单或正式导出。Azure、Redis、S3 在线 OCR/AI、真实业务数据和生产联网仍不在范围。

## 当前状态

- Phase 1 已验收并冻结为 Steven 基线。
- S1 标书/文书、S2 采购比价与 S3 消耗品库存均已完成本机脱敏 Demo 验证；三个模块复用认证/RBAC/CSRF、PostgreSQL、审计与版本化文件底座。
- Steven 全项目交叉验收已完成：真实 PostgreSQL Session 模式下三模块可串联读取、审批、导出并在重启后恢复。
- 当前 Alembic head 为 `20260718_0016`；`0010` 迁移通用 `operator` 角色语义，`0011` 追加 S3 Excel 批量导入，`0012` 追加 S1 多供应商 Word 元数据，`0013` 追加语言偏好、通知、S1 AI 校对候选关联与相关权限，`0014` 补齐 S2 通知审计桥接，`0015` 为 S1 模板追加智能推荐关键词，`0016` 冻结本轮 AI 辅助扩展的交付边界且不复制既有业务表。`0010 → 0016` 保持单一迁移链。
- 本机 Demo 固定为两个数据库账号：`Steven`（显示名 Steven，业务操作员）和 `approve`（显示名 审批人）。Steven 是账号名与模块命名空间，不是角色；项目 README 不记录账号密码，离线交付包使用手册按负责人要求提供演示凭据。
- 本轮全量回归结果为 `219 passed, 1 skipped, 1 warning`；compileall、ESLint、Next.js production build 与 Alembic 迁移链检查均通过。
- 已提供受控脱敏 Demo 数据 reset：默认 dry-run，真实执行要求显式确认和匹配的 plan hash；只处理固定标准脱敏命名空间。
- D1、D1.1 已完成真实 PostgreSQL 与正式项目运行时接线。
- D1.2 已于 2026-07-17 完成项目级 HTTPS、当前用户证书信任和负责人浏览器人工验收。
- S1 已实现三类内置脱敏模板、自定义模板创建/编辑/删除、事项名称关键词智能模板推荐、文书事项、规则阻断、人工修订、提交、独立审批、Word v1/v2/v3 追加式导出、已批准事项多供应商独立批量 Word 导出与分页批量打印；内置 DEMO 模板不可编辑或删除，批量文件使用独立版本、供应商快照和批次 ID 防止串数据。
- S2 已完成 3 家供应商 × 5 个品项的结构化比价、人工推荐/审批、Excel 版本化导出与已批准历史报价供应商搜索/复用入口；AI 分析推荐仅在当前页面临时展示并由用户决定是否带入原人工推荐流程，不自动写推荐字段；询价函仅生成可复制繁体草稿，不发送消息。
- S3 已完成 24 个脱敏库存品项、3 个 `DEMO-STORE-*` 库位、固定格式 Excel 批量导入、AI 建议列映射的智能导入、自然语言快速录入预览/确认、盘点差异、低库存提示、建议订货、独立审批、Excel v1/v2/v3 追加式导出与重启恢复；智能导入继续复用原预检、人工确认、事务写入和审计规则。
- 首次登录提供 S1/S2/S3 三步操作引导，侧边栏帮助按钮可随时重新打开；引导完成状态仅保存在浏览器本地，不改变账号权限或业务数据。
- 默认语言为繁体中文 `zh-TW`，可切换简体中文 `zh-CN`；登录页右上角与侧边栏底部均提供切换入口，偏好保存在浏览器 `localStorage`，且只切换系统固定文案。
- 已实现通知红点与列表、S1/S2/S3 聚合历史、显示名称与语言设置，以及旧密码验证的安全改密；改密会写审计并撤销其他 Session。
- 2026-07-18 经负责人批准，本轮 D2 已完成 S1 扫描导入、S1 模板实时预览、S1 `tender_proofreading`、S2 扫描报价结构化及人工候选确认的受控实现；真实 PaddleOCR 和单次脱敏 DeepSeek smoke 已通过。S3 在线 OCR/AI、Azure、Redis、真实业务数据与生产运行仍未批准。

当前状态只表示本机独立脱敏 Demo 闭环，不表示生产可用或可受控试运行。

## S1 标书／文书 Demo

S1 浏览器入口：

```text
https://localhost:15443/dashboard/steven/tenders
```

已实现：

- 三类持久化脱敏模板：采购／服务邀请、报价资料邀请、服务方案征集；各模板具有不同用途、变量集合和正文；
- 截止日期、预算、重复供应商及未替换 `{{...}}` 规则阻断；
- Word 草稿、人工修订、提交、批准/退回和提交人自审阻断；
- 仅已批准事项可生成正式 Word；
- 已批准事项可一次选择 2–20 名供应商，分别生成独立 Word；每份只渲染当前供应商名称与受控条款，并记录供应商快照和批次 ID；
- PostgreSQL 持久化、业务审计、request_id 与 Word 版本历史；
- 正式 Word 追加式 v1/v2/v3 导出、重新打开校验及重启恢复。

S1 支持使用共用扫描组件上传或拍摄 PNG/JPG/PDF；`tender_source_extraction` 由项目内 PaddleOCR 提取文字，再以规则和关键词匹配截止日期、预算、供应商与条款等字段。扫描结果先进入 `review_candidates(needs_review)`，不确定字段明确标记待确认，人工确认后才写入当前文书草稿，并自动触发 `tender_proofreading`。校对采用严格 JSON Schema，经 `AiReviewPanel` 逐条接受或忽略；服务端只对当前草稿中的唯一原文执行事务替换，找不到、多处重复或候选过期时拒绝写入。三类模板还提供 HTML/CSS 实时预览，未替换变量会高亮显示，不需要先生成 Word。

## 界面语言、通知、历史与个人设置

- 默认界面语言为繁体中文 `zh-TW`，可切换为简体中文 `zh-CN`；登录页和侧边栏均有切换按钮，刷新后保持偏好。
- 语言切换只影响系统固定文案，不转换用户输入、数据库业务数据、金额、SKU、文件名或 Word/Excel 内容。
- 顶部通知入口显示未读红点；审批相关动作创建通知，可标记已读并跳转到对应业务页面。
- 历史页面聚合 S1/S2/S3 操作记录并支持模块筛选；记录继续使用既有审计与 request_id 追溯边界。
- 个人设置支持显示名称、语言偏好和安全改密；改密要求验证旧密码，不回显明文，并撤销其他有效 Session。

## S2 采购比价 Demo

S2 浏览器入口：

```text
https://localhost:15443/dashboard/steven/quotes
```

已实现：

- 3 家脱敏供应商 × 5 个品项的结构化比价、人工推荐、独立审批与 Excel 版本化导出；
- 使用与 S1 相同的扫描上传组件接收 PNG/JPG/PDF，单文件上限 10MB，并进行扩展名、MIME 与 magic bytes 一致性校验；
- `quotation_extraction` 采用“PaddleOCR → DeepSeek 严格 JSON Schema → `review_candidates(needs_review)` → 人工修订/确认 → PostgreSQL 正式报价”的闭环；
- Schema 只允许供应商、报价日期与品项字段，明确禁止 AI 返回推荐、排名、审批、下单、供应商选择或总额决策；
- Provider 失败或超时会进入明确 failed 状态，不会伪装 Mock 成功，也不会直接改写正式报价表。

## S3 消耗品库存 Demo

S3 浏览器入口：

```text
https://localhost:15443/dashboard/steven/inventory
```

已实现：

- 24 个完全脱敏库存品项与 3 个 `DEMO-STORE-*` 演示库位；
- Excel 批量导入采用“上传 → 固定列/大小/行数预检 → 行级异常高亮 → 人工确认 → PostgreSQL 单事务写入”闭环；
- 导入预检覆盖重复 SKU、非负整数、目标库存、安全库存、公式注入和演示库位前缀；存在异常行时禁止确认写入；
- SKU NFKC/去空白/大小写归一唯一、非负整数和目标库存不低于安全库存规则；
- 盘点单、账面快照、盘点差异、低库存提示和服务端建议订货量；
- 人工确认补货数量；偏离系统建议时必须填写理由；
- 提交、独立审批、自审阻断和退回意见校验；
- 仅已批准盘点单可生成正式 Excel；
- PostgreSQL 持久化、业务审计、request_id、Excel v1/v2/v3 追加式历史和重启恢复。

S3 OCR `inventory_sheet_extraction` 与 AI `inventory_exception_explanation` 仅复用 D0 通用候选契约，live 开关关闭；任何未来输出只能进入 `review_candidates(needs_review)`。AI 不得确认实物库存、自动确认补货、下单或审批。

## 本机 PostgreSQL + HTTPS Demo 一键启动

前置条件：

- 既有 Windows 服务 `postgresql-x64-18` 已安装；若服务已停止，一键启动与 dry-run 重置入口会请求一次 Windows UAC，仅用于启动该既有服务，不修改其启动类型或配置；
- 既有数据库 `puiying_steven_demo`、角色 `puiying_steven_demo_app` 和 `%APPDATA%\postgresql\pgpass.conf` 凭据条目可用；
- 项目 `.venv` 已按 `apps/api/requirements.txt` 安装依赖。
- 项目级 Caddy 位于 `tools/caddy/caddy.exe`，不注册系统服务、不修改 PATH。

双击 `启动Steven本地Demo.cmd` 会以本轮批准的 PaddleOCR + DeepSeek 受控模式启动；密钥仅由 FastAPI 在运行时从批准的密钥存储位置或 `DEEPSEEK_API_KEY` 读取，不写入项目、日志或前端。也可执行：

```powershell
.\scripts\start_steven_demo.ps1 -EnableDeepSeekProofreading
```

如需明确关闭在线校对，可直接运行不带 AI 参数的 PowerShell 启动脚本；`-EnableMockProofreading` 只用于明确标记的离线验证。

启动脚本可重复执行：若现有实例健康，会直接复用并打开 HTTPS 登录页；若状态文件陈旧且项目端口均未监听，会安全清理后重新启动；若检测到半启动或异常实例，则要求先运行停止脚本，不会自动终止来源不明的进程。

API 内部健康页为 `http://127.0.0.1:9000/health`，Next.js 内部端口默认是 `127.0.0.1:4300`，浏览器唯一入口为：

```text
https://localhost:15443/login
```

若 Windows 当前动态端口排除范围包含 `4300`，不要修改系统排除配置；可执行 `./scripts/start_steven_demo.ps1 -WebPort 4700` 使用其他空闲 loopback 内部端口。HTTPS 地址、Cookie、CSRF、Origin 与 Caddy loopback 边界保持不变。

Caddy 仅监听 `127.0.0.1:15443`，并只反向代理 Next.js；Next.js 再使用既有同源 API proxy 连接 `127.0.0.1:9000`。启动脚本将 `ALLOWED_ORIGINS` 限定为 HTTPS Origin，并保持 `Secure`、`HttpOnly`、`SameSite=Lax`、CSRF、RBAC、审计及 legacy 身份头拒绝不变。直接访问内部 HTTP 页面会被 Next.js 重定向到 HTTPS。

Caddy 使用项目运行目录生成本地开发 CA，且配置了 `skip_install_trust`，不会自动写入 Windows 信任根。2026-07-17 经项目负责人明确批准，项目根证书已导入当前用户信任根并完成人工浏览器验收；启动脚本仍不会静默安装、更新或移除证书信任。

停止时双击 `停止Steven本地Demo.cmd`。脚本只停止本轮 Caddy、Next.js 与 FastAPI 进程，不修改 PostgreSQL 服务、数据库、ACL、防火墙、hosts、PATH 或系统服务。

停止脚本会按状态文件核对监听端口与进程归属，只终止已验证属于本轮 Demo 的监听进程；重复停止会安全返回，不会按陈旧 PID 误停其他程序。

## 受控重置脱敏演示数据

默认 dry-run：

```powershell
.\.venv\Scripts\python.exe .\scripts\reset_steven_demo_data.py --dry-run
```

或双击：

```text
重置Steven演示数据.cmd
```

`--dry-run` 可省略，默认行为相同。Dry-run 只显示数据库、revision、标准脱敏对象数量、文件数量、保留范围和 plan hash，不写数据库、不移动文件。

真实执行前必须停止项目，并同时提供显式确认与最近一次 dry-run 的 plan hash：

```powershell
.\.venv\Scripts\python.exe .\scripts\reset_steven_demo_data.py --apply --confirm-local-redacted-demo --expected-plan-hash <dry-run hash>
```

Reset 只处理固定标准脱敏命名空间，保留账号、角色、权限、Session schema、migration、审计历史、非标准 Demo 和非 Demo 数据。文件采用 quarantine 与 journal 的可恢复 Saga；失败 staging 数据不会无痕自动删除。

## D1.2 安全边界

- 项目 HTTPS、Next.js 和 FastAPI 均只监听 loopback；Caddy Admin 已配置为 `admin off`，`127.0.0.1:20219` 不监听。
- HTTP 不得作为降低 Secure Cookie、CSRF 或 Origin 校验的备用登录通道。
- 项目目录与项目级 Caddy CA 私钥目录 ACL 已收紧为当前 Windows 用户、`SYSTEM` 与 `Administrators`；ACL 快照保存在 `data/runtime/acl-backup-d2-*.txt`，回滚时从项目父目录使用 `icacls /restore`。
- 本轮 D2 授权仅覆盖本机脱敏 Demo 的 S1/S2 PaddleOCR 与指定 DeepSeek purpose；不自动扩展为 S3、Azure、Redis、真实业务数据、公网服务或持续运营授权。

正式验收与计划文件：

- `..\05-测试验收\Steven_全项目整体验收报告_v1_2026-07-17.md`
- `..\05-测试验收\Steven_全项目风险与D2准入清单_v1_2026-07-17.md`
- `..\90-审计记录\Steven_全项目交付实施记录_v1_2026-07-17.md`
- `..\02-实施任务\Steven_统一演示脚本_v1_2026-07-17.md`
- `..\02-实施任务\Steven_用户操作手册_v1_2026-07-17.md`
- `..\02-实施任务\Steven_交付清单_v1_2026-07-17.md`
- `..\02-实施任务\Steven_演示数据重置说明_v1_2026-07-17.md`
- `..\05-测试验收\Steven_Demo_D1_2_HTTPS验收报告_v1_2026-07-17.md`
- `..\05-测试验收\Steven_Demo_D1_2_安全边界与回滚说明_v1_2026-07-17.md`
- `..\90-审计记录\Steven_Demo_D1_2_实施记录_v1_2026-07-17.md`
- `..\02-实施任务\Steven_Demo_D2_在线OCR_AI实施计划_v1_2026-07-17.md`
- `..\05-测试验收\Steven_S1_验收报告_v1_2026-07-17.md`
- `..\05-测试验收\Steven_S1_验收报告_v2_2026-07-17.md`
- `..\05-测试验收\Steven_S1_安全边界与遗留风险_v1_2026-07-17.md`
- `..\90-审计记录\Steven_S1_实施记录_v1_2026-07-17.md`
- `..\02-实施任务\Steven_S1_演示脚本_v1_2026-07-17.md`
- `..\05-测试验收\Steven_S3_验收报告_v1_2026-07-17.md`
- `..\05-测试验收\Steven_S3_验收报告_v2_2026-07-17.md`
- `..\05-测试验收\Steven_S3_安全边界与遗留风险_v1_2026-07-17.md`
- `..\90-审计记录\Steven_S3_实施记录_v1_2026-07-17.md`
- `..\02-实施任务\Steven_S3_演示脚本_v1_2026-07-17.md`

## 便携交付包的中文路径兼容

便携交付包可以解压到中文本地路径。初始化和启动脚本会在运行期间自动使用临时 ASCII 虚拟盘符供 PostgreSQL 运行，执行停止脚本后自动释放；仍建议使用较短、可写、非网络映射的本地目录，并且不要直接在 ZIP 内运行。

## 便携交付包的大模型配置

便携交付包默认使用明确标记的本地 Mock，并提供根目录 `配置Steven大模型API.cmd`。该窗口预填 DeepSeek Endpoint `https://api.deepseek.com/v1` 与模型 `deepseek-chat`，由使用者在目标电脑本机输入 API Key；Key 通过 Windows DPAPI 按当前用户加密保存在 `data\secrets`，启动 FastAPI 时仅注入子进程环境变量，不写入数据库、日志、前端、README 或 ZIP。保存后必须停止并重新启动便携 Demo。交付包不会预置真实测试 Key。

