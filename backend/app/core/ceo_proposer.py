from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.contracts.ceo_actions import (
    CEOActionBatch,
    CEOActionType,
    CEOCreateTicketAction,
    CEOCreateTicketPayload,
    CEORequestMeetingAction,
    CEORequestMeetingPayload,
    CEONoAction,
    CEONoActionPayload,
)
from app.core.ceo_execution_presets import (
    GOVERNANCE_DOCUMENT_CHAIN_ORDER,
    PROJECT_INIT_AUTOPILOT_ARCHITECTURE_NODE_ID,
    PROJECT_INIT_SCOPE_NODE_ID,
    build_autopilot_architecture_brief_summary,
    build_project_init_scope_summary,
    supports_ceo_create_ticket_preset,
)
from app.core.ceo_prompts import build_ceo_shadow_rendered_payload
from app.core.constants import EVENT_BOARD_DIRECTIVE_RECEIVED
from app.core.execution_targets import (
    employee_supports_execution_contract,
    infer_execution_contract_payload,
)
from app.core.provider_openai_compat import (
    OpenAICompatProviderConfig,
    OpenAICompatProviderError,
    invoke_openai_compat_response,
)
from app.core.provider_claude_code import ClaudeCodeProviderConfig, ClaudeCodeProviderError, invoke_claude_code_response
from app.core.output_schemas import (
    BACKLOG_RECOMMENDATION_SCHEMA_REF,
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    GOVERNANCE_DOCUMENT_SCHEMA_REFS,
    SOURCE_CODE_DELIVERY_SCHEMA_REF,
)
from app.core.workflow_completion import ticket_has_delivery_mainline_evidence
from app.core.workflow_autopilot import workflow_uses_ceo_board_delegate
from app.core.runtime_provider_config import (
    RuntimeProviderAdapterKind,
    ROLE_BINDING_CEO_SHADOW,
    find_provider_entry,
    provider_effective_mode,
    resolve_provider_failover_selections,
    resolve_provider_selection,
    RuntimeProviderConfigStore,
    resolve_runtime_provider_config,
    runtime_provider_effective_mode,
    runtime_provider_health_summary,
)
from app.core.workflow_controller import backlog_followup_key_to_node_id as controller_backlog_followup_key_to_node_id
from app.db.repository import ControlPlaneRepository


@dataclass(frozen=True)
class CEOProposalResult:
    action_batch: CEOActionBatch
    effective_mode: str
    provider_health_summary: str
    model: str | None
    preferred_provider_id: str | None = None
    preferred_model: str | None = None
    actual_provider_id: str | None = None
    actual_model: str | None = None
    selection_reason: str | None = None
    policy_reason: str | None = None
    provider_response_id: str | None = None
    fallback_reason: str | None = None


PROVIDER_FAILOVER_FAILURE_KINDS = {"PROVIDER_RATE_LIMITED", "UPSTREAM_UNAVAILABLE"}


def build_no_action_batch(reason: str) -> CEOActionBatch:
    return CEOActionBatch(
        summary=reason,
        actions=[
            CEONoAction(
                action_type="NO_ACTION",
                payload=CEONoActionPayload(reason=reason),
            )
        ],
    )


def _should_fallback_to_project_init_scope_kickoff(snapshot: dict) -> bool:
    trigger = snapshot.get("trigger") or {}
    ticket_summary = snapshot.get("ticket_summary") or {}
    return (
        str(trigger.get("trigger_type") or "") == EVENT_BOARD_DIRECTIVE_RECEIVED
        and int(ticket_summary.get("total") or 0) == 0
        and not snapshot.get("approvals")
        and not snapshot.get("incidents")
    )


def _should_fallback_to_autopilot_governance_kickoff(snapshot: dict) -> bool:
    return _should_fallback_to_project_init_scope_kickoff(snapshot) and workflow_uses_ceo_board_delegate(
        snapshot.get("workflow")
    )


def _select_default_assignee(
    snapshot: dict,
    *,
    role_profile_ref: str,
    output_schema_ref: str,
) -> str | None:
    execution_contract = infer_execution_contract_payload(
        role_profile_ref=role_profile_ref,
        output_schema_ref=output_schema_ref,
    )
    if execution_contract is None:
        return None

    employees = sorted(
        snapshot.get("employees") or [],
        key=lambda item: str(item.get("employee_id") or ""),
    )
    for employee in employees:
        if str(employee.get("state") or "") != "ACTIVE":
            continue
        if not employee_supports_execution_contract(
            employee=employee,
            execution_contract=execution_contract,
        ):
            continue
        return str(employee["employee_id"])
    return None


def _build_project_init_scope_kickoff_batch(snapshot: dict, reason: str) -> CEOActionBatch:
    workflow = snapshot.get("workflow") or {}
    north_star_goal = str(workflow.get("north_star_goal") or workflow.get("title") or "").strip()
    summary = build_project_init_scope_summary(north_star_goal)
    assignee_employee_id = _select_default_assignee(
        snapshot,
        role_profile_ref="ui_designer_primary",
        output_schema_ref="consensus_document",
    )
    if assignee_employee_id is None:
        return build_no_action_batch("No active assignee satisfies the kickoff execution contract yet.")
    return CEOActionBatch(
        summary=reason,
        actions=[
            CEOCreateTicketAction(
                action_type=CEOActionType.CREATE_TICKET,
                payload=CEOCreateTicketPayload(
                    workflow_id=str(workflow["workflow_id"]),
                    node_id=PROJECT_INIT_SCOPE_NODE_ID,
                    role_profile_ref="ui_designer_primary",
                    output_schema_ref="consensus_document",
                    execution_contract=infer_execution_contract_payload(
                        role_profile_ref="ui_designer_primary",
                        output_schema_ref="consensus_document",
                    ),
                    dispatch_intent={
                        "assignee_employee_id": assignee_employee_id,
                        "selection_reason": "Use the active frontend delivery owner for the kickoff scope consensus ticket.",
                    },
                    summary=summary,
                    parent_ticket_id=None,
                ),
            )
        ],
    )


def _build_autopilot_governance_kickoff_batch(snapshot: dict, reason: str) -> CEOActionBatch:
    workflow = snapshot.get("workflow") or {}
    north_star_goal = str(workflow.get("north_star_goal") or workflow.get("title") or "").strip()
    summary = build_autopilot_architecture_brief_summary(north_star_goal)
    assignee_employee_id = _select_default_assignee(
        snapshot,
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="architecture_brief",
    )
    if assignee_employee_id is None:
        return build_no_action_batch("No active assignee satisfies the autopilot governance kickoff contract yet.")
    return CEOActionBatch(
        summary=reason,
        actions=[
            CEOCreateTicketAction(
                action_type=CEOActionType.CREATE_TICKET,
                payload=CEOCreateTicketPayload(
                    workflow_id=str(workflow["workflow_id"]),
                    node_id=PROJECT_INIT_AUTOPILOT_ARCHITECTURE_NODE_ID,
                    role_profile_ref="frontend_engineer_primary",
                    output_schema_ref="architecture_brief",
                    execution_contract=infer_execution_contract_payload(
                        role_profile_ref="frontend_engineer_primary",
                        output_schema_ref="architecture_brief",
                    ),
                    dispatch_intent={
                        "assignee_employee_id": assignee_employee_id,
                        "selection_reason": "Keep the first governance document on the current live frontend owner.",
                    },
                    summary=summary,
                    parent_ticket_id=None,
                ),
            )
        ],
    )


def _eligible_meeting_candidates(snapshot: dict) -> list[dict]:
    return [
        item
        for item in snapshot.get("meeting_candidates") or []
        if bool(item.get("eligible"))
    ]


def _build_request_meeting_batch(candidate: dict, reason: str) -> CEOActionBatch:
    return CEOActionBatch(
        summary=reason,
        actions=[
            CEORequestMeetingAction(
                action_type=CEOActionType.REQUEST_MEETING,
                payload=CEORequestMeetingPayload(
                    workflow_id=str(candidate["workflow_id"]),
                    meeting_type="TECHNICAL_DECISION",
                    source_node_id=str(candidate["source_node_id"]),
                    source_ticket_id=str(candidate["source_ticket_id"]),
                    topic=str(candidate["topic"]),
                    participant_employee_ids=list(candidate.get("participant_employee_ids") or []),
                    recorder_employee_id=str(candidate["recorder_employee_id"]),
                    input_artifact_refs=list(candidate.get("input_artifact_refs") or []),
                    reason=str(candidate["reason"]),
                ),
            )
        ],
    )


def _normalize_dependency_gate_refs(raw_refs: Any) -> list[str]:
    normalized_refs: list[str] = []
    seen_refs: set[str] = set()
    for item in list(raw_refs or []):
        normalized_ref = str(item).strip()
        if not normalized_ref or normalized_ref in seen_refs:
            continue
        seen_refs.add(normalized_ref)
        normalized_refs.append(normalized_ref)
    return normalized_refs


def _selection_reason_for_role(role_profile_ref: str, output_schema_ref: str) -> str:
    if output_schema_ref in GOVERNANCE_DOCUMENT_SCHEMA_REFS:
        return f"Use the active {role_profile_ref} owner for the next governance document."
    return f"Use the active {role_profile_ref} owner for the next approved delivery ticket."


def _candidate_role_profile_refs(*, output_schema_ref: str, node_id: str) -> list[str]:
    hinted_profiles: list[str] = []
    normalized_node_id = node_id.lower()
    if "cto" in normalized_node_id:
        hinted_profiles.append("cto_primary")
    if "architect" in normalized_node_id:
        hinted_profiles.append("architect_primary")
    if output_schema_ref in GOVERNANCE_DOCUMENT_SCHEMA_REFS:
        hinted_profiles.extend(
            [
                "frontend_engineer_primary",
                "architect_primary",
                "cto_primary",
                "ui_designer_primary",
            ]
        )
    else:
        hinted_profiles.extend(
            [
                "frontend_engineer_primary",
                "ui_designer_primary",
            ]
        )
    deduped_profiles: list[str] = []
    seen_profiles: set[str] = set()
    for profile in hinted_profiles:
        if profile in seen_profiles:
            continue
        seen_profiles.add(profile)
        deduped_profiles.append(profile)
    return deduped_profiles


def _normalized_runtime_preference(raw_payload: dict[str, Any]) -> dict[str, Any] | None:
    runtime_preference = raw_payload.get("runtime_preference")
    if not isinstance(runtime_preference, dict):
        return None
    preferred_provider_id = str(runtime_preference.get("preferred_provider_id") or "").strip()
    preferred_model = str(runtime_preference.get("preferred_model") or "").strip()
    if not preferred_provider_id:
        return None
    payload: dict[str, Any] = {"preferred_provider_id": preferred_provider_id}
    if preferred_model:
        payload["preferred_model"] = preferred_model
    return payload


def _recent_completed_governance_ticket_ids_by_schema(snapshot: dict) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in list((snapshot.get("reuse_candidates") or {}).get("recent_completed_tickets") or []):
        output_schema_ref = str(item.get("output_schema_ref") or "").strip()
        ticket_id = str(item.get("ticket_id") or "").strip()
        if not output_schema_ref or not ticket_id or output_schema_ref in mapping:
            continue
        if output_schema_ref not in GOVERNANCE_DOCUMENT_CHAIN_ORDER:
            continue
        mapping[output_schema_ref] = ticket_id
    return mapping


def _infer_governance_dependency_gate_refs(snapshot: dict, output_schema_ref: str) -> list[str]:
    if output_schema_ref not in GOVERNANCE_DOCUMENT_CHAIN_ORDER:
        return []
    completed_ticket_ids_by_schema = _recent_completed_governance_ticket_ids_by_schema(snapshot)
    dependency_gate_refs: list[str] = []
    for prerequisite_schema_ref in GOVERNANCE_DOCUMENT_CHAIN_ORDER[
        : GOVERNANCE_DOCUMENT_CHAIN_ORDER.index(output_schema_ref)
    ]:
        ticket_id = completed_ticket_ids_by_schema.get(prerequisite_schema_ref)
        if ticket_id:
            dependency_gate_refs.append(ticket_id)
    return dependency_gate_refs


def _normalize_create_ticket_payload(raw_payload: dict[str, Any], snapshot: dict) -> dict[str, Any]:
    workflow = snapshot.get("workflow") or {}
    workflow_id = str(raw_payload.get("workflow_id") or workflow.get("workflow_id") or "").strip()
    node_id = str(raw_payload.get("node_id") or "").strip()
    raw_execution_contract = raw_payload.get("execution_contract")
    if not isinstance(raw_execution_contract, dict):
        raw_execution_contract = {}
    output_schema_ref = str(
        raw_payload.get("output_schema_ref")
        or raw_payload.get("kind")
        or raw_execution_contract.get("deliverable_schema_ref")
        or ""
    ).strip()
    if not node_id and output_schema_ref:
        node_id = f"node_ceo_{output_schema_ref}"

    role_profile_ref = str(
        raw_payload.get("role_profile_ref")
        or raw_payload.get("role_type")
        or ""
    ).strip()
    if role_profile_ref and (
        not supports_ceo_create_ticket_preset(
            role_profile_ref=role_profile_ref,
            output_schema_ref=output_schema_ref,
        )
        or _select_default_assignee(
            snapshot,
            role_profile_ref=role_profile_ref,
            output_schema_ref=output_schema_ref,
        )
        is None
    ):
        role_profile_ref = ""

    if not role_profile_ref:
        for candidate_role_profile_ref in _candidate_role_profile_refs(
            output_schema_ref=output_schema_ref,
            node_id=node_id,
        ):
            if not supports_ceo_create_ticket_preset(
                role_profile_ref=candidate_role_profile_ref,
                output_schema_ref=output_schema_ref,
            ):
                continue
            if _select_default_assignee(
                snapshot,
                role_profile_ref=candidate_role_profile_ref,
                output_schema_ref=output_schema_ref,
            ) is None:
                continue
            role_profile_ref = candidate_role_profile_ref
            break

    execution_contract = (
        infer_execution_contract_payload(
            role_profile_ref=role_profile_ref,
            output_schema_ref=output_schema_ref,
        )
        if role_profile_ref and output_schema_ref
        else None
    )

    raw_dispatch_intent = raw_payload.get("dispatch_intent")
    if not isinstance(raw_dispatch_intent, dict):
        raw_dispatch_intent = {}
    dependency_gate_refs = _normalize_dependency_gate_refs(
        raw_dispatch_intent.get("dependency_gate_refs")
        or raw_payload.get("depends_on_ticket_ids")
        or raw_payload.get("depends_on")
    )
    inferred_governance_dependency_gate_refs: list[str] = []
    if not dependency_gate_refs and output_schema_ref in GOVERNANCE_DOCUMENT_CHAIN_ORDER:
        inferred_governance_dependency_gate_refs = _infer_governance_dependency_gate_refs(snapshot, output_schema_ref)
        dependency_gate_refs = inferred_governance_dependency_gate_refs
    assignee_employee_id = str(raw_dispatch_intent.get("assignee_employee_id") or "").strip()
    if not assignee_employee_id and role_profile_ref and output_schema_ref:
        assignee_employee_id = (
            _select_default_assignee(
                snapshot,
                role_profile_ref=role_profile_ref,
                output_schema_ref=output_schema_ref,
            )
            or ""
        )
    selection_reason = str(
        raw_dispatch_intent.get("selection_reason")
        or raw_dispatch_intent.get("reason")
        or _selection_reason_for_role(role_profile_ref, output_schema_ref)
    ).strip()

    summary = str(
        raw_payload.get("summary")
        or raw_payload.get("title")
        or raw_execution_contract.get("deliverable")
        or raw_execution_contract.get("objective")
        or f"Prepare the next {output_schema_ref} ticket."
    ).strip()
    parent_ticket_id = str(raw_payload.get("parent_ticket_id") or "").strip() or None
    if parent_ticket_id is None and inferred_governance_dependency_gate_refs:
        parent_ticket_id = inferred_governance_dependency_gate_refs[-1]
    if parent_ticket_id is None and dependency_gate_refs:
        parent_ticket_id = dependency_gate_refs[0]
    if parent_ticket_id is None:
        trigger = snapshot.get("trigger") or {}
        if str(trigger.get("trigger_type") or "") == "TICKET_COMPLETED":
            trigger_ref = str(trigger.get("trigger_ref") or "").strip()
            if trigger_ref:
                parent_ticket_id = trigger_ref

    normalized_payload: dict[str, Any] = {
        "workflow_id": workflow_id,
        "node_id": node_id,
        "role_profile_ref": role_profile_ref,
        "output_schema_ref": output_schema_ref,
        "summary": summary,
        "parent_ticket_id": parent_ticket_id,
    }
    if execution_contract is not None:
        normalized_payload["execution_contract"] = execution_contract
    if assignee_employee_id:
        normalized_payload["dispatch_intent"] = {
            "assignee_employee_id": assignee_employee_id,
            "selection_reason": selection_reason,
            "dependency_gate_refs": dependency_gate_refs,
        }
    runtime_preference = _normalized_runtime_preference(raw_payload)
    if runtime_preference is not None:
        normalized_payload["runtime_preference"] = runtime_preference
    return normalized_payload


def _normalize_provider_action_batch_payload(raw_payload: dict[str, Any], snapshot: dict) -> dict[str, Any]:
    normalized_actions: list[dict[str, Any]] = []
    for action in list(raw_payload.get("actions") or []):
        if not isinstance(action, dict):
            continue
        action_type = str(action.get("action_type") or action.get("type") or "").strip()
        action_payload = action.get("payload")
        if action_type == CEOActionType.CREATE_TICKET:
            if not isinstance(action_payload, dict):
                action_payload = {
                    key: value
                    for key, value in action.items()
                    if key not in {"action_type", "type"}
                }
            if not isinstance(action_payload, dict):
                continue
            normalized_actions.append(
                {
                    "action_type": action_type,
                    "payload": _normalize_create_ticket_payload(action_payload, snapshot),
                }
            )
            continue
        if action_type:
            normalized_actions.append(
                {
                    **action,
                    "action_type": action_type,
                }
            )
            continue
        normalized_actions.append(action)
    return {
        "summary": str(raw_payload.get("summary") or "CEO shadow action batch").strip() or "CEO shadow action batch",
        "actions": normalized_actions,
    }


def _backlog_followup_key_to_node_id(ticket_key: str) -> str:
    return controller_backlog_followup_key_to_node_id(ticket_key)


def _read_ticket_json_artifact(
    repository: ControlPlaneRepository,
    *,
    ticket_id: str,
    connection,
) -> dict[str, Any] | None:
    artifact_store = repository.artifact_store
    if artifact_store is None:
        return None
    artifact = next(
        (
            item
            for item in repository.list_ticket_artifacts(ticket_id, connection=connection)
            if str(item.get("storage_relpath") or "").strip()
            and str(item.get("artifact_ref") or "").strip().endswith(".json")
        ),
        None,
    )
    if artifact is None:
        return None
    try:
        return json.loads(
            artifact_store.read_bytes(str(artifact["storage_relpath"])).decode("utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _backlog_recommendation_ticket_id(snapshot: dict, repository: ControlPlaneRepository, connection) -> str | None:
    trigger = snapshot.get("trigger") or {}
    trigger_ref = str(trigger.get("trigger_ref") or "").strip()
    if trigger_ref:
        trigger_created_spec = repository.get_latest_ticket_created_payload(connection, trigger_ref) or {}
        if str(trigger_created_spec.get("output_schema_ref") or "").strip() == BACKLOG_RECOMMENDATION_SCHEMA_REF:
            return trigger_ref

    for item in list((snapshot.get("reuse_candidates") or {}).get("recent_completed_tickets") or []):
        if str(item.get("output_schema_ref") or "").strip() == BACKLOG_RECOMMENDATION_SCHEMA_REF:
            ticket_id = str(item.get("ticket_id") or "").strip()
            if ticket_id:
                return ticket_id
    return None


def _build_backlog_followup_batch(
    repository: ControlPlaneRepository,
    snapshot: dict,
    reason: str,
) -> CEOActionBatch | None:
    workflow = snapshot.get("workflow") or {}
    workflow_id = str(workflow.get("workflow_id") or "").strip()
    if not workflow_id:
        return None
    capability_plan = snapshot.get("capability_plan") or {}
    followup_ticket_plans = list(capability_plan.get("followup_ticket_plans") or [])
    if not followup_ticket_plans:
        return None

    actions: list[dict[str, Any]] = []
    with repository.connection() as connection:
        node_rows = connection.execute(
            """
            SELECT node_id, latest_ticket_id
            FROM node_projection
            WHERE workflow_id = ?
            """,
            (workflow_id,),
        ).fetchall()
        existing_ticket_ids_by_node_id = {
            str(row["node_id"]): str(row["latest_ticket_id"])
            for row in node_rows
            if str(row["node_id"] or "").strip() and str(row["latest_ticket_id"] or "").strip()
        }
        existing_node_ids = {
            str(row["node_id"])
            for row in connection.execute(
                """
                SELECT DISTINCT node_id
                FROM ticket_projection
                WHERE workflow_id = ?
                """,
                (workflow_id,),
            ).fetchall()
            if str(row["node_id"] or "").strip()
        }

    for followup_plan in followup_ticket_plans:
        node_id = str(followup_plan.get("node_id") or "").strip()
        ticket_key = str(followup_plan.get("ticket_key") or "").strip()
        role_profile_ref = str(followup_plan.get("role_profile_ref") or "").strip()
        output_schema_ref = str(followup_plan.get("output_schema_ref") or "").strip()
        assignee_employee_id = str(followup_plan.get("assignee_employee_id") or "").strip()
        backlog_ticket_id = str(followup_plan.get("source_ticket_id") or "").strip()
        if not node_id or not role_profile_ref or not output_schema_ref or not assignee_employee_id:
            continue
        if node_id in existing_ticket_ids_by_node_id or node_id in existing_node_ids:
            continue

        dependency_gate_refs = _normalize_dependency_gate_refs(followup_plan.get("dependency_gate_refs"))
        ready_to_create = True
        for dependency_key in list(followup_plan.get("dependency_ticket_keys") or []):
            dependency_node_id = _backlog_followup_key_to_node_id(str(dependency_key))
            dependency_ticket_id = existing_ticket_ids_by_node_id.get(dependency_node_id)
            if not dependency_ticket_id:
                ready_to_create = False
                break
            if dependency_ticket_id not in dependency_gate_refs:
                dependency_gate_refs.append(dependency_ticket_id)
        if not ready_to_create:
            continue

        task_name = str(followup_plan.get("task_name") or followup_plan.get("summary") or ticket_key).strip() or ticket_key
        task_scope = [
            str(item).strip()
            for item in list(followup_plan.get("scope") or [])
            if str(item).strip()
        ]
        scope_suffix = f"；范围：{'、'.join(task_scope)}" if task_scope else ""
        actions.append(
            {
                "action_type": CEOActionType.CREATE_TICKET,
                "payload": {
                    "workflow_id": workflow_id,
                    "node_id": node_id,
                    "role_profile_ref": role_profile_ref,
                    "output_schema_ref": output_schema_ref,
                    "execution_contract": infer_execution_contract_payload(
                        role_profile_ref=role_profile_ref,
                        output_schema_ref=output_schema_ref,
                    ),
                    "dispatch_intent": {
                        "assignee_employee_id": assignee_employee_id,
                        "selection_reason": (
                            "Follow the current capability plan and translate the approved backlog recommendation into an auditable implementation ticket."
                        ),
                        "dependency_gate_refs": dependency_gate_refs,
                    },
                    "summary": f"{ticket_key} {task_name}{scope_suffix}",
                    "parent_ticket_id": backlog_ticket_id,
                },
            }
        )

    if not actions:
        return None

    return CEOActionBatch.model_validate(
        {
            "summary": reason,
            "actions": actions,
        }
    )


def _build_capability_hire_batch(snapshot: dict, reason: str) -> CEOActionBatch | None:
    workflow_id = str((snapshot.get("workflow") or {}).get("workflow_id") or "").strip()
    capability_plan = snapshot.get("capability_plan") or {}
    recommended_hire = capability_plan.get("recommended_hire")
    if not workflow_id or not isinstance(recommended_hire, dict):
        return None
    role_type = str(recommended_hire.get("role_type") or "").strip()
    role_profile_refs = [
        str(item).strip()
        for item in list(recommended_hire.get("role_profile_refs") or [])
        if str(item).strip()
    ]
    request_summary = str(recommended_hire.get("request_summary") or "").strip() or (
        f"Hire {role_type} so the current capability plan can continue."
    )
    if not role_type or not role_profile_refs:
        return None
    return CEOActionBatch(
        summary=reason,
        actions=[
            {
                "action_type": CEOActionType.HIRE_EMPLOYEE,
                "payload": {
                    "workflow_id": workflow_id,
                    "role_type": role_type,
                    "role_profile_refs": role_profile_refs,
                    "request_summary": request_summary,
                },
            }
        ],
    )


def _resolve_autopilot_closeout_parent_ticket_id(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    connection,
) -> str | None:
    rows = connection.execute(
        """
        SELECT ticket_id
        FROM ticket_projection
        WHERE workflow_id = ? AND status = ?
        ORDER BY updated_at DESC, ticket_id DESC
        """,
        (workflow_id, "COMPLETED"),
    ).fetchall()
    created_specs_by_ticket = {
        str(row["ticket_id"]): repository.get_latest_ticket_created_payload(connection, str(row["ticket_id"])) or {}
        for row in rows
    }
    for row in rows:
        ticket_id = str(row["ticket_id"])
        created_spec = created_specs_by_ticket[ticket_id]
        if not ticket_has_delivery_mainline_evidence(created_spec, created_specs_by_ticket):
            continue
        output_schema_ref = str(created_spec.get("output_schema_ref") or "").strip()
        if output_schema_ref == "maker_checker_verdict":
            maker_checker_context = created_spec.get("maker_checker_context") or {}
            maker_ticket_id = str(maker_checker_context.get("maker_ticket_id") or "").strip()
            if maker_ticket_id:
                return maker_ticket_id
        return ticket_id
    return None


def _workflow_has_existing_closeout_ticket(
    repository: ControlPlaneRepository,
    *,
    workflow_id: str,
    connection,
) -> bool:
    rows = connection.execute(
        """
        SELECT ticket_id
        FROM ticket_projection
        WHERE workflow_id = ?
        ORDER BY updated_at DESC, ticket_id DESC
        """,
        (workflow_id,),
    ).fetchall()
    for row in rows:
        ticket_id = str(row["ticket_id"])
        created_spec = repository.get_latest_ticket_created_payload(connection, ticket_id) or {}
        if str(created_spec.get("output_schema_ref") or "").strip() == DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF:
            return True
    return False


def _build_autopilot_closeout_batch(
    repository: ControlPlaneRepository,
    snapshot: dict,
    reason: str,
) -> CEOActionBatch | None:
    workflow = snapshot.get("workflow") or {}
    if not workflow_uses_ceo_board_delegate(workflow):
        return None
    if snapshot.get("approvals") or snapshot.get("incidents"):
        return None

    ticket_summary = snapshot.get("ticket_summary") or {}
    if int(ticket_summary.get("active_count") or 0) > 0:
        return None

    nodes = list(snapshot.get("nodes") or [])
    if not nodes or any(str(node.get("status") or "") != "COMPLETED" for node in nodes):
        return None

    workflow_id = str(workflow.get("workflow_id") or "").strip()
    if not workflow_id:
        return None

    closeout_node_id = "node_ceo_delivery_closeout"
    closeout_role_profile_ref = "frontend_engineer_primary"
    assignee_employee_id = _select_default_assignee(
        snapshot,
        role_profile_ref=closeout_role_profile_ref,
        output_schema_ref=DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    )
    if assignee_employee_id is None:
        return None

    with repository.connection() as connection:
        if _workflow_has_existing_closeout_ticket(
            repository,
            workflow_id=workflow_id,
            connection=connection,
        ):
            return None
        if repository.get_current_node_projection(workflow_id, closeout_node_id, connection=connection) is not None:
            return None
        parent_ticket_id = _resolve_autopilot_closeout_parent_ticket_id(
            repository,
            workflow_id=workflow_id,
            connection=connection,
        )
    if parent_ticket_id is None:
        return None

    goal = str(workflow.get("north_star_goal") or workflow.get("title") or "the current workflow").strip()
    summary = f"Prepare the final delivery closeout package for {goal}."
    return CEOActionBatch(
        summary=reason,
        actions=[
            CEOCreateTicketAction(
                action_type=CEOActionType.CREATE_TICKET,
                payload=CEOCreateTicketPayload(
                    workflow_id=workflow_id,
                    node_id=closeout_node_id,
                    role_profile_ref=closeout_role_profile_ref,
                    output_schema_ref=DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
                    execution_contract=infer_execution_contract_payload(
                        role_profile_ref=closeout_role_profile_ref,
                        output_schema_ref=DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
                    ),
                    dispatch_intent={
                        "assignee_employee_id": assignee_employee_id,
                        "selection_reason": "Collect final delivery evidence and handoff notes into one auditable closeout package.",
                    },
                    summary=summary,
                    parent_ticket_id=parent_ticket_id,
                ),
            )
        ],
    )


def build_deterministic_fallback_batch(
    repository: ControlPlaneRepository,
    snapshot: dict,
    reason: str,
) -> CEOActionBatch:
    controller_state = snapshot.get("controller_state") or {}
    recommended_action = str(controller_state.get("recommended_action") or "").strip()
    if recommended_action == "HIRE_EMPLOYEE":
        hire_batch = _build_capability_hire_batch(snapshot, reason)
        if hire_batch is not None:
            return hire_batch
    if recommended_action == "REQUEST_MEETING":
        eligible_meeting_candidates = _eligible_meeting_candidates(snapshot)
        if len(eligible_meeting_candidates) == 1:
            candidate = {
                **eligible_meeting_candidates[0],
                "workflow_id": str((snapshot.get("workflow") or {}).get("workflow_id") or ""),
            }
            return _build_request_meeting_batch(
                candidate,
                reason=(
                    "Open one bounded technical decision meeting because the controller state requires it before implementation fanout."
                ),
            )
    backlog_followup_batch = _build_backlog_followup_batch(repository, snapshot, reason)
    if backlog_followup_batch is not None:
        return backlog_followup_batch
    closeout_batch = _build_autopilot_closeout_batch(repository, snapshot, reason)
    if closeout_batch is not None:
        return closeout_batch
    if _should_fallback_to_autopilot_governance_kickoff(snapshot):
        return _build_autopilot_governance_kickoff_batch(snapshot, reason)
    if _should_fallback_to_project_init_scope_kickoff(snapshot):
        return _build_project_init_scope_kickoff_batch(snapshot, reason)
    eligible_meeting_candidates = _eligible_meeting_candidates(snapshot)
    if len(eligible_meeting_candidates) == 1:
        candidate = {
            **eligible_meeting_candidates[0],
            "workflow_id": str((snapshot.get("workflow") or {}).get("workflow_id") or ""),
        }
        return _build_request_meeting_batch(
            candidate,
            reason=(
                "Open one bounded technical decision meeting because the snapshot exposes a single eligible candidate."
            ),
        )
    return build_no_action_batch(reason)


def propose_ceo_action_batch(
    repository: ControlPlaneRepository,
    *,
    snapshot: dict,
    runtime_provider_store: RuntimeProviderConfigStore | None = None,
) -> CEOProposalResult:
    config = resolve_runtime_provider_config(runtime_provider_store)
    effective_mode, effective_reason = runtime_provider_effective_mode(config, repository)
    provider_health_summary = runtime_provider_health_summary(config, repository)
    selection = resolve_provider_selection(config, target_ref=ROLE_BINDING_CEO_SHADOW, employee_provider_id=None)
    if selection is None:
        return CEOProposalResult(
            action_batch=build_deterministic_fallback_batch(repository, snapshot, effective_reason),
            effective_mode=effective_mode,
            provider_health_summary=provider_health_summary,
            model=(find_provider_entry(config, config.default_provider_id).model if find_provider_entry(config, config.default_provider_id) is not None else None),
            fallback_reason=effective_reason,
        )
    provider_mode, provider_reason = provider_effective_mode(selection.provider, repository)
    if not provider_mode.endswith("_LIVE"):
        return CEOProposalResult(
            action_batch=build_deterministic_fallback_batch(repository, snapshot, provider_reason),
            effective_mode=provider_mode,
            provider_health_summary=provider_health_summary,
            model=selection.actual_model or selection.provider.model,
            preferred_provider_id=selection.preferred_provider_id,
            preferred_model=selection.preferred_model,
            actual_provider_id=selection.provider.provider_id,
            actual_model=selection.actual_model or selection.provider.model,
            selection_reason=selection.selection_reason,
            policy_reason=selection.policy_reason,
            fallback_reason=provider_reason,
        )

    def _invoke_selection(current_selection):
        rendered_payload = build_ceo_shadow_rendered_payload(snapshot)
        provider_result = (
            invoke_openai_compat_response(
                OpenAICompatProviderConfig(
                    base_url=str(current_selection.provider.base_url or ""),
                    api_key=str(current_selection.provider.api_key or ""),
                    model=str(current_selection.actual_model or current_selection.provider.model or ""),
                    timeout_sec=current_selection.provider.timeout_sec,
                    reasoning_effort=current_selection.effective_reasoning_effort,
                ),
                rendered_payload,
            )
            if current_selection.provider.adapter_kind == RuntimeProviderAdapterKind.OPENAI_COMPAT
            else invoke_claude_code_response(
                ClaudeCodeProviderConfig(
                    command_path=str(current_selection.provider.command_path or ""),
                    model=str(current_selection.actual_model or current_selection.provider.model or ""),
                    timeout_sec=current_selection.provider.timeout_sec,
                ),
                rendered_payload,
            )
        )
        payload = _normalize_provider_action_batch_payload(
            json.loads(provider_result.output_text),
            snapshot,
        )
        return CEOActionBatch.model_validate(payload), provider_result

    try:
        action_batch, provider_result = _invoke_selection(selection)
        return CEOProposalResult(
            action_batch=action_batch,
            effective_mode=provider_mode,
            provider_health_summary=provider_health_summary,
            model=selection.actual_model or selection.provider.model,
            preferred_provider_id=selection.preferred_provider_id,
            preferred_model=selection.preferred_model,
            actual_provider_id=selection.provider.provider_id,
            actual_model=selection.actual_model or selection.provider.model,
            selection_reason=selection.selection_reason,
            policy_reason=selection.policy_reason,
            provider_response_id=provider_result.response_id,
        )
    except (OpenAICompatProviderError, ClaudeCodeProviderError, ValueError, TypeError, json.JSONDecodeError) as exc:
        failure_kind = (
            exc.failure_kind if isinstance(exc, (OpenAICompatProviderError, ClaudeCodeProviderError)) else None
        )
        if failure_kind in PROVIDER_FAILOVER_FAILURE_KINDS:
            for failover_selection in resolve_provider_failover_selections(
                config,
                repository,
                target_ref=ROLE_BINDING_CEO_SHADOW,
                primary_selection=selection,
            ):
                failover_mode, _ = provider_effective_mode(failover_selection.provider, repository)
                try:
                    action_batch, provider_result = _invoke_selection(failover_selection)
                    return CEOProposalResult(
                        action_batch=action_batch,
                        effective_mode=failover_mode,
                        provider_health_summary=provider_health_summary,
                        model=failover_selection.actual_model or failover_selection.provider.model,
                        preferred_provider_id=failover_selection.preferred_provider_id,
                        preferred_model=failover_selection.preferred_model,
                        actual_provider_id=failover_selection.provider.provider_id,
                        actual_model=failover_selection.actual_model or failover_selection.provider.model,
                        selection_reason=failover_selection.selection_reason,
                        policy_reason=failover_selection.policy_reason,
                        provider_response_id=provider_result.response_id,
                    )
                except (OpenAICompatProviderError, ClaudeCodeProviderError, ValueError, TypeError, json.JSONDecodeError) as failover_exc:
                    failover_failure_kind = (
                        failover_exc.failure_kind
                        if isinstance(failover_exc, (OpenAICompatProviderError, ClaudeCodeProviderError))
                        else None
                    )
                    if failover_failure_kind in PROVIDER_FAILOVER_FAILURE_KINDS:
                        continue
                    break
        fallback_reason = str(exc)
        return CEOProposalResult(
            action_batch=build_deterministic_fallback_batch(repository, snapshot, fallback_reason),
            effective_mode=provider_mode,
            provider_health_summary=provider_health_summary,
            model=selection.actual_model or selection.provider.model,
            preferred_provider_id=selection.preferred_provider_id,
            preferred_model=selection.preferred_model,
            actual_provider_id=selection.provider.provider_id,
            actual_model=selection.actual_model or selection.provider.model,
            selection_reason=selection.selection_reason,
            policy_reason=selection.policy_reason,
            fallback_reason=fallback_reason,
        )
