# AGENTS.md

本文件约束所有 AI agent、人类开发者和自动化工具在 Boardroom OS V2 分支中的行为。

## 默认语言

- 文档、审计说明、项目日志默认使用中文。
- 代码标识符、模块名、schema 字段、命令名默认使用英文。
- 面向外部集成的协议字段应稳定、简短、可版本化。

## 每次任务开始前必须阅读

最小阅读路径：

1. `README.md`
2. `AGENTS.md`
3. `doc/README.md`
4. 当前任务所在目录的 `INDEX.md`
5. 与任务直接相关的规范文档

如任务涉及架构、合同、证据、runtime、测试或 closeout，必须额外阅读：

- `doc/03-architecture/domain-model.md`
- `doc/03-architecture/contract-and-evidence-model.md`
- `doc/03-architecture/execution-and-runtime-boundary.md`
- `doc/04-implementation/acceptance-criteria.md`
- `doc/06-reference/legacy-boundary.md`

## 旧实现边界

旧实现默认状态：

```text
abandoned by default
```

除非用户明确要求 forensic lookup，AI 不应读取、引用、迁移或整理旧实现作为 V2 实施依据。

默认禁止作为 V2 设计或实现依据的旧路径包括但不限于：

- `backend/app/core/runtime.py`
- `backend/app/core/workflow_controller.py`
- `backend/app/core/workflow_progression.py`
- `backend/app/contracts/acceptance_evidence.py`
- `backend/app/core/source_inventory.py`
- `backend/app/core/acceptance_evidence.py`
- `doc/refactor/`
- `doc/live-report/`
- `doc/tests/`

允许用途仅限：

- forensic evidence；
- 失败模式复盘；
- negative test inspiration；
- 用户明确指定的历史查询。

禁止用途：

- copy implementation；
- patch existing runtime；
- preserve compatibility；
- infer V2 architecture from legacy behavior；
- restore fallback success paths。

## 代码落点

V2 代码未来必须进入新命名空间：

```text
src/boardroom_os/
```

测试进入：

```text
tests/
```

脚本进入：

```text
scripts/
```

禁止直接扩展旧 `backend/app/core/runtime.py`、旧 `backend/app/core/workflow_*.py` 或旧 contracts 作为 V2 主路径。

## 文档更新规则

修改文档时必须同步：

1. 相关目录的 `INDEX.md`；
2. 如改变设计决策，更新 `doc/05-project-log/decisions.md`；
3. 如改变近期工作，更新 `doc/04-implementation/backlog.md`；
4. 如完成阶段性任务，更新 `doc/05-project-log/2026-05.md` 或对应月份日志。

不要无限追加长文。若单文件过长，应拆分到同目录下的新专题文档，并在 `INDEX.md` 维护导航。

## 实现硬约束

- Contract first：没有 active contract，不写实现主路径。
- Reducer first：状态变更必须通过 reducer 或等价 validator。
- Evidence first：没有真实 evidence，不允许 closeout。
- Fail closed：缺字段、缺 provider attempt、缺 command evidence、缺 acceptance map 默认失败。
- Runtime bounded：runtime 不做 CEO 决策，不生成 implementation evidence，不合成 test success。
- Negative tests first：先证明伪交付无法通过，再证明 happy path 可以通过。

## 禁止事项

- 禁止把 workflow completed 当作项目完成。
- 禁止把 checker notes 当作 blocker 豁免。
- 禁止用 static acceptance criteria 覆盖动态需求。
- 禁止 runtime 默认补 source files、verification runs 或 closeout evidence。
- 禁止 source inventory 只证明引用存在。
- 禁止 provider zero-attempt 的 implementation ticket 完成。
- 禁止 fallback 满足 implementation evidence，除非合同显式声明该任务是 deterministic transform。

