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

## Round 11A replay import 记录（2026-05-04）

Round 11A 只验证 015 replay DB/artifacts/logs 可以无人工 DB/projection/event 注入导入到新目标库，并生成稳定 `ReplayImportManifest`；本轮没有判断 provider、BR-032、BR-040/BR-041、graph/progression 或 closeout 是否通过。

### 输入与 manifest

- Source DB：`D:/Projects/boardroom-os-replay/library_management_autopilot_live_015_full_replay_20260430/backend/data/scenarios/library_management_autopilot_live_015/boardroom_os.db`
- Artifact root：`D:/Projects/boardroom-os-replay/library_management_autopilot_live_015_full_replay_20260430/backend/data/scenarios/library_management_autopilot_live_015/artifacts`
- Log refs：`run_report.json`、`audit-summary.md`、`integration-monitor-report.md`
- Manifest：`D:/Projects/boardroom-os/.pytest-tmp/replay-import-015/replay-import-manifest.json`
- Manifest hash：`8438fb6aed8e2daa32e90fd19ed171cb1691f06ebe5f0194e20f9e33ccda9d53`
- Idempotency key：`replay-import:3a209b15acc022ff85a35f27efa4f5857f3151d51aaaf391dd7408cf866332b8`

### 导入事实

- Status：`READY`
- Event range：`1..15801`
- Event count：`15801`
- Target DB event count：`15801`
- Artifact index：`362` rows；其中 `LOCAL_FILE=361`、`INLINE_DB=1`
- Target DB artifact index：`362` rows
- Process asset index：`393` rows
- Schema：app `2026-03-28.boardroom.v1`，SQLite `user_version=0`，`schema_version=145`
- DB sha256：`4094836432b17030d21f0d0b1fbf7c19c935940f9912e288fc9079a748610fcf`
- Artifact tree sha256：`336d1ab44e01e1ae77a516b577bb3072a30660bb41441d7607d8b0aca7358061`
- Registered artifact tree sha256：`ea5cbd11ab7aa49e4bf6f155ba882d2f5edddf59b42a217844a4ed7a8296410f`
- Event log hash：`56a621cc7f57e5879cc76d89eb5e74eff44d9522306a57292d7ac83804fe7320`
- Artifact index hash：`d220f1d58db2623c268a1116fee63c08b1414b044c462ba4617b807f6fc8908f`

### 导入诊断

- `artifact_tree_noise_detected`：`26851` 个 AppleDouble / `PaxHeader` archive metadata 文件；归类为 `replay/import issue`，不是 runtime bug。
- `unregistered_artifact_files_detected`：`11594` 个 artifact root 下未登记文件；导入记录但不作为业务验证依据。
- `mutable_storage_relpath_detected`：`10` 个同一 `storage_relpath` 被多个 artifact rows 复用的 workspace 文件；artifact root 中保留最新 bytes，旧 row 由 DB hash 和 artifact index hash 覆盖。
- `inline_db_artifact_recorded`：`art://runtime/tkt_7a888035b4ff/delivery-closeout-package.json` 无 artifact root storage；内容由 DB hash 覆盖。
- `source_projection_mismatch`：`workflow_projection`、`ticket_projection`、`runtime_node_projection`、`execution_attempt_projection`、`process_asset_index` 与 reducer 重建 hash 不一致；导入目标库使用 event reducer 重建 projection，不复制 source projection rows，也不调用 projection repair。

### 11B 依赖

Round 11B Provider failure replay 必须从 11A manifest 继承 event range、DB/artifact/log hash、artifact refs、`INLINE_DB` closeout artifact 诊断、projection mismatch 诊断和 mutable storage relpath 诊断。11B 不得把这些 import diagnostics 归类为 provider/runtime/product/contract issue。

## Round 11B provider failure replay 记录（2026-05-04）

Round 11B 继承 11A import manifest 和 `D:/Projects/boardroom-os/.pytest-tmp/replay-import-015/replay-import.db`，新增只读 provider replay harness。真实 015 case 可定位并可重放，但不能证明 malformed SSE raw archive contract 通过；旧 replay 数据缺少 `raw_archive_ref`，因此 case result 必须 fail-closed 并归类为 `replay/import issue`。

### ReplayCaseResult

- Case id：`provider-failure-015-malformed-sse`
- Source manifest hash：`8438fb6aed8e2daa32e90fd19ed171cb1691f06ebe5f0194e20f9e33ccda9d53`
- Event range：`9969..10016`
- Source ticket context：旧票 `tkt_30c7a10979ae` 在 `9967 TICKET_FAILED` 后出现 late provider events；失败票 `tkt_0c616378c9ac` 在 `9996 TICKET_FAILED` 终止；恢复票 `tkt_2b58304dccb9` 在 `10016 TICKET_COMPLETED` 完成。
- Attempt refs：`attempt:wf_7f2902f3c8c6:tkt_0c616378c9ac:prov_openai_compat_truerealbill:1`，事件 `9973 PROVIDER_ATTEMPT_STARTED` / `9995 PROVIDER_ATTEMPT_FINISHED`，terminal state `FAILED_TERMINAL`。
- Provider failure kind：`PROVIDER_BAD_RESPONSE`。失败正文显示 malformed SSE，但旧 taxonomy 没有记录为 `MALFORMED_STREAM_EVENT`。
- Raw archive refs：空。diagnostic 为 `provider_raw_archive_ref_missing`，缺失 ref 为 `raw_archive_ref`。
- Provider provenance：`preferred_provider_id=prov_openai_compat_truerealbill`、`actual_provider_id=prov_openai_compat_truerealbill`、`preferred_model=gpt-5.5`、`actual_model=gpt-5.5`，来自 ticket failure detail 和 provider attempt event。
- Retry/recovery outcome：`retried_and_completed`，`10007 TICKET_RETRY_SCHEDULED` 指向 `tkt_2b58304dccb9`，`10009 INCIDENT_RECOVERY_STARTED` 使用 `RESTORE_AND_RETRY_LATEST_FAILURE`，`10016 TICKET_COMPLETED` 完成恢复票。
- Policy boundary：replay harness 只记录结构化 `failure_kind`、`failure_detail`、ticket terminal event、incident/followup event；`raw_transcript_used=false`、`late_output_body_used=false`、`timestamp_pointer_guess_used=false`。
- Late guard：case range 内 old ticket late provider events 保留在旧 attempt lineage，current pointer source 为 `case_range_terminal_events`，current ticket 为 `tkt_2b58304dccb9`；没有用最终 source projection 或时间戳猜 pointer。

### 11C 依赖

Round 11C 必须继承 11B 的边界：provider raw transcript、malformed raw archive、late output 正文和 artifact/markdown 正文不得驱动 contract gap、rework、restore 或 closeout。BR-032、BR-040、BR-041 的 contract gap replay 只能消费结构化 event、ticket context、artifact/evidence legality 和 deliverable contract facts。

## Round 11C contract gap replay 记录（2026-05-05）

Round 11C 继承 11A import manifest 和 11B provider 边界，新增只读 contract gap replay harness。Harness 只读取 imported DB 的 `events`、`artifact_index` 和 `process_asset_index`，不读取 provider raw transcript、late output body、artifact markdown/source body、source projection，也不修改 replay DB/projection/event。

### ReplayCaseResult

- BR-032：case id `contract-gap-015-br032-auth-mismatch`，event range `5855..6299`，source manifest hash `8438fb6aed8e2daa32e90fd19ed171cb1691f06ebe5f0194e20f9e33ccda9d53`，case result path `D:/Projects/boardroom-os/.pytest-tmp/replay-contract-gap-015/br032.json`。
- BR-032 contract finding：checker report `art://runtime/tkt_bc0404503ec8/delivery-check-report.json` 记录 `BR032-F06`，replay 编译为 blocking `acceptance_missing_required_evidence`，缺 `api_contract_test`，surface 为 `surface.br032.frontend_auth_contract`。
- BR-032 outcome：`APPROVED_WITH_NOTES` 触发 `convergence_policy_required`，不能放行 blocker；policy proposal 为 `progression.rework.deliverable_contract_gap`，rework target 指向 `tkt_c247833b2c60` / `node_backlog_followup_br_031_m3_frontend_auth_nav`，不是 checker、graph terminal 或 closeout。
- BR-040：case id `contract-gap-015-br040-placeholder-delivery`，event range `11400..11464`，case result path `D:/Projects/boardroom-os/.pytest-tmp/replay-contract-gap-015/br040.json`。
- BR-040 evidence refs：`art://workspace/tkt_2252a7a1f92e/source.py`、`art://workspace/tkt_2252a7a1f92e/test-report.json`、`pa://source-code-delivery/tkt_2252a7a1f92e@1`、`pa://evidence-pack/tkt_2252a7a1f92e@1`；generic command 为 `pytest tests -q`，一条 `1 passed` 不能作为业务断言。
- BR-040 outcome：placeholder source/test 被 `invalid_evidence_for_contract` 和 `acceptance_missing_required_evidence` 阻断；`APPROVED_WITH_NOTES` 不能覆盖 blocker；rework target 指向 `tkt_2252a7a1f92e` / `node_backlog_followup_br_040_m4_catalog_search_availability`。
- BR-041：case id `contract-gap-015-br041-placeholder-delivery`，event range `9933..10016`，case result path `D:/Projects/boardroom-os/.pytest-tmp/replay-contract-gap-015/br041.json`。
- BR-041 evidence refs：`art://workspace/tkt_5707c310bc6d/source.py`、`art://workspace/tkt_5707c310bc6d/test-report.json`、`pa://source-code-delivery/tkt_5707c310bc6d@1`、`pa://evidence-pack/tkt_5707c310bc6d@1`；generic command 为 `pytest tests -q`，一条 `1 passed` 不能作为业务断言。
- BR-041 outcome：placeholder source/test 被 `invalid_evidence_for_contract` 和 `acceptance_missing_required_evidence` 阻断；`APPROVED_WITH_NOTES` 不能覆盖 blocker；rework target 指向 `tkt_5707c310bc6d` / `node_backlog_followup_br_041_m4_isbn_remove_inventory`。
- 共同边界：三条 case 都记录 `raw_transcript_used=false`、`late_output_body_used=false`、`timestamp_pointer_guess_used=false`、`graph_terminal_override_used=false`，issue classification 为 `contract gap replay evidence`。

### 11D 依赖

Round 11D 必须继承 11A manifest、11B provider 边界和 11C contract gap case results。下一步只进入 Graph / progression replay，验证 orphan pending、stale pointer 和 effective edge；不得开始 closeout final evidence 或 audit report 收口。

## Round 11D graph/progression replay 记录（2026-05-05）

Round 11D 继承 11A import manifest、11B provider replay 边界和 11C contract gap case results，新增只读 graph/progression replay harness。Harness 只读取 imported DB 的 `events`，用结构化 `ProgressionSnapshot` 重放 graph pointer、effective edges、readiness、graph complete 和 policy proposal；不读取 source projection，不修改 replay DB/projection/event，也不开始 closeout final evidence 或 audit report 收口。

### ReplayCaseResult

- Orphan pending：case id `graph-progression-015-orphan-pending-br060`，event range `11791..11903`，source manifest hash `8438fb6aed8e2daa32e90fd19ed171cb1691f06ebe5f0194e20f9e33ccda9d53`，case result path `D:/Projects/boardroom-os/.pytest-tmp/replay-graph-progression-015/orphan-pending.json`。
- Orphan pending outcome：`tkt_262f159fc931` 被记录为 stale/orphan pending，不进入 ready/current/effective graph complete；current pointer 保持 `tkt_5d8e536a14c2` 和 review `tkt_665d647e556a`；`graph_complete=true`；policy proposal 为 `NO_ACTION`，reason code `progression.stale_orphan_pending_ignored`，source graph version `gv_11903`，affected refs `["tkt_262f159fc931"]`。
- CANCELLED/SUPERSEDED：case id `graph-progression-015-superseded-cancelled-br032`，event range `5960..6299`，case result path `D:/Projects/boardroom-os/.pytest-tmp/replay-graph-progression-015/cancelled-superseded.json`。
- CANCELLED/SUPERSEDED outcome：`tkt_ade5951f10ec`、`tkt_2262491ff9ae`、`tkt_e2b36aef19e9` 保留为 inactive lineage，不进入 effective edges、readiness、completed/current refs 或 graph complete 判断；current pointer 保持 `tkt_c247833b2c60`、`tkt_f00a95436db3`、`tkt_2e4ac9dd357e`、`tkt_1b2b27220047`；policy proposal reason code 为 `progression.graph_complete_no_closeout_in_8b`，source graph version `gv_6299`。
- Late provider pointer：case id `graph-progression-015-late-provider-current-pointer-br041`，event range `9969..10016`，case result path `D:/Projects/boardroom-os/.pytest-tmp/replay-graph-progression-015/late-provider-pointer.json`。
- Late provider pointer outcome：old ticket `tkt_30c7a10979ae` 的 late provider events 只保留 lineage；current pointer 保持恢复票 `tkt_2b58304dccb9`；`raw_transcript_used=false`、`late_output_body_used=false`、`timestamp_pointer_guess_used=false`；policy source graph version `gv_10016`。
- Missing explicit pointer：case id `graph-progression-015-missing-explicit-pointer`，event range `11791..11903`，case result path `D:/Projects/boardroom-os/.pytest-tmp/replay-graph-progression-015/missing-explicit-pointer.json`。
- Missing explicit pointer outcome：删除 explicit runtime pointer 后不会按 `updated_at` 猜 current；graph diagnostics 记录 `graph.current_pointer.missing_explicit`；policy proposal 为 `INCIDENT`，reason code `progression.incident.graph_reduction_issue`，source graph version `gv_11903`，affected refs `["node_backlog_followup_br_060_m6_circulation_transactions"]`。
- 共同边界：四条 case 均为 `READY`，issue classification 为 `graph progression replay evidence`，policy metadata 都带 reason code、idempotency key、source graph version 和 affected node refs；timestamp pointer guess 均为 `false`。

### 11E 依赖

Round 11E 必须继承 11A–11D case results，再进入 closeout replay 与 audit report。11E 需要验证 closeout package 必须经过 deliverable contract evaluation 和 final evidence table，并汇总 provider/runtime/product/contract/replay issue；不得重新设计 11A–11D 已验证的 import、provider、contract gap 或 graph/progression 语义。

## Round 11E closeout replay 与 audit report 记录（2026-05-05）

Round 11E 继承 11A import manifest、11B provider failure result、11C contract gap results 和 11D graph/progression results，新增只读 closeout replay harness 与 replay audit report。Harness 只读取 imported DB 的 `events`，用现有 closeout contract compiler 验证最终 closeout payload；不修改 replay DB/projection/event，也不做 manual closeout recovery 或 projection repair。

### Closeout ReplayCaseResult

- Case id：`closeout-015-manual-m103-contract-gate`，event range `15778..15801`，case result path `D:/Projects/boardroom-os/.pytest-tmp/replay-closeout-015/closeout.json`。
- `tkt_4624a870959f` 在 `TICKET_FAILED` 中拒绝 `art://project-workspace/wf_7f2902f3c8c6/10-project/ARCHITECTURE.md`，证明 governance-only doc 不能作为 final closeout evidence 单独放行。
- `tkt_737cd07e76e5` 在 `TICKET_FAILED` 中拒绝 `art://runtime/tkt_f58cc1d4ab7b/backlog_recommendation.json`，证明 backlog recommendation-only ref 不能作为 final closeout evidence 单独放行。
- `tkt_7a888035b4ff` 是最终 manual M103 closeout，`TICKET_COMPLETED` 但 payload 缺 `deliverable_contract_version`、`deliverable_contract_id`、`evaluation_fingerprint` 和 `final_evidence_table`。
- Closeout contract summary：`status=BLOCKED`，reason `closeout_missing_final_evidence_table`，compiled final evidence table row count `2`，submitted row count `0`。
- Bypass guard：`manual_closeout_recovery_bypassed_contract=false`、`graph_terminal_override_used=false`、`checker_verdict_only_allowed=false`、`failed_delivery_report_only_allowed=false`、`governance_docs_only_allowed=false`。
- Final evidence table summary：`illegal_statuses_present=[]`、`forbidden_ref_kinds_present=[]`；superseded、placeholder、archive、unknown、stale old attempt、governance-only docs 和 backlog recommendation-only refs 没有进入最终表。
- Disposition：`legacy_manual_closeout_rejected`，status `FAILED`，classification `replay/import issue`。这证明旧 015 closeout 不能满足 Phase 5 contract closeout，不是 contract closeout 通过证据。

### Replay Audit Report

- Report path：`D:/Projects/boardroom-os/.pytest-tmp/replay-audit-015/replay-audit-report.json`
- Report version：`replay-audit-report.v1`
- Report hash：`42765a88f830a1c3b03a489b10816089a9cdb69f3e1b1dfc07b8a227a7ebe8ec`
- Source manifest hash：`8438fb6aed8e2daa32e90fd19ed171cb1691f06ebe5f0194e20f9e33ccda9d53`
- Checkpoint hashes：DB `4094836432b17030d21f0d0b1fbf7c19c935940f9912e288fc9079a748610fcf`，event log `56a621cc7f57e5879cc76d89eb5e74eff44d9522306a57292d7ac83804fe7320`，artifact index `d220f1d58db2623c268a1116fee63c08b1414b044c462ba4617b807f6fc8908f`。
- Issue taxonomy 固定为 `provider failure`、`runtime bug`、`product defect`、`contract gap`、`replay/import issue`。
- Provider case disposition：`provider-failure-015-malformed-sse` 属于 provider failure domain，但 `issue_type=replay/import issue`，因为旧数据缺 raw archive ref 且 taxonomy 为 `PROVIDER_BAD_RESPONSE`。
- Contract gap dispositions：BR-032、BR-040、BR-041 均为 `issue_type=contract gap`，status `READY`。
- Runtime graph dispositions：orphan pending、CANCELLED/SUPERSEDED、late provider pointer、missing explicit pointer 均为 `issue_type=runtime bug` domain replay evidence，status `READY`。
- Closeout disposition：`closeout-015-manual-m103-contract-gate` 属于 contract closeout domain，但 `issue_type=replay/import issue`，status `FAILED`，disposition `legacy_manual_closeout_rejected`。

### Phase 7 状态

- `015 import`：`READY`。
- `provider failure`：`FAILED`，旧 replay 缺 raw archive，checkbox 不勾。
- `BR-032`：`READY`。
- `BR-040/BR-041`：`READY`。
- `orphan pending`：`READY`。
- `contract closeout`：`FAILED`，旧 manual M103 closeout 缺 contract fields/final table，checkbox 不勾。
- `audit report`：`READY`，可勾选。

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

## Round 3 实际清理记录（2026-05-01）

本轮完成仓库瘦身与目录重组，范围限定为文档、旧前端源码和生成物清理；没有修改 provider、scheduler、ticket handler、workflow controller 或 `backend/app/core` runtime 行为代码。

### 删除

| 路径 | 处理 | 原因 |
|---|---|---|
| `frontend/` | 删除 | 当前重构先跑通后端自治 runtime，旧浏览器界面不再作为 active source |
| untracked `frontend/node_modules`、`frontend/dist` | 随目录删除 | 本地依赖/构建产物，不进入新基线 |

### 归档

| 原路径 | 新路径 | 原因 |
|---|---|---|
| `doc/refactor/new-architecture-*.md` | `doc/archive/refactor-legacy/` | 旧新架构实施计划、模板和提示词，不再作为当前 refactor 入口 |
| `doc/tests/intergration-test-001..014*` 及 remediation/audit 文档 | `doc/archive/integration-logs/` | verification history，不默认进入实现上下文 |
| `backend/library-mgmt-prd.md`、`backend/library_management_autopilot_live_013.toml`、`backend/library_management_autopilot_live_015.toml` | `doc/archive/integration-logs/backend-live-configs/` | 旧图书馆 live PRD/config 含旧界面交付要求，当前不再作为 active backend 根目录 fixture |
| `doc/design/` | `doc/archive/design/` | 旧 UI/设计材料，不再作为 active truth |
| `doc/roadmap-reset*`、`doc/milestone-timeline.md` | `doc/archive/roadmap/` | 旧路线材料，当前由 refactor planning 控制面替代 |
| `doc/TODO.md`、`doc/task-backlog*` | `doc/archive/task-backlog/` | 旧任务流水，不再作为当前任务入口 |
| `doc/history/` | `doc/archive/history/` | 旧工作记忆和详细历史，不默认进入上下文 |
| `doc/todo/` | `doc/archive/todo/` | 旧能力清单，只作历史追溯 |
| `dev-prompts.md` | `doc/archive/session-prompts/dev-prompts-legacy.md` | 旧多客户端开发提示词包含已删除 frontend 流程 |

### 保留

- `doc/README.md`、`doc/mainline-truth.md`、`doc/backend-runtime-guide.md`、`doc/api-reference.md`。
- `doc/refactor/planning/**` 与 `doc/refactor/README.md`。
- `doc/new-architecture/**`。
- `doc/archive/specs/feature-spec.md`。
- `doc/tests/intergration-test-015-20260429.md` 与 `doc/tests/intergration-test-015-20260429-final.md`。

## Round 4 backend cleanup 审计记录（2026-05-01）

本轮只审计 `backend/app/core` 和 `backend/tests`，删除明确废弃、无生产引用、无当前测试引用、非审计证据、非未来目标架构必要入口的 backend surface；未拆 `ticket_handlers.py`、`runtime.py`、`workflow_controller.py`，也未启动 provider、progression 或 actor 重构。

### 当前树快照

`backend/app/core` 当前仍保留事件、ticket、projection、artifact、runtime、provider、governance、workspace、worker frozen helpers 和审计 truth 模块；`backend/tests` 当前仍保留普通 pytest、`live/` provider/live harness、`scenario/` library management staged scenario 三类测试树。

### 删除

| 路径 | 处理 | 验证依据 |
|---|---|---|
| `backend/app/core/project_init_architecture_tickets.py` | 删除 | 无生产导入、无当前测试导入；旧 project-init architecture 预置插票 helper 已被 `workflow_progression` / `project_init_governance` / CEO kickoff 路径取代 |

### 同步事实表 / 测试

| 路径 | 处理 | 原因 |
|---|---|---|
| `doc/mainline-truth.md` | 更新 frozen boundary 表 | 人类入口同步当前事实：worker-admin / worker-runtime 是 unmounted frozen material，不是 mounted compatibility surface |
| `backend/app/core/mainline_truth.py` | 更新 frozen boundary | 当前 API registry 不再挂载 `worker-admin` / `worker-runtime` HTTP surface，root CLI 兼容入口也不存在；冻结实现仍留在 `_frozen` 与 token/scope/schema helper 中 |
| `backend/tests/test_mainline_truth.py` | 更新断言 | 回归当前事实：worker surfaces 是 `FROZEN_UNMOUNTED`，不是 mounted compatibility surface |

### 保留 / 不删

| 路径 | 处理 | 原因 |
|---|---|---|
| `backend/app/core/board_riddle_drill.py`、`backend/tests/test_board_riddle_drill.py` | 保留 | 看起来是旧 scenario-only helper，但仍有当前测试引用；不满足“无当前测试引用”删除条件 |
| `backend/app/core/worker_admin.py`、`backend/app/core/worker_runtime.py` | 保留 | 无生产导入，但被 `mainline_truth` 作为冻结壳审计锚点测试；不作为 mounted API 入口 |
| `backend/app/_frozen/worker_admin/**`、`backend/app/_frozen/worker_runtime/**` | 保留 | 冻结实现仍是审计/迁移材料；本轮不做成组退休 |
| `backend/app/core/api_surface.py` | 保留 | route-family truth 的审计支持，仍被测试使用 |
| `backend/app/core/governance_templates.py` | 保留 | `projections.py` 仍生产引用 workforce role templates catalog |
| `backend/app/core/streaming.py` | 保留 | `api/events.py` 生产引用事件流 |
| `backend/app/core/ticket_handlers.py`、`backend/app/core/runtime.py`、`backend/app/core/workflow_controller.py` | 保留，只记录拆分建议 | 当前核心大模块；后续应按 policy/contract 边界拆，不在 cleanup 轮顺手拆 |

## 审计结论

当前项目不是底层不可救的屎山；事件源、ticket、projection、artifact、process asset 和 compiled execution package 是值得保留的基础。

但上层 runtime 已经出现屎山化征兆：delivery 特例、角色硬编码、provider 恢复补洞、closeout gate、projection 修补和 live harness 互相缠绕。

本轮重构应先建立硬边界和可验收计划，再进入行为代码拆分。
