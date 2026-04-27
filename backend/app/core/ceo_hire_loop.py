from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.ceo_snapshot_contracts import capability_plan_view, controller_state_view
from app.core.constants import (
    CIRCUIT_BREAKER_STATE_OPEN,
    EVENT_CIRCUIT_BREAKER_OPENED,
    EVENT_INCIDENT_OPENED,
    INCIDENT_STATUS_OPEN,
    INCIDENT_TYPE_CEO_HIRE_LOOP_DETECTED,
)
from app.core.employee_reuse import ROLE_ALREADY_COVERED_REASON_CODE, normalize_role_profile_refs
from app.core.ids import new_prefixed_id
from app.db.repository import ControlPlaneRepository

CEO_HIRE_LOOP_SUGGESTED_RECOVERY_ACTION = "REUSE_EXISTING_EMPLOYEE_OR_REPLAN_CONTRACT"


def extract_role_already_covered_hire_rejection(
    rejected_actions: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for rejected_action in rejected_actions:
        if str(rejected_action.get("action_type") or "").strip() != "HIRE_EMPLOYEE":
            continue
        details = rejected_action.get("details") or {}
        if not isinstance(details, dict):
            continue
        if str(details.get("reason_code") or "").strip() != ROLE_ALREADY_COVERED_REASON_CODE:
            continue
        return rejected_action
    return None


def _safe_controller_state(snapshot: dict[str, Any]) -> dict[str, Any]:
    try:
        return controller_state_view(snapshot)
    except ValueError:
        return {}


def _safe_capability_plan(snapshot: dict[str, Any]) -> dict[str, Any]:
    try:
        return capability_plan_view(snapshot)
    except ValueError:
        return {}


def build_hire_loop_fingerprint_payload(
    *,
    workflow_id: str,
    snapshot: dict[str, Any],
    rejected_action: dict[str, Any],
) -> dict[str, Any] | None:
    details = rejected_action.get("details") or {}
    payload = rejected_action.get("payload") or {}
    if not isinstance(details, dict) or not isinstance(payload, dict):
        return None
    reason_code = str(details.get("reason_code") or "").strip()
    if reason_code != ROLE_ALREADY_COVERED_REASON_CODE:
        return None

    controller_state = _safe_controller_state(snapshot)
    capability_plan = _safe_capability_plan(snapshot)
    recommended_hire = capability_plan.get("recommended_hire") or {}
    if not isinstance(recommended_hire, dict):
        recommended_hire = {}

    role_type = str(
        details.get("role_type")
        or payload.get("role_type")
        or recommended_hire.get("role_type")
        or ""
    ).strip()
    role_profile_refs = normalize_role_profile_refs(
        details.get("role_profile_refs")
        or payload.get("role_profile_refs")
        or recommended_hire.get("role_profile_refs")
        or []
    )
    if not workflow_id or not role_type or not role_profile_refs:
        return None

    state = str(controller_state.get("state") or "").strip()
    recommended_action = str(controller_state.get("recommended_action") or "").strip()
    fingerprint = ":".join(
        [
            "ceo-hire-loop",
            workflow_id,
            state,
            recommended_action,
            role_type,
            ",".join(role_profile_refs),
            reason_code,
        ]
    )
    return {
        "fingerprint": fingerprint,
        "workflow_id": workflow_id,
        "controller_state": controller_state,
        "recommended_hire": dict(recommended_hire),
        "rejected_action": dict(rejected_action),
        "validator_reason": str(rejected_action.get("reason") or "").strip(),
        "validator_details": details,
        "reuse_candidate_employee_id": str(details.get("reuse_candidate_employee_id") or "").strip(),
        "role_type": role_type,
        "role_profile_refs": role_profile_refs,
        "rejected_reason_code": reason_code,
        "suggested_recovery_action": CEO_HIRE_LOOP_SUGGESTED_RECOVERY_ACTION,
    }


def hire_loop_fingerprint_payload_from_run(run: dict[str, Any]) -> dict[str, Any] | None:
    rejected_action = extract_role_already_covered_hire_rejection(
        list(run.get("rejected_actions") or [])
    )
    if rejected_action is None:
        return None
    return build_hire_loop_fingerprint_payload(
        workflow_id=str(run.get("workflow_id") or "").strip(),
        snapshot=dict(run.get("snapshot") or {}),
        rejected_action=rejected_action,
    )


def detect_consecutive_hire_loop(
    *,
    workflow_id: str,
    snapshot: dict[str, Any],
    rejected_actions: list[dict[str, Any]],
    previous_run: dict[str, Any] | None,
) -> dict[str, Any] | None:
    rejected_action = extract_role_already_covered_hire_rejection(rejected_actions)
    if rejected_action is None or previous_run is None:
        return None
    current = build_hire_loop_fingerprint_payload(
        workflow_id=workflow_id,
        snapshot=snapshot,
        rejected_action=rejected_action,
    )
    previous = hire_loop_fingerprint_payload_from_run(previous_run)
    if current is None or previous is None:
        return None
    if current["fingerprint"] != previous["fingerprint"]:
        return None
    return {
        **current,
        "previous_ceo_shadow_run_id": str(previous_run.get("run_id") or ""),
    }


def ceo_hire_loop_summary_from_incidents(incidents: list[dict[str, Any]]) -> dict[str, Any] | None:
    for incident in incidents:
        if str(incident.get("incident_type") or "").strip() != INCIDENT_TYPE_CEO_HIRE_LOOP_DETECTED:
            continue
        if str(incident.get("status") or "").strip() != INCIDENT_STATUS_OPEN:
            continue
        payload = incident.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}
        return {
            "has_open_loop_incident": True,
            "incident_id": str(incident.get("incident_id") or payload.get("incident_id") or ""),
            "fingerprint": str(
                payload.get("loop_fingerprint") or incident.get("fingerprint") or ""
            ),
            "reuse_candidate_employee_id": str(payload.get("reuse_candidate_employee_id") or ""),
            "role_type": str(payload.get("role_type") or ""),
            "role_profile_refs": normalize_role_profile_refs(payload.get("role_profile_refs") or []),
            "suggested_recovery_action": str(payload.get("suggested_recovery_action") or ""),
        }
    return None


def open_ceo_hire_loop_incident(
    repository: ControlPlaneRepository,
    *,
    connection,
    workflow_id: str,
    detection: dict[str, Any],
    occurred_at: datetime,
    idempotency_key_base: str,
    causation_id: str | None,
) -> str:
    fingerprint = str(detection["fingerprint"])
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
        "ticket_id": None,
        "node_id": None,
        "incident_type": INCIDENT_TYPE_CEO_HIRE_LOOP_DETECTED,
        "status": INCIDENT_STATUS_OPEN,
        "severity": "high",
        "fingerprint": fingerprint,
        "loop_fingerprint": fingerprint,
        "controller_state": detection["controller_state"],
        "recommended_hire": detection["recommended_hire"],
        "rejected_action": detection["rejected_action"],
        "validator_reason": detection["validator_reason"],
        "validator_details": detection["validator_details"],
        "reuse_candidate_employee_id": detection["reuse_candidate_employee_id"],
        "role_type": detection["role_type"],
        "role_profile_refs": detection["role_profile_refs"],
        "rejected_reason_code": detection["rejected_reason_code"],
        "previous_ceo_shadow_run_id": detection["previous_ceo_shadow_run_id"],
        "suggested_recovery_action": detection["suggested_recovery_action"],
    }
    incident_event = repository.insert_event(
        connection,
        event_type=EVENT_INCIDENT_OPENED,
        actor_type="system",
        actor_id="ceo-hire-loop-detector",
        workflow_id=workflow_id,
        idempotency_key=f"{idempotency_key_base}:incident-opened:{fingerprint}",
        causation_id=causation_id,
        correlation_id=workflow_id,
        payload=incident_payload,
        occurred_at=occurred_at,
    )
    if incident_event is None:
        raise RuntimeError("CEO hire loop incident opening idempotency conflict.")

    breaker_event = repository.insert_event(
        connection,
        event_type=EVENT_CIRCUIT_BREAKER_OPENED,
        actor_type="system",
        actor_id="ceo-hire-loop-detector",
        workflow_id=workflow_id,
        idempotency_key=f"{idempotency_key_base}:circuit-breaker-opened:{fingerprint}",
        causation_id=causation_id,
        correlation_id=workflow_id,
        payload={
            "incident_id": incident_id,
            "ticket_id": None,
            "node_id": None,
            "incident_type": INCIDENT_TYPE_CEO_HIRE_LOOP_DETECTED,
            "circuit_breaker_state": CIRCUIT_BREAKER_STATE_OPEN,
            "fingerprint": fingerprint,
        },
        occurred_at=occurred_at,
    )
    if breaker_event is None:
        raise RuntimeError("CEO hire loop circuit breaker opening idempotency conflict.")

    repository.refresh_projections(connection)
    return incident_id
