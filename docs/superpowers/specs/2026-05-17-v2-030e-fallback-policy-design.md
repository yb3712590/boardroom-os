# V2-030E fallback policy（降级策略）设计

## 范围

V2-030E 将 fallback policy classification（降级策略分类）定义为 evidence eligibility gate（证据资格门禁）。它不创建 source files（源码文件）、WorkProduct（工作产物）、ProviderAttempt（模型调用尝试记录）、command evidence（命令证据）或 verified evidence（已验证证据）。它只判断带 fallback（降级）标签的产物是否有资格服务于一个很窄的 evidence purpose（证据用途）。

## 问题

上一版 runtime（运行时）的失败点在于 implicit fallback（隐式降级）会把 provider failure（模型供应商失败）、missing outputs（缺失输出）、synthetic verification（合成验证）或 local draft（本地草案）包装成 apparent implementation success（看似实施成功）。V2 必须让 fallback 显式、类型化、可审计，并默认 fail closed（失败关闭）。

## 设计

新增 `src/boardroom_os/execution/fallback.py`，包含以下 typed models（类型化模型）：

- `FallbackKind`（降级类型）：封闭枚举，只包含架构文档定义的 `DETERMINISTIC_GOVERNANCE_DRAFT`、`TOOLING_PREFLIGHT`、`PROVIDER_UNAVAILABLE`、`TEST_ONLY_SIMULATION`、`CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM`。
- `FallbackPolicy`（降级策略）：不可变策略快照，包含 `fallback_policy_ref`（降级策略引用）、`kind`（类型）、deterministic artifact types（确定性产物类型）允许列表，以及 acceptance refs（验收引用）允许范围。
- `FallbackEvidenceRequest`（降级证据请求）：询问某个 fallback artifact（降级产物）是否能服务于指定 evidence purpose（证据用途）、artifact type（产物类型）和 acceptance refs（验收引用）。
- `FallbackEvidenceDecision`（降级证据判定）：返回 `allowed`（是否允许）和 `blocking_reasons`（阻断原因）。
- `evaluate_fallback_evidence`（降级证据判定函数）：纯函数，只做资格判定，不产生事实。

默认行为是拒绝。`PROVIDER_UNAVAILABLE`、`TEST_ONLY_SIMULATION`、`DETERMINISTIC_GOVERNANCE_DRAFT` 永远不能满足 implementation evidence（实施证据）。`TOOLING_PREFLIGHT` 只用于 diagnostic evidence（诊断证据）。`CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM` 只有在策略显式声明 artifact type（产物类型）和 acceptance scope（验收范围）时，才可以满足对应 deterministic evidence（确定性证据）。

## 边界

V2-030E 不修改 `ExecutionPackageCompiler`（执行包编译器）；`ExecutionPackage`（执行包）继续只携带 `fallback_policy_ref`（降级策略引用）。如果后续工作包引入 fallback policy registry（降级策略注册表），再由 compiler（编译器）校验引用是否可解析。

V2-030E 也不引入 `EvidenceClaim`（证据声明）或 `EvidenceVerifier`（证据验证器）；它们属于 V2-050。fallback（降级）不是第二条 implementation path（实施路径），也不是 provider（模型供应商）、command runner（命令运行器）或 verifier（验证器）的替代品。

## 测试

先写 negative tests（负例测试）到 `tests/negative/test_fallback_cannot_satisfy_implementation.py`：

- `PROVIDER_UNAVAILABLE` 不能满足 implementation evidence（实施证据）。
- `TEST_ONLY_SIMULATION` 不能满足 implementation evidence（实施证据）。
- `DETERMINISTIC_GOVERNANCE_DRAFT` 不能满足 implementation evidence（实施证据）。
- `TOOLING_PREFLIGHT` 不能满足 implementation evidence（实施证据）。
- `CONTRACT_ALLOWED_DETERMINISTIC_TRANSFORM` 缺 artifact type（产物类型）或 acceptance scope（验收范围）时不能满足 evidence（证据）。
- deterministic transform（确定性转换）不能满足 source、integration、acceptance 或 closeout implementation delivery（源码、集成、验收或收尾实施交付）。

再写 happy path tests（正向路径测试）到 `tests/execution/test_fallback_policy.py`：

- deterministic transform（确定性转换）可以满足合同显式允许的 deterministic evidence（确定性证据）。
- decision（判定）是纯函数结果并可稳定序列化。
- unknown extra fields（未知额外字段）和 empty refs（空引用）必须 fail closed（失败关闭）。

## 验收

当 fallback classification（降级分类）能证明 fallback success（降级成功）不可能满足 implementation evidence（实施证据），同时仍允许 contract-declared deterministic transforms（合同声明的确定性转换）被表示为窄范围 eligible evidence（有资格证据）时，V2-030E 完成。
