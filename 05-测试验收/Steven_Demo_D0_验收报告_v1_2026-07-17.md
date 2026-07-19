# Steven Demo D0 验收报告 v1

- 日期：2026-07-17
- 范围：AI/OCR/PG 合同、脱敏样本、S2 候选人工确认切片、通用复用底座
- 结论：D0 代码接口、离线 migration、脱敏样本和自动化回归通过；未联网、未启动 PostgreSQL，不可标记为可试运行或生产可用

## 1. 自动化与构建结果

| 验证 | 结果 | 证据 |
|---|---|---|
| D0 专项测试 | 15 项通过，包含于全量测试 | `04-开发实现/apps/api/tests/test_demo_d0_document_intelligence.py` |
| 后端全量 | `72 passed, 1 warning in 7.47s` | `Steven_Demo_D0_pytest_2026-07-17.txt` |
| Python compileall | 通过 | `Steven_Demo_D0_compile_2026-07-17.txt` |
| Alembic offline SQL | 通过，head 为 `20260717_0007` | `Steven_Demo_D0_alembic_offline_2026-07-17.sql` |
| 前端 ESLint | 通过 | `Steven_Demo_D0_frontend_lint_2026-07-17.txt` |
| Next.js production build | 通过 | `Steven_Demo_D0_frontend_build_2026-07-17.txt` |
| 样本 hash/页数/尺寸 | 通过 | `Steven_Demo_D0_sample_integrity_2026-07-17.json` |
| 样本视觉复核 | 通过：无裁切、乱码、黑块或重叠 | `Steven_Demo_D0_样本预览/` |

唯一 warning 为既有 Starlette `TestClient` / `httpx` 弃用提示，不影响测试通过。本轮未安装或升级依赖。

## 2. Migration 验证

新增：

`20260717_0007_document_intelligence_demo_contract.py`

承接：

`20260716_0006`

离线 SQL 已验证包含：

- `files`
- `ocr_jobs`
- `ai_jobs`
- `review_candidates`
- `steven_quote_import_candidates`
- job/candidate 状态检查约束
- 文件、request、route/status、target object 查询索引
- head 更新至 `20260717_0007`

离线 SQL 不证明 PostgreSQL 实例中已成功建表，也不证明真实行锁、重启恢复或并发行为。

## 3. Adapter 与数据安全验收

已验证：

1. Azure endpoint 必须为 HTTPS。
2. Azure 模型必须为 `prebuilt-invoice`。
3. timeout 必须大于 0。
4. Azure mock transport 的请求与 evidence mapper 正确。
5. Azure polygon 数组与坐标对象均可映射。
6. DeepSeek 输入自动脱敏邮箱与香港电话号码。
7. `request_id` 与 evidence 原文不进入 AI 输入。
8. AI 输出额外字段被严格 Schema 拒绝。
9. 推荐、排序、审批、下单等字段被拒绝。
10. 未启用 Schema 返回 `schema_not_enabled`。
11. Provider 失败时 candidate/job 明确标记 `failed`，不伪装实时成功。
12. Mock 来源明确标记为 `mock`。

本轮没有真实 Key，没有真实 Azure 或 DeepSeek 请求。

## 4. Candidate 与人工确认验收

已验证：

- OCR job、AI job 和 candidate 最终停在 `needs_review`。
- evidence、warnings、provider/model 和 `request_id` 被保存。
- 人工修订后仍保持 `needs_review`。
- 人工拒绝后进入 `rejected`，且不可继续修改。
- 人工确认必须经过独立 `confirm_scan_candidate()`。
- 确认时重新验证 Schema、币种、品项集合、金额规则和重复供应商。
- 正式报价、candidate `confirmed` 和 S2 审计在同一 Unit of Work 内完成。
- 失败时正式品项、供应商、报价明细与审计均保持零增量。

## 5. 3×5 正常样本结果

人工确认三份正常脱敏候选后：

- 品项：5。
- 供应商：3。
- 报价明细：15。
- 币种：HKD。
- 推荐供应商：空白。
- 比较状态：允许。

| 排名 | 供应商 | 小计 | 运费 | 税费 | 总价 |
|---|---|---:|---:|---:|---:|
| 1 | SUP-C | 2,393 | 90 | 100 | 2,583 |
| 2 | SUP-A | 2,405 | 120 | 80 | 2,605 |
| 3 | SUP-B | 2,367 | 180 | 75 | 2,622 |

该排名仅为既有 S2 规则计算结果，不是 AI 推荐或自动选择。

## 6. 异常与回滚验收

| 场景 | 预期与结果 |
|---|---|
| 缺少品项 | `candidate_item_set_mismatch`，零增量回滚 |
| USD/HKD 冲突 | `candidate_currency_mismatch`，零增量回滚 |
| 重复供应商 | `duplicate_supplier_code`，零增量回滚 |
| 报价过期 | 允许人工确认但显示醒目过期 warning，不自动推荐 |
| Provider 失败 | candidate/job 为 `failed`，不回退为伪实时成功 |
| AI 输出决策字段 | `forbidden_ai_decision_field` |
| Demo/OCR/AI 默认关闭 | API 返回 `document_intelligence_disabled` |
| 非 Steven 导入权限 | 返回 403 |

## 7. 脱敏样本验收

样本目录：

`04-开发实现/demo-data/steven-d0/`

已检查：

- `manifest.json` 声明 `contains_real_data=false`。
- 6 组 artifact 均存在对应 ground truth。
- 正常三组覆盖中文扫描、英文/中英混排数字和中英双语表格。
- 异常三组覆盖缺项、币种冲突和过期报价。
- 正常 ground truth 恰好覆盖 SUP-A、SUP-B、SUP-C，每家 5 个品项，均为 HKD。
- PDF 均可读取；PNG 尺寸为 1654×2339。
- 视觉预览无裁切、乱码、黑块或重叠。

## 8. API/UI 验收

API 合同已覆盖：

- 文件上传/读取。
- 扫描导入创建。
- 任务和候选查询。
- 候选人工修改。
- 候选确认或拒绝。

Next.js production build 已生成：

`/dashboard/steven/quotes/[quoteId]/scan-review/[candidateId]`

页面包含原件、OCR evidence、AI 候选和人工最终值并排复核，并显示三项强制声明：

- OCR/AI 提取结果必须人工确认。
- AI 不参与供应商推荐和审批。
- 当前使用脱敏演示资料。

本轮 production build 只证明代码可构建，未进行真实 OCR/AI/PG 端到端在线演示。

## 9. 未联网与未启动证据

- Azure Adapter 仅使用注入式 mock transport 测试。
- DeepSeek Adapter 仅使用注入式 mock transport 测试。
- 无真实 Key 写入项目。
- PostgreSQL 脚本为 `plan-only`，固定 `execution_allowed=false`。
- 本轮未启动 `postgresql-x64-18`。
- 本轮未创建 `puiying_steven_demo` 或数据库账号。
- 本轮未连接任何 PostgreSQL、Azure、DeepSeek、NAS、MinIO、Redis 或外部服务。

## 10. 已知限制与验收结论

当前准确状态：

**D0 合同冻结、脱敏样本、代码接口、离线 migration 与自动化回归通过。**

不得标记为：

- Azure OCR 已接通。
- DeepSeek 已接通。
- PostgreSQL 已迁移或重启恢复已验证。
- PostgreSQL 并发已验证。
- S1/S3 已实现。
- 可试运行或生产可用。

