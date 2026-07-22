# Steven Phase 1 基线 + S2 + P0-A 启动与验证

## 后端

```powershell
cd D:\ZM\AI工坊\某中学\04-开发实现\apps\api
$env:APP_ENV="development"
$env:AUTH_MODE="mock"
$env:DEMO_SEED_ENABLED="true"
$env:MOCK_IDENTITY="steven"
..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 9000
```

验证：

- `GET http://127.0.0.1:9000/health`
- `GET http://127.0.0.1:9000/api/v1/steven/dashboard`
- `GET http://127.0.0.1:9000/api/v1/steven/quotes`
- 开发 mock 身份只由服务端 `MOCK_IDENTITY` 决定；业务请求不得传入 `X-Role`、`X-Actor` 或其他身份覆盖头。

本地 PostgreSQL 模板（仅在本机已有镜像时使用，不会自动部署）：

```powershell
cd D:\ZM\AI工坊\某中学\04-开发实现
docker compose --env-file infra\env\development.env.example -f infra\docker-compose.postgres.yml up -d
```

Session 模式必须配置独立 `DATABASE_URL`，再执行 migration：

```powershell
cd D:\ZM\AI工坊\某中学\04-开发实现\apps\api
$env:APP_ENV="development"
$env:AUTH_MODE="session"
$env:DEMO_SEED_ENABLED="true"
$env:DATABASE_URL="postgresql+psycopg://<dev_user>:<dev_password>@127.0.0.1:5432/puiying_steven_dev"
..\..\.venv\Scripts\python.exe -m alembic upgrade head
..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 9000
```

由于 Session Cookie 强制使用 `Secure`，浏览器端 Session 登录必须通过本地 HTTPS 反向代理或已批准的 HTTPS 环境访问；纯 HTTP 命令可用于 API/migration 调试，但浏览器不会回传 Secure Cookie。

## 前端

开发模式：

```powershell
cd D:\ZM\AI工坊\某中学\04-开发实现
pnpm dev:web
```

production build 与启动：

```powershell
pnpm build:web
pnpm --filter @puiying/web start
```

访问：

- `http://127.0.0.1:3000/dashboard/steven`
- `http://127.0.0.1:3000/dashboard/steven/quotes`
- `http://127.0.0.1:3000/dashboard/steven/quotes/demo-quote-hkd-2026`
- `http://127.0.0.1:3000/login`（仅 `AUTH_MODE=session` 可提交本地账户登录）

前端默认请求 `http://127.0.0.1:9000`；可用 `STEVEN_API_BASE_URL` 覆盖。

## 测试

```powershell
cd D:\ZM\AI工坊\某中学\04-开发实现
.\.venv\Scripts\python.exe -m pytest apps\api\tests -q
pnpm lint:web
pnpm build:web
```

## 当前边界

P0-A 已将身份与授权切换为服务端 Session / permission-based RBAC 底座；开发 mock 仅允许 development/test。S2 业务 Repository 仍为内存实现，API 重启后按环境开关恢复脱敏种子。当前不连接真实 PostgreSQL、NAS、DeepSeek、OCR、供应商搜索、真实附件、密钥或外部服务；S2 持久化、事务和并发导出留待 P0-B。
