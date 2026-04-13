# 技能运行时

## TL;DR

技能不是员工人格的一部分。  
技能是运行时根据票面需求、交付类型、项目地图和故障态势，临时装配给执行者的武器。

## 设计目标

- 把技能从“提示词时代的外挂”收成 runtime 正式合同。
- 让同一角色在不同任务上拿不同技能。
- 让技能注入、冲突解决、回收、审计都可追踪。
- 让 `implementation / review / debugging / planning` 四类任务自动切换技能组。

## 非目标

- 不把技能当成人格。
- 不让 Worker 在执行时自由搜索并启用未知技能。
- 不把技能和 provider 绑定死。
- 不让技能系统直接派单或改图。

## 核心 Contract

### 1. `SkillDescriptor`

| 字段 | 含义 |
|---|---|
| `skill_id` | 技能标识 |
| `capability_tags[]` | 能力标签 |
| `task_categories[]` | 适用任务类别 |
| `deliverable_kinds[]` | 适用交付类型 |
| `conflict_tags[]` | 冲突标签 |
| `injection_mode` | `REQUIRED / PREFERRED / OPTIONAL` |
| `source_ref` | 技能来源 |
| `audit_level` | 审计强度 |

### 2. `SkillBinding`

| 字段 | 含义 |
|---|---|
| `binding_id` | 本次绑定标识 |
| `ticket_ref` | 绑定到哪张票 |
| `resolved_skills[]` | 解析结果 |
| `binding_reason` | 为什么绑定这些技能 |
| `binding_scope` | 对哪个阶段生效 |
| `conflict_resolution` | 冲突怎么解 |
| `expires_on_event` | 在哪个事件后失效 |

### 3. `SkillResolutionPolicy`

解析顺序固定为：

1. 任务类别
2. 交付类型
3. workflow `GovernanceProfile`
4. 失败态势
5. 项目地图风险区
6. 显式强制技能

角色只是过滤器，不是绑定主键。

### 4. 默认技能组

| 场景 | 默认技能 |
|---|---|
| `IMPLEMENTATION` | 实现类、文档同步类、验证类 |
| `REVIEW` | 审查类、证据核对类 |
| `DEBUGGING` | 调试类、失败指纹类 |
| `PLANNING / DESIGN` | 规划类、约束对齐类 |

## 状态机 / 流程

技能解析链固定如下：

1. `Context Compiler` 识别任务类别和风险。
2. `Skill Resolver` 拉取候选技能。
3. 解决冲突，生成 `SkillBinding`。
4. 把技能绑定引用写进 `CompiledExecutionPackage`。
5. Worker 按绑定后的技能组执行。
6. 执行结束后，绑定失效并进入审计记录。

默认冲突解法：

- `REQUIRED` 压过 `PREFERRED`
- 同类互斥技能只保留最贴近任务类别的一组
- 失败态势触发的技能可以覆盖普通实现技能
- `audit_mode` 可以提高最低 `audit_level`，`AUTO_CEO + MINIMAL` 则可以不注入重 trace 技能

## 失败与恢复

| 失败 | 说明 | 恢复 |
|---|---|---|
| `SKILL_NOT_FOUND` | 需要的技能不存在 | 退回 `Context Compiler` 重新解析，必要时开 incident |
| `SKILL_CONFLICT` | 两组技能互斥 | 按 `SkillResolutionPolicy` 决策 |
| `SKILL_STALE` | 绑定版本和当前任务不匹配 | 重新绑定 |
| `SKILL_ABUSE` | Worker 试图使用未绑定技能 | 拒绝执行结果 |

恢复原则：

- 技能缺失要显式暴露，不允许偷偷降成“裸 Worker”。
- 技能冲突靠策略解决，不靠 Worker 临场选。
- 技能绑定必须进入审计面，便于复盘为什么这张票会这样做。

## 统一示例

在 `library_management_autopilot` 里：

- `node_backend_catalog_build` 默认拿实现类技能。
- 如果它连续失败并形成 `FailureFingerprint`，下一次执行包会切到调试类技能。
- `node_delivery_check` 和 `node_board_review` 则不拿实现技能，而拿审查和证据核对技能。

这就保证了“同一角色不是永远一种人格”，而是针对场景切武器。

## 和现有主线的关系

当前主线已经有不少技能和规则存在，但主要还停在：

- 开发代理的会话层
- prompt 组织层
- 人工约定层

当前缺的是：

- `SkillDescriptor`
- `SkillBinding`
- `SkillResolutionPolicy`
- 技能进入 `CompiledExecutionPackage`

新架构把技能从“人知道该怎么用”收成“系统知道什么时候该给谁用什么”。
