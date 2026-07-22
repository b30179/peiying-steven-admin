# Steven Demo D1 实施记录 v1

- 日期：2026-07-17
- 根目录：`D:\ZM\AI工坊\某中学\`
- 基线：S2、P0-A/A.1、P0-B/B.1、D0，Alembic head `20260717_0007`
- 本轮范围：本机原生 PostgreSQL 18 独立 Demo 空库真实验证
- 最终状态：业务闭环通过；数据库连接隔离存在 P0 阻断

## 1. 系统动作记录

1. 确认 Windows 服务 `postgresql-x64-18` 已安装，数据目录为既有 PostgreSQL 18 数据目录。
2. 经用户保存本机 `pgpass.conf` 后验证管理员维护连接；未在聊天、代码、日志或报告中输出密码或明文连接串。
3. 启动服务并确认 `127.0.0.1:5432` 接受连接。
4. 仅按固定名称检查和创建：
   - 角色 `puiying_steven_demo_app`
   - 数据库 `puiying_steven_demo`
5. 未枚举、修改或删除其他数据库名称、schema 或数据。
6. 未删除本轮创建的数据库、角色、migration 记录、业务数据、文件和失败证据。
7. 验证结束时 PostgreSQL 服务保持 `Running / Manual`。

## 2. Migration 与 Bootstrap

真实执行：

`20260716_0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 20260717_0007`

结果：

- `alembic current` 为 `20260717_0007`。
- 目标 21 张表、关键索引、外键和唯一约束存在。
- 首管理员 bootstrap 成功。
- 重复 bootstrap 返回 `admin_already_exists`。
- 验证续跑时固定脱敏管理员执行受控密码轮换：
  - 密码不回显；
  - 失败计数清零；
  - 旧 Session 撤销；
  - `auth.d1_bootstrap_password_rotated` 同事务写入认证与平台审计。

## 3. 真实 PostgreSQL 业务记录

最终成功事项：

`85ce181f-2cde-46ac-919e-969eb41c0fe2`

真实数据库结果：

- 5 品项。
- 3 供应商。
- 15 报价明细。
- SUP-C：2583 HKD。
- SUP-A：2605 HKD。
- SUP-B：2622 HKD。
- 供应商级运费与税费只计一次。
- 非最低价推荐缺理由或审批意见均阻断。
- 提交人自审返回 403。
- 候选确认强制失败时业务写入和审计整体回滚。
- 大小写用户名并发得到一个成功、一个 `duplicate_username`。
- 重复供应商+品项报价由复合唯一约束阻断。
- 连续导出 v1、v2、v3；文件可重新打开，size/SHA-256 与数据库记录一致。
- 新建 FastAPI app 后可恢复读取 Session、报价、候选关联、审批、审计和版本记录。

## 4. 验证脚本修正

修改：

`04-开发实现/scripts/verify_steven_demo_d1_postgres.py`

修正内容：

1. 将 `CREATE DATABASE` 从连接上下文事务中移出，显式启用 autocommit。
2. 为失败后的固定 Demo 角色/数据库增加不删除对象的受控续跑逻辑。
3. 使用实际 `QuoteRankingEntry.supplier_id` 映射供应商代码。
4. 按真实 API 合同验证统一推荐错误码和字段 details。
5. 将候选失败回滚测试移动到事项可编辑阶段。
6. 保留已生成文件和历史数据，不自动清空目录。
7. 新增数据库连接隔离聚合检查；不列出非目标数据库名称。
8. 在应用闭环成功但连接隔离不满足时，以 exit 2 和 `verification=blocked` 收尾。

## 5. 失败证据保留

- `05-测试验收/Steven_Demo_D1_postgres_smoke_2026-07-17.jsonl`
- `05-测试验收/Steven_Demo_D1_postgres_smoke_attempt2_2026-07-17.jsonl`
- `05-测试验收/Steven_Demo_D1_postgres_smoke_attempt3_2026-07-17.jsonl`
- `05-测试验收/Steven_Demo_D1_postgres_smoke_attempt4_2026-07-17.jsonl`
- `05-测试验收/Steven_Demo_D1_postgres_smoke_attempt5_2026-07-17.jsonl`
- `05-测试验收/Steven_Demo_D1_postgres_smoke_attempt6_2026-07-17.jsonl`
- `05-测试验收/Steven_Demo_D1_postgres_smoke_attempt7_final_2026-07-17.jsonl`

失败均来自 D1 验证脚本假设或顺序问题，没有为跑通而跳过 migration、降低业务校验、关闭安全检查或修改历史 migration。

## 6. 回归记录

- 后端 pytest：`72 passed, 1 warning in 23.81s`。
- Python compileall：exit 0。
- 前端 ESLint：通过。
- Next.js production build：通过。
- production build 保留 Steven Dashboard、采购比价、详情、扫描复核和登录路由。

## 7. 安全与边界

- 未调用 Azure、DeepSeek、Redis、网关或其他外部服务。
- 未使用真实 API Key、真实账号密码、真实业务文件或校务数据。
- OCR/AI 候选来自明确标记的脱敏 Mock/ground truth。
- 未实现 S1/S3、NAS、备份、监控、部署或生产配置。
- 未修改 `0001`–`0007` migration。
- 未安装依赖、未拉取 Docker 镜像、未使用 Docker。
- 没有把 D1 表述为生产可用或可试运行。

## 8. 未闭合风险

Demo 角色没有其他数据库所有权、显式授权或集群管理权，但通过默认 `PUBLIC CONNECT` 仍可连接 5 个非 Demo 数据库。本轮没有权限修改 `pg_hba.conf` 或其他数据库 ACL，因此 D1 整体只能标记为部分通过。
