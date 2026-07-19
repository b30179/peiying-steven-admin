# Steven Demo PostgreSQL 18 原生空库验证计划

## 状态与边界

- 本文件是 plan-only 合同，不代表已启动、连接或验证 PostgreSQL。
- 目标服务名：`postgresql-x64-18`。
- 建议独立数据库：`puiying_steven_demo`。
- 建议独立最低权限应用账号：`puiying_steven_demo_app`。
- 本阶段不创建数据库或账号，不启动服务，不读取真实密码，不连接真实实例。

## 获批后的执行顺序

1. 由获授权维护人员确认 PostgreSQL 18 服务状态、维护窗口与备份位置。
2. 创建独立数据库和最低权限账号；管理员权限只用于 migration/bootstrap，应用账号不得拥有建库或超级用户权限。
3. 使用独立 `DATABASE_URL`、`FILE_STORAGE_ROOT` 和 `APP_ENV`，禁止与开发、测试、staging、production 共用数据库或文件根目录。
4. 执行 `alembic upgrade head`，确认 `alembic current` 为 `20260717_0007`，检查 0001-0007 的表、外键、唯一约束和索引。
5. 运行单次首管理员 bootstrap；密码只来自受管环境变量或密钥，不回显、不写日志。
6. 仅导入 `demo-data/steven-d0/` 的完全脱敏样本，并标记 `is_demo=true`。
7. 验证登录、Session Cookie、CSRF、Origin、RBAC、自审拒绝、角色变更撤销 Session、持久审计与 `request_id` 关联。
8. 验证 OCR/AI Mock 候选必须进入 `needs_review`，人工确认后才写正式报价表；异常候选必须保持零行写入。
9. 重启 API 后读取报价、15 条明细、候选、审批、审计和文件版本元数据。
10. 执行并发导入确认与 10 路并发 Excel 导出，验证版本号不重复、文件不可覆盖、SHA-256/大小/版本记录一致。
11. 执行 reserved/failed 导出巡检，验证人工授权 reconcile 流程，不删除、不覆盖、不复用历史版本。

## 失败与回滚

- migration、seed、bootstrap、约束或 smoke 任一步失败即停止，不继续 Demo 准入。
- 失败时保留原始日志并移除密钥；按获批准备份恢复或 Alembic 受控回滚计划处理。
- 文件系统和数据库采用可恢复一致性 Saga，不宣称跨资源原子事务。

## 当前结论

真实 PostgreSQL 空库 smoke 未执行。阻塞条件是尚未获得启动/连接 PostgreSQL、创建独立库与账号的明确批准。
