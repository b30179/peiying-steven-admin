# Open Design → Next.js 落地对应关系

Open Design 成功 run：`0aa4823c-8ec2-42dd-89ef-cbe90a3a4508`；项目：`puiying-steven-dashboard-phase1`。

| Open Design 产物 | Next.js 落地 |
| --- | --- |
| 深青绿侧栏、浅灰工作区、白色信息卡、设计令牌 | `apps/web/app/globals.css` |
| `StevenShell`、Steven 专属导航、顶部栏、PageHeader | `apps/web/components/steven/steven-dashboard-structure.tsx` |
| 指标卡、五项待办、最近活动、模块入口 | 同一组件，由 FastAPI mock repository 提供数据 |
| `ReviewDrawer`、`ConfirmDialog`、`ToastRegion` | 同一 React 客户端组件的 drawer/modal/toast 状态 |
| loading/empty/error 状态契约 | `app/dashboard/steven/loading.tsx`、`error.tsx`，以及 Dashboard 空/错误渲染 |
| 原始设计 HTML 与组件说明 | `steven-dashboard-prototype.html`、`steven-dashboard-components.md` |

严格保留的安全边界：交互仅展示人工复核、抽屉、确认及 Toast；不自动审批、选择供应商、下单、发信或确认实物库存。AI/OCR 仍为禁用占位。