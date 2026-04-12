# Scenarios Guide

这份清单专门解释 `backend/data/scenarios/` 下面这些长测工作区目录到底是干嘛的。

先说核心：

- `backend/data/scenarios/<scenario-slug>/` 是一轮 live 集成测试的独立沙箱。
- 每个场景目录基本都在模拟一个“完整的小型控制面工作区”。
- 里面既有数据库，也有工件、项目工作区、调试材料、失败快照。
- 你排查长测卡点时，基本都从这里下手。

---

## 一层目录怎么理解

`backend/data/scenarios/`

- 这一层是所有场景输出的总根。
- 常见子目录名就是场景名，比如：
  - `library_management_autopilot_live`
  - `requirement_elicitation_autopilot_live`
  - `architecture_governance_autopilot_live`
  - `architecture_governance_autopilot_smoke`

你可以把每个场景目录理解成：

- 一次独立长测的全量现场
- 一个可复盘、可调试、可删除重建的运行快照

---

## 当前这个场景目录

当前你问的是：

`backend/data/scenarios/library_management_autopilot_live/`

它现在包含这些顶层内容：

- `artifacts/`
- `artifact_uploads/`
- `developer_inspector/`
- `failure_snapshots/`
- `ticket_context_archives/`
- `boardroom_os.db`
- `runtime-provider-config.json`
- `integration-monitor-report.md`

下面逐个说用途。

---

## `boardroom_os.db`

用途：

- 这是这轮场景自己的 SQLite 数据库。
- 它是这轮长测最核心的“真实状态源”。
- workflow、ticket、approval、incident、event 都在这里。

你通常会从这里查：

- 当前 workflow 到哪一步了
- 当前哪张 ticket 在跑
- 最近有没有新事件
- 有没有 open incident
- 有没有 pending approval
- 为什么 controller 没继续往下放票

说白了：

- 这是“真实现场”。
- 其他目录大多是它派生出来的调试材料或工件副本。

---

## `runtime-provider-config.json`

用途：

- 这是这轮场景运行时实际吃到的 provider 配置快照。
- 里面会记录：
  - `default_provider_id`
  - `providers[]`
  - `provider_model_entries[]`
  - `role_bindings[]`

你通常会从这里查：

- 这轮到底绑的是哪个 provider
- 模型是不是 `gpt-5.4`
- `ceo_shadow`、`architect_primary`、`checker_primary` 分别绑到哪
- 有没有因为配置写法不对导致 live path 走偏

这个文件的意义是：

- 它不是仓库里的模板。
- 它是这轮场景真正落地后的运行配置。

---

## `integration-monitor-report.md`

用途：

- 这是人工排障时持续追加的巡检报告。
- 不是系统主线必备文件。
- 是我们为了盯长测、记卡点、记修复动作单独写的。

里面通常会记录：

- 某个时间点的 workflow 状态
- 当前 ticket 数
- 当前 incident / approval 数量
- 卡点判断
- 排查证据
- 修复动作
- 重启原因

它的价值很直接：

- 让你不用反复翻聊天记录
- 一眼看到“这轮到底发生过什么”

---

## `artifacts/`

用途：

- 这是这轮场景里所有产出工件的主目录。
- 项目工作区、治理文档、输入工件都在这里。

你可以把它理解成：

- “这轮 workflow 实际产出了什么文件”

它下面最重要的是三块：

- `inputs/`
- `project-workspaces/`
- `reports/`

### `artifacts/inputs/`

用途：

- 保存原始输入工件。
- 当前最典型的是 `project-init` 阶段的 `board-brief.md`。

例如：

- `artifacts/inputs/project-init/<workflow-id>/board-brief.md`

这类文件一般表示：

- 董事会给 CEO 的原始目标说明
- 初始约束和场景目标的落盘版本

### `artifacts/project-workspaces/`

用途：

- 这是每个 workflow 自己的“受管项目工作区”。
- 里面模拟真实项目目录，而不是控制面的数据库视图。

目录结构一般是：

- `project-workspaces/<workflow-id>/00-boardroom`
- `project-workspaces/<workflow-id>/10-project`
- `project-workspaces/<workflow-id>/20-evidence`

这是你排查“有没有真的写代码、有没有真的写证据”的第一现场。

### `artifacts/reports/`

用途：

- 存放运行时生成的结构化报告类工件。
- 当前最常见的是治理文档：
  - `reports/governance/<ticket-id>/*.json`

例如：

- `reports/governance/<ticket-id>/architecture_brief.json`
- `reports/governance/<ticket-id>/technology_decision.json`
- `reports/governance/<ticket-id>/milestone_plan.json`
- `reports/governance/<ticket-id>/detailed_design.json`
- `reports/governance/<ticket-id>/backlog_recommendation.json`

这些文件的意义是：

- 它们是 ticket 实际提交出来的结构化产物
- 也是 maker-checker 和 controller 后续消费的输入

---

## `project-workspaces/<workflow-id>/00-boardroom`

用途：

- 放工作流控制面自己的工作区内部元信息。
- 这里不是业务代码。
- 更像 workflow 运行时的“项目管理层文件”。

当前常见内容在：

- `00-boardroom/workflow/`

里面常见文件：

- `active-worktree-index.md`
  - 当前活跃 worktree / checkout 索引
  - 方便知道哪些 ticket checkout 已经开过

- `hook-policy.md`
  - 工作区 hook 的要求说明
  - 比如代码票必须补哪些文档、证据、git 回执

- `methodology-profile.md`
  - 当前 workflow 采用的项目方法论
  - 比如 `AGILE`

- `phase-status.md`
  - 当前 workflow 的阶段状态摘要

- `workspace-manifest.json`
  - 这整个受管工作区的结构化描述
  - 包括默认文档更新要求、目录布局之类的规则

说白了：

- `00-boardroom` 是“管这个项目怎么跑”的地方。
- 不是“项目代码写在哪”的地方。

---

## `project-workspaces/<workflow-id>/10-project`

用途：

- 这是项目本体目录。
- 真实代码、项目文档、设计说明，理论上都应该在这里。

当前常见结构：

- `AGENTS.md`
  - 项目内部工作约束

- `ARCHITECTURE.md`
  - 项目级架构文档骨架

- `docs/`
  - 项目文档

- `src/`
  - 代码目录

- `tests/`
  - 测试目录

### `10-project/docs/L0-context`

用途：

- 放项目最基础的上下文真相。

常见文件：

- `project-brief.md`
  - 项目目标简述

- `boundaries.md`
  - 当前边界、不做什么、范围锁定

### `10-project/docs/tracking`

用途：

- 放项目执行中的跟踪文件。

常见文件：

- `task-index.md`
  - 当前有哪些活跃 ticket / backlog item

- `active-tasks.md`
  - 当前正在干什么

这两个文件特别重要，因为：

- 代码票的 workspace hook 会强制要求它们的更新状态合法
- 如果 runtime 在 `documentation_updates` 里填错了，这里就会直接导致代码票失败

### `10-project/docs/history`

用途：

- 放历史上下文和近期记忆

常见文件：

- `context-baseline.md`
  - 长期稳定背景

- `memory-recent.md`
  - 最近执行事实、近期变化

这个目录也很关键，因为：

- `memory-recent.md` 同样会被代码票 hook 校验

### `10-project/src/`

用途：

- 业务代码目录。
- 真正写出图书馆管理系统代码，应该落在这里。

如果这里只有 `.gitkeep`，说明：

- 代码票还没真正写进去
- 或代码票在写入前就失败了

### `10-project/tests/`

用途：

- 项目级测试目录。
- 真正的实现完成后，测试代码应该落在这里。

---

## `project-workspaces/<workflow-id>/20-evidence`

用途：

- 放交付证据，不放项目源码。
- 这是“证明你做过”的地方。

当前常见子目录：

- `builds/`
- `git/`
- `releases/`
- `reviews/`
- `tests/`

你可以这样理解：

- `builds/`：构建产物、打包产物
- `git/`：commit 记录、git 回执
- `releases/`：发布相关证据
- `reviews/`：评审相关证据
- `tests/`：测试报告、测试证据

当前只有 `.gitkeep` 时，一般表示：

- 代码阶段还没真正开始
- 或还没成功跑到写证据那一步

---

## `artifact_uploads/`

用途：

- 这是 artifact upload 分段上传的 staging 区。
- 主要给中大文件上传链路用。

当前场景里它经常是空的，原因通常有两个：

- 这轮还没走到需要上传中大文件的阶段
- 当前票大多还是治理文档，小文件直接内联提交，不需要 upload session

---

## `developer_inspector/`

用途：

- 这是排查 live runtime 最有价值的调试目录之一。
- 它保存每张 ticket 在 runtime 执行前后，编译器产出的三类关键材料。

子目录一般有：

- `compiled_context_bundle/compile/<ticket-id>.json`
- `compile_manifest/compile/<ticket-id>.json`
- `rendered_execution_payload/compile/<ticket-id>.json`

### `compiled_context_bundle`

用途：

- 保存编译器真正拼出来的上下文块集合
- 你可以看到它到底把哪些 process assets / docs / artifact 带进去了

### `compile_manifest`

用途：

- 保存编译决策摘要
- 重点看：
  - token budget
  - 哪些来源被截断
  - 哪些来源被降级成摘要或 reference

### `rendered_execution_payload`

用途：

- 保存最终喂给 provider 或 deterministic runtime 的执行 payload
- 这是复现 provider 超时、坏响应、上下文过重最直接的材料

你排查“为什么这一票卡住”时，通常会优先看它。

---

## `ticket_context_archives/`

用途：

- 每张已编译 ticket 都会导出一份 markdown 版上下文档案。
- 文件名一般就是 `<ticket-id>.md`。

它和 `developer_inspector/` 的关系是：

- `developer_inspector/` 更偏机器可读 JSON
- `ticket_context_archives/` 更偏人工查阅

适合干什么：

- 快速看某张 ticket 当时到底带了什么上下文
- 不想直接啃大 JSON 时，用它先做人工检查

---

## `failure_snapshots/`

用途：

- 场景超时、stall、max_ticks 或明确失败时，会把现场快照落这里。
- 里面通常是出事那一刻的 workflow/ticket/incident/orchestration 摘要。

如果这里有文件，通常表示：

- 这轮长测已经显式失败过
- 或某次排障前系统自动留了事故现场

当前为空，表示：

- 这轮目录还没留下自动失败快照

---

## 哪些文件最值得先看

如果你只是想快速判断“现在卡哪了”，优先级建议是：

1. `boardroom_os.db`
   - 查真实 workflow / ticket / event 状态

2. `integration-monitor-report.md`
   - 看人工排障过程和结论

3. `developer_inspector/rendered_execution_payload/compile/<ticket-id>.json`
   - 看 provider 实际吃到的 payload

4. `artifacts/reports/governance/<ticket-id>/*.json`
   - 看治理票到底产出了什么

5. `project-workspaces/<workflow-id>/10-project/docs/tracking/*.md`
   - 看项目跟踪文件有没有开始真实更新

6. `project-workspaces/<workflow-id>/10-project/src/`
   - 看代码有没有真正落盘

---

## 当前这轮怎么看“有没有真的写代码”

最直接的判断法：

- 看 `project-workspaces/<workflow-id>/10-project/src/`
- 如果这里只有 `.gitkeep`
  - 说明还没真正写出代码

再补一个判断：

- 看 `20-evidence/tests/`、`20-evidence/git/`
- 如果也还是 `.gitkeep`
  - 说明还没成功跑到代码票提交证据那一步

---

## 一句话总结

这个场景目录本质上就是：

- `boardroom_os.db` 管真相
- `artifacts/` 放结果
- `project-workspaces/` 放项目本体
- `developer_inspector/` 放编译与 provider 调试材料
- `ticket_context_archives/` 放人工可读上下文快照
- `failure_snapshots/` 放失败现场
- `integration-monitor-report.md` 放人工排障记录

如果你只想查“为什么长测没往前走”，先看数据库和 `developer_inspector`。  
如果你只想查“有没有真的写代码”，先看 `10-project/src/` 和 `20-evidence/`。
