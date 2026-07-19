# Steven Demo D1 遗留风险与 D2 前置条件 v1

- 日期：2026-07-17
- 当前状态：D1 P0-1 PostgreSQL localhost 连接隔离已于 2026-07-17 修复并完成 exit 0 复测；Mock 展示服务 9000、9001 当前未监听，D1 展示健康项待复验
- 结论：P0-1 已关闭；Mock 展示服务恢复并健康复验前，暂不建议进入 D2

## 1. P0 遗留风险

### P0-1：Demo 数据库角色连接隔离（已关闭）

固定角色：`puiying_steven_demo_app`

2026-07-17 已在 PostgreSQL 18 实际运行的 `pg_hba.conf` 中，新增仅针对该角色的 localhost allow/deny 四条规则：目标库 `puiying_steven_demo` 允许，其他数据库明确 reject；allow 在 deny 前。已先创建完整时间戳备份，随后 reload 成功，未重启服务，未改其他角色或数据库 ACL。

复测：`04-开发实现/scripts/verify_steven_demo_d1_postgres.py` 返回 **exit 0**，其中：

- `database_connect_isolation=passed`
- Demo 账号连接目标库通过
- 单次聚合非目标连接探针被认证层拒绝
- 未枚举、读取或写入非 Demo 库表或数据

证据见：

- `05-测试验收/Steven_Demo_D1_PostgreSQL验收报告_v2_2026-07-17.md`
- `90-审计记录/Steven_Demo_D1_连接隔离修复记录_v1_2026-07-17.md`
- `05-测试验收/Steven_Demo_D1_postgres_smoke_attempt11_isolationfix_final_2026-07-17.jsonl`

## 2. D2 前置批准

除 P0-1 外，进入在线 OCR/AI Demo 前至少需要确认：

1. Mock 展示服务 9000、9001 的责任人恢复服务并完成健康复验（当前均未监听；本轮未启动或修改）。
2. Azure Document Intelligence 的获批 endpoint、模型、区域、网络出口和数据传输许可。
3. DeepSeek 的获批服务端 endpoint、模型、网络出口和脱敏字段白名单。
4. Key 的受管存储位置；Key 不得进入源码、前端、日志、审计、样本或 `.env.example`。
5. Demo 仅使用脱敏资料；真实校务/供应商文件继续禁止。
6. 在线 Provider 失败时是否允许使用明确标记的 Mock/缓存继续演示。
7. PostgreSQL 服务在 Demo 前后的启动/停止责任人和操作窗口。

## 3. D2 不应顺带实施

- S1、S3 业务。
- 真实校务数据或真实供应商文件。
- NAS、MinIO、Redis、队列集群。
- 生产部署、备份恢复、监控告警。
- 自动推荐供应商、自动审批、自动下单、自动发信或自动确认库存。
- 为跑通 Demo 而放宽 CSRF、RBAC、审计、金额、币种、完整性或人工确认规则。

## 4. 其他非阻断风险

1. Starlette `TestClient` / `httpx` 存在弃用 warning；当前不影响测试，但后续升级依赖前需做兼容验证。
2. 项目 `.venv` 没有 PostgreSQL driver；D1 使用已安装 psycopg2 的系统 Python 运行专用脚本。D2 若要由正式 API 进程连接数据库，需要明确受控依赖安装或统一运行环境。
3. 本轮验证应用实例重建恢复，没有验证 Windows PostgreSQL 服务重启、机器重启或备份恢复。
4. 三个导出版本业务数据相同，因此 SHA-256 可以相同；版本号、文件名和 storage key 均不同，未发生覆盖。
5. 失败尝试产生的脱敏验证数据和文件已按要求保留；进入长期 Demo 前需制定经批准的数据保留与清理规则。

## 5. 是否进入 D2

**当前建议：暂不进入 D2。**

P0-1 已完成 exit 0 的 D1 PostgreSQL 复测；先恢复并确认 Mock 展示服务 9000、9001 健康，再由项目负责人单独批准 D2 在线 OCR/AI 联调。
