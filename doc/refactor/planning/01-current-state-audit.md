# 当前状态审计

## 总体判断

第 15 轮 `library_management_autopilot_live_015` 是一次高价值压力审计，但不是一次合格的自治验收。

它证明系统可以暴露真实缺陷、记录大量事件、保留丰富运行材料，并在人工介入后被推到一致 closeout 状态；但它没有证明系统可以无人工 DB/projection/event 介入地从 PRD 自治推进到可信交付物。

## 015 测试结论

### 015 实际证明了什么

- workflow 最终可被记录为 `COMPLETED / closeout`。
- runtime graph 最终可达到 `COMPLETED=59`。
- 系统可以发现真实产品问题，例如前后端 auth contract 不匹配。
- 系统可以暴露 runtime 结构问题，例如 stale gate、cancelled lane、orphan pending、maker-checker 长循环和 closeout artifact refs 误选。
- replay 包包含 DB、事件、投影、artifact、process asset、compile payload 和 ticket context archive，具备很强取证价值。

### 015 没有证明什么

- 没有证明 clean autonomous run。
- 没有证明 closeout 等于真实产品验收。
- 没有证明 frontend 交付物完整可用。
- 没有证明 maker-checker 能可靠挡住 placeholder delivery。
- 没有证明任意时间点可自动重放和恢复。
- 没有证明 provider 失败主要来自上游，而不是本项目 adapter/parser/timeout。

### 关键证据

- 最终 `run_report.json` 的 `completion_mode` 是 `manual_closeout_recovery`。
- 最终 ticket status 仍包含 `FAILED=31`、`TIMED_OUT=21`、`CANCELLED=9`、`PENDING=1`。
- M104 通过手工补入 `TICKET_LEASED`、`TICKET_STARTED`、`TICKET_COMPLETED` 并同步 projection/index 完成 closeout。
- P09 记录 provider 交付占位产物但 maker-checker 仍放行。
- replay 包里存在 baseline frontend placeholder view 和 shallow smoke/checklist evidence。

## 当前目录结构问题

### 文档入口过多

当前 `doc/` 已经有 `README.md`、`mainline-truth.md`、`roadmap-reset.md`、`TODO.md`、`task-backlog/*`、`history/*`、`tests/*`、`new-architecture/*`、`refactor/*`、`archive/*` 等多个入口。

问题不是文档太多，而是 active truth、working reference、test evidence、historical archive 和 future architecture 之间的边界仍需更硬。

### 根目录和子目录文档职责不清

`backend/docs/library-management-scenario-next-session-prompt.md` 是一次性 handoff prompt，包含旧机器绝对路径。它更适合进入 archive，而不是保留为 backend 稳定文档。

### 测试日志兼具证据和流水

`doc/tests/*` 中大量 dated integration logs 是重要审计证据，但不应默认进入普通实现上下文。它们需要作为 verification history 管理，而不是 active design source。

## 产物目录和写目录问题

当前系统已有 `00-boardroom / 10-project / 20-evidence` 的雏形，但规则不够硬：

- worker 写入面与角色名耦合。
- provider fallback 可能生成默认 source/test evidence。
- closeout final artifact refs 曾混入非交付文档。
- placeholder source 和 shallow evidence 曾通过 maker-checker。
- runtime、workspace、evidence、archive 的边界需要契约化。

## Actor / Role / Employee 问题

当前实现仍存在角色模板承担执行键职责的倾向。重构后应该采用：

```text
Actor / Employee -> RoleTemplate -> CapabilitySet -> WriteSurface / ExecutionContract
```

runtime kernel 不应判断 `frontend_engineer_primary`、`backend_engineer_primary` 或 `checker_primary`；它只应判断 capability 是否满足 ticket contract。

需要重点解决：

- role template 与 capability 解耦。
- employee enable/disable/suspend/deactivate/replace 状态机。
- excluded employee 的作用域。
- worker pool 为空时不能 silent stall。
- 同一 actor 的 lease、retry、late heartbeat 不应污染 current graph pointer。

## Provider 问题

015 中 provider failure count 极高：first token timeout、upstream unavailable、stream read error、empty assistant、malformed SSE、schema validation retry 等反复出现。

用户观察到同一 API 在其他 AI 编程框架中 streaming 表现正常。因此本项目应默认怀疑以下内部问题，直到被独立 smoke test 排除：

- streaming parser 不健壮；
- timeout 语义混淆；
- total deadline 与 stream idle 预算不合理；
- retry / replacement 与 ticket lease 竞争；
- late provider heartbeat 可见性污染 projection；
- schema validation retry 被误归类为 provider 抽风。

## Runtime 过度耦合问题

当前 delivery 合法性横跨多个模块：

- reducer；
- projection；
- runtime；
- ticket handler；
- approval handler；
- closeout gate；
- workflow autopilot；
- live harness。

这导致系统经常出现“一个门放行，另一个门卡住”的行为。

重构目标是抽出：

```text
DeliveryPolicy / DeliverableContract / CloseoutPolicy / ProgressionPolicy
```

并让它们以同一份 graph/assets/incidents snapshot 计算合法动作。

## Archive-first 候选

| 路径 | 处理建议 | 原因 |
|---|---|---|
| `backend/docs/library-management-scenario-next-session-prompt.md` | 移入 `doc/archive/session-prompts/` | 一次性 handoff，包含旧绝对路径 |
| `doc/tests/intergration-test-*` | 保留为 verification history | 是审计证据，不默认读 |
| `doc/task-backlog/done.md` | 保留或归档索引引用 | 历史任务卡片 |
| `doc/todo/completed-capabilities.md` | 保留或归档索引引用 | 历史能力清单 |
| `doc/history/archive/*` | 保留 archive | 历史 memory/log |
| tracked cache/log/db/artifacts | 若存在则删除 | 生成物不应入库 |

## 暂不删除的内容

- `doc/new-architecture/*`：目标架构 canon。
- `doc/archive/specs/feature-spec.md`：历史愿景来源。
- `doc/tests/intergration-test-015-20260429.md`：015 详细审计证据。
- `doc/tests/intergration-test-015-20260429-final.md`：015 精简结论。
- backend/frontend runtime source：本轮不做行为重构。

## 审计结论

当前项目不是底层不可救的屎山；事件源、ticket、projection、artifact、process asset 和 compiled execution package 是值得保留的基础。

但上层 runtime 已经出现屎山化征兆：delivery 特例、角色硬编码、provider 恢复补洞、closeout gate、projection 修补和 live harness 互相缠绕。

本轮重构应先建立硬边界和可验收计划，再进入行为代码拆分。
