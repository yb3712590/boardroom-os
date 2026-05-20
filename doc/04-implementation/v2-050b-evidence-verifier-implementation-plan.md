# V2-050B EvidenceVerifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement V2-050B EvidenceVerifier（证据验证器） so a single EvidenceClaim（证据声明） can become VerifiedEvidence（已验证证据） only after artifact/hash/provider/command/fallback facts are verified fail-closed.

**Architecture:** Add one focused module, `src/boardroom_os/evidence/verifier.py`, containing value objects, per-claim ArtifactManifest（产物清单）, EvidencePurposePolicy（证据用途策略）, verification input/result models, and EvidenceVerifier（证据验证器） logic. Keep V2-050B strictly per-claim: it emits VerifiedEvidence（已验证证据） or blockers, not FinalEvidenceTable（最终证据表） aggregation.

**Tech Stack:** Python 3, Pydantic BaseModel（Pydantic 模型）, pytest, existing Boardroom OS V2 contracts/execution/evidence models.

---

## File Structure

- Create `src/boardroom_os/evidence/verifier.py`
  - Own all V2-050B verifier models and verification logic.
  - Do not modify `EvidenceObligation`（证据义务） or `required_verifier`（必需验证器） semantics.
- Modify `src/boardroom_os/evidence/__init__.py`
  - Export verifier public types.
- Create `tests/negative/test_synthetic_evidence_rejected.py`
  - Negative/fail-closed tests first.
- Create `tests/evidence/test_evidence_verifier.py`
  - Happy-path and serialization tests.
- Modify `doc/04-implementation/backlog.md`
  - Only after implementation and verification: mark V2-050B DONE, advance current task to V2-050C, update counts.
- Modify `doc/04-implementation/acceptance-criteria.md`
  - Only after implementation and verification: close AC-V2-EXECUTION-003 in Phase 3; leave AC-V2-EVIDENCE-002 open.
- Modify `doc/05-project-log/2026-05.md`
  - Add one V2-050B completion entry with exact verification commands.

---

### Task 1: Add negative tests for verifier input and artifact/hash gates

**Files:**
- Create: `tests/negative/test_synthetic_evidence_rejected.py`
- No production code yet.

- [ ] **Step 1: Write failing tests for missing artifact/hash/provider/contract facts**

Add initial tests for: missing artifact manifest entry, artifact without sha256, malformed sha256, provider zero-attempt, failed provider attempt, acceptance ref outside active contract, and inactive acceptance contract.

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/negative/test_synthetic_evidence_rejected.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'boardroom_os.evidence.verifier'`.

---

### Task 2: Implement verifier value objects and basic blockers

**Files:**
- Create: `src/boardroom_os/evidence/verifier.py`
- Modify: `src/boardroom_os/evidence/__init__.py`
- Test: `tests/negative/test_synthetic_evidence_rejected.py`

- [ ] **Step 1: Create verifier model skeleton**

Implement:

- `EvidenceVerificationError`
- `VerifiedEvidenceRef`
- `ArtifactSha256`
- `FallbackDecisionRecordedRef`
- `ArtifactManifestEntry`
- `ArtifactManifest`
- `EvidencePurposeRule`
- `EvidencePurposePolicy`
- `VerifiedArtifact`
- `EvidenceVerificationBlockerCode`
- `EvidenceVerificationBlocker`
- `VerifiedEvidence`
- `EvidenceVerificationInput`
- `EvidenceVerificationResult`
- `EvidenceVerifier`

Key rules:

- sha256 must be 64 lowercase hex chars.
- ArtifactManifest is per-claim and rejects empty or duplicate entries.
- EvidencePurposePolicy only consumes explicit rules; it does not derive them.
- EvidenceVerifier returns VerifiedEvidence only if no blockers exist.
- Do not whitelist `required_verifier`; preserve contract-derived business strategy value.

- [ ] **Step 2: Export verifier symbols**

Update `src/boardroom_os/evidence/__init__.py` to export new public verifier types.

- [ ] **Step 3: Run Task 1 tests**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/negative/test_synthetic_evidence_rejected.py -q
```

Expected: PASS for the initial tests.

---

### Task 3: Add negative tests for obligation, purpose policy, command run, and primary/fallback attempt mismatch

**Files:**
- Modify: `tests/negative/test_synthetic_evidence_rejected.py`
- Modify: `src/boardroom_os/evidence/verifier.py`

- [ ] **Step 1: Add negative tests**

Add tests named:

1. `test_verifier_rejects_evidence_obligation_ref_mismatch`
2. `test_verifier_rejects_acceptance_refs_mismatch`
3. `test_verifier_rejects_source_surface_refs_mismatch`
4. `test_verifier_rejects_required_artifact_type_mismatch`
5. `test_verifier_rejects_purpose_artifact_type_mismatch`
6. `test_verifier_rejects_manifest_with_extra_artifact_ref`
7. `test_verifier_rejects_synthetic_verification_without_run_record`
8. `test_verifier_rejects_failed_verification_run`
9. `test_verifier_rejects_verification_run_without_stdout_stderr_hashes`
10. `test_verifier_rejects_verification_run_artifact_ref_mismatch`
11. `test_verifier_rejects_primary_claim_with_fallback_attempt`

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/negative/test_synthetic_evidence_rejected.py -q
```

Expected: FAIL on newly added cases, especially missing verification run and attempt outcome checks.

- [ ] **Step 3: Implement minimal verifier checks**

Implement checks for:

- EvidenceObligation alignment.
- Purpose policy rule presence and purpose allowance.
- Per-claim manifest extra artifact refs.
- ProviderAttempt outcome mismatch between primary/fallback claims.
- VerificationRun existence, status, id matching, and stdout/stderr artifact refs.

- [ ] **Step 4: Run tests**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/negative/test_synthetic_evidence_rejected.py -q
```

Expected: PASS for Task 1 and Task 3 negative tests.

---

### Task 4: Add fallback negative tests and implement fallback verification

**Files:**
- Modify: `tests/negative/test_synthetic_evidence_rejected.py`
- Modify: `src/boardroom_os/evidence/verifier.py`

- [ ] **Step 1: Add fallback tests**

Add tests named:

1. `test_verifier_rejects_primary_claim_with_fallback_decision_record`
2. `test_verifier_rejects_fallback_claim_with_primary_attempt`
3. `test_verifier_rejects_fallback_claim_without_registry`
4. `test_verifier_rejects_fallback_claim_with_unresolved_policy`
5. `test_verifier_rejects_fallback_claim_without_decision_record`
6. `test_verifier_rejects_fallback_claim_without_decision_recorded_ref`
7. `test_verifier_rejects_fallback_decision_record_scope_mismatch`
8. `test_verifier_rejects_fallback_decision_allowed_false`
9. `test_verifier_uses_verified_at_for_fallback_decision_evaluation`
10. `test_verifier_uses_evaluate_fallback_claim_once_with_full_scope`

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/negative/test_synthetic_evidence_rejected.py -q
```

Expected: FAIL on fallback-specific blocker expectations.

- [ ] **Step 3: Implement fallback checks**

Implement checks for:

- Primary claim must not include fallback decision lineage.
- Fallback claim requires registry, decision record, and decision recorded ref.
- Registry must resolve claim fallback policy ref.
- Verifier must call `evaluate_fallback_claim` once with full claim scope.
- Verifier must pass `EvidenceVerificationInput.verified_at` as `evaluated_at`.
- Supplied `FallbackDecisionRecord` must equal expected record.
- `allowed=False` blocks VerifiedEvidence.

- [ ] **Step 4: Run negative tests**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/negative/test_synthetic_evidence_rejected.py -q
```

Expected: PASS.

---

### Task 5: Add happy path tests and finish verified evidence shape

**Files:**
- Create: `tests/evidence/test_evidence_verifier.py`
- Modify: `src/boardroom_os/evidence/verifier.py`

- [ ] **Step 1: Write happy-path tests**

Add tests named:

1. `test_primary_work_product_claim_becomes_verified_evidence`
2. `test_command_verification_run_claim_becomes_verified_evidence`
3. `test_allowed_deterministic_fallback_claim_becomes_verified_evidence`
4. `test_blocked_fallback_decision_returns_auditable_blocker`
5. `test_verified_evidence_uses_deterministic_default_id`
6. `test_verified_evidence_serializes_as_audit_friendly_json`
7. `test_verifier_result_is_success_or_blockers_not_both`

- [ ] **Step 2: Run happy tests**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/evidence/test_evidence_verifier.py -q
```

Expected: PASS.

- [ ] **Step 3: Run targeted regression**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/evidence/test_evidence_claim.py tests/evidence/test_fallback_policy_registry.py tests/evidence/test_evidence_verifier.py tests/negative/test_synthetic_evidence_rejected.py tests/negative/test_fallback_registry_fail_closed.py -q
```

Expected: PASS.

---

### Task 6: Run full verification and fix integration regressions

**Files:**
- Modify only files needed to fix failures from prior tasks.

- [ ] **Step 1: Run full relevant suite**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/negative -q
```

Expected: PASS. If it fails, fix only the failing V2-050B integration issue. Do not modify unrelated contract/reducer/runtime semantics.

- [ ] **Step 2: Run spec-required commands again**

Run:

```bash
PYTHONPATH="src:." python -m pytest tests/negative/test_synthetic_evidence_rejected.py -q
PYTHONPATH="src:." python -m pytest tests/evidence/test_evidence_verifier.py -q
PYTHONPATH="src:." python -m pytest tests/evidence/test_evidence_claim.py tests/evidence/test_fallback_policy_registry.py tests/evidence/test_evidence_verifier.py tests/negative/test_synthetic_evidence_rejected.py tests/negative/test_fallback_registry_fail_closed.py -q
PYTHONPATH="src:." python -m pytest tests/contracts tests/reducers tests/execution tests/evidence tests/negative -q
```

Expected: all PASS.

---

### Task 7: Update backlog, acceptance criteria, and project log after verification

**Files:**
- Modify: `doc/04-implementation/backlog.md`
- Modify: `doc/04-implementation/acceptance-criteria.md`
- Modify: `doc/05-project-log/2026-05.md`

- [ ] **Step 1: Update `backlog.md`**

Make these exact semantic changes:

- Top TL;DR: `当前未完成工作包` from `V2-050B` to `V2-050C`.
- Top TL;DR current focus: describe FinalEvidenceTable（最终证据表） as next focus.
- Progress table: Phase 5 from `2 / 7` to `3 / 7`.
- Progress table total from `30 / 53` to `31 / 53`.
- V2-050B status from its current pending state to `DONE`.
- Add completion evidence under V2-050B with the exact test commands and pass counts from Task 6.

- [ ] **Step 2: Update `acceptance-criteria.md`**

Make these exact semantic changes:

- In Phase 3, check AC-V2-EXECUTION-003.
- In Phase 3 “进入 Phase 4 前置”, check “上述 AC checkbox 全部勾选”.
- In Phase 5, update `V2-050A ~ V2-050F 七个工作包全部 DONE（含 V2-050A1；当前 2/7）` to current `3/7` wording.
- Do not check AC-V2-EVIDENCE-002; it waits for V2-060C SourceInventory（源码清单） lineage.

- [ ] **Step 3: Update `doc/05-project-log/2026-05.md`**

Add one entry for `2026-05-20 — V2-050B` with exact verification commands and pass counts.

- [ ] **Step 4: Run doc diff check**

Run:

```bash
git diff -- doc/04-implementation/backlog.md doc/04-implementation/acceptance-criteria.md doc/05-project-log/2026-05.md
```

Expected: only V2-050B completion protocol updates.

---

## Self-Review Checklist

- Spec coverage:
  - Per-claim verification: Tasks 1-5.
  - Artifact/hash gates: Tasks 1-2.
  - Provider attempt gates: Tasks 1-3.
  - VerificationRun command gates: Task 3 and Task 5.
  - Active contract and obligation alignment: Tasks 1 and 3.
  - EvidencePurposePolicy consumption only: Tasks 1-3.
  - Fallback registry/decision/evaluated_at lineage: Task 4 and Task 5.
  - No FinalEvidenceTable aggregation: all tasks keep output to single VerifiedEvidence or blockers.
  - Completion protocol docs: Task 7.
- Placeholder scan: no placeholder markers are used as instructions.
- Type consistency:
  - `EvidenceClaim`（证据声明）、`ProviderAttempt`（模型调用尝试记录）、`VerificationRun`（验证运行）, `FallbackDecisionRecord`（降级判定记录） names match existing modules.
  - `required_verifier`（必需验证器） is not changed or white-listed.
  - `verified_at` is the only datetime passed to fallback decision re-evaluation.
