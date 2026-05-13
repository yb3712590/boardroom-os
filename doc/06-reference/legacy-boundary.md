# Legacy Boundary

## 文档职责

本文件定义旧实现与 V2 的边界。它不是 legacy asset map，也不鼓励迁移旧模块。

## 总状态

```text
legacy status: abandoned by default
```

旧 git 历史可作为归档教训，但 V2 默认不读取、不迁移、不整理旧实现。

## 默认禁止作为 V2 依据

如果旧路径存在，以下内容默认禁止作为 V2 实施依据：

```text
backend/app/core/runtime.py
backend/app/core/workflow_controller.py
backend/app/core/workflow_progression.py
backend/app/core/output_schemas.py
backend/app/core/deliverable_contract.py
backend/app/core/source_inventory.py
backend/app/core/acceptance_evidence.py
backend/app/contracts/acceptance_evidence.py
backend/app/contracts/source_inventory.py
backend/app/core/closeout_state_machine.py
backend/app/core/workflow_completion.py
backend/app/core/role_hooks.py
backend/app/core/project_workspaces.py
backend/tests/live/
backend/tests/test_runtime_fallback_payload.py
doc/refactor/
doc/live-report/
doc/tests/
```

## 允许用途

仅在用户明确要求时，旧内容可用于：

- forensic evidence；
- 历史失败复盘；
- negative test inspiration；
- 审计报告查证。

## 禁止用途

旧内容禁止用于：

- copy implementation；
- patch existing runtime；
- preserve compatibility；
- infer V2 architecture；
- resurrect fallback success；
- generate active V2 contracts；
- define V2 acceptance criteria。

## 触发 forensic lookup 的条件

只有以下情况可以读取旧实现：

1. 用户明确要求查看旧文件；
2. V2 negative test 需要确认某个历史失败模式；
3. 审计材料需要引用旧行为；
4. 法证复盘需要定位历史事实。

即使进行了 forensic lookup，结果也不能直接成为 V2 代码设计依据。必须先转化为 V2 negative requirement 或 documented decision。

## 当前建议

不要创建 legacy quarantine，不要整理 asset map，不要做模块迁移评估。

V2 的时间应投入到：

- contract kernel；
- reducer-protected graph；
- execution package；
- provider attempt evidence；
- command runner；
- evidence verifier；
- generated project package；
- closeout/replay/process audit。

