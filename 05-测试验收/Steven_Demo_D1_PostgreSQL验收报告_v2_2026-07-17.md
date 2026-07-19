# Steven Demo D1 PostgreSQL 验收报告 v2

> 后续状态说明（2026-07-17）：本报告第 5、6 节记录的是 D1 当时的历史端口状态。随后 D1.1 已完成正式项目 FastAPI/Next.js PostgreSQL 运行时接线，D1.2 已完成 `https://localhost:15443` 浏览器 Session 验收；当前整体验收以 `Steven_全项目整体验收报告_v1_2026-07-17.md` 为准。本说明不改变 D1 当时的原始证据。

- 日期：2026-07-17
- 本轮：D1 P0-1 连接隔离最小修复与复测
- 结论：**P0-1 已关闭；PostgreSQL Demo 闭环复测通过（验证脚本 exit code 0）。**
- 边界：此结论仅覆盖本机独立、脱敏 Demo 数据库；**不表示生产可用、可试运行、已部署，或已接入真实 OCR/AI。**

## 1. 唯一配置改动

在经运行中 PostgreSQL 18 实例查询确认的实际认证文件中，新增仅针对固定 Demo 角色 `puiying_steven_demo_app` 的四条 localhost 规则：

1. 允许该角色从 IPv4 localhost 连接目标 Demo 库 `puiying_steven_demo`。
2. 允许该角色从 IPv6 localhost 连接目标 Demo 库 `puiying_steven_demo`。
3. 明确拒绝该角色从 IPv4 localhost 连接其他数据库。
4. 明确拒绝该角色从 IPv6 localhost 连接其他数据库。

规则顺序为 target allow 在 all-database deny 前；两者均位于原有通用 localhost 规则之前。未更改其他角色、数据库 ACL、schema、业务数据、migration、`postgresql.conf`、服务 StartMode 或既有规则。

实际文件：`D:\ZM\PostgreSQL\18\data\pg_hba.conf`  
完整、不可覆盖备份：`D:\ZM\PostgreSQL\18\data\pg_hba.conf.d1-p0-1-backup-20260717_100814`

## 2. Reload 与规则生效

- 使用 `SELECT pg_reload_conf()` reload，返回 `true`。
- 未重启 PostgreSQL 服务。
- PostgreSQL 18 服务在本轮中保持 Running / Manual，未变更服务启动方式。
- 通过 `pg_hba_file_rules` 验证 4 条新增规则均无解析错误。

## 3. 连接隔离复测

复测脚本：`04-开发实现/scripts/verify_steven_demo_d1_postgres.py`

为使聚合隔离检查验证的是 pg_hba 的实际访问路径，验证脚本只在其隔离检查部分作了最小调整：

- 检查固定 Demo 角色对应的有效 pg_hba allow/deny 规则；
- 验证 Demo 账号可连接目标 Demo 库；
- 对一个非目标库执行一次聚合连接拒绝探针，不枚举任何非 Demo 库名称，不读取或写入任何非 Demo 表或数据；
- Windows 本地化拒绝消息出现非 UTF-8 解码时，按“认证在会话建立前被拒绝”处理，避免把成功拒绝误判为脚本失败。

最终结果：

```text
 database_connect_isolation = passed
 aggregate_non_target_connection_probe_count = 1
 aggregate_non_target_connection_rejected_count = 1
 demo_target_connection_passed = true
 verification = passed
 exit code = 0
```

复测证据：`05-测试验收/Steven_Demo_D1_postgres_smoke_attempt11_isolationfix_final_2026-07-17.jsonl`

## 4. D1 PostgreSQL 闭环复测

复测继续通过：

- Alembic revision `20260717_0007` 与 21 张目标表；
- 最小集群权限；
- 3×5 报价数据、金额计算、非最低价双人工确认、自审阻断；
- 并发用户名唯一与报价复合唯一约束；
- 候选失败事务回滚；
- 连续 v1/v2/v3 导出及文件完整性；
- 应用实例重建后的 Session、审计、候选关联与版本元数据恢复。

本次验证没有调用 Azure、DeepSeek、Redis 或任何真实资料/真实 Key。

## 5. Mock 展示服务健康检查

按要求检查既有 Mock 展示端口、未修改其模式或配置：

- `127.0.0.1:9000`：未监听，三条只读 HTTP 探针均返回连接被拒绝（WinError 10061）。
- `127.0.0.1:9001`：未监听，三条只读 HTTP 探针均返回连接被拒绝（WinError 10061）。

因此，**P0-1 与 D1 PostgreSQL 验证已通过，但“当前 Mock 展示服务 9000、9001 依然健康”未能确认。** 本轮未启动、重配或切换 Mock 服务，避免超出授权范围。

## 6. D1 与 D2 结论

- D1 PostgreSQL 安全边界 P0-1：**已通过并关闭**。
- D1 完整通过：**暂不宣称完整通过**，原因是端口 9000、9001 当前均未监听，Mock 展示健康项待服务责任人恢复后单独复验。
- 是否建议进入 D2：**暂不建议进入 D2**；先恢复并确认既有 Mock 展示服务健康，再由项目负责人依据 D2 前置条件另行批准。D2 的在线 OCR/AI、Azure、DeepSeek、Redis、Docker、部署、S1、S3 均未实施。
