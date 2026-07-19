# Steven Demo D1 PostgreSQL 验收报告 v1

- 日期：2026-07-17
- 数据库：`puiying_steven_demo`
- PostgreSQL：本机原生 PostgreSQL 18，服务 `postgresql-x64-18`
- Alembic head：`20260717_0007`
- 数据范围：仅脱敏 Demo 数据
- 总结论：**真实 PostgreSQL 业务闭环通过，但 D1 整体仅部分通过。** Demo 角色无集群管理权、无其他库所有权或显式授权，但仍可通过 PostgreSQL 默认 `PUBLIC CONNECT` 连接 5 个非 Demo 数据库；本轮未获准修改其他数据库 ACL 或 `pg_hba.conf`，因此“只能连接 Demo 库”的严格要求尚未满足。

本结论只适用于独立 Demo 空库验证，不表示生产可用、可受控试运行、已部署或已接入真实 OCR/AI。

## 1. 实际系统动作

1. 启动 Windows 服务 `postgresql-x64-18`；验证结束时服务仍为 `Running / Manual`。
2. 使用管理员维护连接创建固定 Demo 角色 `puiying_steven_demo_app`。
3. 创建独立数据库 `puiying_steven_demo`，所有者为固定 Demo 角色。
4. Demo 角色设置为 `NOSUPERUSER / NOCREATEDB / NOCREATEROLE / NOREPLICATION / NOBYPASSRLS`，无角色继承关系。
5. 执行真实 Alembic migration：`20260716_0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 20260717_0007`。
6. 执行首管理员 bootstrap；重复 bootstrap 被拒绝。验证续跑时仅对固定脱敏管理员执行受控密码轮换、撤销旧 Session 并记录审计，未输出密码。
7. 写入脱敏 S2/D0 数据，完成规则、事务、审批、审计、文件版本和应用重建恢复验证。
8. 未删除数据库、账号、migration、历史业务记录、文件或失败证据。

## 2. 分级结论

### 2.1 已被真实 PostgreSQL 验证

| 项目 | 结果 |
|---|---|
| 独立数据库与固定 Demo 角色 | 已创建并真实连接 |
| 最低集群权限 | 通过：非 superuser，无 createdb/createrole/replication/bypassrls，无角色成员关系 |
| 其他数据库所有权/显式授权 | 通过：聚合计数均为 0，未枚举其他数据库名称 |
| 仅可连接 Demo 库 | **未通过**：默认 `PUBLIC CONNECT` 使角色仍可连接 5 个非 Demo 数据库 |
| Migration | 真实执行到 `20260717_0007` |
| 关键表 | `users`、Session/审计表、`steven_quote_*`、`files`、`ocr_jobs`、`ai_jobs`、`review_candidates`、`steven_quote_import_candidates` 均真实存在 |
| 用户名大小写唯一 | 两路并发创建得到 `1×201 + 1×409 duplicate_username` |
| 报价复合唯一 | `(quote_supplier_id, quote_item_id)` 重复写入由 `uq_steven_quote_offer_lines_supplier_item` 阻断 |
| 3×5 正常数据 | 5 品项、3 供应商、15 报价明细 |
| 金额计算 | SUP-C 2583、SUP-A 2605、SUP-B 2622 HKD |
| 运费/税费 | 供应商级金额只计算一次 |
| 非最低价推荐 | 缺理由或审批意见均返回统一阻断；两项齐全后才能写入 |
| 自审 | 提交人审批自己的事项返回 403 |
| 候选失败回滚 | 强制第三条报价写入失败后，供应商 3、报价 15、事项审计 4，均保持事务前计数 |
| Excel 导出 | 连续生成 v1、v2、v3，3 个独立 storage key，状态均为 `ready`，历史未覆盖 |
| 文件校验 | 3 个 Excel 均可重新打开；数据库 size/SHA-256 与磁盘一致 |
| 应用重建恢复 | 新建 FastAPI app 后，Session、5/3/15 数据、审计、candidate 关联和版本元数据可恢复读取 |
| 平台/业务审计 | 登录、候选确认、推荐、提交、审批、导出审计可在重建应用后查询 |

### 2.2 仅离线或 Mock 验证

- D0 的 Azure Document Intelligence 与 DeepSeek Adapter 仍仅为配置、mapper、严格 Schema、脱敏和 mock HTTP 测试。
- D1 候选输入来自明确标记的 D0 脱敏 ground truth/Mock，不是实时 Azure 或 DeepSeek 输出。
- 全量 pytest 中仍包含 development/test 的内存仓和 Mock Adapter 合同测试；这些结果与真实 PostgreSQL smoke 分开记录。
- Alembic offline SQL 结果仍保留，但 D1 已额外完成真实数据库 migration，不再以 offline SQL 代替真实 migration。

### 2.3 未验证或不在本轮范围

- Azure OCR、DeepSeek、Redis、网关、NAS、MinIO、真实 API Key、真实文件和校务数据。
- S1 标书/文书与 S3 库存业务。
- PostgreSQL 服务进程重启后的恢复；本轮验证的是应用实例重建后的恢复。
- 备份恢复、RPO/RTO、监控告警、生产密钥管理、生产部署。
- 对其他数据库逐库验证写权限；本轮禁止枚举或接触其他数据库。
- 通过 `pg_hba.conf` 或其他数据库 ACL 实现 Demo 角色只可连接目标库。

## 3. Migration 与 Schema 结果

最终 revision：

```text
20260717_0007
```

真实核对 21 张目标表，并验证：

- `uq_users_username_lower`
- `uq_steven_quote_offer_lines_supplier_item`
- `uq_steven_quote_approvals_one_pending`
- 审批 actor 外键
- candidate route/status 索引
- 平台审计 request/time 索引

原始证据：

- `05-测试验收/Steven_Demo_D1_postgres_smoke_attempt7_final_2026-07-17.jsonl`
- `05-测试验收/Steven_Demo_D1_database_closure_2026-07-17.json`

## 4. 3×5 金额结果

成功事项 ID：

`85ce181f-2cde-46ac-919e-969eb41c0fe2`

| 排名 | 供应商 | 小计 | 运费 | 税费 | 总价 |
|---|---|---:|---:|---:|---:|
| 1 | SUP-C | 2393 | 90 | 100 | 2583 HKD |
| 2 | SUP-A | 2405 | 120 | 80 | 2605 HKD |
| 3 | SUP-B | 2367 | 180 | 75 | 2622 HKD |

这是 S2 规则排序，不是 AI 推荐或自动供应商选择。人工推荐字段默认空白。

## 5. 并发、约束与回滚

1. 大小写用户名并发：一个成功，另一个返回 `duplicate_username`。
2. 重复供应商+品项报价：数据库复合唯一约束阻断。
3. 候选确认故障注入：第三条报价写入前强制失败，正式供应商、报价明细与业务审计全部回滚。
4. 非最低价人工推荐：缺任一人工字段均阻断。
5. 提交人自审：403 `self_approval_forbidden`。
6. 三次导出版本号为 `[1,2,3]`，文件名和 storage key 独立，未覆盖或复用历史版本。

## 6. 回归与构建

| 验证 | 结果 | 证据 |
|---|---|---|
| 后端全量 pytest | `72 passed, 1 warning in 23.81s` | `Steven_Demo_D1_backend_pytest_2026-07-17.log` |
| Python compileall | exit 0 | `Steven_Demo_D1_compileall_2026-07-17.log` |
| 前端 ESLint | 通过 | `Steven_Demo_D1_frontend_lint_2026-07-17.log` |
| Next.js production build | 通过 | `Steven_Demo_D1_frontend_build_2026-07-17.log` |

唯一 warning 是既有 Starlette `TestClient` / `httpx` 弃用提示。本轮未安装或升级依赖。

## 7. 失败尝试与修正记录

所有失败证据均保留，没有删除或覆盖：

1. attempt 1：验证脚本把 `CREATE DATABASE` 放入事务上下文，PostgreSQL 拒绝；事务回滚后目标角色和数据库均不存在。
2. attempt 2：建库、migration、bootstrap 成功；验证脚本错误读取不存在的 `supplier_code` 排名字段。
3. attempt 3：受控续跑辅助代码引用了错误的仓库类名。
4. attempt 4：验证脚本错误期待两个推荐错误码；真实 API 使用统一错误码和字段 details。
5. attempt 5：候选失败回滚测试顺序在事项导出锁定之后。
6. attempt 6：真实 PostgreSQL 应用闭环通过。
7. attempt 7：重复完成应用闭环，并新增数据库连接隔离检查；最终以 exit 2 明确报告 `postgres_public_connect` 阻断。

上述修正仅修改 D1 验证脚本，没有修改 migration 或既有业务规则。

## 8. 权限阻断

聚合证据显示：

```json
{
  "role_memberships": 0,
  "other_owned_database_count": 0,
  "explicit_other_database_acl_count": 0,
  "other_database_connect_via_any_grant_count": 5
}
```

这表示 Demo 角色没有其他库所有权、显式授权或管理能力，但仍继承 PostgreSQL 默认 `PUBLIC CONNECT`。本轮禁止修改其他数据库、系统认证配置或宿主机服务配置，因此不能自行消除。

证据：`05-测试验收/Steven_Demo_D1_permission_aggregate_2026-07-17.json`

## 9. D1 结论

**D1 的真实 PostgreSQL migration、数据、事务、约束、审计、版本化导出和应用重建恢复闭环通过；D1 整体验收未完全通过。**

唯一 P0 阻断为 Demo 角色仍可通过 `PUBLIC CONNECT` 连接非目标数据库。解决并复测前，不建议进入 D2，也不得标记为可试运行或生产可用。
