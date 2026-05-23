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

