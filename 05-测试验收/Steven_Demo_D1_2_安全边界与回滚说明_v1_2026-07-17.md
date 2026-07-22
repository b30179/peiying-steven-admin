# Steven Demo D1.2 安全边界与回滚说明 v1

- 日期：2026-07-17
- 适用范围：本机独立脱敏 Demo
- 当前状态：D1.2 已通过
- 边界：本文不是生产部署、受控试运行或 D2 执行说明

## 1. 网络与监听边界

项目拓扑固定为：

```text
Browser HTTPS
  → Caddy 127.0.0.1:15443
  → Next.js 127.0.0.1:4300
  → FastAPI 127.0.0.1:9000
  → puiying_steven_demo
```

要求：

- Caddy HTTPS、Caddy admin、Next.js 和 FastAPI 均只允许 loopback。
- 不新增公网或局域网监听。
- 不修改 hosts、防火墙、全局 PATH 或注册系统服务。
- HTTP 仅作为内部进程间连接，不得成为浏览器降低 Cookie 安全属性的备用登录通道。
- 浏览器只访问 `https://localhost:15443`。

## 2. 身份与请求安全边界

必须保持：

- `AUTH_MODE=session`；
- `__Host-puiying_session`：`Secure`、`HttpOnly`、`SameSite=Lax`、`Path=/`；
- `__Host-puiying_csrf`：`Secure`、`SameSite=Lax`、`Path=/`；
- CSRF 双重提交；
- 严格 Origin / Referer 校验；
- permission-based RBAC；
- 审计记录；
- 四种 legacy 身份头拒绝；
- 登出撤销数据库 Session。

不得为了演示方便关闭或降低以上属性。

## 3. 证书与私钥边界

- Caddy 使用项目级内部 CA。
- 启动脚本配置 `skip_install_trust`，不会自动导入证书。
- 当前根证书仅在负责人明确批准后导入当前用户信任根。
- 不得将私钥、根 CA、Session Token、Cookie 值或密码复制到文档、日志、聊天或源码。
- 当前 Caddy 私钥目录 ACL 过宽；在任何真实 Provider Key 注入前必须整改或完成书面风险接受。

## 4. 数据与服务边界

- 仅使用 `puiying_steven_demo` 和脱敏 Demo 数据。
- 不使用真实校务、供应商、学生、个人或银行资料。
- 不调用 Azure、DeepSeek、Redis 或公网 API。
- 不连接 NAS、MinIO 或其他外部存储。
- 不修改 PostgreSQL 服务配置、账号、ACL、schema、migration 或正式业务数据；人工登录、刷新恢复和登出产生的脱敏 Demo Session 与审计状态写入属于本次验收链路。
- AI/OCR 保持默认关闭；后续即使获批启用，也只能产生 `needs_review` 候选。

## 5. 项目级 HTTPS 回滚

### 5.1 标准停止

执行：

```powershell
cd D:\ZM\AI工坊\某中学\04-开发实现
.\scripts\stop_steven_demo.ps1
```

或双击：

```text
D:\ZM\AI工坊\某中学\04-开发实现\停止Steven本地Demo.cmd
```

预期结果：

- 停止本轮 Caddy、Next.js 和 FastAPI；
- 释放 `15443`、`4300`、`9000`、`20219`；
- 删除本轮进程状态文件；
- 不停止 PostgreSQL 服务；
- 不删除数据库、账号、ACL、schema、migration、业务数据或导出历史。

### 5.2 停用项目级 TLS 入口

在完成标准停止后，负责人可批准以下任一项目级动作：

1. 保持 `infra\caddy\Caddyfile` 与 `tools\caddy\caddy.exe` 原样，但不再运行启动脚本；
2. 将 Caddyfile 移出启动脚本预期路径，使启动保护明确失败；
3. 将项目级 Caddy 工具目录转移到受控归档位置；
4. 在确认不再需要该本地 CA 后，单独批准删除项目运行目录中的 Caddy TLS 存储。

上述动作不得涉及 PostgreSQL 数据和 migration。

### 5.3 当前用户证书信任回滚

从 Windows 当前用户信任根移除项目 Caddy 根证书属于系统信任变更，必须另行批准并记录：

- 仅操作 `CurrentUser\Root` 中明确匹配的项目 Caddy 根证书；
- 不修改本地计算机证书库；
- 不删除其他 Caddy、开发或校方证书；
- 移除后使用本项目 HTTPS 将重新出现证书不受信任状态，除非重新按批准流程导入。

本轮没有执行证书信任回滚。

## 6. 禁止的回滚方式

不得：

- 删除 `puiying_steven_demo`；
- 删除或重建数据库账号；
- 修改 `pg_hba.conf`、数据库 ACL 或 migration；
- 删除历史报价、审计、Session、候选或导出版本；
- 关闭 Secure、HttpOnly、SameSite、CSRF、RBAC、Origin 或审计；
- 改用 HTTP 绕过浏览器 Secure Cookie；
- 修改 hosts、防火墙、系统服务或全局 PATH；
- 用 Mock 数据冒充在线 OCR/AI 成功。

## 7. 当前安全阻断项

在进入 D2.1 或注入任何真实 Key 前：

1. 必须收紧项目运行目录 ACL；
2. 必须收紧 Caddy CA 私钥和证书存储目录 ACL；
3. 必须确认 Caddy admin 的本地管理面处置；
4. 必须确认 PostgreSQL 网络监听与主机边界；
5. 必须完成 D2.0 负责人书面准入。

D1.2 通过不解除这些阻断项。
