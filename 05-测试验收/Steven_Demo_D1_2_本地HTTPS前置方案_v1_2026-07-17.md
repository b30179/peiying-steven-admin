# Steven Demo D1.2 本地 HTTPS 前置方案 v1

- 日期：2026-07-17
- 状态：Plan-only，未实施
- 目的：在不降低 Cookie、CSRF、RBAC、Origin 和审计安全属性的前提下，完成真实浏览器 Session 登录闭环
- 边界：D1.2 需要项目负责人单独批准；本文件不构成实施授权

## 1. 当前事实

1. FastAPI 已可使用 `AUTH_MODE=session` 连接真实 Demo PostgreSQL。
2. Next.js 已可在 `http://127.0.0.1:4300` 启动并访问登录页。
3. Session Cookie 为 `__Host-puiying_session`：
   - `Secure=true`
   - `HttpOnly=true`
   - `SameSite=Lax`
   - `Path=/`
4. CSRF Cookie 为 `__Host-puiying_csrf`：
   - `Secure=true`
   - 前端可读，用于双重提交；
   - `SameSite=Lax`
   - `Path=/`
5. 前端 API proxy 会转发 Cookie、Origin、Referer、`X-CSRF-Token` 与 request ID，并拒绝四种 legacy 身份头。
6. 本轮未取得浏览器 HTTPS origin，因此未完成真实浏览器 Cookie 登录验证；不得通过设置 `SESSION_COOKIE_SECURE=false` 绕过。

## 2. 推荐最小拓扑

推荐保持 FastAPI 仅监听 localhost HTTP，由一个经批准的项目本地 HTTPS 入口承接浏览器流量：

```text
Browser HTTPS
  → 本地受控 TLS 入口
  → Next.js 127.0.0.1:4300
  → Next.js /api proxy
  → FastAPI 127.0.0.1:9000
  → puiying_steven_demo
```

这样浏览器只接触同一个 HTTPS origin；Session Token 仍只存在 HttpOnly Cookie，不进入前端脚本、URL或日志。

## 3. 实施前必须单独批准

1. 本地 TLS 实现方式：
   - 使用校方/项目已批准的现有反向代理；或
   - 批准一个项目级本地 TLS 工具。
2. 证书来源与信任方式：
   - 批准的开发 CA 或校方证书；
   - 是否允许在本机信任证书；
   - 证书与私钥的受管存放位置。
3. 浏览器访问主机名与 HTTPS 端口。
4. 是否允许修改 hosts；如不允许，应使用无需 hosts 变更的获批 loopback 方案。
5. 是否允许安装或使用反向代理、生成证书、开放本地端口。
6. 凭据提供方式：测试账号由负责人提供或通过受控重置流程产生，密码不得进入命令、报告、聊天或日志。

## 4. 需要调整的项目配置

获得批准后，仅按实际 HTTPS origin 配置：

```text
ALLOWED_ORIGINS=https://<approved-local-origin>
SESSION_COOKIE_SECURE=true
AUTH_MODE=session
DEMO_SEED_ENABLED=false
```

继续保持：

- API 仅监听 `127.0.0.1:9000`；
- Next.js 内部通过 `STEVEN_API_BASE_URL` 访问 API；
- 浏览器只通过 HTTPS 前端的 `/api/auth/*` 与 `/api/steven/*`；
- 不接受 `X-Role`、`X-Actor`、`X-Acting-Role`、`X-Acting-Actor`；
- 不把数据库密码、Session Token 或 CSRF Token写入日志。

## 5. D1.2 验收清单

1. 浏览器访问 HTTPS 登录页，无证书告警或证书链已按批准方式处理。
2. 登录响应成功设置两个 `__Host-` Cookie。
3. Session Cookie 在浏览器中显示 `Secure`、`HttpOnly`、`SameSite=Lax`。
4. CSRF Cookie 保持 `Secure`，前端写请求自动发送 `X-CSRF-Token`。
5. 刷新页面后 `/api/v1/auth/me` 可从 PostgreSQL Session 恢复身份。
6. Dashboard 与 S2 页面通过 permission-based RBAC 读取。
7. 无 CSRF、错误 CSRF、非法 Origin、Cookie 缺失均被拒绝。
8. 四种 legacy 身份头通过 Next.js proxy 和 FastAPI 均被拒绝。
9. 登出后 Session 被撤销，旧 Cookie 再请求返回 401。
10. API、审计与浏览器日志均不出现 Token、密码或完整数据库连接串。
11. HTTP 入口不得成为降低安全属性的备用登录通道。

## 6. 不在 D1.2 顺带实施

- Azure、DeepSeek、Redis、OCR/AI 在线调用。
- D2、S1、S3、真实业务资料。
- NAS、MinIO、备份、监控或生产部署。
- 修改 PostgreSQL ACL、migration 或业务数据。
- 关闭 Secure Cookie、CSRF、RBAC、Origin 或审计。

## 7. 建议

D1.2 应作为独立受控任务审批并实施。完成真实浏览器 HTTPS 登录验收之前，**仍不建议进入 D2**。
