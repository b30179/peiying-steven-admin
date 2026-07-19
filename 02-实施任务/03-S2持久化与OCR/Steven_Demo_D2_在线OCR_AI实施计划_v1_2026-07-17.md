# Steven Demo D2 在线 OCR / AI 实施计划 v1

- 日期：2026-07-17
- 状态：**Plan-only，不可执行**
- 当前基线：D0 合同冻结、D1 PostgreSQL、D1.1 运行时接线、D1.2 HTTPS 浏览器 Session 闭环
- 真实演示切片：S2 报价 OCR → AI 候选 → 人工确认 → PostgreSQL → 规则比价 → 人工推荐/审批 → Excel
- 边界：本计划不构成 Azure、DeepSeek、Redis、网络出口、Key 注入或数据传输授权

## 1. 不可改变的业务边界

1. OCR/AI 默认关闭。
2. OCR/AI 结果只能进入 `needs_review` 候选层。
3. OCR/AI 不得直接写 `steven_quote_*` 或未来 S1/S3 正式业务表。
4. 正式写入必须经过人工确认与模块 confirmer / Unit of Work。
5. AI 不得推荐或选择供应商，不得计算可信金额或排序，不得审批、下单、发信或确认库存。
6. Mock、缓存与 live 结果必须显著区分，不得伪装。
7. D2 仅针对脱敏 S2 样本；不实施 S1、S3、NAS、MinIO、Redis、队列集群或生产部署。

## 2. D2.0：负责人决策与准入清单

### 输入

- D1.2 正式验收报告。
- D0 Adapter、Schema、候选状态机与全业务复用架构。
- 负责人对 Provider、网络、数据、Key、fallback 和安全 Gate 的书面决定。
- D2 实施人、验收人、数据负责人、安全负责人和变更窗口。

### 负责人必须确认

| 决策项 | 必须明确的内容 |
|---|---|
| Azure 区域 | 资源区域、数据处理地域、是否涉及跨境 |
| Azure Endpoint | 批准的 HTTPS Endpoint、资源名称、API 版本 |
| Azure 模型 | 建议 `prebuilt-invoice`；最终以批准口径为准 |
| DeepSeek Endpoint | 批准的服务端 Endpoint，不得由前端提供 |
| DeepSeek 模型 | 精确模型名称、版本和 JSON Schema 能力 |
| 网络出口 | DNS、TLS、代理、防火墙、出口 IP、日志和责任人 |
| 数据传输许可 | 可发送数据类别、地域、保留、不训练、第三方日志和批准编号 |
| 脱敏字段白名单 | 允许字段、禁止字段、规则版本、抽检方法、批准人与维护人 |
| Key 托管 | 托管位置、服务端注入方式、授权主体、轮换和撤销 |
| 失败 fallback | 是否允许 `mock` / `cached_demo`；默认建议不自动 fallback |
| 安全 Gate | 项目 ACL、Caddy 私钥 ACL、Caddy admin 和 PostgreSQL 网络边界 |
| 责任与停止条件 | 实施、验收、安全、数据负责人，时间窗口和立即停止条件 |

### 允许动作

- 只读核对现有 Adapter、Schema、Repository/UoW 与审计缺口。
- 编制脱敏白名单、Provider 配置项和最小单样本验证方案。
- 在所有 Gate 书面关闭后，另行发出 D2.1 实施指令。

### 禁止动作

- 联网调用 Azure、DeepSeek 或其他 Provider。
- 读取、生成、保存或注入真实 Key。
- 传输真实业务、校务、供应商或个人数据。
- 修改 PostgreSQL、网络、安全属性或业务规则。
- 将本计划视为执行授权。

### 验收证据

- 签署的 D2.0 决策表。
- 脱敏样本与允许发送字段清单。
- 网络与 Key 托管责任说明。
- 安全 Gate 关闭或书面风险接受记录。
- D2.1–D2.3 的实施、验收和回滚责任人。

### 回滚

- 不批准 D2，保持：

```text
OCR_ENABLED=false
AI_STRUCTURING_ENABLED=false
```

- 不配置 Endpoint、Key 或网络出口。
- D0/D1/D1.1/D1.2 已有能力保持不变。

## 3. D2.1：Azure Document Intelligence 最小联通

### 输入

- D2.0 已书面通过。
- 经批准的 Azure 区域、Endpoint、模型与 API 版本。
- 经批准的服务端 Key 注入方式。
- 单份完全脱敏的 D0 PDF 或 PNG。
- 仅 S2 `quotation_extraction` purpose。

### 允许动作

- 补齐受控 Azure HTTP transport 与正式 PostgreSQL 运行时装配。
- 仅发送一份脱敏样本做最小联通。
- 验证 DNS、TLS、超时、错误映射与 Provider request ID。
- 将合法结果保存为 `needs_review` 候选，标记 `source=live`。
- 记录脱敏的 provider、model、状态、耗时和 request ID。

### 禁止动作

- 批量上传、并发压测或使用真实文件。
- 将 OCR 结果直接写正式报价。
- 开启 S1/S3。
- 在日志或审计中保存 Key、Authorization、完整文件或完整 OCR 原文。
- Provider 失败时自动伪装成 live 成功。

### 验收证据

1. 单次请求的时间、HTTP 状态、耗时和脱敏错误。
2. 实际区域、Endpoint、模型、API 版本及 `source=live`。
3. 页码、bbox、置信度等 evidence 可用于人工复核。
4. 候选状态为 `needs_review`，正式报价表无写入。
5. 超时、无效响应和 Provider 错误均进入明确 `failed`。
6. 日志抽检不含 Key、Authorization、完整原文或连接串。

### 回滚

- 关闭 `OCR_ENABLED`。
- 撤销 Provider Key 的运行时访问并按托管策略轮换或吊销。
- 未确认候选保持非正式状态。
- 保留必要的脱敏失败审计，不保留未批准的原始 Provider 内容。

## 4. D2.2：DeepSeek 严格 JSON Schema 最小联通

### 输入

- D2.1 产生的一份脱敏 OCR 结果。
- 经批准的 DeepSeek Endpoint、模型和服务端 Key 注入方式。
- 冻结的 `steven.s2.quotation` Schema。
- 允许发送字段白名单和禁止决策字段清单。

### 允许动作

- 仅发送白名单字段。
- Provider 原生支持时使用完整 `json_schema` strict 模式。
- 若 Provider 不支持原生 strict Schema，只能在负责人书面接受后采用：

```text
json_object 响应约束
  + 本地 Pydantic extra="forbid" 严格校验
```

- 合法输出只生成 `needs_review` 候选。
- 验证坏 JSON、额外字段、缺失字段、类型错误和禁止决策字段。

### 禁止动作

- 将普通 `json_object` 宣称为原生严格 JSON Schema。
- 发送完整文件、完整 OCR 原文、证据图片或未批准个人信息。
- 允许 AI 推荐、排序、审批、下单、发信或确认库存。
- Schema 校验失败后容错写正式数据。
- live 失败后自动切换 Mock/缓存并伪装为 live。

### 验收证据

1. 合法样本严格通过并仅包含冻结字段。
2. 坏 JSON、额外/缺失字段、类型错误全部失败。
3. 推荐、审批、下单、库存确认等禁止字段全部拒绝。
4. 记录实际 Endpoint、模型、Schema 模式、耗时与 source。
5. 人工确认前正式业务表保持无写入。
6. 明确采用原生 strict Schema，或经批准的本地严格校验降级口径。

### 回滚

- 关闭 `AI_STRUCTURING_ENABLED`。
- 撤销 DeepSeek Key 访问并按托管策略轮换或吊销。
- 返回人工录入或人工重试。
- 如批准使用 Mock/缓存，UI、API 和审计必须标记 `mock` 或 `cached_demo`。

## 5. D2.3：失败回退、脱敏、人工复核与审计

### 输入

- D2.1 与 D2.2 验收证据。
- 经批准的字段级白名单及规则版本。
- confirmer、Unit of Work、权限、重复项和金额规则。
- fallback、审计保留和候选清理策略。

### 允许动作

- 默认失败链：

```text
live failed → failed → 人工录入或人工重试
```

- 仅在书面批准后使用显著标记的 `mock` 或 `cached_demo`。
- 人工并排复核原件、OCR evidence、AI 候选与最终值。
- 确认时重新校验币种、完整性、数量、金额、重复项与权限。
- 仅由 confirmer + Unit of Work 在同一事务写正式报价、candidate 状态和业务审计。

### 禁止动作

- 仅依赖邮箱、电话号码黑名单作为完整脱敏方案。
- 自动确认候选或绕过人工复核。
- 将 Mock、缓存或历史结果伪装为实时 Provider 成功。
- 审计保存 Key、Authorization、完整原文或完整 Provider 响应。
- Provider 失败后创建可误认为正式数据的记录。

### 验收证据

1. 脱敏白名单版本、测试样本、抽检结果与批准人。
2. `live`、`failed`、`mock`、`cached_demo` 在 UI、API 和审计中可区分。
3. 人工确认前候选不进入正式表。
4. 审计记录 provider、model、source、状态、错误码、耗时、request ID、对象 ID 和脱敏规则版本。
5. 失败、人工修订、确认和正式写入形成完整关联链。
6. 候选确认失败时正式报价、candidate 状态和业务审计全部回滚。

### 回滚

- 同时关闭 OCR 与 AI Provider。
- 停止自动重试。
- 保留必要且已脱敏的失败审计。
- 未确认候选保持隔离，按批准的保留策略处理。
- 业务恢复为人工录入，不以 Mock/缓存作为默认路径。

## 6. 建议实施顺序

```text
D2.0 负责人决策与安全 Gate
  → D2.1 Azure 单样本最小联通
  → D2.2 DeepSeek 严格 Schema 单样本联通
  → D2.3 失败回退、脱敏、人工复核与审计
  → 独立验收
```

任何一步失败或越过边界时立即停止，不自动推进下一步。

## 7. 当前结论

- D1.2 已通过本机独立脱敏 Demo 验收。
- Azure、DeepSeek、Redis 和任何公网 API 均未调用。
- 未读取、保存或配置真实 Key。
- D2.0 尚未获得负责人明确批准。
- **现在不能直接执行 D2.1、D2.2 或 D2.3。**
