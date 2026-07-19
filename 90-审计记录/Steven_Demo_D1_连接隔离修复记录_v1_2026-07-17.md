# Steven Demo D1 连接隔离修复记录 v1

- 日期：2026-07-17
- 授权事项：D1 P0-1 最小化 PostgreSQL `pg_hba.conf` localhost 连接隔离修复与复测
- 执行范围：仅 PostgreSQL 18 当前运行实例实际使用的认证规则文件

## 1. 运行时查实

通过运行中的 PostgreSQL 18 查询 `current_setting('hba_file')` 与 `pg_settings`，查实：

- 服务：`postgresql-x64-18`
- 版本：PostgreSQL 18.3
- 服务状态：Running
- 实际 `pg_hba.conf`：`D:\ZM\PostgreSQL\18\data\pg_hba.conf`
- `postgresql.conf` 路径仅作查实：`D:\ZM\PostgreSQL\18\data\postgresql.conf`；**未修改**。

未依赖猜测路径，未修改服务 StartMode，也未重启服务。

## 2. 备份与最小改动

在修改前创建完整、带时间戳且不覆盖的备份：

`D:\ZM\PostgreSQL\18\data\pg_hba.conf.d1-p0-1-backup-20260717_100814`

备份创建后执行了字节级比对，确认与修改前原文件一致。

唯一配置改动为新增仅匹配固定 Demo 角色 `puiying_steven_demo_app` 的 localhost 规则：

```text
host  puiying_steven_demo  puiying_steven_demo_app  127.0.0.1/32  scram-sha-256
host  puiying_steven_demo  puiying_steven_demo_app  ::1/128       scram-sha-256
host  all                  puiying_steven_demo_app  127.0.0.1/32  reject
host  all                  puiying_steven_demo_app  ::1/128       reject
```

allow 位于 deny 前，并且四条规则均位于原有通用 localhost 规则前。未变更任何其他用户、数据库 ACL、schema、业务数据、migration、其他既有 hba 规则或服务配置。

## 3. Reload 与解析检查

- 执行 `SELECT pg_reload_conf()`：返回 `true`。
- 未重启服务。
- 使用 `pg_hba_file_rules` 核对新增四条规则：均无解析错误。

## 4. 复测结果

复测命令：

```text
python scripts\verify_steven_demo_d1_postgres.py
```

最终证据文件：

`05-测试验收/Steven_Demo_D1_postgres_smoke_attempt11_isolationfix_final_2026-07-17.jsonl`

关键结果：

- Demo 账号目标库连接：通过。
- 聚合非目标连接拒绝探针：1/1 在认证阶段被拒绝。
- 未枚举、读取或写入非 Demo 库任何表或数据。
- `database_connect_isolation=passed`。
- 全验证 `exit code=0`。

本轮仅使用脱敏 Demo 数据；未调用 Azure、DeepSeek、Redis、Docker、真实 Key 或真实资料。

## 5. 未包含事项与后续约束

- 未将 Mock 服务改为数据库模式。
- 9000、9001 在只读健康探针时均未监听；未启动或修改它们。
- P0-1 可关闭；但 D1 的 Mock 展示健康确认仍待服务恢复后复验。
- 本记录不构成生产可用、部署、D2 批准或真实在线 OCR/AI 接入结论。
