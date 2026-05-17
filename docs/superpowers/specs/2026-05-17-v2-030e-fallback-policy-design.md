# V2-030E fallback policy（降级策略）设计

## 范围

V2-030E 将 fallback policy classification（降级策略分类）定义为 evidence eligibility gate（证据资格门禁）。它不创建 source files（源码文件）、WorkProduct（工作产物）、ProviderAttempt（模型调用尝试记录）、command evidence（命令证据）或 verified evidence（已验证证据）。它只判断带 fallback（降级）标签的产物是否有资格服务于一个很窄的 evidence purpose（证据用途）。

## 问题

上一版 runtime（运行时）的失败点在于 implicit fallback（隐式降级）会把 provider failure（模型供应商失败）、missing outputs（缺失输出）、synthetic verification（合成验证）或 local draft（本地草案）包装成 apparent implementation success（看似实施成功）。V2 必须让 fallback 显式、类型化、可审计，并默认 fail closed（失败关闭）。

## 设计

新增 `src/boardroom_os/execution/fallback.py`，包含以下 typed models（类型化模型）：

- `EvidencePurpose`（证据用途）：封闭枚举，值为 `IMPLEMENTATION`、`DIAGNOSTIC`、`DETERMINISTIC`。`IMPLEMENTATION` 覆盖 AC-V2-EXECUTION-003 列举的 source / integration / acceptance / closeout 四类 implementation evidence（实施证据）；fallback（降级）对该 purpose（用途）的判定不区分子类，统一拒绝。
- `FallbackKind`（降级类型）：封闭枚举，只包含架构文档定义的 `DETERMINISTIC_GOVERNANCE_DRAFT`、`TOOLING_PREFLIGHT`、`PROVIDER_UNAVAILABLE`、`TEST_ONLY_SIMULATION`、`CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM`。
- `FallbackPolicy`（降级策略）：不可变策略快照，复用 `FallbackPolicyRef`（降级策略引用，来自 `src/boardroom_os/execution/package.py`）、`RequiredArtifactType`（必需产物类型）和 `AcceptanceRef`（验收引用），包含 `fallback_policy_ref`、`kind`、deterministic artifact types（确定性产物类型）允许列表，以及 acceptance refs（验收引用）允许范围。
- `FallbackEvidenceRequest`（降级证据请求）：询问某个 fallback artifact（降级产物）是否能服务于指定 `EvidencePurpose`（证据用途）、`RequiredArtifactType`（必需产物类型）和 `AcceptanceRef`（验收引用）集合。
- `FallbackEvidenceDecision`（降级证据判定）：返回 `fallback_policy_ref`、`applied_kind`、`evaluated_purpose`、`allowed`（是否允许）和 `blocking_reasons`（阻断原因）；不变式为 `allowed=True` 等价于 `blocking_reasons` 为空。
- `evaluate_fallback_evidence`（降级证据判定函数）：纯函数，只做资格判定，不产生事实。

判定逻辑有两个轴：

1. `EvidencePurpose`（证据用途）决定哪些 `FallbackKind`（降级类型）有资格被考虑。
2. 当且仅当 `FallbackKind` 为 `CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM` 时，`allowed_artifact_types` 与 `allowed_acceptance_refs` 进一步收窄 scope（作用域）。

| FallbackKind（降级类型） | IMPLEMENTATION | DIAGNOSTIC | DETERMINISTIC |
|---|---|---|---|
| `PROVIDER_UNAVAILABLE` | 拒绝 | 拒绝 | 拒绝 |
| `TEST_ONLY_SIMULATION` | 拒绝 | 拒绝 | 拒绝 |
| `DETERMINISTIC_GOVERNANCE_DRAFT` | 拒绝 | 拒绝 | 拒绝 |
| `TOOLING_PREFLIGHT` | 拒绝 | 允许 | 拒绝 |
| `CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM` | 拒绝 | 拒绝 | 允许，仅限 policy scope（策略作用域）内 |

默认行为是拒绝。`PROVIDER_UNAVAILABLE`、`TEST_ONLY_SIMULATION`、`DETERMINISTIC_GOVERNANCE_DRAFT` 永远不能满足 implementation evidence（实施证据）。`TOOLING_PREFLIGHT` 只用于 diagnostic evidence（诊断证据）。`CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM` 只有在策略显式声明 artifact type（产物类型）和 acceptance scope（验收范围）时，才可以满足对应 deterministic evidence（确定性证据）。

### 与架构表的差异

`doc/03-architecture/execution-and-runtime-boundary.md` 中对 `TEST_ONLY_SIMULATION` 保留了“除非测试明确验证失败路径”的例外。V2-030E 不保留该例外：failure-path validation（失败路径验证）必须通过 contract-declared deterministic transform（合同声明的确定性转换）显式表达，而不是由 `TEST_ONLY_SIMULATION` 这个 fallback kind（降级类型）隐式承载。该偏离记录为 DEC-0014。

## 边界

V2-030E 不修改 `ExecutionPackageCompiler`（执行包编译器）；`ExecutionPackage`（执行包）继续只携带 `fallback_policy_ref`（降级策略引用）。如果后续工作包引入 fallback policy registry（降级策略注册表），再由 compiler（编译器）校验引用是否可解析。

V2-050 `EvidenceVerifier`（证据验证器）在处理任何标记为 fallback（降级）的 work product（工作产物）之前，必须先解析 `fallback_policy_ref` 到具体 `FallbackPolicy`（降级策略），再调用 `evaluate_fallback_evidence`（降级证据判定函数）。该解析依赖的 registry（注册表）由后续工作包提供；在 registry 落地之前，V2-050 必须对 fallback artifact（降级产物）直接 fail closed（失败关闭）。

V2-030E 也不引入 `EvidenceClaim`（证据声明）或 `EvidenceVerifier`（证据验证器）；它们属于 V2-050。fallback（降级）不是第二条 implementation path（实施路径），也不是 provider（模型供应商）、command runner（命令运行器）或 verifier（验证器）的替代品。

## 测试

先写 negative tests（负例测试）到 `tests/negative/test_fallback_cannot_satisfy_implementation.py`。

构造期负例：

- 非 `CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM` 的 `FallbackKind` 不得携带非空 allow-list（允许列表）。
- `CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM` 必须同时声明非空 `allowed_artifact_types` 与非空 `allowed_acceptance_refs`。
- `FallbackPolicy`、`FallbackEvidenceRequest` 和 `FallbackEvidenceDecision` 的 unknown extra fields（未知额外字段）必须 fail closed（失败关闭）。
- `FallbackEvidenceRequest` 缺 purpose / artifact_type / acceptance_refs 任一字段，或 acceptance_refs 为空，必须 fail closed（失败关闭）。

评估期负例：

- `PROVIDER_UNAVAILABLE` 不能满足 implementation evidence（实施证据）。
- `TEST_ONLY_SIMULATION` 不能满足 implementation evidence（实施证据）。
- `DETERMINISTIC_GOVERNANCE_DRAFT` 不能满足 implementation evidence（实施证据）。
- `TOOLING_PREFLIGHT` 不能满足 implementation evidence（实施证据）。
- `CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM` 缺 artifact type（产物类型）或 acceptance scope（验收范围）匹配时不能满足 evidence（证据）。
- deterministic transform（确定性转换）不能满足 implementation purpose（实施用途）；该 purpose 覆盖 source、integration、acceptance 和 closeout 四类 implementation evidence（实施证据）。

再写 happy path tests（正向路径测试）到 `tests/execution/test_fallback_policy.py`：

- deterministic transform（确定性转换）可以满足合同显式允许的 deterministic evidence（确定性证据）。
- tooling preflight（工具预检）只可以满足 diagnostic evidence（诊断证据）。
- decision（判定）是纯函数结果并可稳定序列化，且携带 policy / kind / purpose 审计字段。

## 验收

V2-030E 是 AC-V2-EXECUTION-003（fallback 默认不能满足 source / integration / acceptance / closeout evidence）的唯一证据来源工作包。

当 fallback classification（降级分类）能证明 fallback success（降级成功）不可能满足 implementation evidence（实施证据），同时仍允许 contract-declared deterministic transforms（合同声明的确定性转换）被表示为窄范围 eligible evidence（有资格证据）时，V2-030E 完成。
