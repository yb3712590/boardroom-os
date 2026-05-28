# V2-071E CloseoutPackage boundary + payload binding（收尾包边界与载荷内容绑定）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development（子代理驱动开发，推荐） or executing-plans（按计划执行） to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement V2-071E so CloseoutPackage（收尾包）strictly binds to the ReplayBundle（重放包）proof boundary（证明边界）, ReplayPayloadManifest（重放载荷清单）sha256 values are recomputed from real payload content via an explicit ReplayPayloadResolver（重放载荷解析器）, and ProcessAudit（流程审计）/ GitVersionAudit（Git 版本审计）/ CloseoutPackage persistent refs（持久引用） are namespace-bound by project, content hash, run, and kind.

**Architecture:** Extend the existing pure-domain closeout/audit contract chain. ReplayBundleReadiness（重放包就绪摘要） becomes a fully verified payload-summary object; ProcessAudit artifact/content refs（产物/内容引用） and CloseoutPackage ids（收尾包标识） use `namespaced_ref(...)`（命名空间引用生成器）; `assert_namespaced_ref_binding(...)`（命名空间绑定断言） provides exact full-string binding validation. No legacy runtime（旧运行时）, filesystem resolver（文件系统解析器）, compatibility shim（兼容垫片）, or optional half-verified readiness path is introduced.

**Tech Stack:** Python 3, Pydantic BaseModel（Pydantic 模型）, pytest, existing Boardroom OS V2 contracts refs（合同引用）, ReplayBundle（重放包）, ProcessAuditBundle（流程审计包）, GitVersionAuditBundle（Git 版本审计包）, CloseoutGate（收尾门禁）, and CloseoutPackage（收尾包）models.

---

## File Structure

- Modify `src/boardroom_os/contracts/refs.py`
  - Add `assert_namespaced_ref_binding(...)`（命名空间绑定断言）.
- Modify `src/boardroom_os/audit/replay_bundle.py`
  - Add `ReplayPayloadResolver`（重放载荷解析器）protocol.
  - Require resolver in `replay_bundle_readiness(...)`（重放包就绪摘要构造函数）.
  - Add payload manifest ref/hash and `payload_sha256_verified=True`（载荷哈希已验证标记）.
- Modify `src/boardroom_os/audit/process_audit.py`
  - Add `run_id`（运行 ID）to builder input.
  - Generate artifact/content refs（产物/内容引用）with `namespaced_ref(...)`.
  - Reject legacy short refs during readiness validation.
- Modify `src/boardroom_os/audit/git_version_audit.py`
  - Add `run_id` to builder input where needed.
  - Generate touched GitVersionAudit refs（Git 版本审计引用）with `namespaced_ref(...)` and preserve V2-071D fact_set_id（事实集标识）semantics.
- Modify `src/boardroom_os/closeout/package.py`
  - Require `graph_version == ReplayBundle.last_graph_version`.
  - Add `run_id` to builder input.
  - Generate and validate CloseoutPackageRef（收尾包引用）with `namespaced_ref(...)`.
  - Ensure checked refs（已检查引用）cover payload manifest ref/hash and replay readiness proof.
- Create tests:
  - `tests/negative/test_closeout_package_graph_version_overflow_rejected.py`
  - `tests/negative/test_replay_payload_manifest_tampering_rejected.py`
  - `tests/closeout/test_closeout_package_boundary.py`
- Modify existing closeout fixtures/tests to pass explicit payload resolver and run_id.
- Modify docs after verification:
  - `doc/04-implementation/backlog.md`
  - `doc/04-implementation/acceptance-criteria.md`
  - `doc/05-project-log/2026-05.md`
  - `doc/04-implementation/INDEX.md`

---

### Task 1: Add failing negative tests for V2-071E boundaries

**Files:**
- Create `tests/negative/test_closeout_package_graph_version_overflow_rejected.py`
- Create `tests/negative/test_replay_payload_manifest_tampering_rejected.py`
- Create initial portions of `tests/closeout/test_closeout_package_boundary.py`

- [ ] Write graph boundary tests proving CloseoutPackage rejects graph_version above and below ReplayBundle proof boundary.
- [ ] Write ReplayPayloadManifest tests proving missing resolver, missing content, tampered sha256, and non-canonical JSON hashes fail closed.
- [ ] Write ProcessAudit legacy short-ref rejection tests for artifact_ref and content_ref.
- [ ] Confirm these tests fail on the current implementation before production code changes.

---

### Task 2: Implement exact namespaced ref binding helper

**Files:**
- Modify `src/boardroom_os/contracts/refs.py`
- Extend `tests/closeout/test_closeout_package_boundary.py`

- [ ] Add `assert_namespaced_ref_binding(...)` using `namespaced_ref(...)` for exact full-string expected value generation.
- [ ] Raise `NamespacedRefError(f"{field_name} namespace binding mismatch")` on mismatch.
- [ ] Cover valid binding and kind/project/hash/run/suffix mismatch cases in tests.

---

### Task 3: Bind ReplayBundleReadiness to real payload content

**Files:**
- Modify `src/boardroom_os/audit/replay_bundle.py`
- Modify existing replay/closeout tests and fixtures

- [ ] Add `ReplayPayloadResolver` protocol with `resolve_payload(content_ref)`.
- [ ] Add deterministic payload byte conversion for bytes, str, Mapping, BaseModel, list, and tuple values using existing canonical JSON semantics.
- [ ] Require `payload_resolver` keyword-only argument in `replay_bundle_readiness(...)`.
- [ ] Verify every `ReplayPayloadManifest.entries[*].sha256` against resolver-returned content.
- [ ] Add `payload_sha256_verified`, `payload_manifest_ref`, and `payload_manifest_hash` to `ReplayBundleReadiness`.
- [ ] Update all callers to pass explicit test resolver; no default filesystem or optional resolver fallback.

---

### Task 4: Namespace ProcessAudit artifact/content refs

**Files:**
- Modify `src/boardroom_os/audit/process_audit.py`
- Modify process audit tests and fixtures

- [ ] Add `run_id` to ProcessAudit builder input and fixture construction.
- [ ] Generate `ProcessAuditArtifactRef` and `ProcessAuditContentRef` with `namespaced_ref(...)` using project_ref, content sha256, run_id, and artifact kind suffix.
- [ ] Ensure artifact lineage payloads use generated namespaced artifact ids instead of hardcoded legacy ids.
- [ ] Validate every artifact/content ref during `process_audit_readiness(...)` with `assert_namespaced_ref_binding(...)`.
- [ ] Reject legacy `process-audit-artifact.{kind}` and `process-audit-content.{kind}` values.

---

### Task 5: Namespace GitVersionAudit and CloseoutPackage refs

**Files:**
- Modify `src/boardroom_os/audit/git_version_audit.py`
- Modify `src/boardroom_os/closeout/package.py`
- Modify git/closeout tests and fixtures

- [ ] Add `run_id` where the touched builder inputs generate persistent refs.
- [ ] Generate GitVersionAudit bundle/report/hash manifest refs with `namespaced_ref(...)` where construction is touched and avoid retaining legacy short formats.
- [ ] Change CloseoutPackage graph boundary validation to exact equality with ReplayBundle last_graph_version.
- [ ] Generate CloseoutPackageRef with `namespaced_ref(kind="closeout-package", project_ref=..., content_hash=..., run_id=...)`.
- [ ] Validate replay/process/git/package refs with `assert_namespaced_ref_binding(...)` where the expected content hash is available.
- [ ] Ensure same project closeouts with different run_id or payload hash produce different package ids.

---

### Task 6: Migrate fixtures and checked_refs coverage

**Files:**
- Modify existing tests under `tests/closeout/` and `tests/negative/`

- [ ] Replace all `replay_bundle_readiness(bundle)` calls with explicit `payload_resolver=...`.
- [ ] Update test payload manifest sha256 values to match resolver canonical payload content.
- [ ] Pass stable run_id through ReplayBundle, ProcessAudit, GitVersionAudit, and CloseoutPackage fixture builders.
- [ ] Update assertions from legacy short refs to namespace helper outputs.
- [ ] Extend CloseoutPackage checked_refs expectations to include payload manifest ref/hash and payload sha256 verification evidence.

---

### Task 7: Verify and close documentation

**Files:**
- Modify `doc/04-implementation/backlog.md`
- Modify `doc/04-implementation/acceptance-criteria.md`
- Modify `doc/05-project-log/2026-05.md`
- Modify `doc/04-implementation/INDEX.md`

- [ ] Run new negative/happy-path tests first:
  - `PYTHONPATH=src:. python -m pytest tests/negative/test_closeout_package_graph_version_overflow_rejected.py tests/negative/test_replay_payload_manifest_tampering_rejected.py tests/closeout/test_closeout_package_boundary.py -q --basetemp=.pytest-tmp-v2071e-new`
- [ ] Run closeout regression:
  - `PYTHONPATH=src:. python -m pytest tests/closeout/test_replay_bundle.py tests/closeout/test_replay_bundle_rereplay.py tests/closeout/test_process_audit.py tests/closeout/test_process_audit_artifacts.py tests/closeout/test_process_audit_fact_chain.py tests/closeout/test_git_version_audit.py tests/closeout/test_closeout_package.py -q --basetemp=.pytest-tmp-v2071e-closeout`
- [ ] Run closeout + negative regression:
  - `PYTHONPATH=src:. python -m pytest tests/closeout tests/negative -q --basetemp=.pytest-tmp-v2071e-closeout-negative`
- [ ] Run broad regression:
  - `PYTHONPATH=src:. python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/proving tests/closeout tests/negative -q --basetemp=.pytest-tmp-v2071e-all`
- [ ] Update backlog, acceptance criteria, project log, and INDEX only after verification passes.

---

## Self-review Checklist

- [ ] No optional resolver path exists.
- [ ] No production filesystem payload resolver exists.
- [ ] No legacy short ProcessAudit artifact/content ref is accepted.
- [ ] CloseoutPackage graph_version overflow and underflow both fail with the same strict-boundary error.
- [ ] Payload manifest hashes are recomputed from resolver content, not only ref coverage.
- [ ] Namespaced refs are exact full-string matches, not prefix-only checks.
- [ ] run_id is explicit in newly generated ProcessAudit artifact/content refs and CloseoutPackage refs.
- [ ] Documentation is updated only after tests prove completion.
