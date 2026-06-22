# 04-implementation 索引

## 职责

定义 V2 实施路线、backlog、验收标准、当前阶段计划和 proving scenario。

## 文件清单

| 文件 | 职责 |
|---|---|
| `roadmap.md` | 长期路线 |
| `backlog.md` | 当前任务列表 |
| `acceptance-criteria.md` | V2 总验收标准 |
| `phase-0-plan.md` | 当前文档基座阶段计划 |
| `proving-scenario-tiny-fullstack.md` | 第一个端到端证明场景 |
| `boardroom-os-tiny-fullstack-audit-20260531.md` | V2-080 tiny-fullstack（微型全栈）失败复审报告 |
| `boardroom-os-tiny-fullstack-gptpro-review.md` | V2-080 tiny-fullstack（微型全栈）专家复审与根因分析 |
| `v2-040d-command-runner-spec.md` | V2-040D CommandRunner（命令执行器）同行评审 spec |
| `v2-040e-runtime-executor-spec.md` | V2-040E RuntimeExecutor（运行时执行器）同行评审 spec |
| `v2-050a-evidence-claim-spec.md` | V2-050A EvidenceClaim（证据声明）同行评审 spec |
| `v2-050a1-fallback-policy-registry-spec.md` | V2-050A1 FallbackPolicyRegistry（降级策略注册表）同行评审 spec |
| `v2-050b-evidence-verifier-spec.md` | V2-050B EvidenceVerifier（证据验证器）同行评审 spec |
| `v2-050b-evidence-verifier-implementation-plan.md` | V2-050B EvidenceVerifier（证据验证器）实施计划 |
| `v2-050c-final-evidence-table-spec.md` | V2-050C FinalEvidenceTable（最终证据表）同行评审 spec |
| `v2-050c-final-evidence-table-implementation-plan.md` | V2-050C FinalEvidenceTable（最终证据表）实施计划 |
| `v2-050d-checker-verdict-spec.md` | V2-050D CheckerVerdict（检查结论）同行评审 spec |
| `v2-050d-checker-verdict-implementation-plan.md` | V2-050D CheckerVerdict（检查结论）实施计划 |
| `v2-050e-rework-ticket-generation-spec.md` | V2-050E ReworkTicketGenerator（返工任务生成器）同行评审 spec |
| `v2-050f-completion-gate-spec.md` | V2-050F CompletionGate（完成门禁）同行评审 spec |
| `v2-060a-workspace-manifest-spec.md` | V2-060A WorkspaceManifest（工作区清单）同行评审 spec |
| `v2-060a-workspace-manifest-implementation-plan.md` | V2-060A WorkspaceManifest（工作区清单）实施计划 |
| `v2-060b-package-assembler-spec.md` | V2-060B PackageAssembler（项目包装配器）同行评审 spec |
| `v2-060b-package-assembler-implementation-plan.md` | V2-060B PackageAssembler（项目包装配器）实施计划 |
| `v2-060c-source-inventory-spec.md` | V2-060C SourceInventory（源码清单）同行评审 spec |
| `v2-060c-source-inventory-implementation-plan.md` | V2-060C SourceInventory（源码清单）实施计划 |
| `v2-060d-run-manifest-spec.md` | V2-060D RunManifest（运行清单）同行评审 spec |
| `v2-060d-run-manifest-implementation-plan.md` | V2-060D RunManifest（运行清单）实施计划 |
| `v2-060e-workspace-evidence-export-spec.md` | V2-060E WorkspaceEvidenceExport（工作区证据导出）同行评审 spec |
| `v2-060e-workspace-evidence-export-implementation-plan.md` | V2-060E WorkspaceEvidenceExport（工作区证据导出）实施计划 |
| `v2-060f-agent-asset-import-spec.md` | V2-060F AgentAssetImport（智能体资产导入）同行评审 spec |
| `v2-060f-agent-asset-import-implementation-plan.md` | V2-060F AgentAssetImport（智能体资产导入）实施计划 |
| `v2-070a-closeout-gate-spec.md` | V2-070A CloseoutGate（收尾门禁）同行评审 spec |
| `v2-070b-replay-bundle-spec.md` | V2-070B ReplayBundle（重放包）同行评审 spec |
| `v2-070c-process-audit-spec.md` | V2-070C ProcessAudit（流程审计）同行评审 spec |
| `v2-070d-git-version-audit-spec.md` | V2-070D GitVersionAudit（Git 版本审计）同行评审 spec |
| `v2-070e-closeout-package-spec.md` | V2-070E CloseoutPackage（收尾包）同行评审 spec |
| `v2-070f-closeout-reducer-spec.md` | V2-070F CloseoutReducer（收尾归约器）同行评审 spec |
| `v2-070f-closeout-reducer-implementation-plan.md` | V2-070F CloseoutReducer（收尾归约器）实施计划 |
| `v2-071a-fact-chain-design-spec.md` | V2-071A Fact-chain（事实链）权威源设计与引用命名空间 helper spec |
| `v2-071b-replay-bundle-rereplay-spec.md` | V2-071B ReplayBundle（重放包）re-replay（重新投影）spec |
| `v2-071c-process-audit-fact-chain-spec.md` | V2-071C ProcessAudit（流程审计）fact-chain（事实链）强化 spec |
| `v2-071d-git-audit-hardening-spec.md` | V2-071D GitAuditAdapter（Git 审计适配器）与 GitVersionAudit（Git 版本审计）硬化 spec |
| `v2-071e-closeout-package-boundary-spec.md` | V2-071E CloseoutPackage（收尾包）边界严格化与 payload（载荷）内容绑定 spec |
| `v2-071e-closeout-package-boundary-implementation-plan.md` | V2-071E CloseoutPackage（收尾包）边界严格化与 payload（载荷）内容绑定实施计划 |
| `v2-071f-fact-chain-regression-spec.md` | V2-071F V2-070 fact-chain（事实链）端到端回归与 Phase 7 重锁 spec |
| `v2-080cd-provider-evidence-repair-spec.md` | V2-080C/D ProviderAttempt（模型调用尝试记录）与 EvidenceVerifier（证据验证器）修补 spec |
| `v2-090-tiny-fullstack-blackbox-recovery-plan.md` | V2-090 Tiny Fullstack Blackbox Recovery（微型全栈黑盒整改）计划 |
| `v2-090g-atomic-agent-package-integration-spec.md` | V2-090G atomic-agent（原子智能体）package/import 集成规范 |
| `v2-090g-atomic-agent-package-integration-implementation-plan.md` | V2-090G atomic-agent（原子智能体）package/import 集成实施计划 |
| `v2-090h-atomic-agent-executor-switch-spec.md` | V2-090H atomic-agent（原子智能体）executor switch（执行器切换）规范 |
| `v2-090h-atomic-agent-executor-switch-implementation-plan.md` | V2-090H atomic-agent（原子智能体）executor switch（执行器切换）实施计划 |
| `../../docs/superpowers/specs/2026-06-12-v2-090f-atomic-golden-sample-rebuild-design.md` | V2-090F PRD-to-delivery agent team golden sample（从 PRD 到交付的智能体团队黄金样例）设计规格 |
| `../../docs/superpowers/plans/2026-06-12-v2-090f-atomic-golden-sample-rebuild.md` | V2-090F PRD-to-delivery agent team golden sample（从 PRD 到交付的智能体团队黄金样例）实施计划 |
| `v2-090f-rerun-rework-entry-validation-spec.md` | **HISTORICAL / SUPERSEDED（历史 / 已被取代）**：旧 V2-090F rerun rework-entry validation（重跑返工入口验证）spec，保留为失败形态与边界复盘；不再作为 V2-090F DONE 完成证明入口 |
| `v2-090f-rerun-rework-entry-validation-implementation-plan.md` | **HISTORICAL / SUPERSEDED（历史 / 已被取代）**：旧 V2-090F rerun rework-entry validation（重跑返工入口验证）实施计划；`scripts/run_v2_090f_prd_agent_team.py --stage rework-entry` 与 `v2_090f_rework_entry.py` 已删除 |
| `src/boardroom_os/orchestration/prd_delivery.py` | 当前 V2 PRD delivery（需求交付）原生入口：输入 PRD，运行 PRD intake（需求摄取）→ contracts/ticket graph（合同/工单图）→ execution/evidence/closeout（执行/证据/收尾）→ native rework（原生返工）状态流 |
| `src/boardroom_os/proving/v2_090f_native_golden_sample.py` | 当前 V2-090F native golden sample（原生黄金样例）包装入口：固定 tiny-fullstack PRD 与 V2-090F 配置，委托通用 PRD delivery（需求交付）入口 |
| `../../docs/superpowers/specs/2026-06-12-v2-090k-agent-team-autonomy-remediation-design.md` | V2-090K agent team autonomy remediation（智能体团队自治整改）设计规格 |
| `../../docs/superpowers/plans/2026-06-12-v2-090k-agent-team-autonomy-remediation.md` | V2-090K agent team autonomy remediation（智能体团队自治整改）实施计划 |
| `../../examples/generated-workspaces/tiny-fullstack/30-audit/v2-090k-failure-snapshot/` | V2-090K curated failure snapshot（精选失败快照），作为 V2-100 rework loop（返工循环）真实失败输入 |
| `current-architecture-review-2026-06-13.md` | 当前项目架构评审、配置体系评估、agent team autonomy（智能体团队自治）阻断项与 V2-100 判断 |
| `v2-100-agent-team-rework-loop-spec.md` | V2-100 agent-team rework loop（智能体团队返工循环）工作包 spec：返工模型、事件/reducer、多角色 graph patch review（图补丁审查）、证据重验与 proving scenario |
| `v2-100a-rework-domain-model-implementation-plan.md` | V2-100A Rework domain model（返工领域模型）实施计划：强类型返工对象、verified blocker（已验证阻塞项）投影、V2-090K failure snapshot（失败快照）映射与负例优先测试 |
| `v2-100b-rework-event-taxonomy-reducer-implementation-plan.md` | V2-100B Rework event taxonomy + reducer（返工事件分类与归约器）实施计划：`REWORK_*` 事件、runtime boundary（运行时边界）、GraphPatchReviewGate（图补丁审查门禁）与可回放 ReworkProjection（返工投影） |
| `v2-100c-ceo-rework-planner-boundary-implementation-plan.md` | V2-100C CEO rework planner boundary（CEO 返工规划边界）实施计划：provider-backed CEO ReworkPlan（模型支撑项目经理返工计划）、TicketGraphPatch（工单图补丁）、多角色审查和 reducer commit（归约器提交）边界 |
| `v2-100d-rework-evidence-checker-reintegration-implementation-plan.md` | V2-100D Rework evidence/checker reintegration（返工证据与检查重接入）实施计划：每次 ReworkAttempt（返工尝试）重建 SourceInventory（源码清单）、FinalEvidenceTable（最终证据表）、CheckerVerdict（检查结论）和必要 CloseoutGate（收尾门禁）链路 |
| `v2-100e-multi-round-rework-proving-scenario-implementation-plan.md` | **DEPRECATED / REJECTED（已废弃 / 已否决，不作为实施入口）**：旧 V2-100E Multi-round rework proving scenario（多轮返工证明场景）实施计划，因包含硬编码事实源、过度定制 adapter（适配器）和可重复性风险，仅可作为 rejected design notes（被否设计记录）查阅 |
| `v2-100e-multi-round-rework-proving-scenario-expert-review-plan.md` | V2-100E Multi-round rework proving scenario（多轮返工证明场景）专家评审版实施计划；已实施并完成，保留为 V2-100E 完成证据 |
| `v2-100f-manifest-tolerant-ingestion-rework-entry-spec.md` | V2-100F RunManifest tolerant ingestion and agent-owned blackbox verification（运行清单宽容摄取与智能体拥有的黑盒验证）spec；解决 LLM assertion vocabulary（断言词汇）变化导致 raw crash（原始崩溃）、无法形成 ReworkRequest（返工请求）的问题 |
| `v2-100f-manifest-tolerant-ingestion-rework-entry-implementation-plan.md` | V2-100F native rework orchestration（原生返工编排）重写实施计划；V2-100F-A/B/C/D/E/F 已完成，真实 provider（模型供应商）端到端证明已通过 |

## AI 启动入口

后续任务优先从 `backlog.md` 开始。`backlog.md` 顶部维护 TL;DR、当前任务入口、当前验收入口、工作包规则、子项目依赖图、进度总览和当前重点。顶层 `V2-xxx` 是里程碑，实际实施必须落到 `V2-xxxA` / `V2-xxxB` 这类工作包。

## 推荐阅读顺序

1. `backlog.md`
2. `acceptance-criteria.md`
3. `roadmap.md`
4. `phase-0-plan.md`
5. `proving-scenario-tiny-fullstack.md`

## 更新触发条件

当任务范围、优先级、验收规则、阶段计划或 proving scenario 改变时，必须更新本目录。
