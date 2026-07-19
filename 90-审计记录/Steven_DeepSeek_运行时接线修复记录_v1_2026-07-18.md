# Steven DeepSeek 运行时接线修复记录 v1

- 日期：2026-07-18
- 范围：本机独立脱敏 Demo 的 S1 `tender_proofreading`
- 非范围：Azure、Redis、S2/S3 在线 AI、其他 AI purpose、D2 全面执行、生产部署

## 问题与根因

- 页面调用返回 `ai_structuring_disabled`。
- DeepSeek Endpoint 与运行时密钥读取经不回显诊断均正常；最小脱敏请求返回 HTTP 200。
- 根因是一键启动入口未传入 `-EnableDeepSeekProofreading`，API 实际以 `ai_enabled=false`、`provider=mock` 启动。
- `/health` 的兼容字段 `ai_provider` 还被硬编码为 `deepseek`，与真实运行配置不一致。

## 实施变更

- `启动Steven本地Demo.cmd`：默认传入 `-EnableDeepSeekProofreading`。
- `scripts/start_steven_demo.ps1`：把请求的 AI 开关与 Provider 纳入重复启动健康匹配、启动后健康检查及状态文件。
- `apps/api/app/main.py`：`/health.ai_provider` 改为真实运行配置值。
- 未修改数据库、角色、ACL、Caddy、证书、系统服务或网络监听范围。

## 验证证据

- PowerShell 启动脚本语法检查通过。
- `test_tender_proofreading_and_user_features.py`：8 passed。
- Python `compileall`：通过。
- 重启后 `/health`：`auth_mode=session`、`persistence.mode=postgresql`、`ai_enabled=true`、`ai_structuring_provider=deepseek`。
- `https://localhost:15443/login`：HTTP 200。
- 真实 `deepseek-chat` 脱敏服务请求成功，创建 `review_candidates(needs_review)`，返回 3 条严格 Schema 问题。
- 候选仍须人工逐条接受或忽略；未自动修改文书、供应商、预算、审批或导出。

## 安全边界

- 密钥只由 FastAPI 运行时从批准的密钥存储位置或环境变量读取；本记录、源码、日志和前端均不含密钥。
- 只允许标记为脱敏 Demo 的 S1 文书进入真实 Provider。
- 当前结论不代表生产可用、受控试运行、Azure/Redis 已接入、S2/S3 在线 AI 已启用或 D2 已获全面批准。
