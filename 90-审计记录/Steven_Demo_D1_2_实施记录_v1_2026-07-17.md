# Steven Demo D1.2 实施记录 v1

- 日期：2026-07-17
- 范围：本机项目级 Caddy、loopback HTTPS、浏览器 Session 闭环及验收收口
- 状态：D1.2 已通过，限定为本机独立脱敏 Demo
- 边界：不表示生产可用、可受控试运行、已进入 D2 或已接入线上 OCR/AI

## 1. 项目级 HTTPS 实现

1. 使用项目级 Caddy，不注册系统服务、不修改全局 PATH。
2. Caddy 版本：`v2.10.2`。
3. `caddy.exe` SHA-256：

```text
586D4A4CD74BDFD2951B6B81766A32904FFA69C4F1C3D521DA3870A2120F1D31
```

4. 文件路径：

```text
D:\ZM\AI工坊\培英\04-开发实现\tools\caddy\caddy.exe
D:\ZM\AI工坊\培英\04-开发实现\infra\caddy\Caddyfile
```

5. 监听边界：
   - HTTPS：`127.0.0.1:15443`
   - Next.js：`127.0.0.1:4300`
   - FastAPI：`127.0.0.1:9000`
   - Caddy admin：`127.0.0.1:20219`
6. 浏览器唯一入口：

```text
https://localhost:15443/login
```

7. Caddy 使用项目运行目录生成本地开发 CA；配置保持 `skip_install_trust`，不会在启动时静默修改 Windows 证书信任。

## 2. 当前用户证书信任

项目负责人已明确批准将当前项目 Caddy 根证书导入当前用户信任根。

- 信任范围：`CurrentUser\Root`
- 未导入本地计算机级证书库。
- 未修改 hosts、防火墙、PATH 或系统服务。
- 启动脚本本身仍不自动安装或修改信任。
- 本记录不包含证书私钥内容。

负责人于 2026-07-17 人工确认浏览器访问 HTTPS 时无证书警告。

## 3. 启动与停止

启动入口：

```text
D:\ZM\AI工坊\培英\04-开发实现\启动Steven本地Demo.cmd
D:\ZM\AI工坊\培英\04-开发实现\scripts\start_steven_demo.ps1
```

停止入口：

```text
D:\ZM\AI工坊\培英\04-开发实现\停止Steven本地Demo.cmd
D:\ZM\AI工坊\培英\04-开发实现\scripts\stop_steven_demo.ps1
```

已验证：

1. 首次启动成功。
2. 重复启动健康实例时直接复用，不再因状态文件报错。
3. 停止后四个项目端口释放，状态文件删除。
4. 再次启动成功。
5. 陈旧状态仅在无相关活动进程和端口时清理。
6. 停止脚本核对监听端口与 PID 归属，避免按陈旧 PID 误停其他程序。

## 4. 浏览器人工验收

项目负责人已完成并确认：

- HTTPS 无证书警告；
- 登录成功；
- `__Host-puiying_session` 的 `Secure`、`HttpOnly`、`SameSite=Lax`、`Path=/` 正常；
- `__Host-puiying_csrf` 的 `Secure`、`SameSite=Lax`、`Path=/` 正常；
- 刷新后 Session 保持；
- Dashboard 与 S2 页面正常；
- 登出后旧会话无法访问。

真实 HTTPS 程序探针同时确认登录、`/auth/me`、Dashboard、登出和旧 Session 401 链路。程序探针没有被当作人工浏览器 DevTools 证据。

## 5. 安全属性保持

- Session Token 仅保存在 HttpOnly Cookie。
- CSRF 使用可读 Secure Cookie 与 `X-CSRF-Token` 双重提交。
- Origin / Referer、RBAC、审计和 legacy 身份头拒绝保持启用。
- HTTP 不作为降低 Secure Cookie 的替代登录通道。
- `AUTH_MODE=session`。
- `DEMO_SEED_ENABLED=false`。
- OCR 与 AI structuring 保持关闭。

## 6. 敏感信息检查

本轮文档与日志核验未写入或回显：

- 密码；
- Session Token；
- CSRF Token；
- Cookie 值；
- 证书私钥；
- 完整数据库连接串；
- Azure、DeepSeek 或其他外部 Key。

## 7. 只读安全审查结果

本轮没有实施安全整改，仅记录风险：

1. **P0**：项目运行目录 ACL 过宽，启动链组件可被其他本机用户修改。
2. **P0**：已受当前用户信任的 Caddy CA 私钥目录继承过宽 ACL。
3. **P1**：Caddy admin 虽仅监听 loopback，但无认证。
4. **P1**：PostgreSQL 监听所有 IPv4/IPv6 接口；现有 pg_hba 仅允许 loopback，仍需在任何部署前独立治理。
5. **P2**：Next.js 的代理信任和上游地址需要在未来部署配置中进一步约束。

在真实 Provider Key 注入、受控试运行或生产化前，P0 风险必须整改或由负责人对隔离单用户测试环境作书面风险接受。

## 8. 本轮没有执行

- 未修改 PostgreSQL 服务配置、ACL、角色、数据库、schema、migration 或正式业务数据；人工登录、刷新恢复和登出产生的脱敏 Demo Session 与审计状态写入属于验收链路。
- 除负责人已批准并完成的项目根证书 `CurrentUser\Root` 导入外，未修改 Windows 服务、PATH、hosts 或防火墙；本次验收收口未再次改变证书信任状态。
- 未调用 Azure、DeepSeek、Redis 或公网 API。
- 未读取或写入真实 Key、真实业务文件或真实校务数据。
- 未进入 D2、S1、S3、NAS、部署、备份或监控。

## 9. 最终记录

D1.2 已完成本机独立脱敏 Demo 的 PostgreSQL + HTTPS 浏览器 Session 闭环。D2 仍未批准；后续只能先完成 D2.0 决策与安全 Gate。
