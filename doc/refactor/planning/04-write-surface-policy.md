# 写入面策略

## 核心原则

写入权限以 capability 为主键，而不是以具体角色名为主键。

错误示例：

```text
if role_profile_ref == "frontend_engineer_primary":
    allow 10-project/src/frontend/**
```

目标示例：

```text
actor -> role template -> capability set -> write surface policy
```

runtime kernel 只判断 actor 是否具备 ticket contract 要求的 capability，不判断该 actor 是不是 frontend engineer、backend engineer 或 checker。

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
| `source.modify.frontend` | 修改 frontend source |
| `source.modify.database` | 修改 schema/migration/seed |
| `source.modify.platform` | 修改 platform/deploy/runtime scripts |
| `test.run.backend` | 运行并登记 backend 测试证据 |
| `test.run.frontend` | 运行并登记 frontend 测试证据 |
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
| `source.modify.frontend` | `10-project/src/frontend/**` | `00-boardroom/**`, `50-closeout/**`, `90-archive/**` | source diff + frontend test/smoke log |
| `source.modify.database` | `10-project/src/**/migrations/**`, `10-project/src/**/schema/**`, `10-project/src/**/seeds/**` | `50-closeout/**`, `90-archive/**` | migration validation + rollback note |
| `source.modify.platform` | `10-project/src/platform/**`, `10-project/scripts/**` | `00-boardroom/20-graph/**`, `90-archive/**` | platform smoke + risk note |
| `test.run.backend` | `20-evidence/tests/**` | `10-project/src/**` | command, exit code, stdout/stderr |
| `test.run.frontend` | `20-evidence/tests/**` | `10-project/src/**` | command, exit code, stdout/stderr, UI evidence if relevant |
| `evidence.write.git` | `20-evidence/git/**` | `10-project/src/**` | changed files, commit/diff metadata |
| `evidence.check.delivery` | `20-evidence/delivery/**`, `20-evidence/reviews/**` | `10-project/src/**` | findings + evidence refs |
| `verdict.write.maker_checker` | `20-evidence/reviews/**` | `10-project/src/**` | verdict + blocking status |
| `docs.update.delivery` | `10-project/docs/**` | `00-boardroom/20-graph/**`, `90-archive/**` | doc update summary |
| `runtime.state.write` | `.runtime/**`, runtime DB/event store | `10-project/**` unless materializer-controlled | event/projection update |
| `closeout.write` | `50-closeout/**` | `10-project/src/**` | final package + final evidence refs |
| `archive.write` | `90-archive/**` | all active source/doc views | immutable archive receipt |

## RoleTemplate 示例

Role template 是组织层配置，不是 runtime 执行键。

```yaml
roles:
  frontend_engineer_primary:
    capabilities:
      - source.modify.frontend
      - test.run.frontend
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
- 描述为“后续里程碑补齐”的页面占位；
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
