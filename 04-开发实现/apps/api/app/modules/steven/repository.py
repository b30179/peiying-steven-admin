from __future__ import annotations

from app.modules.steven.schemas import StevenDashboard


class StevenDashboardRepository:
    """Replaceable Phase 1 mock repository; UI never owns business fixture data."""

    def dashboard_for(self, actor: str) -> StevenDashboard:
        return StevenDashboard(
            actor=actor,
            ai_enabled=False,
            metrics=[
                {"key": "pending-approval", "label": "待审批文书", "value": 2, "tone": "warning", "detail": "需人工审核"},
                {"key": "missing-quotes", "label": "待补报价", "value": 3, "tone": "danger", "detail": "存在不完整报价"},
                {"key": "low-stock", "label": "低库存", "value": 1, "tone": "danger", "detail": "须人工确认补货"},
                {"key": "monthly-exports", "label": "本月已导出", "value": 8, "tone": "success", "detail": "均保留独立版本"},
            ],
            priority_todos=[
                {"id": "todo-1", "module": "tender", "title": "礼堂空调保养", "detail": "书面报价邀请 Draft v2，待上级审核", "status": "待审核", "due_label": "今日", "action_label": "继续处理", "review_sources": [{"label": "模板", "value": "书面报价邀请 · v2"}, {"label": "提交人", "value": "Steven"}], "review_rules": [{"label": "截止日期", "value": "不少于生成日 + 3 天"}, {"label": "审批", "value": "正式导出前必须批准"}]},
                {"id": "todo-2", "module": "quote", "title": "2026 暑期清洁用品", "detail": "缺少 1 家供应商报价", "status": "报价不完整", "due_label": "7 月 18 日", "action_label": "录入报价", "review_sources": [{"label": "供应商报价", "value": "已录入 2 / 3 家"}, {"label": "采购品项", "value": "5 个品项"}], "review_rules": [{"label": "比较", "value": "缺报价时不得作为完整报价比较"}, {"label": "币种", "value": "不一致时阻断计算"}], "exception": "供应商 C 尚未提交报价。"},
                {"id": "todo-3", "module": "inventory", "title": "A4 影印纸", "detail": "低于安全库存，建议订货 20 包", "status": "低库存", "due_label": "需确认", "action_label": "查看库存", "review_sources": [{"label": "本次盘点", "value": "30 包"}, {"label": "安全库存", "value": "40 包"}], "review_rules": [{"label": "建议订货量", "value": "max(0, 目标库存 - 本次盘点量)"}, {"label": "人工确认", "value": "系统不确认实物库存"}], "exception": "低于安全库存，建议人工核实库位。"},
                {"id": "todo-4", "module": "tender", "title": "毕业礼堂布置", "detail": "截止日期将至，等待资料检查", "status": "将到期", "due_label": "明日", "action_label": "检查资料", "review_sources": [{"label": "截止日期", "value": "2026-07-17"}, {"label": "预算", "value": "已填写"}], "review_rules": [{"label": "必填字段", "value": "缺失时不可生成草稿"}, {"label": "供应商", "value": "名称不可重复"}]},
                {"id": "todo-5", "module": "inventory", "title": "美术室耗材", "detail": "等待人工确认盘点差异", "status": "需复核", "due_label": "本周", "action_label": "查看差异", "review_sources": [{"label": "账面量", "value": "18 件"}, {"label": "本次盘点", "value": "15 件"}], "review_rules": [{"label": "盘点量", "value": "必须为非负整数"}, {"label": "差异", "value": "仅提示，须现场确认"}], "exception": "账面量与盘点量相差 3 件。"},
            ],
            activities=[
                {"id": "activity-1", "action": "已生成草稿", "detail": "礼堂空调保养 · Draft v2", "occurred_at": "15 分钟前"},
                {"id": "activity-2", "action": "已录入报价", "detail": "暑期清洁用品 · 供应商 B", "occurred_at": "1 小时前"},
                {"id": "activity-3", "action": "已更新盘点", "detail": "文具库位 · 等待人工确认", "occurred_at": "昨日"},
                {"id": "activity-4", "action": "已导出版本", "detail": "毕业礼堂布置 · v3", "occurred_at": "7 月 14 日"},
            ],
            modules=[
                {"key": "tenders", "title": "标书与报价单", "description": "模板、草稿、人工复核与审批前准备", "exception_count": 2},
                {"key": "quotes", "title": "采购比价", "description": "结构化报价录入与不完整报价提示", "exception_count": 3},
                {"key": "inventory", "title": "消耗品库存", "description": "盘点差异、低库存与人工确认建议", "exception_count": 1},
            ],
        )