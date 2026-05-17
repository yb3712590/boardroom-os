# V2-030 Phase Audit（Agent Seat + Execution Package Compiler 阶段审计）

## 文档职责

本文件留档 V2-030 工作包 6/6 完成后的阶段性审计结论，专注"是否存在偏离 PRD 导致项目失败的风险"。不替代 `acceptance-criteria.md` 的 checkbox 验收，也不展开 V2-040 实施计划。

- 审计日期：2026-05-18
- 审计范围：V2-030A ~ V2-030F 实际产出 + 与 PRD / `doc/03-architecture/` / `acceptance-criteria.md` 的一致性
- 测试基线：`PYTHONPATH="src;." pytest tests/contracts tests/reducers tests/execution tests/negative -q` 通过（400 passed）

## 核心结论

V2-030 阶段实现紧贴 PRD 与架构边界，**无直接导致项目失败的偏离**。接入链 `RoleProfile（角色模板）-> AgentSeat（智能体席位）-> ModelExecutionProfile（模型执行配置）-> ExecutionPackage（执行包）-> AgentContextSnapshot（上下文快照）` 完整闭合，为 V2-040 ProviderAttempt（模型调用尝试记录）提供了稳定接入点。

存在 3 项需要在 V2-040 / V2-050 严格兑现的"延期承诺"型风险，必须在对应工作包启动时显式跟踪。

## PRD 一致性对照

| PRD 产品目标 / 反目标 | V2-030 产出 | 一致性 |
|---|---|---|
| 目标 4 worker 接收结构化 ExecutionPackage | `execution/package.py` 17 字段 + `compiler.py` 编译器 | 完全闭合 |
| 目标 9 provider / model / effort / fallback 可审计 | `ModelExecutionProfile` + `FallbackPolicy` + `FallbackKind` 枚举 | 类型化表达 |
| 目标 10 process audit 可读 | `AgentContextSnapshot` + `AgentContextIndex` + SHA-256 指纹 | V2-070C 可消费 |
| 反目标"fallback 被当 implementation evidence" | `evaluate_fallback_evidence` 类型化拒绝 + DEC-0014 移除 TEST_ONLY_SIMULATION 例外 | schema 层禁止 |
| 反目标"runtime 越权" | `RoleCategory` 封闭枚举 + `BootstrapGovernanceAuthority` + `SeatLifecycleProjector` | 为 V2-040E role-aware 边界铺路 |

## 接入链闭合度

代码已完整实现 `backlog.md` 第 134–145 行声明的链路：

```text
RoleProfile + SkillBinding + ModelExecutionProfile
  -> AgentSeat（via SeatLifecycleProjector，受 BootstrapGovernanceAuthority 保护）
  -> AgentTeamProjection（via AgentTeamProjector，DEC-0013 单一编排入口）
  -> SeatAssignmentGraph（demand-first 派工）
  -> ExecutionPackage（via ExecutionPackageCompiler）
  -> AgentContextSnapshot（via build_agent_context_snapshot）
  -> [V2-040A 接续 ProviderAttempt]
```

ExecutionPackage 完整覆盖 `execution-and-runtime-boundary.md` 第 42–62 行声明的必备字段（execution_package_id / ticket_ref / graph_version / seat_ref / model_execution_profile / objective / acceptance_refs / source_surface_refs / context_refs / constraints / allowed_read_refs / allowed_write_set / required_outputs / commands / evidence_obligations / fallback_policy_ref / audit_requirements）。

## 风险登记

### 风险 1 [中] AC-V2-EXECUTION-003 延期到 V2-050A1 / V2-050B

- **状态**：V2-030E 只交付 typed evaluator（`execution/fallback.py`），尚无 EvidenceVerifier（证据验证器）实际接线。
- **隐患**：若 V2-050A1 / V2-050B 未严格按 DEC-0014 接线（解析 `fallback_policy_ref` → 调用 `evaluate_fallback_evidence` → 记录 decision → 拒绝 `allowed=False` 或 registry 缺失），`evaluate_fallback_evidence` 将沦为死代码，PRD 反目标"fallback 被当 implementation evidence"重新打开。
- **触发条件**：V2-050A1 / V2-050B 未在 verifier 中调用 evaluator。
- **缓解建议**：进入 V2-040 前在 `backlog.md` 顶部 TL;DR 显式标注此延期项。

### 风险 2 [中] 类型分裂 `ContractId` vs `FallbackPolicyRef`

- **位置**：`agents/profiles.py:132` 中 `ModelExecutionProfile.fallback_policy_ref: ContractId`，但 `execution/package.py:74` 中 `ExecutionPackage.fallback_policy_ref: FallbackPolicyRef`，由 `execution/compiler.py:140` 通过裸字符串复制做类型转换。
- **隐患**：V2-050A1 设计 `FallbackPolicyRegistry`（降级策略注册表）时，权威 ref 类型存在歧义；replay 阶段两个 ref 的 hash / equality 语义不一致可能让 fallback lineage（降级来源链）静默丢失。
- **缓解建议**：V2-050A1 实现时统一为 `FallbackPolicyRef`，或在 `decisions.md` 显式记录分裂理由。

### 风险 3 [低] ExecutionPackage 的 `fallback_policy_ref` 实际等同 ModelExecutionProfile

- **位置**：`compiler.py:140` 直接复制 `model_execution_profile.fallback_policy_ref.value`，无 ticket / contract 层 override 通道。
- **隐患**：未来若 PRD 要求"特定 ticket 类型使用更严格 fallback policy"，需扩展 compiler 输入；V2-030 未为此预留接口。
- **当前不构成偏离**：PRD 未要求 ticket-level override。

### 风险 4 [低] V2-030D 输入边界 — 调用方仍要同时传 5+ 个 projection

- **位置**：`ExecutionPackageCompilerInput`（`compiler.py:60`）需要 caller 提供 `seat_assignment_graph` / `agent_team_projection` / `acceptance_contract` / `package_contract` / `evidence_obligations` / `model_execution_profiles` / `workspace_context`。
- **隐患**：V2-040 / V2-080 调用方可能拼装 graph_version 不一致快照（已有 `_validate_graph_version` 防御 seat_assignment 与 agent_team，但 acceptance / package contract 的版本未交叉校验）。
- **影响有限**：V2-030B 的负例覆盖 graph_version mismatch；contract 版本一致性由 V2-010 合同链门禁兜底。

### 风险 5 [低] DEC-0012 推迟外部 agent assets 到 V2-060F

- V2-030D 不读取外部 skill / prompt / MCP 文件 —— 是 DEC-0012 有意为之的边界。
- **隐患**：V2-080 端到端 proving scenario 必须等 V2-060F 落地后才能验证真实 asset 导入；中间 V2-040 ~ V2-070 都用内存 fixture，可能掩盖 real-world skill asset 风险。
- **当前不构成 V2-030 偏离**：已在 V2-060F 工作包追踪。

## 建议

1. **V2-040A 启动前**：把"AC-V2-EXECUTION-003 必须由 V2-050A1 / V2-050B 闭合"写入 `backlog.md` TL;DR 当前重点段。
2. **V2-050A1 实施时**：在 `FallbackPolicyRegistry` 设计阶段统一 `FallbackPolicyRef` 类型；现有 `ContractId` 复制路径属技术债。
3. **V2-040A 负例测试**：必须包含"ProviderAttempt 携带 fallback marker 但 V2-050 verifier 尚未接线时整体 fail closed"，避免 V2-050 接线前出现静默窗口。
4. **不需要回滚 V2-030 任何工作包**：6/6 工作包与 PRD / 架构主线一致，可作为 Phase 4 稳定底座。

## 关键引用

- 工作包状态：`doc/04-implementation/backlog.md:156`、`doc/04-implementation/backlog.md:408-486`
- 类型分裂：`src/boardroom_os/agents/profiles.py:132`、`src/boardroom_os/execution/package.py:74`、`src/boardroom_os/execution/compiler.py:140`
- 接入链编排入口：`src/boardroom_os/agents/team.py:109`（AgentTeamProjector）
- Fallback 类型化判定：`src/boardroom_os/execution/fallback.py:90`
- AC 延期说明：`doc/04-implementation/acceptance-criteria.md:224`
- DEC-0013 编排入口决策：`doc/05-project-log/decisions.md:197`
- DEC-0014 TEST_ONLY_SIMULATION 决策：`doc/05-project-log/decisions.md:218`
