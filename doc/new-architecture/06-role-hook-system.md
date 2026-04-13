# 角色 Hook 系统

## TL;DR

标准化动作不该靠 prompt 里提醒“记得补文档、记得提 review、记得 git commit”。  
这些动作应该绑定到角色和事件上，变成正式的 `RoleHook`。

## 设计目标

- 把高频收口动作从“提醒”变成“制度”。
- 让不同交付类型自动走不同后置动作。
- 让 Worker 完成实现后，系统自己补证据、补文档、提 review、更新项目地图。
- 让 hook 也有幂等键、失败策略和审计线索。

## 非目标

- 不把 hook 做成另一个自由执行器。
- 不让 hook 绕过 `allowed_write_set` 和产物合同。
- 不让 hook 直接决定业务图结构。
- 不把所有小动作都扩成独立票。

## 核心 Contract

### 1. `RoleHook`

| 字段 | 含义 |
|---|---|
| `hook_id` | Hook 标识 |
| `role_ref` | 绑定角色 |
| `lifecycle_event` | 触发事件 |
| `deliverable_kind` | 适用交付类型 |
| `required_inputs[]` | 执行 hook 需要的引用 |
| `produced_assets[]` | hook 写出的资产 |
| `required_write_set[]` | hook 自己的写集 |
| `idempotency_key_template` | 幂等键模板 |
| `failure_policy` | 失败时怎么处理 |
| `activation_policy` | 在不同 `approval_mode / audit_mode` 下是 required、optional 还是 skipped |
| `visibility` | 是否进入 Board / CEO 读面 |

### 2. 生命周期事件

| 事件 | 常见 hook |
|---|---|
| `PACKAGE_COMPILED` | `worker_preflight` |
| `RESULT_ACCEPTED` | `documentation_sync`、`evidence_capture`、`git_closeout` |
| `VERDICT_ACCEPTED` | `review_followup_generation` |
| `BOARD_APPROVED` | `board_pack_archive`、`closeout_release` |
| `INCIDENT_RESOLVED` | `project_map_refresh`、`failure_fingerprint_update` |

### 3. 默认 hook 目录

| Hook | 适用角色 | 作用 |
|---|---|---|
| `worker_preflight` | Worker | 记录执行包和必读面 |
| `documentation_sync` | Worker / Hook Runner | 校验并写文档同步信息 |
| `evidence_capture` | Worker / Checker | 固化测试、截图、日志、review 证据 |
| `git_closeout` | Worker | 固化 branch、commit、merge 证据 |
| `ticket_trace_capture` | Hook Runner | 固化逐票上下文摘要、实施记录和交付索引 |
| `timeline_archive` | Hook Runner | 把自治机沟通时间线写进 `90-archive/transcripts` |
| `review_request` | Maker | 自动创建 Checker 路径 |
| `board_pack_generation` | Review 角色 | 生成 Board 可裁决包 |
| `project_map_refresh` | Hook Runner | 刷新模块边界、责任和热区 |

## 状态机 / 流程

Hook 链固定规则：

1. 事件发生。
2. Registry 根据 `role + lifecycle_event + deliverable_kind + governance modes` 找 hook。
3. Hook Runner 校验输入和写集。
4. Hook 执行。
5. 写 `EventRecord` 和 `ProcessAsset`。
6. 只有必要 hook 全部成功，节点才对下游开放。

这里有一个硬规则：

`TICKET_COMPLETED` 只表示执行成功。  
节点真正转成 `COMPLETED`，必须等 required hooks 全部成功。

required hooks 由 `audit_mode` 决定，但最低地板要按交付类型看。

对 `source_code_delivery`，固定地板如下：

- `documentation_sync`
- 最低 `evidence_capture`
- `git_closeout`

对其他交付类型，也必须保留各自的最低收口证据。  
也就是说，`MINIMAL` 可以跳过逐票 trace 和全量时间线，不可以跳过最低交付收口。

## 失败与恢复

| 失败 | 说明 | 恢复 |
|---|---|---|
| `HOOK_INPUT_MISSING` | 上游结果缺必要输入 | 回到结果提交口修正 |
| `HOOK_WRITE_DENIED` | hook 试图越权写文件 | 失败并开 incident |
| `HOOK_PARTIAL_SUCCESS` | 一部分资产落了，一部分没落 | 按幂等键补跑未完成部分 |
| `HOOK_CHAIN_TIMEOUT` | hook 长时间未收口 | 冻结下游并升级 |
| `AUDIT_POLICY_MISMATCH` | 当前档位要求的审计材料没被物化 | 拒绝 closeout 并补跑 hook |

恢复原则：

- hook 可以重跑，但必须幂等。
- hook 失败不能默默放行下游。
- hook 不负责解释业务意图，只负责标准动作收口。

## 统一示例

`node_backend_catalog_build` 完成后，会自动触发：

1. `documentation_sync`
2. `evidence_capture`
3. `git_closeout`
4. `review_request`
5. `project_map_refresh`

如果这时代码写出来了，但 `git_closeout` 没跑通，`node_delivery_check` 依然不能 ready。  
这样一来，“代码改了但证据没齐”不再靠 Checker 凭经验兜，而是由 hook 协议直接拦住。

## 和现有主线的关系

当前主线已经有 hook 雏形：

- `worker-preflight`
- `worker-postrun`
- `evidence-capture`
- `git-closeout`

当前缺的不是“有没有后置动作”，而是：

- 没有统一 `RoleHook` 注册表
- 没有按角色和交付类型正式匹配
- 没有把 hook 失败写成正式状态机门禁

新架构就是把这些零散回执升级成正式 hook 系统。
