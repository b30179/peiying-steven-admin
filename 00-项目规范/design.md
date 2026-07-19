# 培英中学 AI 数智化平台项目设计指引

## 1. 文档目标

本文件用于规范后续多人协作开发方式。项目采用：

- 前端：Next.js + TypeScript
- 后端：FastAPI + Python
- 数据库：PostgreSQL
- 异步任务：Celery / RQ + Redis
- 文件存储：本地 NAS / MinIO / S3 兼容对象存储
- AI 能力：OCR、LLM、文档解析、结构化抽取、RAG

项目目标不是一开始就把所有需求混在一个大系统里开发，而是先为不同岗位、不同功能开发独立子系统或独立功能页，验证业务流程和交互，再通过统一架构整合成一个多角色 AI 行政管理平台。

## 2. 核心设计原则

### 2.1 一个底座，多个子系统

不同用户登录后只看到自己的专属子系统页面，不在普通侧边栏展示其他角色功能。但底层共用：

- 登录与权限
- 用户与角色
- 文件上传
- OCR 任务
- AI 生成任务
- 通知与邮件
- 审批流
- 审计日志
- 导入导出
- 系统设置

子系统只负责岗位差异化业务，例如 Apple 的奖学金、Danielle 的宿费、Tommy 的文档归档。其他角色入口只允许 Admin 或跨模块管理角色查看。

### 2.2 先模块自治，再统一集成

开发阶段允许每个用户子系统独立推进，但必须遵守统一目录、接口、数据、UI 和权限规范。每个子系统都要能被平台统一挂载到：

```text
/dashboard/{module}
/api/v1/{module}
```

前期开发策略：

- 每个功能先单独开发、单独验收，避免多人同时改同一批文件。
- 每个功能可以先做静态页面或本地 mock API，确认交互后再接入真实后端。
- 每个功能必须保留清晰边界：页面、API、数据模型、AI 任务、权限规则分别写清楚。
- 不同功能之间暂时不要互相强依赖，后续通过统一 Dashboard、统一权限、统一文件和统一任务中心集成。
- 任何功能即使独立开发，也必须遵守本文件的 UI、API、权限和审计规范，避免后期集成时返工。

后期集成策略：

- 把已验证的独立功能挂载到统一路由。
- 把重复能力抽象为共用组件或共用 API，例如文件上传、OCR 任务、AI 结果确认、审计日志。
- 由 Admin 配置用户可以访问哪些子系统。
- 普通用户登录后只看到自己的工作台和本岗位功能。

### 2.3 AI 结果必须可复核

涉及学生、人事、财务、薪酬、正式通告、对外邮件的 AI 结果，不允许直接无人确认落地。

统一流程：

```text
上传/输入
  → AI/OCR 处理
  → 生成结构化结果
  → 用户确认/修改
  → 保存正式记录
  → 写入审计日志
```

### 2.4 敏感数据优先本地化

薪酬、人事、学生名单、家长联系方式、财务记录属于敏感数据。默认策略：

- 不将敏感原文发送到未评估的外部模型。
- 外部 AI API 必须经过脱敏或审批。
- 所有文件访问和 AI 调用需记录审计日志。
- 后续如接入云模型，需确认数据不用于训练。

## 3. 总体架构

```text
Browser
  ↓
Next.js Frontend
  ↓
FastAPI Backend
  ↓
PostgreSQL
  ↓
Redis Queue
  ↓
AI/OCR Workers
  ↓
OCR / LLM / Office / PDF / Email / eClass / NAS
```

### 3.1 前端职责

Next.js 负责：

- 登录页
- 多角色 Dashboard
- 子系统页面
- 表单、表格、文件上传
- AI 结果确认界面
- 任务状态轮询
- 审批与通知 UI

前端不负责：

- 保存敏感 Token
- 直接调用第三方 OCR / LLM
- 直接访问校内文件系统
- 绕过后端发送邮件或通知

### 3.2 后端职责

FastAPI 负责：

- REST API
- 用户认证与权限校验
- 文件上传与存储
- 数据库 CRUD
- 创建 AI/OCR 异步任务
- 接收任务结果
- 审计日志
- 第三方系统集成

### 3.3 Worker 职责

Worker 负责耗时任务：

- OCR 识别
- PDF / Word / Excel 解析
- AI 文档生成
- AI 分类与摘要
- 批量邮件生成
- 批量导入校验
- 定时抓取教育局通告或邮箱

## 4. 用户与子系统规划

| 用户 | 登录后默认入口 | 侧边栏只显示 | 核心功能 |
|---|---|---|---|
| Apple | `/dashboard/apple` | 奖状奖学金、收支记录、报价单、资产管理 | 奖学金计算、奖状生成、报价单、资产盘点 |
| Danielle | `/dashboard/danielle` | 宿费对账、零用金、家长查询 | 宿费对账、零用金、家长查询 |
| Steven | `/dashboard/steven` | 标书报价、采购、库存 | 标书生成、供应商比较、库存录入 |
| Tommy | `/dashboard/tommy` | 文件归档、租务提醒、扫描件处理、归档记录 | 扫描件分类、自动命名、租务提醒 |
| Wendy | `/dashboard/wendy` | 家长通告、代课安排、月历 | 家长通告、代课安排、月历 |
| 梁小姐 | `/dashboard/leung` | 资讯汇总、薪酬计算、任务分派 | 邮件/教育局资讯汇总、薪酬、任务分派 |
| Admin | `/dashboard/admin` | 用户、权限、模块、日志、配置、跨角色入口 | 用户、权限、模块、日志、配置 |

## 5. 推荐仓库结构

建议采用单仓库 monorepo，方便统一约束和 vibe coding。

```text
school-ai-platform/
├─ apps/
│  ├─ web/                  # Next.js
│  └─ api/                  # FastAPI
├─ packages/
│  ├─ shared-types/         # OpenAPI 生成类型或手写共享类型
│  └─ ui-guidelines/        # UI token / 表单规范文档
├─ workers/
│  ├─ ocr_worker/
│  ├─ llm_worker/
│  └─ file_worker/
├─ docs/
│  ├─ design.md
│  ├─ api.md
│  └─ module-template.md
├─ infra/
│  ├─ docker-compose.yml
│  └─ nginx/
└─ README.md
```

如果团队经验较少，也可以先拆成两个目录：

```text
frontend/
backend/
```

但仍需保持同一套接口和模块命名。

## 6. 前端设计规范

### 6.1 页面布局

统一采用后台工作台布局：

```text
顶部：学校名称、当前用户、通知、退出
左侧：当前用户子系统导航
右侧：当前子系统工作区
```

每个子系统页面建议包含：

- 页面标题
- 当前最重要任务摘要
- 主操作按钮
- 核心数据表格或列表
- 当前记录详情 / AI 结果确认区

默认页面不应一次展示过多信息。统计、筛选、批量处理、导出、审计记录、历史记录等相关但非主流程功能，应优先通过按钮打开弹窗、抽屉或详情页使用。

侧边栏只放当前用户相关功能，例如 Tommy：

```text
总览
文件智能归档
租务提醒
扫描件处理
归档记录
设置
```

不要在 Tommy 的侧边栏中显示 Apple、Danielle、Wendy 等其他用户模块。

主页面信息量控制：

- 默认只展示用户当前最需要处理的内容。
- 首屏尽量控制在一个视口内完成主要操作。
- 不要同时展示统计卡、任务队列、日志、筛选器、详情、表格等所有信息。
- 同类辅助功能应合并到一个入口，例如「更多操作」。
- 搜索、筛选、批量 OCR、导出等低频操作可以放入弹窗。
- 摘要、审计日志、来源详情等信息可以放入「查看详情」弹窗。
- 页面必须保持视觉留白，不用为了填满空间而堆叠无关信息。

### 6.2 页面层级

```text
/login
/dashboard
/dashboard/apple
/dashboard/apple/awards
/dashboard/apple/finance
/dashboard/danielle/hostel-payments
/dashboard/tommy/archive
/dashboard/wendy/notices
/dashboard/admin/users
```

普通用户登录后只允许进入自己的 `/dashboard/{user}` 路径。跨角色路径必须由后端权限拒绝，不能只依赖前端隐藏菜单。

### 6.3 UI 风格

整体风格：

- 专业、清晰、低干扰
- 适合行政人员长时间使用
- 表格信息密度高，但操作清楚
- 避免花哨动效
- 避免营销式大 hero

建议色彩：

```text
主色：深青绿 / 学校品牌色
背景：#F6F7F9
卡片：#FFFFFF
边框：#D8DEE6
正文：#1D2939
弱文本：#667085
危险：#B42318
成功：#027A48
警告：#936A00
```

### 6.4 组件规范

必须统一组件：

- `PageHeader`
- `StatsCard`
- `DataTable`
- `FilterBar`
- `UploadDropzone`
- `TaskStatusBadge`
- `AiReviewPanel`
- `ConfirmDialog`
- `AuditTimeline`
- `FormSection`
- `EmptyState`

不要每个子系统自己重新设计一套按钮、表格、弹窗。

### 6.5 表格规范

表格默认只显示核心字段和必要行操作。以下能力可以提供，但不一定默认全部展开：

- 搜索
- 筛选
- 排序
- 分页
- 空状态
- 加载状态
- 错误状态
- 行操作

建议做法：

- 主页面表格只保留 5-7 个关键字段。
- 长文本字段要支持换行或截断后查看详情。
- 搜索、筛选、导出、批量操作统一放在「更多操作」或表格工具弹窗中。
- 行内操作最多保留 1-2 个主要按钮，其他操作放入更多菜单。
- 表格内容必须完整可读，不要因为列太多导致横向滚动成为主要使用方式。

典型行操作：

```text
查看
编辑
上传附件
运行 OCR
生成草稿
提交审批
删除
```

### 6.6 AI 结果确认区

AI 生成或 OCR 抽取的结果必须使用统一 UI：

```text
主界面：
- 原文件 / OCR 文本摘要
- 结构化结果核心字段
- 确认保存 / 归档 / 标记异常

详情弹窗：
- 完整 OCR 原文
- AI 摘要
- 字段来源
- 审计记录
- 重新识别
```

结果字段要显示来源：

```text
字段：付款金额
值：HK$ 500
来源：OCR
置信度：中
状态：待确认
```

## 7. 后端设计规范

### 7.1 API 命名

统一使用：

```text
/api/v1/{module}/{resource}
```

示例：

```text
GET    /api/v1/apple/awards
POST   /api/v1/apple/awards
GET    /api/v1/danielle/hostel-payments
POST   /api/v1/files/upload
POST   /api/v1/ocr/jobs
GET    /api/v1/ocr/jobs/{job_id}
POST   /api/v1/ai/generate
GET    /api/v1/audit/logs
```

### 7.2 返回格式

成功返回：

```json
{
  "data": {},
  "meta": {
    "request_id": "req_xxx"
  }
}
```

列表返回：

```json
{
  "data": [],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 100
  }
}
```

错误返回：

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "请检查输入内容",
    "details": {}
  },
  "meta": {
    "request_id": "req_xxx"
  }
}
```

### 7.3 FastAPI app 结构

```text
apps/api/
├─ app/
│  ├─ main.py
│  ├─ core/
│  │  ├─ config.py
│  │  ├─ security.py
│  │  ├─ permissions.py
│  │  └─ logging.py
│  ├─ db/
│  │  ├─ session.py
│  │  └─ base.py
│  ├─ modules/
│  │  ├─ accounts/
│  │  ├─ files/
│  │  ├─ ocr/
│  │  ├─ ai/
│  │  ├─ audit/
│  │  ├─ apple/
│  │  ├─ danielle/
│  │  ├─ steven/
│  │  ├─ tommy/
│  │  ├─ wendy/
│  │  └─ leung/
│  └─ common/
│     ├─ schemas.py
│     ├─ pagination.py
│     └─ errors.py
└─ tests/
```

### 7.4 每个模块内部结构

```text
modules/apple/
├─ router.py
├─ schemas.py
├─ models.py
├─ service.py
├─ repository.py
├─ permissions.py
└─ tests/
```

职责：

- `router.py`：API 路由
- `schemas.py`：Pydantic 请求/响应模型
- `models.py`：SQLAlchemy ORM 模型
- `service.py`：业务逻辑
- `repository.py`：数据库访问
- `permissions.py`：模块权限

## 8. 数据库设计规范

### 8.1 共用基础表

建议所有模块先共用这些表：

```text
users
roles
user_roles
permissions
role_permissions
modules
files
ocr_jobs
ai_jobs
tasks
approvals
notifications
audit_logs
system_settings
```

### 8.2 模块业务表命名

使用模块前缀：

```text
apple_awards
apple_award_recipients
danielle_hostel_payments
tommy_archive_documents
wendy_notices
leung_payroll_records
```

### 8.3 必备字段

所有业务表建议包含：

```text
id
created_at
updated_at
created_by
updated_by
status
```

涉及敏感数据的表额外包含：

```text
last_reviewed_by
last_reviewed_at
source_file_id
```

## 9. 权限设计

### 9.1 角色

```text
admin
apple
danielle
steven
tommy
wendy
leung
reviewer
```

### 9.2 权限格式

```text
{module}:{resource}:{action}
```

示例：

```text
apple:awards:read
apple:awards:write
danielle:hostel_payments:approve
tommy:archive_documents:delete
leung:payroll:export
```

### 9.3 权限规则

- 前端根据权限隐藏菜单。
- 后端必须再次校验权限。
- 导出、删除、发送通知、确认 AI 结果必须写审计日志。
- 管理员可配置用户所属角色。

## 10. AI 与 OCR 设计规范

### 10.1 统一任务模型

任何 AI/OCR 操作都创建任务：

```json
{
  "job_type": "ocr.extract_receipt",
  "module": "danielle",
  "source_file_id": "file_xxx",
  "status": "pending"
}
```

状态：

```text
pending
running
succeeded
failed
needs_review
confirmed
```

### 10.2 Prompt 管理

Prompt 不允许散落在业务代码中。统一放在：

```text
modules/{module}/prompts/
```

命名：

```text
notice_generate_zh_hk.md
receipt_extract_zh_hk.md
document_classify_zh_hk.md
```

每个 prompt 需包含：

- 适用模块
- 输入字段
- 输出 JSON schema
- 安全限制
- 示例输入
- 示例输出

### 10.3 AI 输出格式

AI 输出必须结构化：

```json
{
  "fields": {},
  "confidence": "medium",
  "warnings": [],
  "raw_text": ""
}
```

禁止只返回一段不可解析自然语言。

## 11. 多人协作与 vibe coding 规范

### 11.1 开发顺序

前期每个功能独立开发，后期再做统一集成。每个子系统或功能按以下顺序开发：

1. 写清楚岗位用户和痛点。
2. 写模块需求文档。
3. 定义数据模型。
4. 定义 API。
5. 先做独立静态页面或 mock 页面。
6. 确认页面信息量、弹窗交互和核心流程。
7. 接 API。
8. 接 AI/OCR 任务。
9. 加权限。
10. 加审计日志。
11. 写测试和使用说明。
12. 通过统一导航、权限和任务中心集成到平台。

独立功能开发要求：

- 一个功能一个目录、一个路由、一个 API 前缀。
- 不要在前期强行把多个用户需求揉进同一页面。
- 不要为了演示完整性把所有辅助信息都铺在主页面上。
- 先完成一个可以独立演示的最小闭环，再考虑和其他模块联动。
- 集成前必须确认：UI 风格统一、API 命名统一、权限规则统一、审计日志格式统一。

### 11.2 给 AI 的任务格式

每次让 AI 写代码，必须说明：

```text
模块：
用户：
业务目标：
已有文件：
要修改的文件：
不要修改的文件：
输入数据：
输出效果：
验收标准：
```

页面设计类任务还必须补充：

```text
默认页面需要展示的信息：
需要放入弹窗/抽屉的信息：
哪些按钮触发弹窗：
首屏内必须完成的操作：
不希望默认展示的信息：
```

### 11.3 禁止事项

- 不要让 AI 一次生成整个大系统。
- 不要跳过数据模型直接写页面。
- 不要在前端硬编码权限判断作为唯一安全措施。
- 不要把 Token 写入前端代码。
- 不要让 AI 输出未确认的财务、人事、学生结论直接入库。
- 不要每个模块使用不同 UI 风格。
- 不要在主页面一次展示过多信息。
- 不要把搜索、筛选、导出、审计、批量任务全部默认铺开。
- 不要在普通用户侧边栏显示其他角色子系统。

### 11.4 Pull Request 检查项

每个 PR 至少检查：

- 是否符合目录规范。
- 是否有权限校验。
- 是否有错误处理。
- 是否有空状态/加载状态。
- 是否有审计日志。
- 是否没有硬编码密钥。
- 是否更新 API 文档。
- 是否包含基本测试。

## 12. 示例模板：新增一个用户子系统

下面以 `Tommy 文件智能归档子系统` 为例。

### 12.1 模块说明

```text
模块名称：Tommy 文件智能归档
模块路径：/dashboard/tommy/archive
API 前缀：/api/v1/tommy/archive-documents
目标用户：Tommy
核心痛点：每天需要手动打开扫描文件、判断类别、改名、归档、提取金额和到期日。
业务目标：上传扫描件后，系统自动 OCR、分类、建议文件名、提取关键信息，用户确认后归档。
```

### 12.2 页面模板

```text
页面标题：文件智能归档

顶部统计：
- 今日上传
- 待复核
- 已归档
- 异常文件

主操作：
- 上传文件
- 批量运行 OCR
- 导出清单

主体区域：
- 左侧：文件列表
- 中间：文件预览 / OCR 原文
- 右侧：AI 分类结果确认表单

表格字段：
- 文件名
- 建议分类
- 建议新文件名
- 金额
- 到期日
- 状态
- 操作
```

### 12.3 前端路由模板

```text
apps/web/app/dashboard/tommy/archive/page.tsx
apps/web/app/dashboard/tommy/archive/[id]/page.tsx
apps/web/components/modules/tommy/ArchiveTable.tsx
apps/web/components/modules/tommy/ArchiveReviewPanel.tsx
apps/web/components/modules/tommy/ArchiveUploadDialog.tsx
```

### 12.4 后端 API 模板

```text
GET    /api/v1/tommy/archive-documents
POST   /api/v1/tommy/archive-documents
GET    /api/v1/tommy/archive-documents/{id}
PATCH  /api/v1/tommy/archive-documents/{id}
DELETE /api/v1/tommy/archive-documents/{id}

POST   /api/v1/tommy/archive-documents/{id}/run-ocr
POST   /api/v1/tommy/archive-documents/{id}/classify
POST   /api/v1/tommy/archive-documents/{id}/confirm
POST   /api/v1/tommy/archive-documents/{id}/archive
```

### 12.5 Pydantic Schema 模板

```python
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime

class ArchiveDocumentCreate(BaseModel):
    original_file_id: str
    note: Optional[str] = None

class ArchiveDocumentUpdate(BaseModel):
    category: Optional[str] = None
    suggested_name: Optional[str] = None
    amount: Optional[float] = None
    due_date: Optional[date] = None
    status: Optional[str] = None

class ArchiveDocumentRead(BaseModel):
    id: str
    original_file_id: str
    original_filename: str
    category: Optional[str]
    suggested_name: Optional[str]
    amount: Optional[float]
    due_date: Optional[date]
    status: str
    created_at: datetime
```

### 12.6 前端页面骨架模板

```tsx
export default function TommyArchivePage() {
  return (
    <ModulePage
      title="文件智能归档"
      description="上传扫描件后，系统会自动识别、分类、命名并提取关键信息。"
      actions={<UploadButton />}
    >
      <StatsGrid
        items={[
          { label: "今日上传", value: 12 },
          { label: "待复核", value: 4 },
          { label: "已归档", value: 36 },
          { label: "异常文件", value: 2 },
        ]}
      />

      <TwoPaneLayout
        left={<ArchiveTable />}
        right={<ArchiveReviewPanel />}
      />
    </ModulePage>
  )
}
```

### 12.7 AI Prompt 模板

```text
你是香港中学校务处文件归档助手。

请根据 OCR 文本判断文件类别，并提取结构化字段。

可选类别：
- 财务
- 人事
- 租务
- 教育局通告
- 会议
- 其他

请返回 JSON：
{
  "category": "",
  "suggested_name": "",
  "amount": null,
  "due_date": null,
  "summary": "",
  "confidence": "low|medium|high",
  "warnings": []
}

要求：
1. 不确定时 confidence 返回 low。
2. 不要编造金额和日期。
3. 文件名建议格式：YYYY-MM-DD_类别_标题。
4. 输出必须是合法 JSON。
```

### 12.8 验收标准模板

```text
1. Tommy 登录后只看到 Tommy 子系统入口，不显示 Apple、Danielle、Wendy 等其他角色功能。
2. Tommy 可以看到「文件智能归档」模块。
3. 可以上传 PDF 或图片。
4. 上传后系统创建 OCR 任务。
5. OCR 成功后显示原文。
6. AI 给出分类、建议文件名、金额、到期日。
7. 用户可以修改 AI 结果。
8. 用户点击确认后，记录状态变为 confirmed。
9. 点击归档后，文件进入对应目录。
10. 所有确认和归档动作写入审计日志。
11. 无权限用户无法访问该模块 API。
```

## 13. 模块开发文档模板

每个用户子系统必须先写一份模块设计文档：

```markdown
# 模块名称

## 1. 用户与场景

## 2. 当前痛点

## 3. MVP 范围

## 4. 暂不实现

## 5. 页面设计

## 6. 数据模型

## 7. API 设计

## 8. AI/OCR 流程

## 9. 权限规则

## 10. 审计日志

## 11. 异常处理

## 12. 验收标准
```

## 14. 第一阶段建议开发顺序

第一阶段不要同时开 6 个复杂子系统。建议：

1. 搭建统一登录、权限、Dashboard。
2. 搭建文件上传、OCR 任务、AI 任务、审计日志。
3. 先做 Tommy 文件归档或 Danielle 宿费对账作为样板模块。
4. 抽象通用组件和 API 模式。
5. 再复制样板模式给其他用户模块。

推荐第一个样板模块：

```text
Tommy 文件智能归档
```

理由：

- 需求边界清楚。
- OCR + 分类 + 文件命名 + 人工确认链路完整。
- 不直接涉及薪酬等高敏感计算。
- 可复用到教育局通告、财务单据、租务文件。

第二个样板模块：

```text
Danielle 宿费对账
```

理由：

- 能展示 OCR、金额匹配、异常队列、催缴通知。
- 和财务场景强相关，业务价值明显。

## 15. 最终目标

最终平台应形成：

```text
统一登录
统一权限
统一文件
统一 AI/OCR
统一任务
统一审计
多个岗位子系统
```

每个用户登录后只看到自己的工作台和本岗位功能，不看到其他角色对应子系统。开发、部署、权限、安全和 AI 能力仍在同一套架构内管理。
