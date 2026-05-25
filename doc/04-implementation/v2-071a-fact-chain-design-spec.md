# V2-071A Fact-chain 设计 + 跨包命名空间 helper（同行评审 spec）

## 1. 背景与现实场景

2026-05-25 外部独立审计（`doc/04-implementation/v2-070-batch-review-report.md`）在 V2-070A~G 实施基础上识别出 18 项 P0/P1/P2 缺口。其中：

- **5 项 P0**（构造环 / 第二事实源 / events 不一致 / 隐式 fallback / graph_version 越界）是结构性问题，不能用单点补丁修补。
- **5 项 P1**（payload 内容未绑定 / 占位 fallback / consumer 伪造 / fallback 排他 / 命名空间不足）是事实绑定缺陷。
- **5 项 P2**（哈希非确定性 / Git 解析正确性）是技术细节缺陷。

V2-071A 作为 V2-071 阶段的第一个工作包，不修改任何 V2-070 已有 builder，只承担**冻结整体设计**与**提供共享基础设施**两件事，让后续 V2-071B~E 的修改有共同地基：

1. 在本文件第 3 节固定 V2-070 fact-chain（事实链）的权威源、构造顺序、禁止外部传入字段清单。这是 DEC-0017 的落地形式，后续 V2-071B~E 修改必须显式满足这份契约。
2. 新建 `src/boardroom_os/contracts/refs.py`，提供两类纯函数 helper：
   - `namespaced_ref(...)`：跨包引用命名空间助手（解决 P1-5）。
   - `canonical_sort_for_hash(...)`：集合语义输入规范排序助手（解决 P2-1/2/3）。

Pre-flight（一致性预检）：`backlog.md` 当前未完成工作包为 V2-071A；本 spec 路径在 backlog 工作包输出文件清单中已声明；`src/boardroom_os/contracts/refs.py` 尚不存在；本工作包不修改 V2-070 任何源码。

## 2. 范围与边界

### 2.1 In Scope

- `doc/04-implementation/v2-071a-fact-chain-design-spec.md`（本文件）：fact-chain 权威源、构造顺序、禁止外部字段清单。
- `src/boardroom_os/contracts/refs.py`：namespace helper + canonical sort helper。
- `tests/contracts/test_namespaced_refs.py` + `tests/negative/test_namespaced_refs_fail_closed.py`：covers helper 行为。
- `src/boardroom_os/contracts/__init__.py`、`doc/04-implementation/INDEX.md`：导出与索引同步。

### 2.2 Out of Scope

- 不修改 `src/boardroom_os/audit/`、`src/boardroom_os/closeout/`、`src/boardroom_os/adapters/`、`src/boardroom_os/reducers/` 任何文件（这些留给 V2-071B~F）。
- 不引入新的 SHA value object（与 V2-070G P2-13 重叠的部分按既有 V2-070G 已落实的 `boardroom_os/contracts/hashes.py` 复用；V2-071A 只新增 namespace + canonical sort）。
- 不实现 `ReplayPayloadResolver` 协议（留给 V2-071E）。

### 2.3 兼容性策略

新增模块，不破坏既有接口。V2-070 任何模块直到 V2-071B 才开始改造，本工作包对运行时无可观察影响。

## 3. V2-070 Fact-chain 权威源契约（对外冻结）

### 3.1 权威源原则（DEC-0017 落地）

| 事实类型 | 唯一权威源 | 禁止外部传入 |
|---|---|---|
| 事件（EventRecord） | `InMemoryEventLog`（或后续持久化 EventLog） | — |
| 投影摘要（ProjectionReplaySummary） | `ProjectionReplay.replay_events(events)` | `ReplayBundleBuilderInput.projection_summary`（必须删除） |
| 事件切片（audit 消费的 events） | `ReplayBundle.events` | `ProcessAuditBuilderInput.events`（必须删除，强制复用 replay_bundle.events） |
| Git facts | `GitAuditAdapter.collect(...)` 显式传入参数 | `base_commit_sha or final_commit_sha`、`worktree_ref or f"worktree.{package_root}"` 等 fallback |
| Closeout terminal status | `CloseoutReducer` 消费 `CLOSEOUT_COMMITTED` 治理事件 | runtime / executor 不得直接产生 terminal success |

### 3.2 构造顺序（无环）

```text
EventLog（事件日志）
   ↓
ReplayBundle（重放包：从 events 重新投影）
   ↓
ProcessAuditBundle（流程审计包：复用 replay_bundle.events，不要求 closeout_committed）
   ↓
GitVersionAuditBundle（Git 版本审计包：绑定真实 commit range，无 fallback）
   ↓
CloseoutGate（消费三件 readiness summaries）
   ↓
CloseoutPackage（收尾包：聚合已验证审计包，graph_version == replay_last_graph_version）
   ↓
CLOSEOUT_COMMITTED event（governance event）
   ↓
CloseoutReducer / CloseoutProjection（terminal_status = succeeded）
```

关键约束：

1. ProcessAudit 不得要求事件流中已存在 `CLOSEOUT_COMMITTED`（旧实现违反此约束）。
2. `CLOSEOUT_COMMITTED` 必须在 CloseoutPackage 构造完成后才能发出。
3. 任何 audit 产物不得引用尚未构造的对象。

### 3.3 命名空间契约

所有持久化引用必须满足：

```text
<kind>.<project_ref>.<content_hash_short>[.<run_id>]
```

例如：

- `replay-bundle.project.abc123def456.<run_id_short>`（旧实现：`replay-bundle.<project>.<summary_hash[:12]>`，缺 run_id）
- `process-audit-artifact.project.abc123def456.timeline`（旧实现：`process-audit-artifact.timeline`，完全无 project / content）
- `git-version-audit-facts.project.<final_commit_sha[:12]>`（旧实现：`git-version-audit-facts.<project>`，缺 commit 段）

namespace 段的非空字符必须满足 `_NAMESPACE_SEGMENT_PATTERN = r"^[a-z0-9][a-z0-9-]*$"`（小写字母数字与连字符）。

### 3.4 集合语义输入 canonical sort 契约

| 输入 | 排序 key | 适用 builder |
|---|---|---|
| `verification_runs` | `run.verification_run_id.value` | GitVersionAudit / ProcessAudit |
| `command_evidence_bindings` | `binding.binding_id.value` | GitVersionAudit |
| `verified_evidence` | `evidence.verified_evidence_id.value` | ProcessAudit |
| `provider_attempt_refs` | `ref.value` | ProcessAudit |
| `payload_manifest.entries` | `entry.content_ref.value` | ReplayBundle |
| `artifact_manifest.entries` | `entry.kind.value` | ReplayBundle |
| `checked_refs` | identity (`str`) | 所有 builder |

序列语义输入（events、event_hash_chain）按 `graph_version` 严格递增，**不**按 canonical sort 重排。

## 4. 模块设计

### 4.1 文件结构

```text
src/boardroom_os/contracts/refs.py        (新建)
tests/contracts/test_namespaced_refs.py   (新建)
tests/negative/test_namespaced_refs_fail_closed.py (新建)
```

### 4.2 公开 API

```python
# src/boardroom_os/contracts/refs.py
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from typing import Any, Callable, TypeVar

_T = TypeVar("_T")
_NAMESPACE_SEGMENT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class NamespacedRefError(ValueError):
    pass


def assert_namespace_segment(value: str, *, field_name: str) -> str:
    """校验单个 namespace segment。"""
    normalized = value.strip()
    if not normalized:
        raise NamespacedRefError(f"{field_name} must not be empty")
    if not _NAMESPACE_SEGMENT_PATTERN.fullmatch(normalized):
        raise NamespacedRefError(
            f"{field_name} must match {_NAMESPACE_SEGMENT_PATTERN.pattern}: {normalized!r}"
        )
    return normalized


def namespaced_ref(
    *,
    kind: str,
    project_ref: str,
    content_hash: str,
    run_id: str | None = None,
    extra_suffix: str | None = None,
) -> str:
    """生成稳定的 namespaced reference 字符串。

    Format: `<kind>.<project_ref>.<content_hash[:12]>[.<run_id>][.<extra_suffix>]`
    """
    parts: list[str] = [
        assert_namespace_segment(kind, field_name="namespaced_ref.kind"),
        assert_namespace_segment(project_ref, field_name="namespaced_ref.project_ref"),
    ]
    if not isinstance(content_hash, str) or len(content_hash) < 12:
        raise NamespacedRefError("content_hash must be a string of length >= 12")
    parts.append(content_hash[:12].lower())
    if run_id is not None:
        parts.append(assert_namespace_segment(run_id, field_name="namespaced_ref.run_id"))
    if extra_suffix is not None:
        parts.append(assert_namespace_segment(extra_suffix, field_name="namespaced_ref.extra_suffix"))
    return ".".join(parts)


def canonical_sort_for_hash(
    values: Iterable[_T],
    *,
    key: Callable[[_T], str],
) -> tuple[_T, ...]:
    """对集合语义输入按 key 排序，保证哈希稳定。

    与内置 `sorted` 的区别：
    - 拒绝重复 key（视为调用方契约错误）。
    - 拒绝 key 返回 None / 非 str。
    """
    keyed: list[tuple[str, _T]] = []
    seen: set[str] = set()
    for value in values:
        k = key(value)
        if not isinstance(k, str):
            raise NamespacedRefError(
                f"canonical_sort_for_hash key must return str, got {type(k).__name__}"
            )
        if k in seen:
            raise NamespacedRefError(f"canonical_sort_for_hash detected duplicate key: {k!r}")
        seen.add(k)
        keyed.append((k, value))
    keyed.sort(key=lambda item: item[0])
    return tuple(value for _, value in keyed)


def hash_namespaced_payload(payload: dict[str, Any]) -> str:
    """对 dict payload 做 canonical JSON sha256。

    与各模块内 `_hash_jsonable` 等价，但作为本模块的官方实现暴露。
    """
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "NamespacedRefError",
    "assert_namespace_segment",
    "canonical_sort_for_hash",
    "hash_namespaced_payload",
    "namespaced_ref",
]
```

## 5. Validation 规则

### 5.1 `assert_namespace_segment`

- 拒绝空 / 仅空白 / 含大写字母 / 含点 / 含斜杠 / 含下划线 / 含特殊字符。
- 拒绝以 `-` 开头或结尾。
- 返回 stripped value。

### 5.2 `namespaced_ref`

- `kind`、`project_ref`、必要时 `run_id` / `extra_suffix` 各自通过 `assert_namespace_segment`。
- `content_hash` 必须是 str 且长度 ≥ 12（取前 12 字符并 lowercase）。
- 拼接顺序固定，便于反向解析。

### 5.3 `canonical_sort_for_hash`

- 拒绝重复 key。
- 拒绝 key 函数返回非 str。
- 排序稳定（同 key 不可能存在）。

### 5.4 `hash_namespaced_payload`

- `sort_keys=True` 保证字段顺序不影响 hash。
- `ensure_ascii=False` 保留 UTF-8 内容。
- 返回 lowercase hex sha256。

## 6. 测试计划

### 6.1 Negative tests（必须先写）

`tests/negative/test_namespaced_refs_fail_closed.py`：

1. `test_namespaced_ref_rejects_empty_kind` — `kind=""` 必须 raise `NamespacedRefError`。
2. `test_namespaced_ref_rejects_uppercase_kind` — `kind="Replay-Bundle"` 必须 raise。
3. `test_namespaced_ref_rejects_path_in_kind` — `kind="replay/bundle"` 必须 raise。
4. `test_namespaced_ref_rejects_short_content_hash` — `content_hash="abc"` 必须 raise。
5. `test_namespaced_ref_rejects_uppercase_run_id` — `run_id="RUN-001"` 必须 raise。
6. `test_canonical_sort_rejects_duplicate_keys` — 输入有两条 key 相同的项必须 raise。
7. `test_canonical_sort_rejects_non_str_key_return` — `key=lambda v: v.x`（返回 int）必须 raise。
8. `test_assert_namespace_segment_rejects_leading_dash` — `value="-foo"` 必须 raise。
9. `test_assert_namespace_segment_rejects_trailing_dash` — `value="foo-"` 必须 raise。

### 6.2 Happy path

`tests/contracts/test_namespaced_refs.py`：

1. `test_namespaced_ref_is_deterministic` — 相同输入返回字节相同的 ref；不同 `content_hash` 返回不同 ref。
2. `test_namespaced_ref_includes_run_id_when_provided` — 含 `run_id` 与不含 `run_id` 的输出有差异。
3. `test_canonical_sort_for_hash_is_stable_under_reordering` — 同一组输入乱序后产生相同 tuple。
4. `test_canonical_sort_for_hash_preserves_objects_not_keys` — 返回 tuple 包含原对象（不是 key）。
5. `test_hash_namespaced_payload_is_stable_under_field_reorder` — `{"a":1,"b":2}` 与 `{"b":2,"a":1}` 产生相同 hash。
6. `test_hash_namespaced_payload_round_trips_utf8` — 含中文 / emoji 字段的 payload 可稳定 hash。

## 7. 验证命令

```powershell
$env:PYTHONPATH = "src;."
python -m pytest tests/contracts/test_namespaced_refs.py tests/negative/test_namespaced_refs_fail_closed.py -q --basetemp=.pytest-tmp-v2071a
```

成功标准：全部测试通过；V2-070 其它套件**不应**受影响（本工作包不修改 V2-070 模块）。可选回归：

```powershell
python -m pytest tests/closeout tests/contracts -q --basetemp=.pytest-tmp-v2071a-regression
```

确认 V2-070 既有套件未被影响。

## 8. 文档同步

完成本工作包后：

1. `doc/04-implementation/backlog.md`：V2-071A 状态改 DONE；TL;DR 当前未完成工作包指向 V2-071B；Phase 7.5 进度 1/6。
2. `doc/04-implementation/acceptance-criteria.md`：勾选 Phase 7.5 中"AC-V2-CLOSEOUT-009 / 010"对应的初步基础设施（实际由 V2-071E / V2-071B~D 最终闭合，本包只交付 helper）。
3. `doc/04-implementation/INDEX.md`：本 spec 已登记；新建 `src/boardroom_os/contracts/refs.py` 不需要 doc INDEX 同步（属于代码）。
4. `doc/05-project-log/2026-05.md`：追加 V2-071A 完成记录。
5. `doc/05-project-log/decisions.md`：不新增 DEC（DEC-0016 / DEC-0017 已覆盖原则）。

## 9. 完成判定

V2-071A 完成时：

1. `src/boardroom_os/contracts/refs.py` 存在并导出 `namespaced_ref`、`canonical_sort_for_hash`、`hash_namespaced_payload`、`NamespacedRefError`。
2. 第 6 节测试全部通过。
3. 第 3 节 fact-chain 设计契约对外可被 V2-071B~E 直接引用。
4. V2-070 既有套件未受影响。
5. backlog 顶部 TL;DR 已指向 V2-071B。
