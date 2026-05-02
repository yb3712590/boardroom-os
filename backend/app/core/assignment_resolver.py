from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.constants import ACTOR_STATUS_ACTIVE

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
    normalized_required_capabilities = _normalize_string_list(required_capabilities)
    candidate_details: list[dict[str, Any]] = []
    selected_actor: dict[str, Any] | None = None

    for actor in actors:
        actor_id = _normalize_string(actor.get("actor_id"))
        capability_set = _normalize_string_list(actor.get("capability_set") or [])
        missing_capabilities = [
            capability
            for capability in normalized_required_capabilities
            if capability not in capability_set
        ]
        status = _normalize_string(actor.get("status"))
        status_eligible = status == ACTOR_STATUS_ACTIVE
        busy_identity_values = {actor_id}
        employee_id = _normalize_string(actor.get("employee_id"))
        if employee_id:
            busy_identity_values.add(employee_id)
        busy = bool(busy_identity_values & active_lease_actor_ids)
        provider_id = _resolve_provider_id(actor)
        provider_paused = provider_id in paused_provider_ids if provider_id else False
        exclusion_matches = _matching_scoped_exclusions(
            actor_id=actor_id,
            employee_id=employee_id,
            ticket_id=ticket_id,
            workflow_id=workflow_id,
            node_id=node_id,
            required_capabilities=normalized_required_capabilities,
            scoped_exclusions=scoped_exclusions,
            attempt_no=attempt_no,
        )
        excluded = bool(exclusion_matches)
        eligible = (
            status_eligible
            and not missing_capabilities
            and not busy
            and not provider_paused
            and not excluded
        )
        candidate_detail = {
            "actor_id": actor_id,
            "employee_id": _normalize_string(actor.get("employee_id")) or None,
            "status": status or None,
            "status_eligible": status_eligible,
            "capability_set": capability_set,
            "missing_capabilities": missing_capabilities,
            "busy": busy,
            "provider_id": provider_id,
            "provider_paused": provider_paused,
            "excluded": excluded,
            "exclusion_matches": exclusion_matches,
            "eligible": eligible,
        }
        candidate_details.append(candidate_detail)
        if eligible and selected_actor is None:
            selected_actor = actor

    if selected_actor is not None:
        return AssignmentResolution(
            selected_actor_id=_normalize_string(selected_actor.get("actor_id")) or None,
            selected_actor=selected_actor,
            candidate_details=candidate_details,
            diagnostic_payload=None,
        )

    diagnostic_payload = {
        "ticket_id": ticket_id,
        "workflow_id": workflow_id,
        "node_id": node_id,
        "reason_code": "NO_ELIGIBLE_ACTOR",
        "required_capabilities": normalized_required_capabilities,
        "candidate_summary": _build_candidate_summary(candidate_details),
        "candidate_details": candidate_details,
        "suggested_actions": list(NO_ELIGIBLE_ACTOR_SUGGESTED_ACTIONS),
    }
    return AssignmentResolution(
        selected_actor_id=None,
        selected_actor=None,
        candidate_details=candidate_details,
        diagnostic_payload=diagnostic_payload,
    )


def _build_candidate_summary(candidate_details: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total_candidate_count": len(candidate_details),
        "eligible_count": sum(1 for detail in candidate_details if detail["eligible"]),
        "status_ineligible_count": sum(1 for detail in candidate_details if not detail["status_eligible"]),
        "missing_capability_count": sum(1 for detail in candidate_details if detail["missing_capabilities"]),
        "busy_count": sum(1 for detail in candidate_details if detail["busy"]),
        "provider_paused_count": sum(1 for detail in candidate_details if detail["provider_paused"]),
        "excluded_count": sum(1 for detail in candidate_details if detail["excluded"]),
    }


def _matching_scoped_exclusions(
    *,
    actor_id: str,
    employee_id: str,
    ticket_id: str,
    workflow_id: str,
    node_id: str,
    required_capabilities: list[str],
    scoped_exclusions: list[dict[str, Any]],
    attempt_no: int | None,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    actor_identity_values = {actor_id}
    if employee_id:
        actor_identity_values.add(employee_id)
    for exclusion in scoped_exclusions:
        if _normalize_string(exclusion.get("actor_id")) not in actor_identity_values:
            continue
        if _scoped_exclusion_matches(
            exclusion=exclusion,
            ticket_id=ticket_id,
            workflow_id=workflow_id,
            node_id=node_id,
            required_capabilities=required_capabilities,
            attempt_no=attempt_no,
        ):
            matches.append(dict(exclusion))
    return matches


def _scoped_exclusion_matches(
    *,
    exclusion: dict[str, Any],
    ticket_id: str,
    workflow_id: str,
    node_id: str,
    required_capabilities: list[str],
    attempt_no: int | None,
) -> bool:
    scope = _normalize_string(exclusion.get("scope"))
    if scope == "ticket":
        exclusion_ticket_id = _normalize_string(exclusion.get("ticket_id"))
        return bool(exclusion_ticket_id) and exclusion_ticket_id == ticket_id
    if scope == "node":
        exclusion_node_id = _normalize_string(exclusion.get("node_id"))
        return bool(exclusion_node_id) and exclusion_node_id == node_id
    if scope == "workflow":
        exclusion_workflow_id = _normalize_string(exclusion.get("workflow_id"))
        return bool(exclusion_workflow_id) and exclusion_workflow_id == workflow_id
    if scope == "capability":
        capability = _normalize_string(exclusion.get("capability"))
        return bool(capability) and capability in required_capabilities
    if scope == "attempt":
        exclusion_ticket_id = _normalize_string(exclusion.get("ticket_id"))
        exclusion_attempt_no = exclusion.get("attempt_no")
        return (
            bool(exclusion_ticket_id)
            and exclusion_ticket_id == ticket_id
            and attempt_no is not None
            and exclusion_attempt_no == attempt_no
        )
    return False


def _resolve_provider_id(actor: dict[str, Any]) -> str | None:
    provider_preferences = actor.get("provider_preferences")
    if not isinstance(provider_preferences, dict):
        return None
    provider_id = _normalize_string(provider_preferences.get("provider_id"))
    if provider_id:
        return provider_id
    preferred_provider_id = _normalize_string(provider_preferences.get("preferred_provider_id"))
    return preferred_provider_id or None


def _normalize_string_list(values: list[Any]) -> list[str]:
    normalized_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized_value = _normalize_string(value)
        if not normalized_value or normalized_value in seen:
            continue
        seen.add(normalized_value)
        normalized_values.append(normalized_value)
    return normalized_values


def _normalize_string(value: Any) -> str:
    return str(value or "").strip()
