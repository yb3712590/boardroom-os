# 写入面策略

## 核心原则

写入权限以 capability 为主键，而不是以具体角色名为主键。

错误示例：

```text
if role_profile_ref == "implementation_worker_primary":
    allow 10-project/src/app/**
```

目标示例：

```text
actor -> role template -> capability set -> write surface policy
```

runtime kernel 只判断 actor 是否具备 ticket contract 要求的 capability，不判断该 actor 是不是 implementation worker、backend engineer 或 checker。

## 核心对象

```text
Actor / Employee
  -> RoleTemplate
  -> CapabilitySet
  -> WriteSurfaceGrant
  -> CompiledExecutionPackage.allowed_write_set
```

## Capability 分类

| Capability | 说明 |
|---|---|
| `source.modify.backend` | 修改 backend source |
| `source.modify.application` | 修改交付项目 application source |
| `source.modify.database` | 修改 schema/migration/seed |
| `source.modify.platform` | 修改 platform/deploy/runtime scripts |
| `test.run.backend` | 运行并登记 backend 测试证据 |
| `test.run.application` | 运行并登记交付项目测试证据 |
| `evidence.write.test` | 写测试证据 |
| `evidence.write.git` | 写 git closeout evidence |
| `evidence.check.delivery` | 写 delivery check report |
| `verdict.write.maker_checker` | 写 maker-checker verdict |
| `docs.update.delivery` | 更新交付文档 |
| `policy.propose.graph_patch` | 提议 graph patch |
| `runtime.state.write` | 写 runtime event/projection 内部状态 |
| `closeout.write` | 写 closeout package |
| `archive.write` | 写 immutable archive |

## Capability 到写入面的映射

| Capability | Allowed roots | Forbidden roots | Required evidence |
|---|---|---|---|
| `source.modify.backend` | `10-project/src/backend/**` | `00-boardroom/**`, `50-closeout/**`, `90-archive/**` | source diff + backend test log |
| `source.modify.application` | `10-project/src/app/**` | `00-boardroom/**`, `50-closeout/**`, `90-archive/**` | source diff + application test/smoke log |
| `source.modify.database` | `10-project/src/**/migrations/**`, `10-project/src/**/schema/**`, `10-project/src/**/seeds/**` | `50-closeout/**`, `90-archive/**` | migration validation + rollback note |
| `source.modify.platform` | `10-project/src/platform/**`, `10-project/scripts/**` | `00-boardroom/20-graph/**`, `90-archive/**` | platform smoke + risk note |
| `test.run.backend` | `20-evidence/tests/**` | `10-project/src/**` | command, exit code, stdout/stderr |
| `test.run.application` | `20-evidence/tests/**` | `10-project/src/**` | command, exit code, stdout/stderr |
| `evidence.write.git` | `20-evidence/git/**` | `10-project/src/**` | changed files, commit/diff metadata |
| `evidence.check.delivery` | `20-evidence/delivery/**`, `20-evidence/reviews/**` | `10-project/src/**` | findings + evidence refs |
| `verdict.write.maker_checker` | `20-evidence/reviews/**` | `10-project/src/**` | verdict + blocking status |
| `docs.update.delivery` | `10-project/docs/**` | `00-boardroom/20-graph/**`, `90-archive/**` | doc update summary |
| `runtime.state.write` | `.runtime/**`, runtime DB/event store | `10-project/**` unless materializer-controlled | event/projection update |
| `closeout.write` | `50-closeout/**` | `10-project/src/**` | final package + final evidence refs |
| `archive.write` | `90-archive/**` | all active source/doc views | immutable archive receipt |

## Phase 1 implementation status

Phase 1 has codified the current fixed workspace write-surface profile in `backend/app/core/workspace_path_contracts.py`:

- `CAPABILITY_WRITE_SURFACES` maps capability keys to allowed directory globs; execution code consumes these compiled write sets instead of branching on role names.
- `match_contract_write_set()` is the shared path matcher used by artifact write validation.
- `resolve_artifact_ref_contract()` and `classify_closeout_final_artifact_ref()` provide the shared artifact legality vocabulary for source delivery, evidence, git, delivery check, and closeout refs.
- `source_code_delivery` ticket hooks now validate source refs, test/verification evidence refs, git evidence refs, and documentation update refs against this contract.
- closeout validation and workflow completion gates reject governance/archive/unknown/superseded/placeholder/fallback refs as final evidence.

This phase intentionally does not refactor actor lifecycle, hiring, role template assignment, provider selection, provider streaming, or progression policy. Future flexible project directory layouts should be introduced by parameterizing this contract profile, not by reintroducing role-name-to-root branches in ticket handlers or runtime code.

## Phase 3 closure status

Round 7A–7E kept the Phase 1 write-surface boundary intact while moving runtime identity to actor / assignment / lease:

- Scheduler eligibility now consumes `actor_projection` and compiled `required_capabilities`; it does not map role names to writable roots.
- Context compiler execution package identity carries `actor_id` / `assignment_id` / `lease_id`; `allowed_write_set` remains capability/directory-contract derived.
- Unknown legacy `role_profile_ref` no longer compiles into a `role_profile:*` runtime execution key, so it cannot become an indirect write-root selector.
- Provider `role_bindings` remain import/display preference data only and do not influence write-surface policy.

Round 7E grep acceptance focuses on runtime, scheduler, provider selection and context compiler paths; any remaining `role_profile_ref` usage must stay in governance templates, product display, legacy input compilation or tests.



```yaml
roles:
  implementation_worker_primary:
    capabilities:
      - source.modify.application
      - test.run.application
      - evidence.write.test
      - evidence.write.git
      - docs.update.delivery

  backend_engineer_primary:
    capabilities:
      - source.modify.backend
      - test.run.backend
      - evidence.write.test
      - evidence.write.git
      - docs.update.delivery

  checker_primary:
    capabilities:
      - evidence.check.delivery
      - verdict.write.maker_checker

  closeout_runner:
    capabilities:
      - closeout.write
```

## Ticket Contract 编译规则

每张 ticket 必须声明：

- required capabilities；
- output contract；
- source read refs；
- allowed tools；
- write surfaces；
- evidence requirements。

Context Compiler 根据 actor capability 和 directory contract 生成 `allowed_write_set`。

Worker 不能自行扩大 allowed write set。

## Validation 规则

结果提交时必须同时通过：

1. schema validation；
2. write-set validation；
3. artifact ref validation；
4. evidence completeness validation；
5. placeholder detection；
6. supersede/lineage validation。

任一失败都不能进入 completed。必须进入 incident 或 rework。

## Placeholder 阻断

以下内容不能作为真实 delivery evidence：

- `source.py` 单文件占位；
- 只有 `1 passed` 的泛化 smoke，无业务断言；
- 描述为“后续里程碑补齐”的产物占位；
- 未覆盖 PRD acceptance 的 checklist；
- provider fallback 自动生成的默认 source/test payload；
- 没有 changed file inventory 的 source delivery。

## Closeout 写入限制

`closeout.write` 只能引用：

- source delivery asset；
- delivery check report；
- verification/test evidence；
- git closeout evidence；
- approved risk disposition；
- final audit summary。

不能引用：

- architecture brief；
- backlog recommendation；
- PRD 原文；
- unrelated governance docs；
- placeholder route/view；
- raw provider transcript。

## 验收标准

- runtime 中不再出现以 role name 直接决定 write root 的新代码。
- 所有 execution package 的 allowed write set 可由 capability policy 解释。
- checker 和 closeout 对 artifact refs 的判定使用同一 write-surface policy。
- 015 中出现过的 placeholder delivery 不能通过该策略。
