# Steven Demo D1.2 HTTPS 验收报告 v1

- 日期：2026-07-17
- 项目目录：`D:\ZM\AI工坊\某中学\04-开发实现`
- 验收范围：本机、独立、脱敏 Demo 的 PostgreSQL + HTTPS 浏览器 Session 闭环
- 最终结论：**D1.2 通过，但仅限上述本机 Demo 范围。**
- 结论边界：不表示生产可用、可受控试运行、已连接线上 OCR/AI，亦不构成 D2 执行授权。

## 1. 验收拓扑

```text
浏览器 https://localhost:15443
  → 项目级 Caddy 127.0.0.1:15443
  → Next.js 127.0.0.1:4300
  → Next.js 同源 API Proxy
  → FastAPI 127.0.0.1:9000
  → puiying_steven_demo
```

运行状态证据：

- Caddy、Next.js、FastAPI 和 Caddy admin 均监听 loopback。
- 运行状态文件为 `phase=ready`。
- `/health` 显示 `AUTH_MODE=session`、持久化模式为 `postgresql`、数据库为 `puiying_steven_demo`。
- Session、平台审计、S2 报价与 Excel 版本元数据均使用 PostgreSQL，不回退 InMemory Repository。

## 2. 已由真实 PostgreSQL、HTTPS 和人工浏览器验证

负责人于 2026-07-17 完成人工浏览器验收并确认“一切正常”：

| 验收项 | 结果 | 证据类型 |
|---|---|---|
| `https://localhost:15443/login` 无证书警告 | 通过 | 人工浏览器验收；当前用户已信任项目 Caddy 本地根证书 |
| 登录成功 | 通过 | 人工浏览器验收；真实 HTTPS 运行日志记录 HTTP 200 |
| `__Host-puiying_session` 属性 | `Secure`、`HttpOnly`、`SameSite=Lax`、`Path=/` | 人工浏览器验收 |
| `__Host-puiying_csrf` 属性 | `Secure`、`SameSite=Lax`、`Path=/` | 人工浏览器验收 |
| 刷新后 Session 保持 | 通过 | 人工浏览器验收；`/api/v1/auth/me` 返回 200 |
| Dashboard 正常读取 | 通过 | 人工浏览器验收；真实 HTTPS 日志返回 200 |
| S2 采购比价页面正常读取 | 通过 | 人工浏览器验收；真实 HTTPS 日志返回 200 |
| 登出后旧会话失效 | 通过 | 人工浏览器验收；同一运行中登出 200，旧 Session 再访问返回 401 |
| PostgreSQL Session 恢复 | 通过 | D1.1 真实 PostgreSQL 运行时与重启恢复证据 |
| HTTPS 仅从 loopback 提供 | 通过 | Caddyfile、运行状态与监听端口核验 |

人工验收没有保存 Cookie 值、密码、Token、私钥或完整连接串；本报告也不记录这些内容。

## 3. 自动化、Mock 或离线验证

以下内容已有自动化或静态证据，但没有冒充人工浏览器或真实 PostgreSQL 证据：

1. FastAPI 自动化测试覆盖：
   - Cookie Session；
   - CSRF 正向与缺失、错误 Token 拒绝；
   - Origin / Referer 校验；
   - 无效、过期、撤销 Session 拒绝；
   - permission-based RBAC；
   - 提交人自审阻断；
   - 四种 legacy 身份头拒绝。
2. Next.js proxy 自动化 smoke 覆盖 legacy 身份头拒绝与同源代理。
3. D1.1 留存回归证据：

```text
pytest：73 passed，1 个既有 Starlette/httpx 弃用 warning
compileall：passed
ESLint：passed
Next.js production build：passed
```

4. D0 Azure Document Intelligence 与 DeepSeek 仅完成 Adapter、mapper、严格 Schema 和 Mock transport 测试；本轮没有任何在线 Provider 调用。

## 4. 未验证或不在 D1.2 范围

1. 未保存浏览器 DevTools 截图、HAR 或 Cookie 面板导出；人工验收结论由项目负责人明确提供。
2. 浏览器人工验收没有单独导出 `X-CSRF-Token` 请求头；合法写请求已通过真实 HTTPS 路径，CSRF 负向用例由自动化测试覆盖。
3. 缺失/错误 CSRF、非法 Origin、缺 Cookie 和四种 legacy 身份头，未在最终 `15443` 运行中逐项保存网络抓包；现有证据为后端自动化和历史 proxy smoke。
4. 未验证 Windows 重启、数据库服务重启、备份恢复、故障切换、生产并发或公网部署。
5. 未调用 Azure、DeepSeek、Redis 或其他外部服务；未使用真实业务文件、账号或 Key。
6. 未实施 S1、S3、NAS、MinIO、监控、备份或生产部署。

## 5. 安全审查发现

本节仅记录安全风险，未执行风险整改。D1.2 实施阶段已完成项目级 Caddy 接入，以及负责人批准的当前用户根证书信任动作。发现以下 D2 前置风险：

### P0：进入任何真实 Key 或外部 Provider 联调前必须处理

1. 项目目录当前继承过宽 ACL，普通本机用户可修改启动脚本、Caddy、项目 Python 和 Web 代码。
2. 已被当前用户信任的 Caddy 本地 CA 私钥位于同一宽 ACL 目录，其他本机用户可能读取或修改。

处理要求：在 D2.0 中必须收紧项目运行目录与 Caddy 私钥目录 ACL，或由负责人基于隔离单用户测试机边界作出书面风险接受；真实 Provider Key 不得在此问题未关闭时注入。

### P1：需在 D2.0 或部署前明确

1. Caddy admin 仅监听 loopback，但当前无认证；任意本机进程可访问管理面。
2. PostgreSQL 当前运行配置监听所有 IPv4/IPv6 接口；现有 `pg_hba.conf` 对非 loopback 默认拒绝，但该状态不能等同于生产网络隔离。
3. Docker PostgreSQL 示例不属于当前 Demo 启动链，但包含不适合直接运行的演示默认值。

### P2：局部防御加固

1. Next.js 对 `X-Forwarded-Proto` 的信任应仅来自受控反向代理。
2. Next.js API 上游应在后续部署配置中限制为批准的 loopback 或受控服务地址。
3. 启动失败清理存在窄竞态窗口，后续应再次核对进程归属。

上述风险不否定本机单用户脱敏 Demo 的 D1.2 功能验收，但会阻断外部 Key 注入、受控试运行和生产化结论。

## 6. D1.2 最终结论

**D1.2 正式通过。**

通过内容仅为：

- 本机独立脱敏 Demo；
- 真实 PostgreSQL Session 与持久数据；
- 项目级 loopback HTTPS；
- Secure / HttpOnly / SameSite Cookie；
- 浏览器登录、刷新恢复、Dashboard/S2 读取与登出撤销。

本结论不表示：

- 生产可用；
- 可受控试运行；
- 安全加固风险已全部关闭；
- Azure、DeepSeek 或其他线上 OCR/AI 已连接；
- D2 已获批准。

## 7. D2 前置 Gate

D2.0 至少需要负责人书面确认：

1. 项目目录与 Caddy CA 私钥 ACL 的整改方式或隔离环境风险接受。
2. Caddy admin 本地管理面的处置方式。
3. Azure 区域、Endpoint、模型、API 版本与数据处理地域。
4. DeepSeek Endpoint、模型及严格 JSON Schema 支持口径。
5. 网络出口、代理、防火墙和出口日志责任边界。
6. 数据传输许可、跨境/地域、保留、不训练和第三方日志要求。
7. 允许外发的脱敏字段白名单与绝对禁止字段。
8. Key 托管、服务端注入、轮换和撤销方案。
9. Provider 失败时是否允许显著标记的 Mock/缓存；默认建议失败后人工录入或人工重试。
10. D2 实施人、验收人、数据负责人、安全负责人、变更窗口与停止条件。

在 D2.0 明确批准前，不得直接执行 D2.1–D2.3。

## 8. 证据路径

- `D:\ZM\AI工坊\某中学\05-测试验收\Steven_Demo_D1_1_运行时接线验收报告_v1_2026-07-17.md`
- `D:\ZM\AI工坊\某中学\05-测试验收\Steven_Demo_D1_1_真实运行时证据_2026-07-17.jsonl`
- `D:\ZM\AI工坊\某中学\05-测试验收\Steven_Demo_D1_1_重启恢复证据_2026-07-17.jsonl`
- `D:\ZM\AI工坊\某中学\05-测试验收\Steven_Demo_D1_PostgreSQL验收报告_v2_2026-07-17.md`
- `D:\ZM\AI工坊\某中学\04-开发实现\data\runtime\runs\20260717-115316\logs\api.out.log`
- `D:\ZM\AI工坊\某中学\04-开发实现\data\runtime\runs\20260717-115316\logs\web.out.log`
- `D:\ZM\AI工坊\某中学\04-开发实现\data\runtime\runs\20260717-115316\logs\caddy.err.log`
- `D:\ZM\AI工坊\某中学\04-开发实现\data\runtime\steven-demo-processes.json`
- `D:\ZM\AI工坊\某中学\04-开发实现\infra\caddy\Caddyfile`
- `D:\ZM\AI工坊\某中学\04-开发实现\scripts\start_steven_demo.ps1`
- `D:\ZM\AI工坊\某中学\04-开发实现\scripts\stop_steven_demo.ps1`
