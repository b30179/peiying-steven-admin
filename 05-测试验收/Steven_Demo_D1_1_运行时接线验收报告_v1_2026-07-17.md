# Steven Demo D1.1 运行时接线验收报告 v1

- 日期：2026-07-17
- 项目根目录：`D:\ZM\AI工坊\某中学\04-开发实现`
- 结论：**D1.1 通过。**
- 结论边界：仅证明正式项目 Python 环境、既有独立 Demo PostgreSQL、FastAPI 与 Next.js 可形成真实本地运行时闭环；**不表示生产可用、可受控试运行或已进入 D2。**

## 1. 本轮实际动作

1. 仅在项目 `.venv` 安装最小 PostgreSQL driver：
   - `psycopg==3.3.4`
   - `psycopg-binary==3.3.4`
   - 传递依赖 `tzdata==2026.3`
2. 在 `apps/api/requirements.txt` 固定声明 `psycopg[binary]==3.3.4`。
3. 修正正式 API 的 development/session 运行时接线：认证 Session、平台审计、S2 报价均使用同一 PostgreSQL engine，不回退内存实现。
4. 增加脱敏 `/health` 持久化状态，不输出密码或完整连接串。
5. 增加真实运行时验证脚本与运行时接线单元测试。
6. 增加一键启动、停止方式；因 Windows 排除端口范围包含 `3000`，前端默认改用 `4300`。
7. 未修改数据库、角色、schema、migration、ACL、PostgreSQL 配置或业务数据。

## 2. 一键启动

前置条件：

- 既有服务 `postgresql-x64-18` 已运行；
- 既有数据库为 `puiying_steven_demo`；
- 既有最低权限账号为 `puiying_steven_demo_app`；
- 本机受控 `pgpass.conf` 已存在目标账号条目。

启动方式：

```powershell
cd D:\ZM\AI工坊\某中学\04-开发实现
.\scripts\start_steven_demo.ps1
```

也可双击：

```text
D:\ZM\AI工坊\某中学\04-开发实现\启动Steven本地Demo.cmd
```

访问地址：

- API：`http://127.0.0.1:9000/health`
- Web：`http://127.0.0.1:4300/login`

停止方式：

```powershell
.\scripts\stop_steven_demo.ps1
```

或双击 `停止Steven本地Demo.cmd`。停止脚本只停止本项目 API/Web 进程，不停止 PostgreSQL 服务。

## 3. 已被真实 PostgreSQL 验证的内容

### 3.1 正式 Python 环境与连接

- Python：`D:\ZM\AI工坊\某中学\04-开发实现\.venv\Scripts\python.exe`
- Driver：`psycopg 3.3.4`、`psycopg-binary 3.3.4`
- 实际数据库：`puiying_steven_demo`
- 实际角色：`puiying_steven_demo_app`
- Alembic revision：`20260717_0007`
- `APP_ENV=development`
- `AUTH_MODE=session`
- `DEMO_SEED_ENABLED=false`
- OCR/AI 均保持关闭，未调用外部服务。

### 3.2 FastAPI 真实运行时

`/health` 返回 HTTP 200，关键脱敏结果：

```text
auth_mode = session
persistence.mode = postgresql
persistence.database = puiying_steven_demo
persistence.session_store = postgresql
persistence.audit_store = postgresql
persistence.quote_store = postgresql
```

未出现 InMemory Repository 回退；健康响应未包含密码或完整连接串。

### 3.3 持久数据读取

正式项目 `.venv` 通过实际 PostgreSQL engine 读取：

```text
Session 元数据 = 54
平台审计事件 = 196
采购事项 = 14
报价品项 = 70
供应商 = 42
报价明细 = 210
Excel 版本元数据 = 18
ready 文件 = 18
可由 openpyxl 重新打开的 Excel = 18
```

以上为既有脱敏 D1 数据，只读验证过程中未新增、修改或删除业务数据。

### 3.4 重启恢复

实际停止 API/Web 后重新执行一键启动，再次读取的数据计数与文件版本计数完全一致；18 个 ready Excel 均可重新打开。该结果证明数据来自 PostgreSQL 与受控文件根目录，而非进程内状态。

证据：

- `D:\ZM\AI工坊\某中学\05-测试验收\Steven_Demo_D1_1_真实运行时证据_2026-07-17.jsonl`
- `D:\ZM\AI工坊\某中学\05-测试验收\Steven_Demo_D1_1_重启恢复证据_2026-07-17.jsonl`

### 3.5 前后端启动

- FastAPI：`127.0.0.1:9000` 启动成功，`/health` HTTP 200。
- Next.js：`127.0.0.1:4300` 启动成功，`/login` HTTP 200。
- 初次尝试前端 `3000` 时，Windows 返回 `EACCES`；只读检查确认系统排除端口范围覆盖 `2993–3092`。未修改系统网络配置，改用项目参数化端口 `4300`。

## 4. 仅自动化/离线验证的内容

- development/session 仓储选择与健康响应脱敏单元测试。
- 既有 Session、RBAC、CSRF、Origin、身份头拒绝、S2、P0-A/A.1/B/B.1、D0 Mock Adapter 与候选规则回归。
- Python 语法编译。
- ESLint 与 Next.js production build。

本轮没有把 Mock、fake engine 或离线 SQL 作为真实 PostgreSQL 运行时证据。

## 5. 未验证或不在本轮范围

1. **真实浏览器 Secure Cookie 登录未完成。** 当前 Session Cookie 与 CSRF Cookie 均保持 `Secure`，Session Cookie 保持 `HttpOnly`、`SameSite=Lax`；本轮未生成证书、安装反向代理、修改 hosts、网络或安全属性。
2. HTTPS 浏览器登录、Cookie 持久化、浏览器内 CSRF 成功链路属于 D1.2，需要项目负责人单独批准。
3. 未验证 Windows 服务重启、机器重启、备份恢复、故障切换或生产并发。
4. 未进入 D2，未调用 Azure、DeepSeek、Redis、网关或真实 API。
5. 未实施 S1、S3、NAS、部署、监控或生产配置。

## 6. 回归结果

```text
pytest：73 passed，1 个既有 Starlette/httpx 弃用 warning
compileall：passed
ESLint：passed
Next.js production build：passed
```

构建路由包含：

```text
/login
/dashboard/steven
/dashboard/steven/quotes
/dashboard/steven/quotes/[quoteId]
/dashboard/steven/quotes/[quoteId]/scan-review/[candidateId]
/api/auth/[...path]
/api/steven/[...path]
```

证据：

- `D:\ZM\AI工坊\某中学\05-测试验收\Steven_Demo_D1_1_pytest_2026-07-17.txt`
- `D:\ZM\AI工坊\某中学\05-测试验收\Steven_Demo_D1_1_compileall_2026-07-17.txt`
- `D:\ZM\AI工坊\某中学\05-测试验收\Steven_Demo_D1_1_eslint_2026-07-17.txt`
- `D:\ZM\AI工坊\某中学\05-测试验收\Steven_Demo_D1_1_next_build_2026-07-17.txt`

## 7. 验收结论

**D1.1 通过。**

通过范围是本机独立 Demo 空库成果之上的真实项目运行时接线、只读恢复、前后端启动和回归。真实浏览器登录仍需要 D1.2 HTTPS 前置批准。当前仍不建议进入 D2。
