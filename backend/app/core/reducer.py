from __future__ import annotations

import json
import hashlib
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any

from app.core.constants import (
    BLOCKING_REASON_BOARD_REJECTED,
    BLOCKING_REASON_BOARD_REVIEW_REQUIRED,
    BLOCKING_REASON_MODIFY_CONSTRAINTS,
    BLOCKING_REASON_PROVIDER_REQUIRED,
    CIRCUIT_BREAKER_STATE_CLOSED,
    CIRCUIT_BREAKER_STATE_OPEN,
    ACTOR_STATUS_ACTIVE,
    ACTOR_STATUS_DEACTIVATED,
    ACTOR_STATUS_REPLACED,
    ACTOR_STATUS_SUSPENDED,
    DEFAULT_BOARD_GATE_STATE,
    EMPLOYEE_STATE_ACTIVE,
    EMPLOYEE_STATE_FROZEN,
    EMPLOYEE_STATE_REPLACED,
    DEFAULT_TENANT_ID,
    DEFAULT_WORKFLOW_STAGE,
    DEFAULT_WORKFLOW_STATUS,
    DEFAULT_WORKSPACE_ID,
    EVENT_BOARD_REVIEW_APPROVED,
    EVENT_BOARD_REVIEW_REJECTED,
    EVENT_BOARD_REVIEW_REQUIRED,
    EVENT_CIRCUIT_BREAKER_CLOSED,
    EVENT_CIRCUIT_BREAKER_OPENED,
    EVENT_EMPLOYEE_FROZEN,
    EVENT_EMPLOYEE_HIRED,
    EVENT_EMPLOYEE_REPLACED,
    EVENT_EMPLOYEE_RESTORED,
    EVENT_ACTOR_DEACTIVATED,
    EVENT_ACTOR_ENABLED,
    EVENT_ACTOR_REPLACED,
    EVENT_ACTOR_SUSPENDED,
    EVENT_TICKET_ASSIGNED,
    EVENT_TICKET_LEASE_GRANTED,
    EVENT_INCIDENT_CLOSED,
    EVENT_INCIDENT_RECOVERY_STARTED,
    EVENT_INCIDENT_OPENED,
    EVENT_PROVIDER_ATTEMPT_FINISHED,
    EVENT_PROVIDER_ATTEMPT_HEARTBEAT_RECORDED,
    EVENT_PROVIDER_ATTEMPT_STARTED,
    EVENT_PROVIDER_ATTEMPT_TIMED_OUT,
    EVENT_PROVIDER_FIRST_TOKEN_RECEIVED,
    EVENT_TICKET_CANCELLED,
    EVENT_TICKET_CANCEL_REQUESTED,
    EVENT_TICKET_COMPLETED,
    EVENT_TICKET_CREATED,
    EVENT_TICKET_EXECUTION_PRECONDITION_BLOCKED,
    EVENT_TICKET_EXECUTION_PRECONDITION_CLEARED,
    EVENT_TICKET_FAILED,
    EVENT_TICKET_HEARTBEAT_RECORDED,
    EVENT_TICKET_LEASED,
    EVENT_TICKET_RETRY_SCHEDULED,
    EVENT_TICKET_STARTED,
    EVENT_TICKET_TIMED_OUT,
    EVENT_WORKFLOW_CREATED,
    NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW,
    NODE_STATUS_CANCELLED,
    NODE_STATUS_CANCEL_REQUESTED,
    NODE_STATUS_COMPLETED,
    NODE_STATUS_EXECUTING,
    NODE_STATUS_PENDING,
    NODE_STATUS_REWORK_REQUIRED,
    TICKET_STATUS_BLOCKED_FOR_BOARD_REVIEW,
    TICKET_STATUS_CANCELLED,
    TICKET_STATUS_CANCEL_REQUESTED,
    TICKET_STATUS_COMPLETED,
    TICKET_STATUS_EXECUTING,
    TICKET_STATUS_FAILED,
    TICKET_STATUS_LEASED,
    TICKET_STATUS_PENDING,
    TICKET_STATUS_REWORK_REQUIRED,
    TICKET_STATUS_TIMED_OUT,
)
from app.core.persona_profiles import normalize_persona_profiles
from app.core.graph_identity import GraphIdentityResolutionError, resolve_ticket_graph_identity
from app.core.versioning import build_graph_version
from app.core.workflow_completion import (
    infer_workflow_current_stage,
    resolve_workflow_closeout_completion,
)


def _event_payload(event: dict) -> dict:
    payload = event.get("payload")
    if payload is not None:
        return payload
    return json.loads(event["payload_json"])


def _base_ticket_projection(event: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "ticket_id": payload["ticket_id"],
        "workflow_id": event["workflow_id"],
        "node_id": payload["node_id"],
        "tenant_id": payload.get("tenant_id", DEFAULT_TENANT_ID),
        "workspace_id": payload.get("workspace_id", DEFAULT_WORKSPACE_ID),
        "actor_id": None,
        "assignment_id": None,
        "lease_id": None,
        "lease_owner": None,
        "lease_expires_at": None,
        "started_at": None,
        "last_heartbeat_at": None,
        "heartbeat_expires_at": None,
        "heartbeat_timeout_sec": None,
        "retry_count": payload.get("retry_count", 0),
        "retry_budget": payload.get("retry_budget"),
        "timeout_sla_sec": payload.get("timeout_sla_sec"),
        "priority": payload.get("priority"),
        "last_failure_kind": None,
        "last_failure_message": None,
        "last_failure_fingerprint": None,
        "blocking_reason_code": None,
    }


def _base_node_projection(event: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "workflow_id": event["workflow_id"],
        "node_id": payload["node_id"],
        "latest_ticket_id": payload["ticket_id"],
        "blocking_reason_code": None,
    }


def _resolve_scope(
    payload: dict[str, Any],
    previous_projection: dict[str, Any] | None = None,
) -> tuple[str, str]:
    previous_projection = previous_projection or {}
    tenant_id = str(
        payload.get("tenant_id")
        or previous_projection.get("tenant_id")
        or DEFAULT_TENANT_ID
    )
    workspace_id = str(
        payload.get("workspace_id")
        or previous_projection.get("workspace_id")
        or DEFAULT_WORKSPACE_ID
    )
    return tenant_id, workspace_id


def _base_incident_projection(event: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "incident_id": payload["incident_id"],
        "workflow_id": event["workflow_id"],
        "node_id": payload.get("node_id"),
        "ticket_id": payload.get("ticket_id"),
        "provider_id": payload.get("provider_id"),
        "incident_type": payload.get("incident_type"),
        "status": payload.get("status"),
        "severity": payload.get("severity"),
        "fingerprint": payload.get("fingerprint"),
        "circuit_breaker_state": None,
        "opened_at": None,
        "closed_at": None,
        "payload": payload,
    }


PROVIDER_ATTEMPT_TERMINAL_STATES = {
    "COMPLETED",
    "FAILED_RETRYABLE",
    "FAILED_TERMINAL",
    "TIMED_OUT",
}


def _fallback_attempt_id(payload: dict[str, Any], workflow_id: str | None) -> str:
    ticket_id = str(payload.get("ticket_id") or "unknown-ticket")
    attempt_no = int(payload.get("attempt_no") or 1)
    return f"attempt:{workflow_id or 'unknown-workflow'}:{ticket_id}:{attempt_no}"


def _fallback_provider_policy_ref(payload: dict[str, Any]) -> str:
    provider_id = str(payload.get("provider_id") or payload.get("actual_provider_id") or "unknown-provider")
    model = str(payload.get("actual_model") or payload.get("preferred_model") or "unknown-model")
    reasoning = str(payload.get("effective_reasoning_effort") or "unknown-reasoning")
    adapter = str(payload.get("adapter_kind") or "unknown-adapter")
    return f"provider-policy:{provider_id}:{model}:{reasoning}:{adapter}"


def _attempt_id_from_payload(payload: dict[str, Any], workflow_id: str | None) -> str:
    return str(payload.get("attempt_id") or _fallback_attempt_id(payload, workflow_id))


def rebuild_execution_attempt_projections(events: Iterable[dict]) -> list[dict]:
    projections: dict[str, dict[str, Any]] = {}
    for event in events:
        event_type = event["event_type"]
        if event_type not in {
            EVENT_PROVIDER_ATTEMPT_STARTED,
            EVENT_PROVIDER_FIRST_TOKEN_RECEIVED,
            EVENT_PROVIDER_ATTEMPT_HEARTBEAT_RECORDED,
            EVENT_PROVIDER_ATTEMPT_FINISHED,
            EVENT_PROVIDER_ATTEMPT_TIMED_OUT,
        }:
            continue

        payload = _event_payload(event)
        workflow_id = str(payload.get("workflow_id") or event.get("workflow_id") or "")
        ticket_id = str(payload.get("ticket_id") or "")
        node_id = str(payload.get("node_id") or "")
        if not workflow_id or not ticket_id or not node_id:
            continue
        attempt_id = _attempt_id_from_payload(payload, workflow_id)
        occurred_at = event["occurred_at"].isoformat()
        version = event["sequence_no"]

        if event_type == EVENT_PROVIDER_ATTEMPT_STARTED:
            projections[attempt_id] = {
                "attempt_id": attempt_id,
                "workflow_id": workflow_id,
                "ticket_id": ticket_id,
                "node_id": node_id,
                "attempt_no": int(payload.get("attempt_no") or 1),
                "idempotency_key": str(payload.get("attempt_idempotency_key") or payload.get("idempotency_key") or ""),
                "provider_policy_ref": str(payload.get("provider_policy_ref") or _fallback_provider_policy_ref(payload)),
                "deadline_at": str(payload.get("deadline_at") or occurred_at),
                "last_heartbeat_at": str(payload.get("last_heartbeat_at") or occurred_at),
                "state": str(payload.get("state") or "PROVIDER_CONNECTING"),
                "failure_kind": None,
                "failure_fingerprint": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        projection = projections.get(attempt_id)
        if projection is None:
            projection = {
                "attempt_id": attempt_id,
                "workflow_id": workflow_id,
                "ticket_id": ticket_id,
                "node_id": node_id,
                "attempt_no": int(payload.get("attempt_no") or 1),
                "idempotency_key": str(payload.get("attempt_idempotency_key") or payload.get("idempotency_key") or ""),
                "provider_policy_ref": str(payload.get("provider_policy_ref") or _fallback_provider_policy_ref(payload)),
                "deadline_at": str(payload.get("deadline_at") or occurred_at),
                "last_heartbeat_at": None,
                "state": "CREATED",
                "failure_kind": None,
                "failure_fingerprint": None,
                "updated_at": occurred_at,
                "version": version,
            }

        if str(projection.get("state") or "") in PROVIDER_ATTEMPT_TERMINAL_STATES:
            projections[attempt_id] = projection
            continue

        if event_type in {EVENT_PROVIDER_FIRST_TOKEN_RECEIVED, EVENT_PROVIDER_ATTEMPT_HEARTBEAT_RECORDED}:
            projection = {
                **projection,
                "state": "STREAMING",
                "last_heartbeat_at": str(payload.get("last_heartbeat_at") or occurred_at),
                "updated_at": occurred_at,
                "version": version,
            }
        elif event_type == EVENT_PROVIDER_ATTEMPT_FINISHED:
            raw_state = str(payload.get("state") or "").strip()
            status = str(payload.get("status") or "").strip().upper()
            if raw_state:
                state = raw_state
            elif status == "COMPLETED":
                state = "COMPLETED"
            elif bool(payload.get("retryable")):
                state = "FAILED_RETRYABLE"
            else:
                state = "FAILED_TERMINAL"
            projection = {
                **projection,
                "state": state,
                "failure_kind": payload.get("failure_kind"),
                "failure_fingerprint": payload.get("fingerprint") or payload.get("failure_fingerprint"),
                "updated_at": occurred_at,
                "version": version,
            }
        elif event_type == EVENT_PROVIDER_ATTEMPT_TIMED_OUT:
            projection = {
                **projection,
                "state": "TIMED_OUT",
                "failure_kind": payload.get("failure_kind"),
                "failure_fingerprint": payload.get("fingerprint") or payload.get("failure_fingerprint"),
                "updated_at": occurred_at,
                "version": version,
            }
        projections[attempt_id] = projection

    return sorted(projections.values(), key=lambda item: (item["updated_at"], item["attempt_id"]))


def _coerce_iso_datetime(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return value


def _normalized_ticket_projection_for_workflow(projection: dict[str, Any]) -> dict[str, Any]:
    return {
        **projection,
        "lease_expires_at": _coerce_iso_datetime(projection.get("lease_expires_at")),
        "started_at": _coerce_iso_datetime(projection.get("started_at")),
        "last_heartbeat_at": _coerce_iso_datetime(projection.get("last_heartbeat_at")),
        "heartbeat_expires_at": _coerce_iso_datetime(projection.get("heartbeat_expires_at")),
        "updated_at": _coerce_iso_datetime(projection.get("updated_at")),
    }


def _normalized_node_projection_for_workflow(projection: dict[str, Any]) -> dict[str, Any]:
    return {
        **projection,
        "updated_at": _coerce_iso_datetime(projection.get("updated_at")),
    }


def rebuild_workflow_projections(events: Iterable[dict]) -> list[dict]:
    event_list = list(events)
    projections: dict[str, dict] = {}
    created_specs_by_ticket: dict[str, dict[str, Any]] = {}
    ticket_state_by_id: dict[str, dict[str, Any]] = {}
    node_state_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    open_approval_count_by_workflow: dict[str, int] = {}
    open_incident_count_by_workflow: dict[str, int] = {}

    for event in event_list:
        payload = _event_payload(event)
        event_type = event["event_type"]
        workflow_id = event["workflow_id"]

        if event_type == EVENT_WORKFLOW_CREATED:
            projections[workflow_id] = {
                "workflow_id": workflow_id,
                "title": payload.get("title") or payload["north_star_goal"],
                "north_star_goal": payload["north_star_goal"],
                "workflow_profile": str(payload.get("workflow_profile") or "STANDARD"),
                "tenant_id": payload.get("tenant_id", DEFAULT_TENANT_ID),
                "workspace_id": payload.get("workspace_id", DEFAULT_WORKSPACE_ID),
                "current_stage": DEFAULT_WORKFLOW_STAGE,
                "status": DEFAULT_WORKFLOW_STATUS,
                "budget_total": payload["budget_cap"],
                "budget_used": 0,
                "board_gate_state": DEFAULT_BOARD_GATE_STATE,
                "deadline_at": payload.get("deadline_at"),
                "started_at": event["occurred_at"].isoformat(),
                "updated_at": event["occurred_at"].isoformat(),
                "version": event["sequence_no"],
            }
            open_approval_count_by_workflow[workflow_id] = 0
            open_incident_count_by_workflow[workflow_id] = 0
            continue

        if workflow_id is None or workflow_id not in projections:
            continue

        projection = projections[workflow_id]
        occurred_at = event["occurred_at"].isoformat()
        projection["updated_at"] = occurred_at
        projection["version"] = event["sequence_no"]

        if event_type == EVENT_TICKET_CREATED:
            ticket_id = str(payload["ticket_id"])
            node_id = str(payload["node_id"])
            created_specs_by_ticket[ticket_id] = payload
            ticket_state_by_id[ticket_id] = {
                "ticket_id": ticket_id,
                "workflow_id": workflow_id,
                "node_id": node_id,
                "status": TICKET_STATUS_PENDING,
                "updated_at": event["occurred_at"],
            }
            node_state_by_key[(workflow_id, node_id)] = {
                "workflow_id": workflow_id,
                "node_id": node_id,
                "latest_ticket_id": ticket_id,
                "status": NODE_STATUS_PENDING,
                "updated_at": event["occurred_at"],
            }
            continue

        if event_type == EVENT_TICKET_LEASED:
            ticket_id = str(payload["ticket_id"])
            node_id = str(payload["node_id"])
            ticket_state = ticket_state_by_id.get(
                ticket_id,
                {"ticket_id": ticket_id, "workflow_id": workflow_id, "node_id": node_id},
            )
            ticket_state_by_id[ticket_id] = {
                **ticket_state,
                "status": TICKET_STATUS_LEASED,
                "updated_at": event["occurred_at"],
            }
            node_state_by_key[(workflow_id, node_id)] = {
                **node_state_by_key.get(
                    (workflow_id, node_id),
                    {
                        "workflow_id": workflow_id,
                        "node_id": node_id,
                    },
                ),
                "latest_ticket_id": ticket_id,
                "status": NODE_STATUS_PENDING,
                "updated_at": event["occurred_at"],
            }
            continue

        if event_type == EVENT_TICKET_STARTED:
            ticket_id = str(payload["ticket_id"])
            node_id = str(payload["node_id"])
            ticket_state = ticket_state_by_id.get(
                ticket_id,
                {"ticket_id": ticket_id, "workflow_id": workflow_id, "node_id": node_id},
            )
            ticket_state_by_id[ticket_id] = {
                **ticket_state,
                "status": TICKET_STATUS_EXECUTING,
                "updated_at": event["occurred_at"],
            }
            node_state_by_key[(workflow_id, node_id)] = {
                **node_state_by_key.get(
                    (workflow_id, node_id),
                    {
                        "workflow_id": workflow_id,
                        "node_id": node_id,
                    },
                ),
                "latest_ticket_id": ticket_id,
                "status": NODE_STATUS_EXECUTING,
                "updated_at": event["occurred_at"],
            }
            continue

        if event_type == EVENT_TICKET_CANCEL_REQUESTED:
            ticket_id = str(payload["ticket_id"])
            node_id = str(payload["node_id"])
            ticket_state = ticket_state_by_id.get(
                ticket_id,
                {"ticket_id": ticket_id, "workflow_id": workflow_id, "node_id": node_id},
            )
            ticket_state_by_id[ticket_id] = {
                **ticket_state,
                "status": TICKET_STATUS_CANCEL_REQUESTED,
                "updated_at": event["occurred_at"],
            }
            node_state_by_key[(workflow_id, node_id)] = {
                **node_state_by_key.get(
                    (workflow_id, node_id),
                    {
                        "workflow_id": workflow_id,
                        "node_id": node_id,
                    },
                ),
                "latest_ticket_id": ticket_id,
                "status": NODE_STATUS_CANCEL_REQUESTED,
                "updated_at": event["occurred_at"],
            }
            continue

        if event_type == EVENT_TICKET_CANCELLED:
            ticket_id = str(payload["ticket_id"])
            node_id = str(payload["node_id"])
            ticket_state = ticket_state_by_id.get(
                ticket_id,
                {"ticket_id": ticket_id, "workflow_id": workflow_id, "node_id": node_id},
            )
            ticket_state_by_id[ticket_id] = {
                **ticket_state,
                "status": TICKET_STATUS_CANCELLED,
                "updated_at": event["occurred_at"],
            }
            node_state_by_key[(workflow_id, node_id)] = {
                **node_state_by_key.get(
                    (workflow_id, node_id),
                    {
                        "workflow_id": workflow_id,
                        "node_id": node_id,
                    },
                ),
                "latest_ticket_id": ticket_id,
                "status": NODE_STATUS_CANCELLED,
                "updated_at": event["occurred_at"],
            }
            continue

        if event_type == EVENT_TICKET_COMPLETED:
            ticket_id = str(payload["ticket_id"])
            node_id = str(payload["node_id"])
            ticket_state = ticket_state_by_id.get(
                ticket_id,
                {"ticket_id": ticket_id, "workflow_id": workflow_id, "node_id": node_id},
            )
            ticket_state_by_id[ticket_id] = {
                **ticket_state,
                "status": TICKET_STATUS_COMPLETED,
                "updated_at": event["occurred_at"],
            }
            if not payload.get("board_review_requested"):
                node_state_by_key[(workflow_id, node_id)] = {
                    **node_state_by_key.get(
                        (workflow_id, node_id),
                        {
                            "workflow_id": workflow_id,
                            "node_id": node_id,
                        },
                    ),
                    "latest_ticket_id": ticket_id,
                    "status": NODE_STATUS_COMPLETED,
                    "updated_at": event["occurred_at"],
                }
            continue

        if event_type == EVENT_TICKET_FAILED:
            ticket_id = str(payload["ticket_id"])
            node_id = str(payload["node_id"])
            ticket_state = ticket_state_by_id.get(
                ticket_id,
                {"ticket_id": ticket_id, "workflow_id": workflow_id, "node_id": node_id},
            )
            ticket_state_by_id[ticket_id] = {
                **ticket_state,
                "status": TICKET_STATUS_FAILED,
                "updated_at": event["occurred_at"],
            }
            node_state_by_key[(workflow_id, node_id)] = {
                **node_state_by_key.get(
                    (workflow_id, node_id),
                    {
                        "workflow_id": workflow_id,
                        "node_id": node_id,
                    },
                ),
                "latest_ticket_id": ticket_id,
                "status": NODE_STATUS_REWORK_REQUIRED,
                "updated_at": event["occurred_at"],
            }
            continue

        if event_type == EVENT_TICKET_TIMED_OUT:
            ticket_id = str(payload["ticket_id"])
            node_id = str(payload["node_id"])
            ticket_state = ticket_state_by_id.get(
                ticket_id,
                {"ticket_id": ticket_id, "workflow_id": workflow_id, "node_id": node_id},
            )
            ticket_state_by_id[ticket_id] = {
                **ticket_state,
                "status": TICKET_STATUS_TIMED_OUT,
                "updated_at": event["occurred_at"],
            }
            node_state_by_key[(workflow_id, node_id)] = {
                **node_state_by_key.get(
                    (workflow_id, node_id),
                    {
                        "workflow_id": workflow_id,
                        "node_id": node_id,
                    },
                ),
                "latest_ticket_id": ticket_id,
                "status": NODE_STATUS_REWORK_REQUIRED,
                "updated_at": event["occurred_at"],
            }
            continue

        if event_type == EVENT_BOARD_REVIEW_REQUIRED:
            ticket_id = payload.get("ticket_id")
            node_id = payload.get("node_id")
            if ticket_id is None or node_id is None:
                continue
            ticket_state_by_id[str(ticket_id)] = {
                **ticket_state_by_id.get(
                    str(ticket_id),
                    {"ticket_id": str(ticket_id), "workflow_id": workflow_id, "node_id": str(node_id)},
                ),
                "status": TICKET_STATUS_BLOCKED_FOR_BOARD_REVIEW,
                "updated_at": event["occurred_at"],
            }
            node_state_by_key[(workflow_id, str(node_id))] = {
                **node_state_by_key.get(
                    (workflow_id, str(node_id)),
                    {
                        "workflow_id": workflow_id,
                        "node_id": str(node_id),
                    },
                ),
                "latest_ticket_id": str(ticket_id),
                "status": NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW,
                "updated_at": event["occurred_at"],
            }
            open_approval_count_by_workflow[workflow_id] = open_approval_count_by_workflow.get(workflow_id, 0) + 1
            continue

        if event_type == EVENT_BOARD_REVIEW_APPROVED:
            ticket_id = payload.get("ticket_id")
            node_id = payload.get("node_id")
            if ticket_id is not None and node_id is not None:
                ticket_state_by_id[str(ticket_id)] = {
                    **ticket_state_by_id.get(
                        str(ticket_id),
                        {"ticket_id": str(ticket_id), "workflow_id": workflow_id, "node_id": str(node_id)},
                    ),
                    "status": TICKET_STATUS_COMPLETED,
                    "updated_at": event["occurred_at"],
                }
                node_state_by_key[(workflow_id, str(node_id))] = {
                    **node_state_by_key.get(
                        (workflow_id, str(node_id)),
                        {
                            "workflow_id": workflow_id,
                            "node_id": str(node_id),
                        },
                    ),
                    "latest_ticket_id": str(ticket_id),
                    "status": NODE_STATUS_COMPLETED,
                    "updated_at": event["occurred_at"],
                }
            open_approval_count_by_workflow[workflow_id] = max(
                open_approval_count_by_workflow.get(workflow_id, 0) - 1,
                0,
            )
            continue

        if event_type == EVENT_BOARD_REVIEW_REJECTED:
            ticket_id = payload.get("ticket_id")
            node_id = payload.get("node_id")
            if ticket_id is not None and node_id is not None:
                ticket_state_by_id[str(ticket_id)] = {
                    **ticket_state_by_id.get(
                        str(ticket_id),
                        {"ticket_id": str(ticket_id), "workflow_id": workflow_id, "node_id": str(node_id)},
                    ),
                    "status": TICKET_STATUS_REWORK_REQUIRED,
                    "updated_at": event["occurred_at"],
                }
                node_state_by_key[(workflow_id, str(node_id))] = {
                    **node_state_by_key.get(
                        (workflow_id, str(node_id)),
                        {
                            "workflow_id": workflow_id,
                            "node_id": str(node_id),
                        },
                    ),
                    "latest_ticket_id": str(ticket_id),
                    "status": NODE_STATUS_REWORK_REQUIRED,
                    "updated_at": event["occurred_at"],
                }
            open_approval_count_by_workflow[workflow_id] = max(
                open_approval_count_by_workflow.get(workflow_id, 0) - 1,
                0,
            )
            continue

        if event_type == EVENT_INCIDENT_OPENED:
            open_incident_count_by_workflow[workflow_id] = open_incident_count_by_workflow.get(workflow_id, 0) + 1
            continue

        if event_type == EVENT_INCIDENT_CLOSED:
            open_incident_count_by_workflow[workflow_id] = max(
                open_incident_count_by_workflow.get(workflow_id, 0) - 1,
                0,
            )

    ticket_projections = rebuild_ticket_projections(event_list)
    node_projections = rebuild_node_projections(event_list)
    incident_projections = rebuild_incident_projections(event_list)
    tickets_by_workflow: dict[str, list[dict[str, Any]]] = {}
    nodes_by_workflow: dict[str, list[dict[str, Any]]] = {}
    open_incident_count_by_workflow_from_projection: dict[str, int] = {}
    for ticket in ticket_projections:
        tickets_by_workflow.setdefault(str(ticket["workflow_id"]), []).append(
            _normalized_ticket_projection_for_workflow(ticket)
        )
    for node in node_projections:
        nodes_by_workflow.setdefault(str(node["workflow_id"]), []).append(
            _normalized_node_projection_for_workflow(node)
        )
    for incident in incident_projections:
        if str(incident.get("status") or "") != "OPEN":
            continue
        workflow_id = str(incident.get("workflow_id") or "")
        if not workflow_id:
            continue
        open_incident_count_by_workflow_from_projection[workflow_id] = (
            open_incident_count_by_workflow_from_projection.get(workflow_id, 0) + 1
        )

    ticket_terminal_events_by_ticket: dict[str, dict[str, Any]] = {}
    for event in event_list:
        event_type = event["event_type"]
        if event_type not in {EVENT_TICKET_COMPLETED, EVENT_TICKET_FAILED, EVENT_TICKET_TIMED_OUT}:
            continue
        payload = _event_payload(event)
        ticket_id = str(payload.get("ticket_id") or "")
        if not ticket_id:
            continue
        ticket_terminal_events_by_ticket[ticket_id] = {
            "event_type": event_type,
            "occurred_at": event["occurred_at"],
            "payload": payload,
        }

    for workflow_id, projection in projections.items():
        workflow_tickets = list(tickets_by_workflow.get(workflow_id, []))
        workflow_nodes = list(nodes_by_workflow.get(workflow_id, []))
        workflow_created_specs = {
            ticket_id: created_spec
            for ticket_id, created_spec in created_specs_by_ticket.items()
            if str(created_spec.get("workflow_id") or workflow_id) == workflow_id
        }
        workflow_terminal_events = {
            str(ticket["ticket_id"]): ticket_terminal_events_by_ticket.get(str(ticket["ticket_id"]))
            for ticket in workflow_tickets
        }
        closeout_completion = resolve_workflow_closeout_completion(
            tickets=workflow_tickets,
            nodes=workflow_nodes,
            has_open_approval=open_approval_count_by_workflow.get(workflow_id, 0) > 0,
            has_open_incident=open_incident_count_by_workflow_from_projection.get(workflow_id, 0) > 0,
            created_specs_by_ticket=workflow_created_specs,
            ticket_terminal_events_by_ticket=workflow_terminal_events,
        )
        projection["status"] = "COMPLETED" if closeout_completion is not None else DEFAULT_WORKFLOW_STATUS
        projection["current_stage"] = infer_workflow_current_stage(
            nodes=workflow_nodes,
            created_specs_by_ticket=workflow_created_specs,
            closeout_completion=closeout_completion,
        )

    return list(projections.values())


def _dedupe_text_values(values: Iterable[Any]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        deduped.append(normalized)
        seen.add(normalized)
    return deduped


def rebuild_actor_projections(events: Iterable[dict]) -> list[dict[str, Any]]:
    projections: dict[str, dict[str, Any]] = {}

    for event in events:
        event_type = event["event_type"]
        if event_type not in {
            EVENT_ACTOR_ENABLED,
            EVENT_ACTOR_SUSPENDED,
            EVENT_ACTOR_DEACTIVATED,
            EVENT_ACTOR_REPLACED,
        }:
            continue

        payload = _event_payload(event)
        actor_id = str(payload.get("actor_id") or "").strip()
        if not actor_id:
            continue
        occurred_at = event["occurred_at"].isoformat()
        version = int(event["sequence_no"])
        previous_projection = projections.get(actor_id, {})

        if event_type == EVENT_ACTOR_ENABLED:
            projections[actor_id] = {
                "actor_id": actor_id,
                "employee_id": payload.get("employee_id") or previous_projection.get("employee_id"),
                "status": ACTOR_STATUS_ACTIVE,
                "capability_set": _dedupe_text_values(payload.get("capability_set") or []),
                "provider_preferences": dict(payload.get("provider_preferences") or {}),
                "availability": dict(payload.get("availability") or {}),
                "created_from_policy": str(payload.get("created_from_policy") or ""),
                "deactivated_reason": None,
                "replaced_by_actor_id": None,
                "replacement_reason": None,
                "replacement_plan": None,
                "lifecycle_reason": payload.get("audit_reason"),
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_ACTOR_SUSPENDED:
            projections[actor_id] = {
                **previous_projection,
                "actor_id": actor_id,
                "employee_id": previous_projection.get("employee_id") or payload.get("employee_id"),
                "status": ACTOR_STATUS_SUSPENDED,
                "capability_set": list(previous_projection.get("capability_set") or []),
                "provider_preferences": dict(previous_projection.get("provider_preferences") or {}),
                "availability": dict(previous_projection.get("availability") or {}),
                "created_from_policy": previous_projection.get("created_from_policy"),
                "deactivated_reason": None,
                "lifecycle_reason": payload.get("suspended_reason") or payload.get("reason"),
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_ACTOR_DEACTIVATED:
            projections[actor_id] = {
                **previous_projection,
                "actor_id": actor_id,
                "employee_id": previous_projection.get("employee_id") or payload.get("employee_id"),
                "status": ACTOR_STATUS_DEACTIVATED,
                "capability_set": list(previous_projection.get("capability_set") or []),
                "provider_preferences": dict(previous_projection.get("provider_preferences") or {}),
                "availability": dict(previous_projection.get("availability") or {}),
                "created_from_policy": previous_projection.get("created_from_policy"),
                "deactivated_reason": payload.get("deactivated_reason") or payload.get("reason"),
                "replacement_plan": payload.get("replacement_plan"),
                "lifecycle_reason": payload.get("deactivated_reason") or payload.get("reason"),
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_ACTOR_REPLACED:
            replacement_actor_id = str(payload.get("replacement_actor_id") or "").strip() or None
            replacement_reason = payload.get("replacement_reason") or payload.get("reason")
            projections[actor_id] = {
                **previous_projection,
                "actor_id": actor_id,
                "employee_id": previous_projection.get("employee_id") or payload.get("employee_id"),
                "status": ACTOR_STATUS_REPLACED,
                "capability_set": list(previous_projection.get("capability_set") or []),
                "provider_preferences": dict(previous_projection.get("provider_preferences") or {}),
                "availability": dict(previous_projection.get("availability") or {}),
                "created_from_policy": previous_projection.get("created_from_policy"),
                "deactivated_reason": previous_projection.get("deactivated_reason"),
                "replaced_by_actor_id": replacement_actor_id,
                "replacement_reason": replacement_reason,
                "replacement_plan": payload.get("replacement_plan"),
                "lifecycle_reason": replacement_reason,
                "updated_at": occurred_at,
                "version": version,
            }

    return [projections[actor_id] for actor_id in sorted(projections)]


def _assignment_provider_selection(payload: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "preferred_provider_id",
        "preferred_model",
        "actual_provider_id",
        "actual_model",
        "selection_reason",
        "policy_reason",
        "fallback_reason",
        "provider_health_snapshot",
        "cost_class",
        "latency_class",
    )
    return {key: payload.get(key) for key in keys if key in payload}


def rebuild_assignment_projections(events: Iterable[dict]) -> list[dict[str, Any]]:
    projections: dict[str, dict[str, Any]] = {}

    for event in events:
        if event["event_type"] != EVENT_TICKET_ASSIGNED:
            continue
        payload = _event_payload(event)
        assignment_id = str(payload.get("assignment_id") or "").strip()
        actor_id = str(payload.get("actor_id") or "").strip()
        ticket_id = str(payload.get("ticket_id") or "").strip()
        node_id = str(payload.get("node_id") or "").strip()
        workflow_id = str(payload.get("workflow_id") or event.get("workflow_id") or "").strip()
        if not assignment_id or not actor_id or not ticket_id or not node_id or not workflow_id:
            continue
        occurred_at = event["occurred_at"].isoformat()
        projections[assignment_id] = {
            "assignment_id": assignment_id,
            "workflow_id": workflow_id,
            "ticket_id": ticket_id,
            "node_id": node_id,
            "actor_id": actor_id,
            "required_capabilities": _dedupe_text_values(payload.get("required_capabilities") or []),
            "status": str(payload.get("status") or "ASSIGNED"),
            "assignment_reason": str(payload.get("assignment_reason") or payload.get("reason") or ""),
            "provider_selection": _assignment_provider_selection(payload),
            "assigned_at": str(payload.get("assigned_at") or occurred_at),
            "updated_at": occurred_at,
            "version": int(event["sequence_no"]),
        }

    return [projections[assignment_id] for assignment_id in sorted(projections)]


def rebuild_lease_projections(events: Iterable[dict]) -> list[dict[str, Any]]:
    projections: dict[str, dict[str, Any]] = {}

    for event in events:
        event_type = event["event_type"]
        if event_type not in {
            EVENT_TICKET_LEASE_GRANTED,
            EVENT_TICKET_STARTED,
            EVENT_TICKET_COMPLETED,
            EVENT_TICKET_FAILED,
            EVENT_TICKET_TIMED_OUT,
            EVENT_TICKET_CANCELLED,
        }:
            continue
        payload = _event_payload(event)
        lease_id = str(payload.get("lease_id") or "").strip()
        if not lease_id:
            continue
        occurred_at = event["occurred_at"].isoformat()
        previous_projection = projections.get(lease_id, {})
        if event_type == EVENT_TICKET_LEASE_GRANTED:
            projections[lease_id] = {
                "lease_id": lease_id,
                "assignment_id": str(payload.get("assignment_id") or ""),
                "workflow_id": str(payload.get("workflow_id") or event.get("workflow_id") or ""),
                "ticket_id": str(payload.get("ticket_id") or ""),
                "node_id": str(payload.get("node_id") or ""),
                "actor_id": str(payload.get("actor_id") or ""),
                "status": str(payload.get("status") or "LEASED"),
                "lease_timeout_sec": payload.get("lease_timeout_sec"),
                "lease_expires_at": payload.get("lease_expires_at"),
                "started_at": None,
                "closed_at": None,
                "failure_kind": None,
                "updated_at": occurred_at,
                "version": int(event["sequence_no"]),
            }
            continue
        if not previous_projection:
            continue
        status_by_event = {
            EVENT_TICKET_STARTED: "EXECUTING",
            EVENT_TICKET_COMPLETED: "RELEASED",
            EVENT_TICKET_FAILED: "FAILED",
            EVENT_TICKET_TIMED_OUT: "TIMED_OUT",
            EVENT_TICKET_CANCELLED: "CANCELLED",
        }
        projections[lease_id] = {
            **previous_projection,
            "status": status_by_event[event_type],
            "started_at": occurred_at if event_type == EVENT_TICKET_STARTED else previous_projection.get("started_at"),
            "closed_at": None if event_type == EVENT_TICKET_STARTED else occurred_at,
            "failure_kind": payload.get("failure_kind", previous_projection.get("failure_kind")),
            "updated_at": occurred_at,
            "version": int(event["sequence_no"]),
        }

    return [projections[lease_id] for lease_id in sorted(projections)]


def rebuild_employee_projections(events: Iterable[dict]) -> list[dict]:
    projections: dict[str, dict] = {}

    for event in events:
        payload = _event_payload(event)
        event_type = event["event_type"]
        occurred_at = event["occurred_at"].isoformat()
        version = event["sequence_no"]

        if event_type == EVENT_EMPLOYEE_HIRED:
            employee_id = payload["employee_id"]
            normalized_profiles = normalize_persona_profiles(
                str(payload.get("role_type") or "unknown"),
                skill_profile=payload.get("skill_profile"),
                personality_profile=payload.get("personality_profile"),
                aesthetic_profile=payload.get("aesthetic_profile"),
            )
            projections[employee_id] = {
                "employee_id": employee_id,
                "role_type": str(payload.get("role_type") or "unknown"),
                "skill_profile_json": normalized_profiles["skill_profile"],
                "personality_profile_json": normalized_profiles["personality_profile"],
                "aesthetic_profile_json": normalized_profiles["aesthetic_profile"],
                "state": str(payload.get("state") or EMPLOYEE_STATE_ACTIVE),
                "board_approved": bool(payload.get("board_approved")),
                "provider_id": payload.get("provider_id"),
                "role_profile_refs": list(payload.get("role_profile_refs") or []),
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_EMPLOYEE_REPLACED:
            employee_id = payload["employee_id"]
            previous_projection = projections.get(
                employee_id,
                {
                    "employee_id": employee_id,
                    "role_type": str(payload.get("role_type") or "unknown"),
                    "skill_profile_json": {},
                    "personality_profile_json": {},
                    "aesthetic_profile_json": {},
                    "provider_id": None,
                    "role_profile_refs": [],
                },
            )
            projections[employee_id] = {
                **previous_projection,
                "state": EMPLOYEE_STATE_REPLACED,
                "board_approved": False,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_EMPLOYEE_FROZEN:
            employee_id = payload["employee_id"]
            previous_projection = projections.get(
                employee_id,
                {
                    "employee_id": employee_id,
                    "role_type": str(payload.get("role_type") or "unknown"),
                    "skill_profile_json": {},
                    "personality_profile_json": {},
                    "aesthetic_profile_json": {},
                    "board_approved": False,
                    "provider_id": None,
                    "role_profile_refs": [],
                },
            )
            projections[employee_id] = {
                **previous_projection,
                "state": EMPLOYEE_STATE_FROZEN,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_EMPLOYEE_RESTORED:
            employee_id = payload["employee_id"]
            previous_projection = projections.get(
                employee_id,
                {
                    "employee_id": employee_id,
                    "role_type": str(payload.get("role_type") or "unknown"),
                    "skill_profile_json": {},
                    "personality_profile_json": {},
                    "aesthetic_profile_json": {},
                    "board_approved": False,
                    "provider_id": None,
                    "role_profile_refs": [],
                },
            )
            projections[employee_id] = {
                **previous_projection,
                "state": EMPLOYEE_STATE_ACTIVE,
                "updated_at": occurred_at,
                "version": version,
            }

    return [projections[employee_id] for employee_id in sorted(projections)]


def _process_asset_content_hash(asset: dict[str, Any]) -> str:
    payload = {
        key: value
        for key, value in asset.items()
        if key not in {"content_hash", "visibility_status"}
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    ).hexdigest()


def rebuild_process_asset_index(events: Iterable[dict]) -> list[dict[str, Any]]:
    projections: dict[str, dict[str, Any]] = {}

    for event in events:
        if event["event_type"] != EVENT_TICKET_COMPLETED:
            continue
        payload = _event_payload(event)
        produced_assets = payload.get("produced_process_assets")
        if not isinstance(produced_assets, list):
            continue
        occurred_at = event["occurred_at"].isoformat()
        version = int(event["sequence_no"])
        workflow_id = str(payload.get("workflow_id") or event.get("workflow_id") or "").strip() or None
        ticket_id = str(payload.get("ticket_id") or "").strip() or None
        node_id = str(payload.get("node_id") or "").strip() or None

        for asset in produced_assets:
            if not isinstance(asset, dict):
                continue
            asset_ref = str(asset.get("process_asset_ref") or asset.get("canonical_ref") or "").strip()
            if not asset_ref:
                continue
            asset_kind = str(asset.get("process_asset_kind") or "").strip()
            asset_workflow_id = str(asset.get("workflow_id") or workflow_id or "").strip() or None
            producer_node_id = str(asset.get("producer_node_id") or node_id or "").strip() or None
            if asset_kind == "SOURCE_CODE_DELIVERY" and asset_workflow_id and producer_node_id:
                for existing in projections.values():
                    if (
                        existing.get("process_asset_kind") == "SOURCE_CODE_DELIVERY"
                        and existing.get("workflow_id") == asset_workflow_id
                        and existing.get("producer_node_id") == producer_node_id
                        and existing.get("visibility_status") == "CONSUMABLE"
                    ):
                        existing["visibility_status"] = "SUPERSEDED"
                        existing["updated_at"] = occurred_at
                        existing["version"] = version

            canonical_ref = str(asset.get("canonical_ref") or asset_ref).strip()
            projection = {
                "process_asset_ref": asset_ref,
                "canonical_ref": canonical_ref,
                "version_int": asset.get("version_int"),
                "supersedes_ref": asset.get("supersedes_ref"),
                "process_asset_kind": asset_kind,
                "workflow_id": asset_workflow_id,
                "producer_ticket_id": str(asset.get("producer_ticket_id") or ticket_id or "").strip()
                or None,
                "producer_node_id": producer_node_id,
                "graph_version": str(asset.get("graph_version") or "").strip() or None,
                "content_hash": str(asset.get("content_hash") or "").strip()
                or _process_asset_content_hash(asset),
                "visibility_status": str(asset.get("visibility_status") or "CONSUMABLE").strip()
                or "CONSUMABLE",
                "linked_process_asset_refs": [
                    str(ref).strip()
                    for ref in list(asset.get("linked_process_asset_refs") or [])
                    if str(ref).strip()
                ],
                "summary": asset.get("summary"),
                "consumable_by": [
                    str(value).strip()
                    for value in list(asset.get("consumable_by") or [])
                    if str(value).strip()
                ],
                "source_metadata": dict(asset.get("source_metadata") or {}),
                "updated_at": occurred_at,
                "version": version,
            }
            projections[asset_ref] = projection

    return [
        projections[asset_ref]
        for asset_ref in sorted(
            projections,
            key=lambda ref: (
                str(projections[ref].get("workflow_id") or ""),
                str(projections[ref].get("producer_node_id") or ""),
                str(projections[ref].get("producer_ticket_id") or ""),
                str(projections[ref].get("process_asset_kind") or ""),
                ref,
            ),
        )
    ]


def rebuild_ticket_projections(events: Iterable[dict]) -> list[dict]:
    projections: dict[str, dict] = {}

    for event in events:
        payload = _event_payload(event)
        event_type = event["event_type"]
        occurred_at = event["occurred_at"].isoformat()
        version = event["sequence_no"]

        if event_type == EVENT_TICKET_CREATED:
            ticket_id = payload["ticket_id"]
            projections[ticket_id] = {
                **_base_ticket_projection(event, payload),
                "status": TICKET_STATUS_PENDING,
                "last_failure_kind": None,
                "last_failure_message": None,
                "last_failure_fingerprint": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_ASSIGNED:
            ticket_id = payload["ticket_id"]
            previous_projection = projections.get(ticket_id, _base_ticket_projection(event, payload))
            tenant_id, workspace_id = _resolve_scope(payload, previous_projection)
            projections[ticket_id] = {
                **previous_projection,
                "workflow_id": event["workflow_id"],
                "node_id": payload["node_id"],
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
                "actor_id": payload.get("actor_id"),
                "assignment_id": payload.get("assignment_id"),
                "lease_id": previous_projection.get("lease_id"),
                "status": TICKET_STATUS_PENDING,
                "lease_owner": None,
                "lease_expires_at": None,
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_LEASE_GRANTED:
            ticket_id = payload["ticket_id"]
            previous_projection = projections.get(ticket_id, _base_ticket_projection(event, payload))
            tenant_id, workspace_id = _resolve_scope(payload, previous_projection)
            projections[ticket_id] = {
                **previous_projection,
                "workflow_id": event["workflow_id"],
                "node_id": payload["node_id"],
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
                "actor_id": payload.get("actor_id"),
                "assignment_id": payload.get("assignment_id"),
                "lease_id": payload.get("lease_id"),
                "status": TICKET_STATUS_LEASED,
                "lease_owner": None,
                "lease_expires_at": payload.get("lease_expires_at"),
                "heartbeat_timeout_sec": payload.get(
                    "lease_timeout_sec",
                    previous_projection.get("heartbeat_timeout_sec"),
                ),
                "last_failure_kind": previous_projection.get("last_failure_kind"),
                "last_failure_message": previous_projection.get("last_failure_message"),
                "last_failure_fingerprint": previous_projection.get("last_failure_fingerprint"),
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_LEASED:
            ticket_id = payload["ticket_id"]
            tenant_id, workspace_id = _resolve_scope(payload, projections.get(ticket_id))
            projections[ticket_id] = {
                **projections.get(ticket_id, _base_ticket_projection(event, payload)),
                "workflow_id": event["workflow_id"],
                "node_id": payload["node_id"],
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
                "status": TICKET_STATUS_LEASED,
                "lease_owner": payload.get("leased_by"),
                "lease_expires_at": payload.get("lease_expires_at"),
                "heartbeat_timeout_sec": payload.get(
                    "lease_timeout_sec",
                    projections.get(ticket_id, {}).get("heartbeat_timeout_sec"),
                ),
                "last_failure_kind": projections.get(ticket_id, {}).get("last_failure_kind"),
                "last_failure_message": projections.get(ticket_id, {}).get("last_failure_message"),
                "last_failure_fingerprint": projections.get(ticket_id, {}).get("last_failure_fingerprint"),
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_STARTED:
            ticket_id = payload["ticket_id"]
            node_id = payload["node_id"]
            previous_projection = projections.get(ticket_id, _base_ticket_projection(event, payload))
            tenant_id, workspace_id = _resolve_scope(payload, previous_projection)
            heartbeat_timeout_sec = previous_projection.get("heartbeat_timeout_sec")
            heartbeat_expires_at = None
            if heartbeat_timeout_sec is not None:
                heartbeat_expires_at = (
                    event["occurred_at"] + timedelta(seconds=heartbeat_timeout_sec)
                ).isoformat()
            projections[ticket_id] = {
                **previous_projection,
                "workflow_id": event["workflow_id"],
                "node_id": node_id,
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
                "status": TICKET_STATUS_EXECUTING,
                "actor_id": payload.get("actor_id", previous_projection.get("actor_id")),
                "assignment_id": payload.get("assignment_id", previous_projection.get("assignment_id")),
                "lease_id": payload.get("lease_id", previous_projection.get("lease_id")),
                "lease_owner": None,
                "started_at": occurred_at,
                "last_heartbeat_at": occurred_at,
                "heartbeat_expires_at": heartbeat_expires_at,
                "last_failure_kind": previous_projection.get("last_failure_kind"),
                "last_failure_message": previous_projection.get("last_failure_message"),
                "last_failure_fingerprint": previous_projection.get("last_failure_fingerprint"),
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_EXECUTION_PRECONDITION_BLOCKED:
            ticket_id = payload["ticket_id"]
            previous_projection = projections.get(ticket_id, _base_ticket_projection(event, payload))
            tenant_id, workspace_id = _resolve_scope(payload, previous_projection)
            projections[ticket_id] = {
                **previous_projection,
                "workflow_id": event["workflow_id"],
                "node_id": payload["node_id"],
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
                "status": TICKET_STATUS_PENDING,
                "lease_owner": None,
                "lease_expires_at": None,
                "started_at": None,
                "last_heartbeat_at": None,
                "heartbeat_expires_at": None,
                "blocking_reason_code": payload.get("reason_code", BLOCKING_REASON_PROVIDER_REQUIRED),
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_EXECUTION_PRECONDITION_CLEARED:
            ticket_id = payload["ticket_id"]
            previous_projection = projections.get(ticket_id, _base_ticket_projection(event, payload))
            tenant_id, workspace_id = _resolve_scope(payload, previous_projection)
            projections[ticket_id] = {
                **previous_projection,
                "workflow_id": event["workflow_id"],
                "node_id": payload["node_id"],
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
                "status": TICKET_STATUS_PENDING,
                "lease_owner": None,
                "lease_expires_at": None,
                "started_at": None,
                "last_heartbeat_at": None,
                "heartbeat_expires_at": None,
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_HEARTBEAT_RECORDED:
            ticket_id = payload["ticket_id"]
            previous_projection = projections.get(ticket_id, _base_ticket_projection(event, payload))
            tenant_id, workspace_id = _resolve_scope(payload, previous_projection)
            heartbeat_timeout_sec = previous_projection.get("heartbeat_timeout_sec")
            heartbeat_expires_at = payload.get("heartbeat_expires_at")
            if heartbeat_expires_at is None and heartbeat_timeout_sec is not None:
                heartbeat_expires_at = (
                    event["occurred_at"] + timedelta(seconds=heartbeat_timeout_sec)
                ).isoformat()
            projections[ticket_id] = {
                **previous_projection,
                "workflow_id": event["workflow_id"],
                "node_id": payload["node_id"],
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
                "status": TICKET_STATUS_EXECUTING,
                "last_heartbeat_at": occurred_at,
                "heartbeat_expires_at": heartbeat_expires_at,
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_CANCEL_REQUESTED:
            ticket_id = payload["ticket_id"]
            previous_projection = projections.get(ticket_id, _base_ticket_projection(event, payload))
            tenant_id, workspace_id = _resolve_scope(payload, previous_projection)
            projections[ticket_id] = {
                **previous_projection,
                "workflow_id": event["workflow_id"],
                "node_id": payload["node_id"],
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
                "status": TICKET_STATUS_CANCEL_REQUESTED,
                "lease_owner": previous_projection.get("lease_owner"),
                "lease_expires_at": previous_projection.get("lease_expires_at"),
                "started_at": previous_projection.get("started_at"),
                "last_heartbeat_at": previous_projection.get("last_heartbeat_at"),
                "heartbeat_expires_at": previous_projection.get("heartbeat_expires_at"),
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_CANCELLED:
            ticket_id = payload["ticket_id"]
            previous_projection = projections.get(ticket_id, _base_ticket_projection(event, payload))
            tenant_id, workspace_id = _resolve_scope(payload, previous_projection)
            projections[ticket_id] = {
                **previous_projection,
                "workflow_id": event["workflow_id"],
                "node_id": payload["node_id"],
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
                "status": TICKET_STATUS_CANCELLED,
                "lease_owner": None,
                "lease_expires_at": None,
                "started_at": None,
                "last_heartbeat_at": None,
                "heartbeat_expires_at": None,
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_COMPLETED:
            ticket_id = payload["ticket_id"]
            tenant_id, workspace_id = _resolve_scope(payload, projections.get(ticket_id))
            projections[ticket_id] = {
                **projections.get(ticket_id, _base_ticket_projection(event, payload)),
                "workflow_id": event["workflow_id"],
                "node_id": payload["node_id"],
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
                "status": TICKET_STATUS_COMPLETED,
                "lease_owner": None,
                "lease_expires_at": None,
                "started_at": None,
                "last_heartbeat_at": None,
                "heartbeat_expires_at": None,
                "last_failure_kind": None,
                "last_failure_message": None,
                "last_failure_fingerprint": None,
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_FAILED:
            ticket_id = payload["ticket_id"]
            tenant_id, workspace_id = _resolve_scope(payload, projections.get(ticket_id))
            projections[ticket_id] = {
                **projections.get(ticket_id, _base_ticket_projection(event, payload)),
                "workflow_id": event["workflow_id"],
                "node_id": payload["node_id"],
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
                "status": TICKET_STATUS_FAILED,
                "lease_owner": None,
                "lease_expires_at": None,
                "started_at": None,
                "last_heartbeat_at": None,
                "heartbeat_expires_at": None,
                "last_failure_kind": payload.get("failure_kind"),
                "last_failure_message": payload.get("failure_message"),
                "last_failure_fingerprint": payload.get("failure_fingerprint"),
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_TIMED_OUT:
            ticket_id = payload["ticket_id"]
            tenant_id, workspace_id = _resolve_scope(payload, projections.get(ticket_id))
            projections[ticket_id] = {
                **projections.get(ticket_id, _base_ticket_projection(event, payload)),
                "workflow_id": event["workflow_id"],
                "node_id": payload["node_id"],
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
                "status": TICKET_STATUS_TIMED_OUT,
                "lease_owner": None,
                "lease_expires_at": None,
                "started_at": None,
                "last_heartbeat_at": None,
                "heartbeat_expires_at": None,
                "last_failure_kind": payload.get("failure_kind"),
                "last_failure_message": payload.get("failure_message"),
                "last_failure_fingerprint": payload.get("failure_fingerprint"),
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_RETRY_SCHEDULED:
            continue

        if event_type == EVENT_BOARD_REVIEW_REQUIRED:
            ticket_id = payload.get("ticket_id")
            node_id = payload.get("node_id")
            if ticket_id is None or node_id is None:
                continue
            tenant_id, workspace_id = _resolve_scope(payload, projections.get(ticket_id))
            projections[ticket_id] = {
                **projections.get(ticket_id, _base_ticket_projection(event, payload)),
                "workflow_id": event["workflow_id"],
                "node_id": node_id,
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
                "status": TICKET_STATUS_BLOCKED_FOR_BOARD_REVIEW,
                "lease_owner": None,
                "lease_expires_at": None,
                "started_at": None,
                "last_heartbeat_at": None,
                "heartbeat_expires_at": None,
                "last_failure_kind": None,
                "last_failure_message": None,
                "last_failure_fingerprint": None,
                "blocking_reason_code": BLOCKING_REASON_BOARD_REVIEW_REQUIRED,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_BOARD_REVIEW_APPROVED:
            ticket_id = payload.get("ticket_id")
            node_id = payload.get("node_id")
            if ticket_id is None or node_id is None:
                continue
            tenant_id, workspace_id = _resolve_scope(payload, projections.get(ticket_id))
            projections[ticket_id] = {
                **projections.get(ticket_id, _base_ticket_projection(event, payload)),
                "workflow_id": event["workflow_id"],
                "node_id": node_id,
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
                "status": TICKET_STATUS_COMPLETED,
                "lease_owner": None,
                "lease_expires_at": None,
                "started_at": None,
                "last_heartbeat_at": None,
                "heartbeat_expires_at": None,
                "last_failure_kind": None,
                "last_failure_message": None,
                "last_failure_fingerprint": None,
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_BOARD_REVIEW_REJECTED:
            ticket_id = payload.get("ticket_id")
            node_id = payload.get("node_id")
            if ticket_id is None or node_id is None:
                continue
            tenant_id, workspace_id = _resolve_scope(payload, projections.get(ticket_id))
            blocking_reason = (
                BLOCKING_REASON_MODIFY_CONSTRAINTS
                if payload.get("decision_action") == "MODIFY_CONSTRAINTS"
                else BLOCKING_REASON_BOARD_REJECTED
            )
            projections[ticket_id] = {
                **projections.get(ticket_id, _base_ticket_projection(event, payload)),
                "workflow_id": event["workflow_id"],
                "node_id": node_id,
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
                "status": TICKET_STATUS_REWORK_REQUIRED,
                "lease_owner": None,
                "lease_expires_at": None,
                "started_at": None,
                "last_heartbeat_at": None,
                "heartbeat_expires_at": None,
                "last_failure_kind": None,
                "last_failure_message": None,
                "last_failure_fingerprint": None,
                "blocking_reason_code": blocking_reason,
                "updated_at": occurred_at,
                "version": version,
            }

    return list(projections.values())


def rebuild_node_projections(events: Iterable[dict]) -> list[dict]:
    projections: dict[tuple[str, str], dict] = {}

    for event in events:
        payload = _event_payload(event)
        event_type = event["event_type"]
        occurred_at = event["occurred_at"].isoformat()
        version = event["sequence_no"]
        workflow_id = event["workflow_id"]

        if workflow_id is None:
            continue

        if event_type == EVENT_TICKET_CREATED:
            node_id = payload["node_id"]
            key = (workflow_id, node_id)
            projections[key] = {
                **_base_node_projection(event, payload),
                "status": NODE_STATUS_PENDING,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_LEASED:
            node_id = payload["node_id"]
            key = (workflow_id, node_id)
            projections[key] = {
                **projections.get(key, _base_node_projection(event, payload)),
                "latest_ticket_id": payload["ticket_id"],
                "status": NODE_STATUS_PENDING,
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_STARTED:
            node_id = payload["node_id"]
            key = (workflow_id, node_id)
            projections[key] = {
                **projections.get(key, _base_node_projection(event, payload)),
                "latest_ticket_id": payload["ticket_id"],
                "status": NODE_STATUS_EXECUTING,
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_EXECUTION_PRECONDITION_BLOCKED:
            node_id = payload["node_id"]
            key = (workflow_id, node_id)
            projections[key] = {
                **projections.get(key, _base_node_projection(event, payload)),
                "latest_ticket_id": payload["ticket_id"],
                "status": NODE_STATUS_PENDING,
                "blocking_reason_code": payload.get("reason_code", BLOCKING_REASON_PROVIDER_REQUIRED),
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_EXECUTION_PRECONDITION_CLEARED:
            node_id = payload["node_id"]
            key = (workflow_id, node_id)
            projections[key] = {
                **projections.get(key, _base_node_projection(event, payload)),
                "latest_ticket_id": payload["ticket_id"],
                "status": NODE_STATUS_PENDING,
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_CANCEL_REQUESTED:
            node_id = payload["node_id"]
            key = (workflow_id, node_id)
            projections[key] = {
                **projections.get(key, _base_node_projection(event, payload)),
                "latest_ticket_id": payload["ticket_id"],
                "status": NODE_STATUS_CANCEL_REQUESTED,
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_CANCELLED:
            node_id = payload["node_id"]
            key = (workflow_id, node_id)
            projections[key] = {
                **projections.get(key, _base_node_projection(event, payload)),
                "latest_ticket_id": payload["ticket_id"],
                "status": NODE_STATUS_CANCELLED,
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_COMPLETED:
            if payload.get("board_review_requested"):
                continue
            node_id = payload["node_id"]
            key = (workflow_id, node_id)
            projections[key] = {
                **projections.get(key, _base_node_projection(event, payload)),
                "latest_ticket_id": payload["ticket_id"],
                "status": NODE_STATUS_COMPLETED,
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type in {EVENT_TICKET_FAILED, EVENT_TICKET_TIMED_OUT}:
            node_id = payload["node_id"]
            key = (workflow_id, node_id)
            projections[key] = {
                **projections.get(key, _base_node_projection(event, payload)),
                "latest_ticket_id": payload["ticket_id"],
                "status": NODE_STATUS_REWORK_REQUIRED,
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_RETRY_SCHEDULED:
            continue

        if event_type == EVENT_BOARD_REVIEW_REQUIRED:
            ticket_id = payload.get("ticket_id")
            node_id = payload.get("node_id")
            if ticket_id is None or node_id is None:
                continue
            key = (workflow_id, node_id)
            projections[key] = {
                **projections.get(key, _base_node_projection(event, payload)),
                "latest_ticket_id": ticket_id,
                "status": NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW,
                "blocking_reason_code": BLOCKING_REASON_BOARD_REVIEW_REQUIRED,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_BOARD_REVIEW_APPROVED:
            ticket_id = payload.get("ticket_id")
            node_id = payload.get("node_id")
            if ticket_id is None or node_id is None:
                continue
            key = (workflow_id, node_id)
            projections[key] = {
                **projections.get(key, _base_node_projection(event, payload)),
                "latest_ticket_id": ticket_id,
                "status": NODE_STATUS_COMPLETED,
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_BOARD_REVIEW_REJECTED:
            ticket_id = payload.get("ticket_id")
            node_id = payload.get("node_id")
            if ticket_id is None or node_id is None:
                continue
            blocking_reason = (
                BLOCKING_REASON_MODIFY_CONSTRAINTS
                if payload.get("decision_action") == "MODIFY_CONSTRAINTS"
                else BLOCKING_REASON_BOARD_REJECTED
            )
            key = (workflow_id, node_id)
            projections[key] = {
                **projections.get(key, _base_node_projection(event, payload)),
                "latest_ticket_id": ticket_id,
                "status": NODE_STATUS_REWORK_REQUIRED,
                "blocking_reason_code": blocking_reason,
                "updated_at": occurred_at,
                "version": version,
            }

    return list(projections.values())


def rebuild_runtime_node_projections(events: Iterable[dict]) -> list[dict]:
    created_specs_by_ticket_id: dict[str, dict[str, Any]] = {}
    projections: dict[tuple[str, str], dict[str, Any]] = {}
    graph_version_int_by_workflow: dict[str, int] = {}
    graph_mutation_events = {
        EVENT_WORKFLOW_CREATED,
        EVENT_TICKET_CREATED,
        EVENT_TICKET_COMPLETED,
        EVENT_TICKET_CANCELLED,
        EVENT_BOARD_REVIEW_REQUIRED,
        EVENT_BOARD_REVIEW_APPROVED,
        EVENT_BOARD_REVIEW_REJECTED,
        "GRAPH_PATCH_APPLIED",
        "MEETING_REQUESTED",
        "MEETING_STARTED",
        "MEETING_CONCLUDED",
    }

    for event in events:
        payload = _event_payload(event)
        if event["event_type"] != EVENT_TICKET_CREATED:
            continue
        ticket_id = str(payload.get("ticket_id") or "").strip()
        if not ticket_id:
            continue
        created_specs_by_ticket_id[ticket_id] = dict(payload)

    for event in events:
        payload = _event_payload(event)
        event_type = event["event_type"]
        occurred_at = event["occurred_at"].isoformat()
        version = event["sequence_no"]
        workflow_id = event["workflow_id"]

        if workflow_id is None:
            continue
        if event_type in graph_mutation_events:
            graph_version_int_by_workflow[workflow_id] = graph_version_int_by_workflow.get(workflow_id, 0) + 1
        graph_version = build_graph_version(max(graph_version_int_by_workflow.get(workflow_id, 0), 1))

        ticket_id = str(payload.get("ticket_id") or "").strip()
        created_spec = created_specs_by_ticket_id.get(ticket_id)
        if not ticket_id or created_spec is None:
            continue
        try:
            identity = resolve_ticket_graph_identity(
                ticket_id=ticket_id,
                created_spec=created_spec,
                runtime_node_id=str(payload.get("node_id") or created_spec.get("node_id") or "").strip(),
            )
        except GraphIdentityResolutionError:
            continue
        key = (workflow_id, identity.graph_node_id)
        base_projection = {
            "workflow_id": workflow_id,
            "graph_node_id": identity.graph_node_id,
            "node_id": identity.runtime_node_id,
            "runtime_node_id": identity.runtime_node_id,
            "latest_ticket_id": ticket_id,
            "blocking_reason_code": None,
            "graph_version": graph_version,
        }

        if event_type == EVENT_TICKET_CREATED:
            projections[key] = {
                **base_projection,
                "status": NODE_STATUS_PENDING,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_LEASED:
            projections[key] = {
                **projections.get(key, base_projection),
                "latest_ticket_id": ticket_id,
                "status": NODE_STATUS_PENDING,
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_STARTED:
            projections[key] = {
                **projections.get(key, base_projection),
                "latest_ticket_id": ticket_id,
                "status": NODE_STATUS_EXECUTING,
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_EXECUTION_PRECONDITION_BLOCKED:
            projections[key] = {
                **projections.get(key, base_projection),
                "latest_ticket_id": ticket_id,
                "status": NODE_STATUS_PENDING,
                "blocking_reason_code": payload.get("reason_code", BLOCKING_REASON_PROVIDER_REQUIRED),
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_EXECUTION_PRECONDITION_CLEARED:
            projections[key] = {
                **projections.get(key, base_projection),
                "latest_ticket_id": ticket_id,
                "status": NODE_STATUS_PENDING,
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_CANCEL_REQUESTED:
            projections[key] = {
                **projections.get(key, base_projection),
                "latest_ticket_id": ticket_id,
                "status": NODE_STATUS_CANCEL_REQUESTED,
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_CANCELLED:
            projections[key] = {
                **projections.get(key, base_projection),
                "latest_ticket_id": ticket_id,
                "status": NODE_STATUS_CANCELLED,
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_TICKET_COMPLETED:
            if payload.get("board_review_requested"):
                continue
            projections[key] = {
                **projections.get(key, base_projection),
                "latest_ticket_id": ticket_id,
                "status": NODE_STATUS_COMPLETED,
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type in {EVENT_TICKET_FAILED, EVENT_TICKET_TIMED_OUT}:
            projections[key] = {
                **projections.get(key, base_projection),
                "latest_ticket_id": ticket_id,
                "status": NODE_STATUS_REWORK_REQUIRED,
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_BOARD_REVIEW_REQUIRED:
            projections[key] = {
                **projections.get(key, base_projection),
                "latest_ticket_id": ticket_id,
                "status": NODE_STATUS_BLOCKED_FOR_BOARD_REVIEW,
                "blocking_reason_code": BLOCKING_REASON_BOARD_REVIEW_REQUIRED,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_BOARD_REVIEW_APPROVED:
            projections[key] = {
                **projections.get(key, base_projection),
                "latest_ticket_id": ticket_id,
                "status": NODE_STATUS_COMPLETED,
                "blocking_reason_code": None,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_BOARD_REVIEW_REJECTED:
            blocking_reason = (
                BLOCKING_REASON_MODIFY_CONSTRAINTS
                if payload.get("decision_action") == "MODIFY_CONSTRAINTS"
                else BLOCKING_REASON_BOARD_REJECTED
            )
            projections[key] = {
                **projections.get(key, base_projection),
                "latest_ticket_id": ticket_id,
                "status": NODE_STATUS_REWORK_REQUIRED,
                "blocking_reason_code": blocking_reason,
                "updated_at": occurred_at,
                "version": version,
            }

    return list(projections.values())


def rebuild_incident_projections(events: Iterable[dict]) -> list[dict]:
    projections: dict[str, dict[str, Any]] = {}

    for event in events:
        payload = _event_payload(event)
        event_type = event["event_type"]
        incident_id = payload.get("incident_id")
        if incident_id is None:
            continue

        occurred_at = event["occurred_at"].isoformat()
        version = event["sequence_no"]

        if event_type == EVENT_INCIDENT_OPENED:
            projections[incident_id] = {
                **_base_incident_projection(event, payload),
                "incident_type": payload.get("incident_type"),
                "status": payload.get("status", "OPEN"),
                "severity": payload.get("severity"),
                "fingerprint": payload.get("fingerprint"),
                "opened_at": occurred_at,
                "closed_at": None,
                "payload": payload,
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_CIRCUIT_BREAKER_OPENED:
            projections[incident_id] = {
                **projections.get(incident_id, _base_incident_projection(event, payload)),
                "workflow_id": event["workflow_id"],
                "node_id": payload.get("node_id", projections.get(incident_id, {}).get("node_id")),
                "ticket_id": payload.get("ticket_id", projections.get(incident_id, {}).get("ticket_id")),
                "provider_id": payload.get(
                    "provider_id",
                    projections.get(incident_id, {}).get("provider_id"),
                ),
                "fingerprint": payload.get("fingerprint", projections.get(incident_id, {}).get("fingerprint")),
                "circuit_breaker_state": payload.get("circuit_breaker_state", CIRCUIT_BREAKER_STATE_OPEN),
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_CIRCUIT_BREAKER_CLOSED:
            projections[incident_id] = {
                **projections.get(incident_id, _base_incident_projection(event, payload)),
                "workflow_id": event["workflow_id"],
                "node_id": payload.get("node_id", projections.get(incident_id, {}).get("node_id")),
                "ticket_id": payload.get("ticket_id", projections.get(incident_id, {}).get("ticket_id")),
                "provider_id": payload.get(
                    "provider_id",
                    projections.get(incident_id, {}).get("provider_id"),
                ),
                "circuit_breaker_state": payload.get(
                    "circuit_breaker_state",
                    CIRCUIT_BREAKER_STATE_CLOSED,
                ),
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_INCIDENT_RECOVERY_STARTED:
            previous_projection = projections.get(incident_id, _base_incident_projection(event, payload))
            projections[incident_id] = {
                **previous_projection,
                "workflow_id": event["workflow_id"],
                "node_id": payload.get("node_id", previous_projection.get("node_id")),
                "ticket_id": payload.get("ticket_id", previous_projection.get("ticket_id")),
                "provider_id": payload.get("provider_id", previous_projection.get("provider_id")),
                "status": payload.get("status", "RECOVERING"),
                "payload": {
                    **(previous_projection.get("payload") or {}),
                    **payload,
                },
                "updated_at": occurred_at,
                "version": version,
            }
            continue

        if event_type == EVENT_INCIDENT_CLOSED:
            previous_projection = projections.get(incident_id, _base_incident_projection(event, payload))
            projections[incident_id] = {
                **previous_projection,
                "workflow_id": event["workflow_id"],
                "node_id": payload.get("node_id", previous_projection.get("node_id")),
                "ticket_id": payload.get("ticket_id", previous_projection.get("ticket_id")),
                "provider_id": payload.get("provider_id", previous_projection.get("provider_id")),
                "status": payload.get("status", "CLOSED"),
                "closed_at": occurred_at,
                "payload": {
                    **(previous_projection.get("payload") or {}),
                    **payload,
                },
                "updated_at": occurred_at,
                "version": version,
            }

    return list(projections.values())
