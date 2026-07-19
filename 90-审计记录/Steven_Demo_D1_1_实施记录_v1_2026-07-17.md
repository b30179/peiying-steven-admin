# Steven Demo D1.1 实施记录 v1

- 日期：2026-07-17
- 范围：真实 PostgreSQL 运行时接线、本地前后端启动、一键启动与回归
- 项目目录：`D:\ZM\AI工坊\培英\04-开发实现`
- 状态：D1.1 开发与本机真实运行时验收通过

## 1. 依赖动作

仅在项目 `.venv` 安装：

```text
psycopg==3.3.4
psycopg-binary==3.3.4
tzdata==2026.3
```

项目依赖声明增加 `psycopg[binary]==3.3.4`。未全局安装、升级或重装 Python/Node，也未安装其他框架。

安装结果通过 `.venv\Scripts\python.exe -m pip show` 验证，安装位置仅为项目 `.venv\Lib\site-packages`。

## 2. 代码与脚本改动

1. `apps/api/app/main.py`
   - session 模式存在数据库配置时建立统一 PostgreSQL engine；
   - Auth Session、平台审计和 S2 Quote 选择 PostgreSQL；
   - `/health` 返回脱敏持久化类型与数据库名；
   - 不返回密码或完整连接串。
2. `apps/api/requirements.txt`
   - 固定 PostgreSQL driver 精确版本。
3. `apps/api/tests/test_d1_1_runtime_wiring.py`
   - 验证 development/session 不回退内存；
   - 验证健康响应不泄漏连接凭据。
4. `scripts/verify_steven_demo_d1_1_runtime.py`
   - 使用正式项目 `.venv` 与实际 PostgreSQL；
   - 校验数据库名、revision、仓储类型、持久数据、版本元数据和 Excel 可读性；
   - 脚本最初引用了不存在的 `steven_quote_file_versions`，对照既有 migration 修正为真实表 `steven_quote_versions`；未修改 schema。
5. `scripts/start_steven_demo.ps1`
   - 设置 development/session 的受控本地环境；
   - 使用无密码连接 URL，凭据由既有 `pgpass.conf` 提供；
   - 启动 FastAPI 9000 与 Next.js 4300；
   - 记录 launcher/listener PID；
   - 启动失败时清理状态文件和已启动进程。
6. `scripts/stop_steven_demo.ps1`
   - 停止记录的 API/Web launcher 与 listener；
   - 不改变 PostgreSQL 服务。
7. `启动Steven本地Demo.cmd`、`停止Steven本地Demo.cmd`
   - 提供双击启动与停止入口。
8. `README.md`
   - 补充一键启动、访问地址、停止方式和 D1.2 HTTPS 边界。

## 3. 实际运行记录

### 3.1 PostgreSQL

- 仅连接既有 `puiying_steven_demo`。
- 仅使用既有 `puiying_steven_demo_app`。
- 服务 `postgresql-x64-18` 验证时为 Running / Manual。
- 未创建或删除数据库、账号、schema、migration、业务数据。
- 未修改 `pg_hba.conf`、`postgresql.conf`、ACL 或服务启动方式。

### 3.2 端口处理

初次前端启动使用 `127.0.0.1:3000`，原始错误：

```text
Error: listen EACCES: permission denied 127.0.0.1:3000
code: EACCES
errno: -4092
syscall: listen
address: 127.0.0.1
port: 3000
```

只读系统检查显示 Windows 排除端口范围包含 `2993–3092`。未修改系统网络配置、排除范围、防火墙或服务，启动器默认端口改为 `4300`，并保留 `-WebPort` 参数。

### 3.3 真实运行时

FastAPI 与 Next.js 均启动成功：

```text
API /health = HTTP 200
Web /login = HTTP 200
auth_mode = session
database = puiying_steven_demo
session/audit/quote store = postgresql
```

实际读取：

```text
Session 54
平台审计 196
采购事项 14
品项 70
供应商 42
报价明细 210
版本元数据 18
ready Excel 可重开 18/18
```

停止并重新启动 API/Web 后，以上数据和文件版本读取结果保持一致。

## 4. 验证结果

```text
新增运行时接线测试：1 passed
后端全量测试：73 passed
Python compileall：passed
前端 ESLint：passed
Next.js production build：passed
```

已保存独立的真实 PostgreSQL、重启恢复、pytest、compileall、ESLint 与 build 证据文件。

## 5. 安全与范围记录

- 未输出、记录或提交密码、完整连接串、Token 或 Session 明文。
- 未关闭 Secure Cookie、CSRF、Origin、RBAC、审计或身份头拒绝。
- 未调用 Azure、DeepSeek、Redis、网关或任何外部业务服务。
- 未使用真实校务、供应商、学生或个人资料。
- 未实施 D2、S1、S3、NAS、部署、证书、反向代理、备份或监控。
- 浏览器 Secure Cookie 登录未完成，明确移交 D1.2 单独批准。
- 本记录不构成生产可用或可受控试运行结论。
