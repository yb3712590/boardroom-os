# 代码约束

本文件定义 V2 后续实现必须遵守的代码层约束。当前基座不包含实现代码。

## 命名空间

V2 实现代码必须进入：

```text
src/boardroom_os/
```

建议初始模块边界：

```text
src/boardroom_os/
├── contracts/
├── events/
├── reducers/
├── graph/
├── agents/
├── execution/
├── providers/
├── workspace/
├── evidence/
├── closeout/
├── audit/
└── adapters/
```

## 禁止旧主链扩展

禁止把以下路径作为 V2 主路径：

```text
backend/app/core/runtime.py
backend/app/core/workflow_controller.py
backend/app/core/workflow_progression.py
backend/app/core/closeout_state_machine.py
backend/app/core/source_inventory.py
backend/app/core/acceptance_evidence.py
```

如果当前分支为 orphan clean branch，这些文件不应存在。

## Contract-first

任何实现前必须有明确 contract：

- 输入；
- 输出；
- 状态变更；
- evidence obligation；
- failure mode；
- replay / audit 语义。

没有 contract 的实现只能是 spike，不能进入主路径。

## Reducer-first

状态变更必须通过 reducer 或等价 validator。

禁止：

- 直接修改 ticket status；
- 由 executor 决定 project completed；
- 由 closeout 扫 raw events 猜最终状态；
- 在数据结构中混入不可追踪 side effect。

## Runtime 边界

runtime / executor 只能：

- lease ready ticket；
- 调用 provider 或 tool；
- 写入 raw output；
- 运行 declared command；
- 记录 stdout、stderr、exit code、hash；
- 发出 typed event。

runtime / executor 禁止：

- 生成默认 source delivery；
- 生成 synthetic verification success；
- 自动补 acceptance evidence；
- 把 fallback 当作 implementation evidence；
- 替 CEO 做 closeout 决策。

## Fail-closed

以下情况必须失败：

- 缺 active acceptance contract；
- 缺 package contract；
- implementation ticket 缺 provider attempt；
- command evidence 不是由 runner 产生；
- source inventory 无 git/hash/producer；
- acceptance map 不完整；
- checker verdict 有 blocker；
- replay bundle 不可重建。

## 可版本化对象

所有外部可持久化对象必须包含：

```yaml
schema_version:
object_id:
created_at:
producer_ref:
```

涉及 graph 的对象必须包含：

```yaml
graph_version:
event_cursor:
```

## 模块依赖方向

建议依赖方向：

```text
contracts <- events <- reducers <- services <- adapters
```

业务对象不依赖 provider SDK；provider SDK 只出现在 adapters 层。

