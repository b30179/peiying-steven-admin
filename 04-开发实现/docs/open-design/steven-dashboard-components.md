# Steven 采购行政工作台组件说明

目标路由：`/dashboard/steven`。此方案只服务 Steven（采购行政），不要复用为其他岗位导航、页面或数据入口。

## 建议目录

```text
app/dashboard/steven/page.tsx
components/steven/
  StevenShell.tsx
  StevenSidebar.tsx
  StevenTopbar.tsx
  DashboardHeader.tsx
  MetricCard.tsx
  PriorityTodoList.tsx
  PriorityTodoItem.tsx
  RecentActivity.tsx
  ModuleEntryCard.tsx
  ReviewDrawer.tsx
  ConfirmDialog.tsx
  ToastRegion.tsx
  EmptyState.tsx
  ErrorState.tsx
  LoadingTodoList.tsx
lib/steven/
  types.ts
  fixtures.ts
  actions.ts
```

## 组件契约

| 组件 | 职责 | 关键 props / 状态 |
| --- | --- | --- |
| `StevenShell` | 桌面侧栏、顶部栏与响应式布局框架 | `activeModule`、`children` |
| `StevenSidebar` | 仅展示总览、标书与报价单、采购比价、消耗品库存、历史记录、个人设置 | `activeModule`、`onNavigate` |
| `DashboardHeader` | 展示安全说明与三个操作入口 | `onNewTender`、`onNewComparison`、`onStocktake` |
| `MetricCard` | 语义状态指标，状态必须同时展示文字、图标与颜色 | `label`、`value`、`tone`、`description` |
| `PriorityTodoList` | 载入、空、错误、正常四种明确状态 | `status`、`items`、`onReview`、`onRetry` |
| `ReviewDrawer` | 字段来源、规则、AI 占位、异常和人工确认 | `item`、`open`、`onAttachment`、`onRequestConfirm` |
| `ConfirmDialog` | 对人工复核记录及任何高影响行为显式二次确认 | `open`、`title`、`description`、`onConfirm`、`onCancel` |
| `ToastRegion` | 回传成功、错误、占位行为提示；不应暗示后台已自动执行 | `messages` |
| `ModuleEntryCard` | 三个业务模块入口及待处理异常数 | `module`、`exceptionCount`、`onOpen` |

## TypeScript 数据模型

```ts
export type StevenModule =
  | 'overview'
  | 'tenders'
  | 'comparisons'
  | 'inventory'
  | 'history'
  | 'settings';

export type SemanticTone = 'neutral' | 'teal' | 'amber' | 'orange' | 'red';
export type LoadState = 'loading' | 'ready' | 'empty' | 'error';

export interface PriorityTodo {
  id: string;
  title: string;
  module: Exclude<StevenModule, 'overview' | 'history' | 'settings'>;
  badge: string;
  tone: SemanticTone;
  dueLabel: string;
  actionLabel: string;
  review: {
    sources: Array<{ label: string; value: string }>;
    rules: Array<{ label: string; value: string }>;
    exception?: string;
    aiDraftStatus: 'disabled' | 'available';
  };
}

export interface AuditEvent {
  id: string;
  actor: 'Steven' | '系统规则';
  action: string;
  entityType: 'tender' | 'comparison' | 'inventory' | 'export';
  entityId: string;
  createdAt: string;
  metadata?: Record<string, string>;
}
```

## 交互和权限约束

1. 所有修改状态的操作都必须先打开表单或复核抽屉，再经过 `ConfirmDialog`。确认按钮的文案要描述实际动作，例如“确认记录人工复核”。
2. 前端不提供自动审批、自动选择供应商、自动下单、自动发信或自动确认实物库存的 action、mutation 或快捷路径。
3. `ReviewDrawer` 只能创建一条 `AuditEvent`（例如 `review_recorded`）与可选人工备注；它不能改变审批、供应商、订单或盘点确认状态。
4. AI 区域此轮固定为 `disabled` 占位。将来即使有草稿，也只能作为 `review.aiDraft` 展示，且必须保持人工确认链路。
5. 导入、导出、筛选、审计和附件详情使用右侧抽屉或弹窗。导出前应确认导出范围；导入后应先展示校验错误，不直接写入正式数据。
6. 后端应从 session 获取 Steven 身份并在服务端校验路由权限；不要把岗位判断只放在客户端。

## 页面状态和可访问性

- 每一种状态使用可读文本、图标和色彩三重表达。不要只用颜色区分异常。
- 交互元素保留可见的 `:focus-visible` 边框，表单校验错误用 `aria-describedby` 关联到具体说明。
- 抽屉与对话框应实现焦点捕获、初始焦点、`Escape` 关闭和关闭后焦点归还。
- 桌面优先：大于 920px 使用完整侧栏；720px 至 920px 折叠为图标导航；更窄时转为横向紧凑导航，不压缩待办行的核心文本。
- 数值使用 `font-variant-numeric: tabular-nums`，审计时间和记录 ID 建议用等宽字体。

## 设计令牌

```css
:root {
  --steven-nav: #0f4946;
  --steven-canvas: #f3f5f4;
  --steven-surface: #ffffff;
  --steven-text: #172321;
  --steven-muted: #687572;
  --steven-line: #dce3e0;
  --steven-primary: #16736d;
  --status-amber: #a96500;
  --status-orange: #b74a14;
  --status-red: #b42318;
}
```

## 验收清单

- 路由为 `/dashboard/steven`，页面和导航中没有任何其他岗位名称或入口。
- 顶部栏只出现 Steven/采购行政、通知占位和头像菜单。
- 首屏含四项指标、五项指定待办、最近活动、三张模块入口卡和完整安全说明。
- 所有影响业务状态的行为走复核抽屉和显式确认对话框。
- loading、空、错误状态可独立渲染，且不掩盖数据是否已被处理。
- 无障碍状态、键盘焦点、窄屏折叠导航均有实现与测试。
