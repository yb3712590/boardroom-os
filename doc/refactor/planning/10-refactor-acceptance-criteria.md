# 重构验收标准

## 总验收

- [ ] 无人工 DB/projection/event 注入完成 replay/resume。
- [ ] 无 placeholder source/evidence 能通过 deliverable closeout。
- [ ] Provider streaming smoke 在同一 API 配置下达到外部 AI 编程框架同级稳定性。
- [ ] Runtime kernel 不硬编码 CEO、员工、角色模板或业务 milestone。
- [ ] Closeout 证明 PRD acceptance，而不是只证明 graph terminal。
- [ ] 文档视图可从 event/process asset 重新物化。

## Phase 0：文档与边界冻结

- [x] 12 份重构规划文档已写入 `doc/refactor/planning/`。
- [x] 新规划索引 `INDEX.md` 已建立。
- [x] `doc/README.md` 已加入新规划入口。
- [x] 一次性 handoff 文档已安全归档。
- [x] 旧 `frontend/` 源码树已删除。
- [x] 旧设计、路线、任务 backlog、历史记忆和 001-014 integration logs 已集中归档。
- [x] `doc/` active 入口只保留当前真相、重构控制面、后端参考和必要 015 证据。
- [x] Phase 0 未修改 provider、scheduler、ticket handler、workflow controller 或 `backend/app/core` runtime 行为。
- [x] Round 4 backend cleanup 已删除无生产/测试引用的旧 project-init architecture helper，并同步 frozen boundary truth。
- [x] Round 4 未拆 provider、progression、actor 或核心 runtime 大模块。

## Phase 1：目录 / 产物 / 写权限 contract

- [x] 仓库根目录已清理为 backend-only runtime rebuild 基线。

- [ ] 每种 artifact ref 都有合法路径映射。
- [ ] write-set policy 以 capability 为主键。
- [ ] 角色模板不直接决定 write root。
- [ ] closeout final refs 只接受合法 delivery evidence。
- [ ] placeholder source/test fallback 被阻断。
- [ ] 目录契约有单测或 contract test。

## Phase 2：Provider adapter 与 streaming soak

- [ ] Provider adapter 输出标准 `ProviderEvent`。
- [ ] first-token timeout、stream-idle timeout、request-total timeout、ticket lease timeout 被区分。
- [ ] malformed SSE 有 raw archive 和 retryable 分类。
- [ ] empty assistant text 被分类为 provider bad response。
- [ ] schema validation failure 不被归为 upstream unavailable。
- [ ] 同一 API 配置连续 20 次 streaming smoke 成功率 >= 95%。
- [ ] late provider event 不覆盖 current graph pointer。

## Phase 3：Actor / Role lifecycle

- [ ] Actor registry 有 enable/suspend/deactivate/replace 状态机。
- [ ] RoleTemplate 只映射 capability，不作为 runtime 执行键。
- [ ] Assignment 与 Lease 分离。
- [ ] `excluded_employee_ids` 有作用域，不会继承污染。
- [ ] no eligible actor 产生显式 action 或 incident。
- [ ] provider preferred/actual 记录完整。

## Phase 4：Progression policy engine

- [ ] `decide_next_actions(snapshot, policy)` 可独立测试。
- [ ] CREATE_TICKET / WAIT / REWORK / CLOSEOUT / INCIDENT / NO_ACTION 都有 reason code。
- [ ] Effective graph pointer 不受 orphan pending 干扰。
- [ ] CANCELLED/SUPERSEDED 节点不参与 effective edges。
- [ ] substring hint 不再驱动会议/架构 gate。
- [ ] hardcoded backlog milestone fanout 被 policy/graph patch 替代。

## Phase 5：Deliverable contract

- [ ] PRD acceptance criteria 可编译成 `DeliverableContract`。
- [ ] Required source surfaces 有路径、capability、evidence 映射。
- [ ] Evidence pack 能映射到 acceptance criteria。
- [ ] `APPROVED_WITH_NOTES` 不放行 blocking contract gap。
- [ ] closeout package 包含 contract version 和 final evidence table。
- [ ] superseded/placeholder evidence 不进入 final evidence set。

## Phase 6：Replay / resume / checkpoint

- [ ] 支持 resume from event id。
- [ ] 支持 resume from graph version。
- [ ] 支持 resume from ticket id。
- [ ] 支持 resume from incident id。
- [ ] projection checkpoint 避免每次全量 JSON replay。
- [ ] replay 后 doc/materialized view hash 可验证。
- [ ] 不需要人工补写 projection/index。

## Phase 7：015 replay 包验证

- [ ] 能导入 015 replay DB/artifacts。
- [ ] 能定位并重放关键 provider failure。
- [ ] 能重放 BR-032 auth contract mismatch。
- [ ] 能阻断 BR-040/BR-041 placeholder delivery。
- [ ] 能处理 orphan pending 不阻断 graph complete。
- [ ] 能生成 closeout 但必须满足 deliverable contract。
- [ ] 输出新的 replay audit report。

## Phase 8：新 live scenario clean run

- [ ] provider soak 前置通过。
- [ ] 新 live scenario 不需要人工 DB/projection 介入。
- [ ] 所有 source delivery 有非 placeholder source inventory。
- [ ] 所有关键 acceptance 有 evidence refs。
- [ ] final closeout package 合法。
- [ ] 可从中间 checkpoint resume。
- [ ] 最终报告区分 provider noise、runtime bug、product defect。
