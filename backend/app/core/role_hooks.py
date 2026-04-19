from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
import hashlib
import json
from typing import TYPE_CHECKING, Any, Iterable

from app.core.constants import (
    CIRCUIT_BREAKER_STATE_OPEN,
    EVENT_CIRCUIT_BREAKER_OPENED,
    EVENT_INCIDENT_OPENED,
    INCIDENT_STATUS_OPEN,
    INCIDENT_TYPE_REQUIRED_HOOK_GATE_BLOCKED,
    TICKET_STATUS_COMPLETED,
)
from app.core.graph_identity import resolve_ticket_graph_identity
from app.core.output_schemas import (
    DELIVERY_CHECK_REPORT_SCHEMA_REF,
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    MAKER_CHECKER_VERDICT_SCHEMA_REF,
    UI_MILESTONE_REVIEW_SCHEMA_REF,
)
from app.core.ids import new_prefixed_id
from app.core.time import now_local
from app.core.project_workspaces import (
    load_artifact_capture_receipt,
    load_documentation_sync_receipt,
    load_git_closeout_receipt,
    load_worker_postrun_receipt,
    project_workspace_manifest_exists,
    resolve_project_workspace_root,
    sync_active_worktree_index,
    sync_ticket_boardroom_views,
    write_artifact_capture_receipt,
    write_documentation_sync_receipt,
    write_evidence_capture_receipt,
    write_git_closeout_receipt,
    write_worker_postrun_receipt,
)

if TYPE_CHECKING:
    import sqlite3

    from app.db.repository import ControlPlaneRepository


HOOK_GATE_MODE_NOT_APPLICABLE = "not_applicable"
HOOK_GATE_MODE_REQUIRED = "required"
HOOK_GATE_APPLICABILITY_OUT_OF_SCOPE = "out_of_scope_deliverable"
HOOK_GATE_APPLICABILITY_WORKSPACE_SOURCE = "workspace_managed_source_code_delivery"
HOOK_GATE_APPLICABILITY_WORKSPACE_STRUCTURED_DOCUMENT = "workspace_managed_structured_document_delivery"
HOOK_GATE_APPLICABILITY_WORKSPACE_REVIEW_EVIDENCE = "workspace_managed_review_evidence"


class HookGateStatus(StrEnum):
    PASSED = "PASSED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class RoleHookSpec:
    hook_id: str
    lifecycle_event: str
    deliverable_kind: str
    required_for_gate: bool
    receipt_filename: str
    output_schema_refs: tuple[str, ...] | None = None


@dataclass(frozen=True)
class HookGateResult:
    gate_mode: str
    applicability: str
    required_hook_ids: list[str]
    checked_hook_ids: list[str]
    missing_hook_ids: list[str]
    status: HookGateStatus
    reason_code: str
    reason_detail: str | None
    incident_fingerprint: str | None


@dataclass(frozen=True)
class ReplayRequiredHooksResult:
    replayed_hook_ids: list[str]


@dataclass(frozen=True)
class RequiredHookIncidentScanResult:
    opened_incident_ids: list[str]


def default_role_hook_registry() -> list[RoleHookSpec]:
    return [
        RoleHookSpec(
            hook_id="worker_preflight",
            lifecycle_event="PACKAGE_COMPILED",
            deliverable_kind="source_code_delivery",
            required_for_gate=False,
            receipt_filename="worker-preflight.json",
        ),
        RoleHookSpec(
            hook_id="worker_postrun",
            lifecycle_event="RESULT_ACCEPTED",
            deliverable_kind="source_code_delivery",
            required_for_gate=True,
            receipt_filename="worker-postrun.json",
        ),
        RoleHookSpec(
            hook_id="evidence_capture",
            lifecycle_event="RESULT_ACCEPTED",
            deliverable_kind="source_code_delivery",
            required_for_gate=True,
            receipt_filename="evidence-capture.json",
        ),
        RoleHookSpec(
            hook_id="git_closeout",
            lifecycle_event="RESULT_ACCEPTED",
            deliverable_kind="source_code_delivery",
            required_for_gate=True,
            receipt_filename="git-closeout.json",
        ),
        RoleHookSpec(
            hook_id="artifact_capture",
            lifecycle_event="RESULT_ACCEPTED",
            deliverable_kind="structured_document_delivery",
            required_for_gate=True,
            receipt_filename="artifact-capture.json",
        ),
        RoleHookSpec(
            hook_id="documentation_sync",
            lifecycle_event="RESULT_ACCEPTED",
            deliverable_kind="structured_document_delivery",
            required_for_gate=True,
            receipt_filename="documentation-sync.json",
            output_schema_refs=(DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,),
        ),
        RoleHookSpec(
            hook_id="artifact_capture",
            lifecycle_event="RESULT_ACCEPTED",
            deliverable_kind="review_evidence",
            required_for_gate=True,
            receipt_filename="artifact-capture.json",
            output_schema_refs=(
                DELIVERY_CHECK_REPORT_SCHEMA_REF,
                UI_MILESTONE_REVIEW_SCHEMA_REF,
                MAKER_CHECKER_VERDICT_SCHEMA_REF,
            ),
        ),
    ]


def _ticket_receipt_path(workflow_id: str, ticket_id: str, receipt_filename: str) -> Path:
    return (
        resolve_project_workspace_root(workflow_id)
        / "00-boardroom"
        / "tickets"
        / ticket_id
        / "hook-receipts"
        / receipt_filename
    )


def _load_json_receipt(workflow_id: str, ticket_id: str, receipt_filename: str) -> dict[str, Any]:
    receipt_path = _ticket_receipt_path(workflow_id, ticket_id, receipt_filename)
    if not receipt_path.exists():
        return {}
    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def _is_workspace_managed_source_code_delivery(created_spec: dict[str, Any]) -> bool:
    if str(created_spec.get("output_schema_ref") or "").strip() != "source_code_delivery":
        return False
    if not project_workspace_manifest_exists(str(created_spec.get("workflow_id") or "")):
        return False
    return any(
        str(pattern or "").startswith(("10-project/", "20-evidence/", "00-boardroom/"))
        for pattern in list(created_spec.get("allowed_write_set") or [])
    )


def _is_workspace_managed_structured_document_delivery(created_spec: dict[str, Any]) -> bool:
    if str(created_spec.get("deliverable_kind") or "").strip() != "structured_document_delivery":
        return False
    if not project_workspace_manifest_exists(str(created_spec.get("workflow_id") or "")):
        return False
    return any(
        str(pattern or "").startswith(("10-project/", "20-evidence/", "00-boardroom/"))
        for pattern in list(created_spec.get("allowed_write_set") or [])
    )


def _is_workspace_managed_review_evidence(created_spec: dict[str, Any]) -> bool:
    if str(created_spec.get("deliverable_kind") or "").strip() != "review_evidence":
        return False
    return project_workspace_manifest_exists(str(created_spec.get("workflow_id") or ""))


def _resolve_registry(registry: Iterable[RoleHookSpec] | None) -> list[RoleHookSpec]:
    return list(registry) if registry is not None else default_role_hook_registry()


def _resolve_required_hook_receipt(
    workflow_id: str,
    ticket_id: str,
    hook_id: str,
    receipt_filename: str,
) -> dict[str, Any]:
    if hook_id == "worker_postrun":
        return load_worker_postrun_receipt(workflow_id, ticket_id)
    if hook_id == "artifact_capture":
        return load_artifact_capture_receipt(workflow_id, ticket_id)
    if hook_id == "documentation_sync":
        return load_documentation_sync_receipt(workflow_id, ticket_id)
    if hook_id == "git_closeout":
        return load_git_closeout_receipt(workflow_id, ticket_id)
    return _load_json_receipt(workflow_id, ticket_id, receipt_filename)


def _resolve_applicable_hook_specs(
    created_spec: dict[str, Any],
    *,
    registry: Iterable[RoleHookSpec] | None = None,
) -> tuple[str, str, list[RoleHookSpec]]:
    resolved_registry = _resolve_registry(registry)
    output_schema_ref = str(created_spec.get("output_schema_ref") or "").strip()
    if _is_workspace_managed_source_code_delivery(created_spec):
        return (
            HOOK_GATE_MODE_REQUIRED,
            HOOK_GATE_APPLICABILITY_WORKSPACE_SOURCE,
            [spec for spec in resolved_registry if spec.deliverable_kind == "source_code_delivery"],
        )
    if _is_workspace_managed_structured_document_delivery(created_spec):
        return (
            HOOK_GATE_MODE_REQUIRED,
            HOOK_GATE_APPLICABILITY_WORKSPACE_STRUCTURED_DOCUMENT,
            [
                spec
                for spec in resolved_registry
                if spec.deliverable_kind == "structured_document_delivery"
                and (
                    spec.output_schema_refs is None
                    or output_schema_ref in spec.output_schema_refs
                )
            ],
        )
    if _is_workspace_managed_review_evidence(created_spec):
        return (
            HOOK_GATE_MODE_REQUIRED,
            HOOK_GATE_APPLICABILITY_WORKSPACE_REVIEW_EVIDENCE,
            [
                spec
                for spec in resolved_registry
                if spec.deliverable_kind == "review_evidence"
                and (
                    spec.output_schema_refs is None
                    or output_schema_ref in spec.output_schema_refs
                )
            ],
        )
    return (HOOK_GATE_MODE_NOT_APPLICABLE, HOOK_GATE_APPLICABILITY_OUT_OF_SCOPE, [])


def _build_required_hook_incident_fingerprint(
    repository: "ControlPlaneRepository",
    connection: "sqlite3.Connection",
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    missing_hook_ids: list[str],
) -> str:
    terminal_event = repository.get_latest_ticket_terminal_event(connection, ticket_id)
    source_ref = (
        str(terminal_event.get("event_id") or terminal_event.get("sequence_no") or "no-terminal-event")
        if terminal_event is not None
        else "no-terminal-event"
    )
    fingerprint_payload = {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "terminal_event_ref": source_ref,
        "missing_hook_ids": sorted(missing_hook_ids),
    }
    digest = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]
    return f"{workflow_id}:{ticket_id}:required-hook-gate:{digest}"


def evaluate_ticket_required_hook_gate(
    repository: "ControlPlaneRepository",
    *,
    ticket: dict[str, Any],
    created_spec: dict[str, Any],
    connection: "sqlite3.Connection" | None = None,
    registry: Iterable[RoleHookSpec] | None = None,
) -> HookGateResult:
    if connection is None:
        with repository.connection() as owned_connection:
            return evaluate_ticket_required_hook_gate(
                repository,
                ticket=ticket,
                created_spec=created_spec,
                connection=owned_connection,
                registry=registry,
            )

    gate_mode, applicability, applicable_specs = _resolve_applicable_hook_specs(
        created_spec,
        registry=registry,
    )
    if gate_mode == HOOK_GATE_MODE_NOT_APPLICABLE:
        return HookGateResult(
            gate_mode=HOOK_GATE_MODE_NOT_APPLICABLE,
            applicability=HOOK_GATE_APPLICABILITY_OUT_OF_SCOPE,
            required_hook_ids=[],
            checked_hook_ids=[],
            missing_hook_ids=[],
            status=HookGateStatus.PASSED,
            reason_code="HOOK_GATE_NOT_APPLICABLE",
            reason_detail="The current ticket is outside the required hook gate scope.",
            incident_fingerprint=None,
        )

    workflow_id = str(ticket.get("workflow_id") or created_spec.get("workflow_id") or "").strip()
    ticket_id = str(ticket.get("ticket_id") or created_spec.get("ticket_id") or "").strip()
    node_id = str(ticket.get("node_id") or created_spec.get("node_id") or "").strip()
    checked_hook_ids = [spec.hook_id for spec in applicable_specs]
    required_hook_ids = [spec.hook_id for spec in applicable_specs if spec.required_for_gate]

    if str(ticket.get("status") or "").strip() != TICKET_STATUS_COMPLETED:
        return HookGateResult(
            gate_mode=gate_mode,
            applicability=applicability,
            required_hook_ids=required_hook_ids,
            checked_hook_ids=checked_hook_ids,
            missing_hook_ids=[],
            status=HookGateStatus.PASSED,
            reason_code="HOOK_GATE_DEFERRED",
            reason_detail="The required hook gate only opens after the ticket reaches COMPLETED.",
            incident_fingerprint=None,
        )

    missing_hook_ids: list[str] = []
    for spec in applicable_specs:
        if not spec.required_for_gate:
            continue
        receipt_payload = _resolve_required_hook_receipt(
            workflow_id,
            ticket_id,
            spec.hook_id,
            spec.receipt_filename,
        )
        if not receipt_payload:
            missing_hook_ids.append(spec.hook_id)

    if not missing_hook_ids:
        return HookGateResult(
            gate_mode=gate_mode,
            applicability=applicability,
            required_hook_ids=required_hook_ids,
            checked_hook_ids=checked_hook_ids,
            missing_hook_ids=[],
            status=HookGateStatus.PASSED,
            reason_code="HOOK_GATE_PASSED",
            reason_detail="All required RESULT_ACCEPTED hooks have materialized receipts.",
            incident_fingerprint=None,
        )

    incident_fingerprint = _build_required_hook_incident_fingerprint(
        repository,
        connection,
        workflow_id=workflow_id,
        ticket_id=ticket_id,
        node_id=node_id,
        missing_hook_ids=missing_hook_ids,
    )
    reason_code = f"REQUIRED_HOOK_PENDING:{missing_hook_ids[0]}"
    return HookGateResult(
        gate_mode=gate_mode,
        applicability=applicability,
        required_hook_ids=required_hook_ids,
        checked_hook_ids=checked_hook_ids,
        missing_hook_ids=missing_hook_ids,
        status=HookGateStatus.BLOCKED,
        reason_code=reason_code,
        reason_detail=(
            "Required hook receipts are missing for "
            + ", ".join(missing_hook_ids)
            + ". The node must stay fail-closed until recovery replays the missing hooks."
        ),
        incident_fingerprint=incident_fingerprint,
    )


def replay_required_hook_receipts(
    repository: "ControlPlaneRepository",
    *,
    workflow_id: str,
    ticket_id: str,
    connection: "sqlite3.Connection" | None = None,
    registry: Iterable[RoleHookSpec] | None = None,
) -> ReplayRequiredHooksResult:
    if connection is None:
        with repository.connection() as owned_connection:
            return replay_required_hook_receipts(
                repository,
                workflow_id=workflow_id,
                ticket_id=ticket_id,
                connection=owned_connection,
                registry=registry,
            )

    ticket = repository.get_current_ticket_projection(ticket_id, connection=connection)
    created_spec = repository.get_latest_ticket_created_payload(connection, ticket_id) or {}
    if ticket is None:
        raise ValueError(f"Ticket {ticket_id} does not exist.")

    gate_result = evaluate_ticket_required_hook_gate(
        repository,
        ticket=ticket,
        created_spec=created_spec,
        connection=connection,
        registry=registry,
    )
    if gate_result.gate_mode != HOOK_GATE_MODE_REQUIRED:
        return ReplayRequiredHooksResult(replayed_hook_ids=[])

    terminal_event = repository.get_latest_ticket_terminal_event(connection, ticket_id)
    if terminal_event is None or str(terminal_event.get("event_type") or "") != "TICKET_COMPLETED":
        raise ValueError(
            f"Ticket {ticket_id} does not have a completed terminal event that can replay required hooks."
        )

    terminal_payload = dict(terminal_event.get("payload") or {})
    replayed_hook_ids: list[str] = []
    for hook_id in gate_result.missing_hook_ids:
        if hook_id == "worker_postrun":
            documentation_updates = terminal_payload.get("documentation_updates")
            if not isinstance(documentation_updates, list):
                raise ValueError("Cannot replay worker_postrun without documentation_updates.")
            write_worker_postrun_receipt(
                workflow_id=workflow_id,
                ticket_id=ticket_id,
                documentation_updates=list(documentation_updates),
            )
        elif hook_id == "evidence_capture":
            verification_evidence_refs = terminal_payload.get("verification_evidence_refs")
            if not isinstance(verification_evidence_refs, list):
                raise ValueError("Cannot replay evidence_capture without verification_evidence_refs.")
            write_evidence_capture_receipt(
                workflow_id=workflow_id,
                ticket_id=ticket_id,
                verification_evidence_refs=list(verification_evidence_refs),
            )
        elif hook_id == "artifact_capture":
            artifact_refs = terminal_payload.get("artifact_refs")
            if not isinstance(artifact_refs, list):
                raise ValueError("Cannot replay artifact_capture without artifact_refs.")
            written_artifacts = terminal_payload.get("written_artifacts")
            if not isinstance(written_artifacts, list):
                raise ValueError("Cannot replay artifact_capture without written_artifacts.")
            written_artifact_paths = [
                str(item.get("path") or "").strip()
                for item in written_artifacts
                if isinstance(item, dict) and str(item.get("path") or "").strip()
            ]
            write_artifact_capture_receipt(
                workflow_id=workflow_id,
                ticket_id=ticket_id,
                artifact_refs=[str(item).strip() for item in artifact_refs if str(item).strip()],
                written_artifact_paths=written_artifact_paths,
            )
        elif hook_id == "documentation_sync":
            documentation_updates = terminal_payload.get("documentation_updates")
            if not isinstance(documentation_updates, list):
                raise ValueError("Cannot replay documentation_sync without documentation_updates.")
            write_documentation_sync_receipt(
                workflow_id=workflow_id,
                ticket_id=ticket_id,
                documentation_updates=list(documentation_updates),
            )
        elif hook_id == "git_closeout":
            git_commit_record = terminal_payload.get("git_commit_record")
            if not isinstance(git_commit_record, dict) or not git_commit_record:
                raise ValueError("Cannot replay git_closeout without git_commit_record.")
            write_git_closeout_receipt(
                workflow_id=workflow_id,
                ticket_id=ticket_id,
                git_commit_record=dict(git_commit_record),
            )
        else:
            raise ValueError(f"Cannot replay unknown required hook {hook_id}.")
        replayed_hook_ids.append(hook_id)

    if replayed_hook_ids:
        sync_ticket_boardroom_views(
            repository,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
        )
        sync_active_worktree_index(repository, workflow_id=workflow_id)

    return ReplayRequiredHooksResult(replayed_hook_ids=replayed_hook_ids)


def open_required_hook_gate_incident(
    repository: "ControlPlaneRepository",
    *,
    workflow_id: str,
    ticket_id: str,
    node_id: str,
    gate_result: HookGateResult,
    idempotency_key_base: str,
    actor_id: str = "autopilot-controller",
) -> str:
    if gate_result.status != HookGateStatus.BLOCKED or gate_result.incident_fingerprint is None:
        raise ValueError("Required hook incident opening requires a blocked gate result with a stable fingerprint.")

    command_id = new_prefixed_id("cmd")
    occurred_at = now_local()
    fingerprint = gate_result.incident_fingerprint

    with repository.transaction() as connection:
        existing_row = connection.execute(
            """
            SELECT incident_id
            FROM incident_projection
            WHERE workflow_id = ? AND fingerprint = ? AND status = ?
            ORDER BY opened_at DESC, incident_id DESC
            LIMIT 1
            """,
            (workflow_id, fingerprint, INCIDENT_STATUS_OPEN),
        ).fetchone()
        if existing_row is not None:
            return str(existing_row["incident_id"])

        incident_id = new_prefixed_id("inc")
        incident_payload = {
            "incident_id": incident_id,
            "ticket_id": ticket_id,
            "node_id": node_id,
            "incident_type": INCIDENT_TYPE_REQUIRED_HOOK_GATE_BLOCKED,
            "status": INCIDENT_STATUS_OPEN,
            "severity": "high",
            "fingerprint": fingerprint,
            "gate_mode": gate_result.gate_mode,
            "applicability": gate_result.applicability,
            "required_hook_ids": list(gate_result.required_hook_ids),
            "checked_hook_ids": list(gate_result.checked_hook_ids),
            "missing_hook_ids": list(gate_result.missing_hook_ids),
            "reason_code": gate_result.reason_code,
            "reason_detail": gate_result.reason_detail,
        }
        incident_event = repository.insert_event(
            connection,
            event_type=EVENT_INCIDENT_OPENED,
            actor_type="system",
            actor_id=actor_id,
            workflow_id=workflow_id,
            idempotency_key=f"{idempotency_key_base}:incident-opened:{ticket_id}",
            causation_id=command_id,
            correlation_id=workflow_id,
            payload=incident_payload,
            occurred_at=occurred_at,
        )
        if incident_event is None:
            raise RuntimeError("Required hook gate incident opening idempotency conflict.")

        breaker_event = repository.insert_event(
            connection,
            event_type=EVENT_CIRCUIT_BREAKER_OPENED,
            actor_type="system",
            actor_id=actor_id,
            workflow_id=workflow_id,
            idempotency_key=f"{idempotency_key_base}:circuit-breaker-opened:{ticket_id}",
            causation_id=command_id,
            correlation_id=workflow_id,
            payload={
                "incident_id": incident_id,
                "ticket_id": ticket_id,
                "node_id": node_id,
                "circuit_breaker_state": CIRCUIT_BREAKER_STATE_OPEN,
                "fingerprint": fingerprint,
            },
            occurred_at=occurred_at,
        )
        if breaker_event is None:
            raise RuntimeError("Required hook gate circuit breaker opening idempotency conflict.")
        repository.refresh_projections(connection)

    return incident_id


def scan_and_open_required_hook_gate_incidents(
    repository: "ControlPlaneRepository",
    *,
    workflow_id: str,
    idempotency_key_base: str,
    registry: Iterable[RoleHookSpec] | None = None,
) -> RequiredHookIncidentScanResult:
    opened_incident_ids: list[str] = []
    with repository.connection() as connection:
        from app.core.runtime_node_views import build_runtime_graph_node_views

        runtime_graph_node_views = build_runtime_graph_node_views(
            repository,
            workflow_id,
            connection=connection,
        )
        ticket_rows = connection.execute(
            """
            SELECT *
            FROM ticket_projection
            WHERE workflow_id = ?
            ORDER BY updated_at ASC, ticket_id ASC
            """,
            (workflow_id,),
        ).fetchall()
        for row in ticket_rows:
            ticket = repository._convert_ticket_projection_row(row)
            created_spec = repository.get_latest_ticket_created_payload(connection, str(ticket["ticket_id"])) or {}
            graph_identity = resolve_ticket_graph_identity(
                ticket_id=str(ticket["ticket_id"]),
                created_spec=created_spec,
                runtime_node_id=str(ticket.get("node_id") or ""),
            )
            runtime_node_view = runtime_graph_node_views.get(graph_identity.graph_node_id)
            if runtime_node_view is None or str(runtime_node_view.ticket_id or "") != str(ticket["ticket_id"]):
                continue
            gate_result = evaluate_ticket_required_hook_gate(
                repository,
                ticket=ticket,
                created_spec=created_spec,
                connection=connection,
                registry=registry,
            )
            if gate_result.status != HookGateStatus.BLOCKED:
                continue
            incident_id = open_required_hook_gate_incident(
                repository,
                workflow_id=workflow_id,
                ticket_id=str(ticket["ticket_id"]),
                node_id=str(ticket.get("node_id") or ""),
                gate_result=gate_result,
                idempotency_key_base=f"{idempotency_key_base}:{ticket['ticket_id']}",
            )
            if incident_id not in opened_incident_ids:
                opened_incident_ids.append(incident_id)
    return RequiredHookIncidentScanResult(opened_incident_ids=opened_incident_ids)
