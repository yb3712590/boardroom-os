# Round 7B Capability Assignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace scheduler assignment eligibility with required-capabilities + actor eligibility, add scoped exclusions, and emit explicit no-eligible-actor diagnostics.

**Architecture:** Add a focused `assignment_resolver` module that knows only actors, required capabilities, active leases, provider pause state, and scoped exclusions. Keep `ticket_handlers.run_scheduler_tick()` as orchestration: it compiles legacy ticket inputs into required capabilities, calls the resolver, and writes the existing lease or diagnostic events. Do not introduce Assignment/Lease split events in this plan; Round 7C owns that migration.

**Tech Stack:** Python 3, dataclasses, pytest, SQLite-backed `ControlPlaneRepository`, existing event/projection model.

---

## File Structure

- Create `backend/app/core/assignment_resolver.py`
  - Owns capability-driven eligibility, scoped exclusion normalization, candidate diagnostics, and no-eligible suggested actions.
  - Does not import `ticket_handlers.py` and does not inspect role names or ticket summaries.
- Create `backend/tests/test_assignment_resolver.py`
  - Fast unit tests for resolver behavior with plain dicts.
- Modify `backend/app/core/execution_targets.py`
  - Add helper to compile runtime required capabilities from ticket spec using RoleTemplate -> Capability contract only as migration input.
- Modify `backend/app/core/ticket_handlers.py`
  - Replace scheduler worker candidate resolution and role matching with actor projections + resolver.
  - Preserve existing `EVENT_TICKET_LEASED` write path, using selected `actor_id` as current `leased_by` until Round 7C separates assignment/lease identity.
  - Upgrade no-eligible diagnostic payload.
  - Stop copying unscoped legacy `excluded_employee_ids` in retry/rework follow-ups.
- Modify `backend/tests/test_scheduler_runner.py`
  - Migrate old scheduler exclusion tests to actor/capability fixtures.
  - Add no-eligible diagnostic integration coverage.
- Modify `backend/tests/test_api.py`
  - Keep actor projection persistence tests; add focused API/repository assertions only if scheduler tests need shared fixture helpers.
- Modify `doc/refactor/planning/06-actor-role-lifecycle.md`
  - Document 7B implementation state, scoped exclusion semantics, no-eligible diagnostic output, and 7C lease dependency.
- Modify `doc/refactor/planning/09-refactor-plan.md`
  - Mark 7B actor assignment tasks complete and note 7C lease split remains.
- Modify `doc/refactor/planning/10-refactor-acceptance-criteria.md`
  - Check only Phase 3 items backed by tests: scoped exclusions and no-eligible output; keep Assignment/Lease separation unchecked.

---

### Task 1: Add resolver unit tests

**Files:**
- Create: `backend/tests/test_assignment_resolver.py`
- Create later in Task 2: `backend/app/core/assignment_resolver.py`

- [ ] **Step 1: Write failing resolver tests**

Create `backend/tests/test_assignment_resolver.py` with this content:

```python
from __future__ import annotations

from app.core.assignment_resolver import (
    EXCLUSION_SCOPE_CAPABILITY,
    EXCLUSION_SCOPE_NODE,
    EXCLUSION_SCOPE_TICKET,
    EXCLUSION_SCOPE_WORKFLOW,
    NO_ELIGIBLE_ACTOR_REASON_CODE,
    resolve_assignment,
)
from app.core.constants import ACTOR_STATUS_ACTIVE, ACTOR_STATUS_SUSPENDED


def _actor(actor_id: str, capabilities: list[str], *, status: str = ACTOR_STATUS_ACTIVE) -> dict:
    return {
        "actor_id": actor_id,
        "status": status,
        "capability_set": capabilities,
        "provider_preferences": {"provider_id": f"prov_{actor_id}"},
    }


def test_resolver_selects_active_actor_with_required_capabilities() -> None:
    result = resolve_assignment(
        ticket_id="tkt_backend",
        workflow_id="wf_assign",
        node_id="node_backend",
        required_capabilities=["source.modify.backend", "test.run.backend"],
        actors=[
            _actor("actor_frontend", ["source.modify.application", "test.run.application"]),
            _actor("actor_backend", ["source.modify.backend", "test.run.backend", "evidence.write.test"]),
        ],
        active_lease_actor_ids=set(),
        paused_provider_ids=set(),
        scoped_exclusions=[],
    )

    assert result.selected_actor_id == "actor_backend"
    assert result.diagnostic_payload is None


def test_resolver_rejects_actor_without_required_capabilities_even_when_available() -> None:
    result = resolve_assignment(
        ticket_id="tkt_backend",
        workflow_id="wf_assign",
        node_id="node_backend",
        required_capabilities=["source.modify.backend"],
        actors=[_actor("actor_frontend", ["source.modify.application"])],
        active_lease_actor_ids=set(),
        paused_provider_ids=set(),
        scoped_exclusions=[],
    )

    assert result.selected_actor_id is None
    assert result.diagnostic_payload is not None
    assert result.diagnostic_payload["reason_code"] == NO_ELIGIBLE_ACTOR_REASON_CODE
    assert result.diagnostic_payload["required_capabilities"] == ["source.modify.backend"]
    assert result.diagnostic_payload["candidate_details"][0]["missing_capabilities"] == ["source.modify.backend"]
    assert "CREATE_ACTOR" in result.diagnostic_payload["suggested_actions"]
    assert "BLOCK_NODE_NO_CAPABLE_ACTOR" in result.diagnostic_payload["suggested_actions"]


def test_resolver_applies_only_matching_scoped_exclusions() -> None:
    actors = [
        _actor("actor_backend_primary", ["source.modify.backend"]),
        _actor("actor_backend_backup", ["source.modify.backend"]),
    ]

    result = resolve_assignment(
        ticket_id="tkt_backend_current",
        workflow_id="wf_assign",
        node_id="node_backend_current",
        required_capabilities=["source.modify.backend"],
        actors=actors,
        active_lease_actor_ids=set(),
        paused_provider_ids=set(),
        scoped_exclusions=[
            {
                "actor_id": "actor_backend_primary",
                "scope": EXCLUSION_SCOPE_TICKET,
                "ticket_id": "tkt_unrelated",
                "reason": "unrelated ticket retry",
            },
            {
                "actor_id": "actor_backend_primary",
                "scope": EXCLUSION_SCOPE_NODE,
                "node_id": "node_backend_current",
                "reason": "current node exclusion",
            },
        ],
    )

    assert result.selected_actor_id == "actor_backend_backup"
    primary_detail = next(
        detail for detail in result.candidate_details if detail["actor_id"] == "actor_backend_primary"
    )
    assert primary_detail["excluded"] is True
    assert primary_detail["exclusion_matches"] == [
        {
            "scope": EXCLUSION_SCOPE_NODE,
            "reason": "current node exclusion",
            "capability": None,
            "ticket_id": None,
            "node_id": "node_backend_current",
            "workflow_id": None,
        }
    ]


def test_resolver_scopes_capability_and_workflow_exclusions() -> None:
    actors = [
        _actor("actor_backend_primary", ["source.modify.backend", "test.run.backend"]),
        _actor("actor_backend_backup", ["source.modify.backend", "test.run.backend"]),
    ]

    capability_result = resolve_assignment(
        ticket_id="tkt_backend",
        workflow_id="wf_assign",
        node_id="node_backend",
        required_capabilities=["source.modify.backend"],
        actors=actors,
        active_lease_actor_ids=set(),
        paused_provider_ids=set(),
        scoped_exclusions=[
            {
                "actor_id": "actor_backend_primary",
                "scope": EXCLUSION_SCOPE_CAPABILITY,
                "capability": "test.run.backend",
                "reason": "different capability",
            }
        ],
    )
    assert capability_result.selected_actor_id == "actor_backend_primary"

    workflow_result = resolve_assignment(
        ticket_id="tkt_backend",
        workflow_id="wf_assign",
        node_id="node_backend",
        required_capabilities=["source.modify.backend"],
        actors=actors,
        active_lease_actor_ids=set(),
        paused_provider_ids=set(),
        scoped_exclusions=[
            {
                "actor_id": "actor_backend_primary",
                "scope": EXCLUSION_SCOPE_WORKFLOW,
                "workflow_id": "wf_assign",
                "reason": "workflow incident",
            }
        ],
    )
    assert workflow_result.selected_actor_id == "actor_backend_backup"


def test_resolver_marks_status_busy_and_provider_paused_reasons() -> None:
    result = resolve_assignment(
        ticket_id="tkt_backend",
        workflow_id="wf_assign",
        node_id="node_backend",
        required_capabilities=["source.modify.backend"],
        actors=[
            _actor("actor_suspended", ["source.modify.backend"], status=ACTOR_STATUS_SUSPENDED),
            _actor("actor_busy", ["source.modify.backend"]),
            _actor("actor_paused", ["source.modify.backend"]),
        ],
        active_lease_actor_ids={"actor_busy"},
        paused_provider_ids={"prov_actor_paused"},
        scoped_exclusions=[],
    )

    assert result.selected_actor_id is None
    details = {detail["actor_id"]: detail for detail in result.diagnostic_payload["candidate_details"]}
    assert details["actor_suspended"]["status_eligible"] is False
    assert details["actor_busy"]["busy"] is True
    assert details["actor_paused"]["provider_paused"] is True
```

- [ ] **Step 2: Run tests to verify they fail because resolver does not exist**

Run:

```bash
pytest backend/tests/test_assignment_resolver.py -q
```

Expected: FAIL during import with `ModuleNotFoundError: No module named 'app.core.assignment_resolver'` or missing symbols.

---

### Task 2: Implement resolver module

**Files:**
- Create: `backend/app/core/assignment_resolver.py`
- Test: `backend/tests/test_assignment_resolver.py`

- [ ] **Step 1: Add minimal resolver implementation**

Create `backend/app/core/assignment_resolver.py` with this content:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from app.core.constants import ACTOR_STATUS_ACTIVE

EXCLUSION_SCOPE_ATTEMPT = "attempt"
EXCLUSION_SCOPE_TICKET = "ticket"
EXCLUSION_SCOPE_NODE = "node"
EXCLUSION_SCOPE_CAPABILITY = "capability"
EXCLUSION_SCOPE_WORKFLOW = "workflow"
NO_ELIGIBLE_ACTOR_REASON_CODE = "NO_ELIGIBLE_ACTOR"
NO_ELIGIBLE_ACTOR_SUGGESTED_ACTIONS = [
    "CREATE_ACTOR",
    "REASSIGN_EXECUTOR",
    "REQUEST_HUMAN_DECISION",
    "BLOCK_NODE_NO_CAPABLE_ACTOR",
]


@dataclass(frozen=True)
class AssignmentResolution:
    selected_actor_id: str | None
    selected_actor: dict[str, Any] | None
    candidate_details: list[dict[str, Any]]
    diagnostic_payload: dict[str, Any] | None


def _dedupe_text_values(values: Iterable[Any]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        deduped.append(normalized)
        seen.add(normalized)
    return deduped


def _actor_provider_id(actor: dict[str, Any]) -> str | None:
    preferences = actor.get("provider_preferences") if isinstance(actor, dict) else None
    if isinstance(preferences, dict):
        provider_id = str(preferences.get("provider_id") or preferences.get("preferred_provider_id") or "").strip()
        if provider_id:
            return provider_id
    provider_binding_refs = actor.get("provider_binding_refs") if isinstance(actor, dict) else None
    if isinstance(provider_binding_refs, list) and provider_binding_refs:
        provider_id = str(provider_binding_refs[0] or "").strip()
        return provider_id or None
    return None


def _normalize_exclusion(entry: dict[str, Any]) -> dict[str, Any] | None:
    actor_id = str(entry.get("actor_id") or entry.get("employee_id") or "").strip()
    scope = str(entry.get("scope") or "").strip().lower()
    if not actor_id or scope not in {
        EXCLUSION_SCOPE_ATTEMPT,
        EXCLUSION_SCOPE_TICKET,
        EXCLUSION_SCOPE_NODE,
        EXCLUSION_SCOPE_CAPABILITY,
        EXCLUSION_SCOPE_WORKFLOW,
    }:
        return None
    return {
        "actor_id": actor_id,
        "scope": scope,
        "reason": str(entry.get("reason") or "").strip() or None,
        "capability": str(entry.get("capability") or "").strip() or None,
        "ticket_id": str(entry.get("ticket_id") or "").strip() or None,
        "node_id": str(entry.get("node_id") or "").strip() or None,
        "workflow_id": str(entry.get("workflow_id") or "").strip() or None,
        "attempt_no": int(entry["attempt_no"]) if entry.get("attempt_no") is not None else None,
    }


def _exclusion_matches(
    exclusion: dict[str, Any],
    *,
    actor_id: str,
    ticket_id: str,
    workflow_id: str,
    node_id: str,
    required_capabilities: set[str],
    attempt_no: int | None,
) -> bool:
    if exclusion["actor_id"] != actor_id:
        return False
    scope = exclusion["scope"]
    if scope == EXCLUSION_SCOPE_ATTEMPT:
        return (
            exclusion.get("ticket_id") in {None, ticket_id}
            and exclusion.get("attempt_no") in {None, attempt_no}
        )
    if scope == EXCLUSION_SCOPE_TICKET:
        return exclusion.get("ticket_id") in {None, ticket_id}
    if scope == EXCLUSION_SCOPE_NODE:
        return exclusion.get("node_id") in {None, node_id}
    if scope == EXCLUSION_SCOPE_CAPABILITY:
        capability = exclusion.get("capability")
        return capability is None or capability in required_capabilities
    if scope == EXCLUSION_SCOPE_WORKFLOW:
        return exclusion.get("workflow_id") in {None, workflow_id}
    return False


def resolve_assignment(
    *,
    ticket_id: str,
    workflow_id: str,
    node_id: str,
    required_capabilities: list[str],
    actors: list[dict[str, Any]],
    active_lease_actor_ids: set[str],
    paused_provider_ids: set[str],
    scoped_exclusions: list[dict[str, Any]],
    attempt_no: int | None = None,
) -> AssignmentResolution:
    normalized_required_capabilities = _dedupe_text_values(required_capabilities)
    required_capability_set = set(normalized_required_capabilities)
    normalized_exclusions = [
        exclusion
        for exclusion in (_normalize_exclusion(entry) for entry in scoped_exclusions)
        if exclusion is not None
    ]
    candidate_details: list[dict[str, Any]] = []
    selected_actor: dict[str, Any] | None = None

    for actor in actors:
        actor_id = str(actor.get("actor_id") or "").strip()
        if not actor_id:
            continue
        actor_capabilities = _dedupe_text_values(actor.get("capability_set") or [])
        actor_capability_set = set(actor_capabilities)
        missing_capabilities = sorted(required_capability_set - actor_capability_set)
        status = str(actor.get("status") or "").strip()
        provider_id = _actor_provider_id(actor)
        exclusion_matches = [
            {
                "scope": exclusion["scope"],
                "reason": exclusion.get("reason"),
                "capability": exclusion.get("capability"),
                "ticket_id": exclusion.get("ticket_id"),
                "node_id": exclusion.get("node_id"),
                "workflow_id": exclusion.get("workflow_id"),
            }
            for exclusion in normalized_exclusions
            if _exclusion_matches(
                exclusion,
                actor_id=actor_id,
                ticket_id=ticket_id,
                workflow_id=workflow_id,
                node_id=node_id,
                required_capabilities=required_capability_set,
                attempt_no=attempt_no,
            )
        ]
        status_eligible = status == ACTOR_STATUS_ACTIVE
        busy = actor_id in active_lease_actor_ids
        provider_paused = provider_id in paused_provider_ids if provider_id else False
        eligible = (
            status_eligible
            and not missing_capabilities
            and not busy
            and not provider_paused
            and not exclusion_matches
        )
        detail = {
            "actor_id": actor_id,
            "employee_id": actor.get("employee_id"),
            "status": status,
            "status_eligible": status_eligible,
            "capability_set": actor_capabilities,
            "missing_capabilities": missing_capabilities,
            "busy": busy,
            "provider_id": provider_id,
            "provider_paused": provider_paused,
            "excluded": bool(exclusion_matches),
            "exclusion_matches": exclusion_matches,
            "eligible": eligible,
        }
        candidate_details.append(detail)
        if eligible and selected_actor is None:
            selected_actor = actor

    if selected_actor is not None:
        return AssignmentResolution(
            selected_actor_id=str(selected_actor["actor_id"]),
            selected_actor=selected_actor,
            candidate_details=candidate_details,
            diagnostic_payload=None,
        )

    return AssignmentResolution(
        selected_actor_id=None,
        selected_actor=None,
        candidate_details=candidate_details,
        diagnostic_payload={
            "ticket_id": ticket_id,
            "workflow_id": workflow_id,
            "node_id": node_id,
            "reason_code": NO_ELIGIBLE_ACTOR_REASON_CODE,
            "required_capabilities": normalized_required_capabilities,
            "candidate_summary": {
                "total_candidate_count": len(candidate_details),
                "eligible_count": 0,
                "missing_capability_count": sum(1 for detail in candidate_details if detail["missing_capabilities"]),
                "excluded_count": sum(1 for detail in candidate_details if detail["excluded"]),
                "busy_count": sum(1 for detail in candidate_details if detail["busy"]),
                "provider_paused_count": sum(1 for detail in candidate_details if detail["provider_paused"]),
                "inactive_count": sum(1 for detail in candidate_details if not detail["status_eligible"]),
            },
            "candidate_details": candidate_details,
            "suggested_actions": list(NO_ELIGIBLE_ACTOR_SUGGESTED_ACTIONS),
        },
    )
```

- [ ] **Step 2: Run resolver unit tests**

Run:

```bash
pytest backend/tests/test_assignment_resolver.py -q
```

Expected: PASS.

- [ ] **Step 3: Commit resolver tests and implementation**

Run:

```bash
git add backend/app/core/assignment_resolver.py backend/tests/test_assignment_resolver.py
git commit -m "refactor(actors): 增加能力派工解析器"
```

Expected: commit succeeds.

---

### Task 3: Compile ticket required capabilities without runtime role eligibility

**Files:**
- Modify: `backend/app/core/execution_targets.py:127-138`, `backend/app/core/execution_targets.py:359-374`
- Test: `backend/tests/test_execution_targets.py`

- [ ] **Step 1: Add failing capability compilation tests**

Append these tests to `backend/tests/test_execution_targets.py`:

```python
from app.core.execution_targets import compile_required_capabilities_for_ticket_spec
from app.core.output_schemas import SOURCE_CODE_DELIVERY_SCHEMA_REF


def test_compile_required_capabilities_prefers_explicit_contract_capabilities() -> None:
    capabilities = compile_required_capabilities_for_ticket_spec(
        {
            "role_profile_ref": "frontend_engineer_primary",
            "output_schema_ref": SOURCE_CODE_DELIVERY_SCHEMA_REF,
            "execution_contract": {
                "required_capabilities": ["source.modify.backend", "test.run.backend"],
                "required_capability_tags": ["implementation"],
            },
        }
    )

    assert capabilities == ["source.modify.backend", "test.run.backend"]


def test_compile_required_capabilities_uses_role_template_only_as_migration_input() -> None:
    capabilities = compile_required_capabilities_for_ticket_spec(
        {
            "role_profile_ref": "backend_engineer_primary",
            "output_schema_ref": SOURCE_CODE_DELIVERY_SCHEMA_REF,
            "execution_contract": {
                "execution_target_ref": "execution_target:backend_build",
                "required_capability_tags": ["structured_output", "implementation"],
            },
        }
    )

    assert capabilities == [
        "source.modify.backend",
        "test.run.backend",
        "evidence.write.test",
        "evidence.write.git",
        "docs.update.delivery",
    ]
```

If imports already exist in `test_execution_targets.py`, merge these imports instead of duplicating them.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest backend/tests/test_execution_targets.py::test_compile_required_capabilities_prefers_explicit_contract_capabilities backend/tests/test_execution_targets.py::test_compile_required_capabilities_uses_role_template_only_as_migration_input -q
```

Expected: FAIL with `ImportError` or `NameError` for `compile_required_capabilities_for_ticket_spec`.

- [ ] **Step 3: Add capability compilation helper**

In `backend/app/core/execution_targets.py`, after `build_role_template_capability_contract()`, add:

```python
def _dedupe_capability_values(values: list[Any] | tuple[Any, ...]) -> list[str]:
    capabilities: list[str] = []
    seen: set[str] = set()
    for value in values:
        capability = str(value or "").strip()
        if not capability or capability in seen:
            continue
        capabilities.append(capability)
        seen.add(capability)
    return capabilities


def compile_required_capabilities_for_ticket_spec(created_spec: dict[str, Any] | None) -> list[str]:
    if not isinstance(created_spec, dict):
        return []
    execution_contract = created_spec.get("execution_contract")
    if isinstance(execution_contract, dict):
        explicit_capabilities = _dedupe_capability_values(
            list(execution_contract.get("required_capabilities") or [])
        )
        if explicit_capabilities:
            return explicit_capabilities

    role_template_contract = build_role_template_capability_contract(
        str(created_spec.get("role_profile_ref") or "").strip()
    )
    if role_template_contract is not None:
        return _dedupe_capability_values(list(role_template_contract.get("capability_set") or []))
    return []
```

Do not change `infer_execution_contract_payload()` in this task; it remains a legacy execution-target compiler.

- [ ] **Step 4: Run execution target tests**

Run:

```bash
pytest backend/tests/test_execution_targets.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit capability compilation helper**

Run:

```bash
git add backend/app/core/execution_targets.py backend/tests/test_execution_targets.py
git commit -m "refactor(actors): 编译票据所需能力"
```

Expected: commit succeeds.

---

### Task 4: Integrate resolver into scheduler leasing

**Files:**
- Modify: `backend/app/core/ticket_handlers.py:129-133`, `backend/app/core/ticket_handlers.py:4592-4782`, `backend/app/core/ticket_handlers.py:5120-5416`
- Test: `backend/tests/test_scheduler_runner.py`

- [ ] **Step 1: Add actor seeding helper in scheduler tests**

In `backend/tests/test_scheduler_runner.py`, update the constants import near the top to include `EVENT_ACTOR_ENABLED` and `ACTOR_STATUS_ACTIVE` if they are not already imported:

```python
from app.core.constants import (
    ACTOR_STATUS_ACTIVE,
    EVENT_ACTOR_ENABLED,
    BLOCKING_REASON_CONTEXT_COMPILATION_BLOCKED,
    EVENT_INCIDENT_OPENED,
    EVENT_SCHEDULER_ORCHESTRATION_RECORDED,
    EVENT_TICKET_CREATED,
)
```

Then add this helper near `_ticket_create_payload()`:

```python
def _enable_actor(repository, *, actor_id: str, workflow_id: str, capabilities: list[str]) -> None:
    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_ACTOR_ENABLED,
            actor_type="system",
            actor_id="test-seed",
            workflow_id=workflow_id,
            idempotency_key=f"test-enable-actor:{workflow_id}:{actor_id}",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "actor_id": actor_id,
                "employee_id": actor_id,
                "capability_set": capabilities,
                "provider_preferences": {"provider_id": OPENAI_COMPAT_PROVIDER_ID},
                "availability": {},
                "created_from_policy": "test",
                "audit_reason": "scheduler assignment test",
            },
            occurred_at=datetime.fromisoformat("2026-04-01T10:00:00+08:00"),
        )
        repository.refresh_projections(connection)
```

- [ ] **Step 2: Add failing scheduler integration test for actor capability selection**

Append to `backend/tests/test_scheduler_runner.py`:

```python
def test_scheduler_leases_actor_by_required_capabilities_not_employee_role(client):
    repository = client.app.state.repository
    workflow_id = _project_init(client, goal="Capability assignment")
    ticket_payload = _ticket_create_payload(
        workflow_id=workflow_id,
        ticket_id="tkt_backend_capability_assignment",
        node_id="node_backend_capability_assignment",
        role_profile_ref="backend_engineer_primary",
        output_schema_ref="source_code_delivery",
    )
    _enable_actor(
        repository,
        actor_id="actor_frontend_only",
        workflow_id=workflow_id,
        capabilities=["source.modify.application", "test.run.application"],
    )
    _enable_actor(
        repository,
        actor_id="actor_backend_capable",
        workflow_id=workflow_id,
        capabilities=[
            "source.modify.backend",
            "test.run.backend",
            "evidence.write.test",
            "evidence.write.git",
            "docs.update.delivery",
        ],
    )

    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_TICKET_CREATED,
            actor_type="system",
            actor_id="test-seed",
            workflow_id=workflow_id,
            idempotency_key="test-ticket-created:backend-capability-assignment",
            causation_id=None,
            correlation_id=workflow_id,
            payload=ticket_payload,
            occurred_at=datetime.fromisoformat("2026-04-01T10:01:00+08:00"),
        )
        repository.refresh_projections(connection)

    run_scheduler_tick(repository, command=SchedulerTickCommand())

    events = repository.list_events_for_ticket("tkt_backend_capability_assignment")
    lease_events = [event for event in events if event["event_type"] == "TICKET_LEASED"]
    assert lease_events[-1]["payload"]["leased_by"] == "actor_backend_capable"
```

- [ ] **Step 3: Run test to verify current scheduler fails or leases old employee path**

Run:

```bash
pytest backend/tests/test_scheduler_runner.py::test_scheduler_leases_actor_by_required_capabilities_not_employee_role -q
```

Expected before implementation: FAIL because scheduler still uses employee worker candidates, not actor projections.

- [ ] **Step 4: Replace scheduler worker helpers with actor helpers**

In `backend/app/core/ticket_handlers.py`, add imports:

```python
from app.core.assignment_resolver import (
    NO_ELIGIBLE_ACTOR_REASON_CODE,
    resolve_assignment,
)
```

Update the existing execution targets import to include `compile_required_capabilities_for_ticket_spec`:

```python
from app.core.execution_targets import (
    compile_required_capabilities_for_ticket_spec,
    employee_supports_execution_contract,
    infer_execution_contract_payload,
    resolve_execution_target_ref_from_ticket_spec,
)
```

Replace `_resolve_scheduler_workers()`, `_worker_is_dispatchable_for_ticket()`, `_build_no_eligible_worker_diagnostic_payload()`, `_record_no_eligible_worker_diagnostic()`, and `_should_relax_singleton_rework_exclusions()` with:

```python
def _resolve_scheduler_actors(
    repository: ControlPlaneRepository,
    connection,
) -> list[dict[str, Any]]:
    return repository.list_actor_projections(
        connection,
        statuses=[ACTOR_STATUS_ACTIVE],
    )


def _active_lease_actor_ids(repository: ControlPlaneRepository, connection) -> set[str]:
    return {
        str(ticket.get("lease_owner") or "").strip()
        for ticket in repository.list_active_ticket_projections(connection)
        if str(ticket.get("lease_owner") or "").strip()
    }


def _paused_provider_ids_for_actors(
    repository: ControlPlaneRepository,
    connection,
    actors: list[dict[str, Any]],
) -> set[str]:
    paused_provider_ids: set[str] = set()
    for actor in actors:
        provider_preferences = actor.get("provider_preferences") or {}
        provider_id = str(provider_preferences.get("provider_id") or provider_preferences.get("preferred_provider_id") or "").strip()
        if provider_id and _is_provider_paused(repository, connection, provider_id):
            paused_provider_ids.add(provider_id)
    return paused_provider_ids


def _build_legacy_scoped_exclusions(created_spec: dict[str, Any]) -> list[dict[str, Any]]:
    ticket_id = str(created_spec.get("ticket_id") or "").strip()
    node_id = str(created_spec.get("node_id") or "").strip()
    workflow_id = str(created_spec.get("workflow_id") or "").strip()
    attempt_no = int(created_spec.get("attempt_no") or 0) or None
    scoped_exclusions: list[dict[str, Any]] = []
    for entry in created_spec.get("scoped_exclusions") or []:
        if isinstance(entry, dict):
            scoped_exclusions.append(dict(entry))
    for employee_id in created_spec.get("excluded_employee_ids") or []:
        actor_id = str(employee_id or "").strip()
        if not actor_id:
            continue
        scoped_exclusions.append(
            {
                "actor_id": actor_id,
                "scope": "ticket",
                "ticket_id": ticket_id,
                "node_id": node_id,
                "workflow_id": workflow_id,
                "attempt_no": attempt_no,
                "reason": "legacy excluded_employee_ids ticket scope",
            }
        )
    return scoped_exclusions


def _record_no_eligible_actor_diagnostic(
    repository: ControlPlaneRepository,
    connection,
    *,
    command_id: str,
    occurred_at: datetime,
    idempotency_key: str,
    diagnostic_payload: dict[str, Any],
) -> bool:
    event = repository.insert_event(
        connection,
        event_type=EVENT_SCHEDULER_LEASE_DIAGNOSTIC_RECORDED,
        actor_type="system",
        actor_id="scheduler",
        workflow_id=str(diagnostic_payload.get("workflow_id") or ""),
        idempotency_key=idempotency_key,
        causation_id=command_id,
        correlation_id=str(diagnostic_payload.get("workflow_id") or ""),
        payload=diagnostic_payload,
        occurred_at=occurred_at,
    )
    return event is not None
```

This replacement intentionally removes role-profile worker matching and singleton rework relaxation.

- [ ] **Step 5: Update scheduler main loop to call resolver**

Inside `run_scheduler_tick()`, replace the early worker candidate setup:

```python
worker_candidates, worker_by_id = _resolve_scheduler_workers(repository, connection, command.workers)
busy_workers = {
    ticket["lease_owner"]
    for ticket in repository.list_active_ticket_projections(connection)
    if ticket.get("lease_owner")
}
```

with:

```python
actor_candidates = _resolve_scheduler_actors(repository, connection)
busy_actor_ids = _active_lease_actor_ids(repository, connection)
paused_provider_ids = _paused_provider_ids_for_actors(repository, connection, actor_candidates)
```

Then replace the block from target role lookup through no-eligible diagnostic, starting at the current lines like:

```python
target_role_profile = created_spec.get("role_profile_ref")
if not target_role_profile:
    continue
lease_timeout_sec = _resolve_ticket_lease_timeout_sec(created_spec)
...
```

with:

```python
required_capabilities = compile_required_capabilities_for_ticket_spec(created_spec)
if not required_capabilities:
    continue
lease_timeout_sec = _resolve_ticket_lease_timeout_sec(created_spec)
assignment = resolve_assignment(
    ticket_id=str(ticket["ticket_id"]),
    workflow_id=str(ticket["workflow_id"]),
    node_id=str(ticket["node_id"]),
    required_capabilities=required_capabilities,
    actors=actor_candidates,
    active_lease_actor_ids=busy_actor_ids,
    paused_provider_ids=paused_provider_ids,
    scoped_exclusions=_build_legacy_scoped_exclusions(created_spec),
    attempt_no=int(created_spec.get("attempt_no") or 0) or None,
)
selected_worker_id = assignment.selected_actor_id
selected_worker_precondition: dict[str, Any] | None = None
if selected_worker_id is not None:
    precondition_result = _evaluate_ticket_execution_precondition(
        repository,
        connection,
        ticket=ticket,
        created_spec=created_spec,
        lease_owner=selected_worker_id,
    )
    if precondition_result is not None and precondition_result["blocked"]:
        _sync_ticket_execution_precondition_state(
            repository,
            connection,
            command_id=command_id,
            occurred_at=received_at,
            workflow_id=ticket["workflow_id"],
            ticket=ticket,
            node_id=ticket["node_id"],
            precondition_result=precondition_result,
            actor_id="scheduler",
        )
        changed_state = True
        continue
    selected_worker_precondition = precondition_result
else:
    diagnostic_payload = dict(assignment.diagnostic_payload or {})
    recorded = _record_no_eligible_actor_diagnostic(
        repository,
        connection,
        command_id=command_id,
        occurred_at=received_at,
        idempotency_key=next_idempotency_key(
            f"lease-diagnostic:{ticket['ticket_id']}:no-eligible-actor"
        ),
        diagnostic_payload=diagnostic_payload,
    )
    if not recorded:
        return _scheduler_duplicate_ack(
            command_id=command_id,
            idempotency_key=idempotency_key,
            received_at=received_at,
        )
    changed_state = True
    continue
```

Keep the existing `selected_worker_precondition` sync guard and `EVENT_TICKET_LEASED` insertion below this block. Change the busy update after lease insertion from:

```python
busy_workers.add(selected_worker_id)
```

to:

```python
busy_actor_ids.add(selected_worker_id)
```

- [ ] **Step 6: Fix missing actor status import**

If `ACTOR_STATUS_ACTIVE` is not imported in `ticket_handlers.py`, add it to the constants import near line 39:

```python
from app.core.constants import (
    ACTOR_STATUS_ACTIVE,
    CIRCUIT_BREAKER_STATE_CLOSED,
    ...
)
```

- [ ] **Step 7: Run the targeted scheduler test**

Run:

```bash
pytest backend/tests/test_scheduler_runner.py::test_scheduler_leases_actor_by_required_capabilities_not_employee_role -q
```

Expected: PASS.

- [ ] **Step 8: Run resolver + scheduler smoke tests**

Run:

```bash
pytest backend/tests/test_assignment_resolver.py backend/tests/test_scheduler_runner.py::test_scheduler_leases_actor_by_required_capabilities_not_employee_role -q
```

Expected: PASS.

Do not commit yet; Task 5 updates exclusion integration tests in the same scheduler area.

---

### Task 5: Migrate scheduler exclusion tests to scoped actor semantics

**Files:**
- Modify: `backend/tests/test_scheduler_runner.py:6004-6393`
- Modify if needed: `backend/app/core/ticket_handlers.py`

- [ ] **Step 1: Replace excluded-employee backup test with scoped actor test**

Replace existing `test_scheduler_skips_excluded_employee_ids_and_leases_backup_worker` with:

```python
def test_scheduler_treats_legacy_excluded_employee_ids_as_current_ticket_scope(client):
    repository = client.app.state.repository
    workflow_id = _project_init(client, goal="Scoped exclusion")
    ticket_payload = _ticket_create_payload(
        workflow_id=workflow_id,
        ticket_id="tkt_scoped_exclusion",
        node_id="node_scoped_exclusion",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="source_code_delivery",
        excluded_employee_ids=["actor_frontend_primary"],
    )
    capabilities = [
        "source.modify.application",
        "test.run.application",
        "evidence.write.test",
        "evidence.write.git",
        "docs.update.delivery",
    ]
    _enable_actor(repository, actor_id="actor_frontend_primary", workflow_id=workflow_id, capabilities=capabilities)
    _enable_actor(repository, actor_id="actor_frontend_backup", workflow_id=workflow_id, capabilities=capabilities)

    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_TICKET_CREATED,
            actor_type="system",
            actor_id="test-seed",
            workflow_id=workflow_id,
            idempotency_key="test-ticket-created:scoped-exclusion",
            causation_id=None,
            correlation_id=workflow_id,
            payload=ticket_payload,
            occurred_at=datetime.fromisoformat("2026-04-01T10:01:00+08:00"),
        )
        repository.refresh_projections(connection)

    run_scheduler_tick(repository, command=SchedulerTickCommand())

    lease_events = [
        event
        for event in repository.list_events_for_ticket("tkt_scoped_exclusion")
        if event["event_type"] == "TICKET_LEASED"
    ]
    assert lease_events[-1]["payload"]["leased_by"] == "actor_frontend_backup"
```

- [ ] **Step 2: Replace singleton rework relaxation test with non-pollution test**

Replace existing `test_scheduler_relaxes_excluded_employee_ids_for_single_capable_rework_fix_worker` with:

```python
def test_scheduler_does_not_relax_current_ticket_scoped_exclusion_for_rework(client):
    repository = client.app.state.repository
    workflow_id = _project_init(client, goal="Rework scoped exclusion")
    ticket_payload = _ticket_create_payload(
        workflow_id=workflow_id,
        ticket_id="tkt_rework_scoped_exclusion",
        node_id="node_rework_scoped_exclusion",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="source_code_delivery",
        excluded_employee_ids=["actor_frontend_primary"],
    )
    ticket_payload["ticket_kind"] = "MAKER_REWORK_FIX"
    _enable_actor(
        repository,
        actor_id="actor_frontend_primary",
        workflow_id=workflow_id,
        capabilities=[
            "source.modify.application",
            "test.run.application",
            "evidence.write.test",
            "evidence.write.git",
            "docs.update.delivery",
        ],
    )

    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_TICKET_CREATED,
            actor_type="system",
            actor_id="test-seed",
            workflow_id=workflow_id,
            idempotency_key="test-ticket-created:rework-scoped-exclusion",
            causation_id=None,
            correlation_id=workflow_id,
            payload=ticket_payload,
            occurred_at=datetime.fromisoformat("2026-04-01T10:01:00+08:00"),
        )
        repository.refresh_projections(connection)

    run_scheduler_tick(repository, command=SchedulerTickCommand())

    diagnostic_events = [
        event
        for event in repository.list_events_for_ticket("tkt_rework_scoped_exclusion")
        if event["event_type"] == "SCHEDULER_LEASE_DIAGNOSTIC_RECORDED"
    ]
    assert diagnostic_events[-1]["payload"]["reason_code"] == "NO_ELIGIBLE_ACTOR"
    assert diagnostic_events[-1]["payload"]["candidate_details"][0]["excluded"] is True
```

- [ ] **Step 3: Update no-eligible diagnostic test expectation**

Find the test that currently asserts `NO_ELIGIBLE_WORKER` near `backend/tests/test_scheduler_runner.py:6382` and update its key assertions to:

```python
assert diagnostic["reason_code"] == "NO_ELIGIBLE_ACTOR"
assert diagnostic["required_capabilities"] == [
    "source.modify.backend",
    "test.run.backend",
    "evidence.write.test",
    "evidence.write.git",
    "docs.update.delivery",
]
assert diagnostic["suggested_actions"] == [
    "CREATE_ACTOR",
    "REASSIGN_EXECUTOR",
    "REQUEST_HUMAN_DECISION",
    "BLOCK_NODE_NO_CAPABLE_ACTOR",
]
assert diagnostic["candidate_summary"]["eligible_count"] == 0
```

If the test currently seeds only employee projections, add `_enable_actor()` calls for candidate actors or keep no actors to validate empty actor pool behavior.

- [ ] **Step 4: Run migrated scheduler tests**

Run:

```bash
pytest backend/tests/test_scheduler_runner.py::test_scheduler_treats_legacy_excluded_employee_ids_as_current_ticket_scope backend/tests/test_scheduler_runner.py::test_scheduler_does_not_relax_current_ticket_scoped_exclusion_for_rework -q
```

Expected: PASS.

- [ ] **Step 5: Run broader scheduler focused range**

Run:

```bash
pytest backend/tests/test_scheduler_runner.py -q
```

Expected: PASS. If unrelated long-running live/provider tests are present and fail due to environment, capture the exact failing test names and run the focused scheduler assignment tests plus affected local tests before proceeding.

- [ ] **Step 6: Commit scheduler resolver integration**

Run:

```bash
git add backend/app/core/ticket_handlers.py backend/tests/test_scheduler_runner.py
git commit -m "refactor(actors): 按能力选择调度执行者"
```

Expected: commit succeeds.

---

### Task 6: Prevent retry/rework exclusion pollution

**Files:**
- Modify: `backend/app/core/ticket_handlers.py:1135-1253`, `backend/app/core/ticket_handlers.py:3603-3630`
- Modify: `backend/tests/test_scheduler_runner.py`

- [ ] **Step 1: Add failing retry pollution unit/integration test**

Append to `backend/tests/test_scheduler_runner.py`:

```python
def test_retry_ticket_does_not_copy_legacy_excluded_employee_ids(client):
    repository = client.app.state.repository
    workflow_id = _project_init(client, goal="Retry exclusion pollution")
    ticket_payload = _ticket_create_payload(
        workflow_id=workflow_id,
        ticket_id="tkt_retry_exclusion_source",
        node_id="node_retry_exclusion_source",
        role_profile_ref="backend_engineer_primary",
        output_schema_ref="source_code_delivery",
        excluded_employee_ids=["actor_backend_previous"],
    )

    with repository.transaction() as connection:
        next_ticket_id = ticket_handlers_module._schedule_retry_ticket(
            repository,
            connection,
            command_id="cmd_retry_exclusion_pollution",
            occurred_at=datetime.fromisoformat("2026-04-01T10:02:00+08:00"),
            workflow_id=workflow_id,
            failed_ticket_id="tkt_retry_exclusion_source",
            node_id="node_retry_exclusion_source",
            created_spec=ticket_payload,
            failure_payload={
                "failure_fingerprint": "retry-exclusion-pollution",
            },
            retry_source_event_type="TICKET_FAILED",
            idempotency_key_base="test-retry-exclusion-pollution",
        )
        retry_payload = repository.get_latest_ticket_created_payload(connection, next_ticket_id)

    assert retry_payload["excluded_employee_ids"] == []
    assert retry_payload.get("scoped_exclusions", []) == []
```

If direct access to `_schedule_retry_ticket` requires existing import, use the existing `import app.core.ticket_handlers as ticket_handlers_module` already present in `test_scheduler_runner.py` or add it.

- [ ] **Step 2: Add failing rework scoped exclusion test**

Append to `backend/tests/test_scheduler_runner.py`:

```python
def test_rework_fix_ticket_converts_maker_to_scoped_exclusion_without_copying_legacy_list() -> None:
    payload = ticket_handlers_module._build_fix_ticket_payload(
        workflow_id="wf_rework_scope",
        node_id="node_rework_scope",
        checker_ticket_id="tkt_checker",
        checker_created_spec={
            "attempt_no": 1,
            "constraints_ref": "global_constraints_v3",
            "lease_timeout_sec": 600,
            "retry_budget": 0,
            "priority": "high",
            "timeout_sla_sec": 1800,
            "maker_checker_context": {
                "maker_ticket_id": "tkt_maker",
                "maker_completed_by": "actor_maker_previous",
                "maker_artifact_refs": ["art://maker/result.json"],
                "maker_process_asset_refs": [],
                "maker_ticket_spec": {
                    "ticket_id": "tkt_maker",
                    "workflow_id": "wf_rework_scope",
                    "node_id": "node_rework_scope",
                    "role_profile_ref": "frontend_engineer_primary",
                    "output_schema_ref": "source_code_delivery",
                    "output_schema_version": 1,
                    "excluded_employee_ids": ["actor_legacy_pollution"],
                    "allowed_write_set": [],
                    "allowed_tools": ["read_artifact"],
                    "acceptance_criteria": ["Fix the issue"],
                    "context_query_plan": {"max_context_tokens": 3000},
                },
                "original_review_request": {},
            },
        },
        checker_result_payload={"artifact_refs": ["art://checker/report.json"]},
        blocking_findings=[
            {
                "finding_id": "finding_1",
                "headline": "Blocking issue",
                "required_action": "Fix the issue",
                "severity": "high",
                "category": "correctness",
            }
        ],
        rework_fingerprint="rework-scope",
        rework_streak_count=1,
    )

    assert payload["excluded_employee_ids"] == []
    assert payload["scoped_exclusions"] == [
        {
            "actor_id": "actor_maker_previous",
            "scope": "ticket",
            "ticket_id": payload["ticket_id"],
            "node_id": "node_rework_scope",
            "workflow_id": "wf_rework_scope",
            "capability": None,
            "reason": "maker rework should use a different actor for this fix ticket",
        }
    ]
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```bash
pytest backend/tests/test_scheduler_runner.py::test_retry_ticket_does_not_copy_legacy_excluded_employee_ids backend/tests/test_scheduler_runner.py::test_rework_fix_ticket_converts_maker_to_scoped_exclusion_without_copying_legacy_list -q
```

Expected: FAIL because retry/rework still copies legacy `excluded_employee_ids`.

- [ ] **Step 4: Stop copying legacy exclusions on retry**

In `_schedule_retry_ticket()` after `next_ticket_payload = { ... }`, add:

```python
    next_ticket_payload["excluded_employee_ids"] = []
    next_ticket_payload["scoped_exclusions"] = []
```

Place this before `_ensure_ticket_execution_contract_payload(next_ticket_payload)`.

- [ ] **Step 5: Convert rework maker exclusion to scoped exclusion**

In `_build_fix_ticket_payload()`, replace:

```python
    excluded_employee_ids = _dedupe_string_values(
        list(maker_ticket_spec.get("excluded_employee_ids") or [])
        + [maker_checker_context.get("maker_completed_by")]
    )
```

with:

```python
    maker_completed_by = str(maker_checker_context.get("maker_completed_by") or "").strip()
```

Then before the return dict, after `next_ticket_id = new_prefixed_id("tkt")`, add:

```python
    scoped_exclusions = []
    if maker_completed_by:
        scoped_exclusions.append(
            {
                "actor_id": maker_completed_by,
                "scope": "ticket",
                "ticket_id": next_ticket_id,
                "node_id": node_id,
                "workflow_id": workflow_id,
                "capability": None,
                "reason": "maker rework should use a different actor for this fix ticket",
            }
        )
```

In the return dict, replace:

```python
        "excluded_employee_ids": excluded_employee_ids,
```

with:

```python
        "excluded_employee_ids": [],
        "scoped_exclusions": scoped_exclusions,
```

- [ ] **Step 6: Run retry/rework tests**

Run:

```bash
pytest backend/tests/test_scheduler_runner.py::test_retry_ticket_does_not_copy_legacy_excluded_employee_ids backend/tests/test_scheduler_runner.py::test_rework_fix_ticket_converts_maker_to_scoped_exclusion_without_copying_legacy_list -q
```

Expected: PASS.

- [ ] **Step 7: Commit exclusion pollution fix**

Run:

```bash
git add backend/app/core/ticket_handlers.py backend/tests/test_scheduler_runner.py
git commit -m "fix(actors): 限定派工排除作用域"
```

Expected: commit succeeds.

---

### Task 7: Update planning docs for Round 7B

**Files:**
- Modify: `doc/refactor/planning/06-actor-role-lifecycle.md:195-224`
- Modify: `doc/refactor/planning/09-refactor-plan.md:66-83`
- Modify: `doc/refactor/planning/10-refactor-acceptance-criteria.md:46-54`

- [x] **Step 1: Update actor lifecycle implementation status**

In `doc/refactor/planning/06-actor-role-lifecycle.md`, after the Round 7A implementation status block, add:

```markdown
## Round 7B 实现状态

Round 7B 已把 scheduler 派工资格从 `role_profile_ref` / employee role matching 收口到 capability-driven actor eligibility：

- `backend/app/core/assignment_resolver.py` 接收 required capabilities、actor projection、actor status、provider health、current active leases 和 scoped exclusion policy，输出 selected actor 或 no-eligible diagnostic payload。
- `backend/app/core/ticket_handlers.py` 的 ready ticket lease path 读取 `actor_projection`，并用 actor capability/status/provider/busy/exclusion 判断 eligibility；`role_profile_ref` 仅在进入 resolver 前作为历史 ticket spec 的 capability 编译输入。
- `excluded_employee_ids` 迁移解释为当前 ticket scope 的 legacy 输入；新 `scoped_exclusions` 支持 `attempt` / `ticket` / `node` / `capability` / `workflow`，scheduler 只应用命中当前 ticket/node/capability/workflow 的排除项。
- retry 不再复制 legacy `excluded_employee_ids`；maker-checker rework 只把 maker 转换为当前 fix ticket 的 scoped exclusion，避免污染无关票、节点或 capability。
- no eligible actor 沿用 `EVENT_SCHEDULER_LEASE_DIAGNOSTIC_RECORDED`，payload 包含 `required_capabilities`、候选 actor 排除原因和建议动作：`CREATE_ACTOR`、`REASSIGN_EXECUTOR`、`REQUEST_HUMAN_DECISION`、`BLOCK_NODE_NO_CAPABLE_ACTOR`。

7B 仍保留现有 `TICKET_LEASED.leased_by` 写入字段来承载 selected `actor_id`，因为 assignment/lease 独立事件、`assignment_id` 和 `lease_id` 是 7C 范围。
```

- [x] **Step 2: Update refactor plan Phase 3**

In `doc/refactor/planning/09-refactor-plan.md`, update Phase 3 tasks to:

```markdown
- [x] 建立 actor registry：Round 7A added independent `ACTOR_*` lifecycle events, replayable `actor_projection`, repository read APIs, and tests proving no `EMPLOYEE_*` bridge.
- [x] 建立 capability mapping：Round 7A added `build_role_template_capability_contract()` so RoleTemplate emits capability/provider preference only, not runtime execution keys.
- [x] 定义 actor enable/suspend/deactivate/replace 事件：Round 7A reducer tests cover the actor lifecycle state transitions and replacement lineage.
- [x] 修复 excluded employee 继承污染：Round 7B interprets legacy `excluded_employee_ids` as current-ticket scoped input, adds scoped exclusions, and prevents retry/rework from copying unscoped lists.
- [x] actor pool empty 时生成显式 action/incident：Round 7B upgrades scheduler diagnostics with required capabilities, candidate exclusion reasons, and suggested actions.
- [ ] Assignment 与 Lease 分离：Round 7C must introduce independent assignment/lease identity and move current `TICKET_LEASED.leased_by` actor usage to explicit `assignment_id` / `lease_id` semantics.
```

- [x] **Step 3: Update acceptance criteria**

In `doc/refactor/planning/10-refactor-acceptance-criteria.md`, update Phase 3 lines to:

```markdown
- [x] Actor registry 有 enable/suspend/deactivate/replace 状态机（Round 7A: `pytest backend/tests/test_reducer.py::test_reducer_rebuilds_actor_projection_from_independent_actor_events -q`）。
- [x] RoleTemplate 只映射 capability，不作为 runtime 执行键（Round 7A: `pytest backend/tests/test_execution_targets.py::test_role_template_capability_contract_does_not_emit_runtime_execution_key -q`）。
- [ ] Assignment 与 Lease 分离。
- [x] `excluded_employee_ids` 有作用域，不会继承污染（Round 7B: `pytest backend/tests/test_assignment_resolver.py backend/tests/test_scheduler_runner.py::test_retry_ticket_does_not_copy_legacy_excluded_employee_ids backend/tests/test_scheduler_runner.py::test_rework_fix_ticket_converts_maker_to_scoped_exclusion_without_copying_legacy_list -q`）。
- [x] no eligible actor 产生显式 action 或 incident（Round 7B: `pytest backend/tests/test_scheduler_runner.py::test_ready_ticket_without_eligible_worker_surfaces_staffing_gap -q`）。
- [ ] provider preferred/actual 记录完整。
```

- [ ] **Step 4: Commit planning docs**

Run:

```bash
git add doc/refactor/planning/06-actor-role-lifecycle.md doc/refactor/planning/09-refactor-plan.md doc/refactor/planning/10-refactor-acceptance-criteria.md
git commit -m "docs(actors): 更新能力派工验收状态"
```

Expected: commit succeeds.

---

### Task 8: Final verification and required Round 7B commit

**Files:**
- Verify all changed files
- Final commit if earlier task commits were squashed or skipped

- [x] **Step 1: Run focused Round 7B tests**

Run:

```bash
pytest backend/tests/test_assignment_resolver.py backend/tests/test_execution_targets.py backend/tests/test_scheduler_runner.py::test_scheduler_leases_actor_by_required_capabilities_not_employee_role backend/tests/test_scheduler_runner.py::test_scheduler_treats_legacy_excluded_employee_ids_as_current_ticket_scope backend/tests/test_scheduler_runner.py::test_scheduler_does_not_relax_current_ticket_scoped_exclusion_for_rework backend/tests/test_scheduler_runner.py::test_retry_ticket_does_not_copy_legacy_excluded_employee_ids backend/tests/test_scheduler_runner.py::test_rework_fix_ticket_converts_maker_to_scoped_exclusion_without_copying_legacy_list -q
```

Expected: PASS.

- [ ] **Step 2: Run broader affected tests**

Run:

```bash
pytest backend/tests/test_scheduler_runner.py backend/tests/test_api.py -q
```

Expected: PASS. If this is too slow or environment-dependent, capture exact failures and rerun the focused failing tests after fixes.

- [x] **Step 3: Run grep guardrail for role-name fallback**

Run:

```bash
git grep -n "role_profile_ref.*leased_by\|leased_by.*role_profile_ref\|target_role_profile\|NO_ELIGIBLE_WORKER" -- backend/app/core/ticket_handlers.py backend/app/core/workflow_controller.py backend/app/core/execution_targets.py
```

Expected: no scheduler/controller/ticket-handler role-name-to-execution-key branch remains. `execution_targets.py` may still contain migration-time role template capability contract helpers; verify any matches are not runtime eligibility fallbacks.

- [ ] **Step 4: Inspect final diff**

Run:

```bash
git status --short
git diff --stat HEAD~4..HEAD
```

Expected: only resolver, scheduler/tests, and planning docs changed since implementation started.

- [ ] **Step 5: Ensure final requested commit message exists**

If the implementation was committed in multiple task commits, create one final empty-free commit only if there are remaining staged changes. If the user specifically requires the suggested message as the final implementation commit and changes remain uncommitted, run:

```bash
git add backend/app/core/assignment_resolver.py backend/app/core/execution_targets.py backend/app/core/ticket_handlers.py backend/tests/test_assignment_resolver.py backend/tests/test_execution_targets.py backend/tests/test_scheduler_runner.py doc/refactor/planning/06-actor-role-lifecycle.md doc/refactor/planning/09-refactor-plan.md doc/refactor/planning/10-refactor-acceptance-criteria.md
git commit -m "$(cat <<'EOF'
refactor-actors: assign by capability eligibility

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

Expected: commit succeeds only if there are remaining changes. Do not create an empty commit.

---

## Self-Review Notes

- Spec coverage: resolver, scheduler integration, capability compilation, scoped exclusions, retry/rework pollution, no-eligible diagnostic, docs, tests, and grep guardrail are each mapped to tasks.
- Placeholder scan: no red-flag placeholders remain.
- Type consistency: resolver APIs use `actor_id`, `required_capabilities`, `scoped_exclusions`, and `AssignmentResolution` consistently. Scheduler still writes `leased_by` until Round 7C as documented.
