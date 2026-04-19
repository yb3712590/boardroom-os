from __future__ import annotations

from app.contracts.runtime import (
    RenderedExecutionMessage,
    RenderedExecutionPayload,
    RenderedExecutionPayloadMeta,
    RenderedExecutionPayloadSummary,
)
from app.core.ceo_snapshot_contracts import capability_plan_view, controller_state_view, task_sensemaking_view
from app.core.ceo_execution_presets import (
    GOVERNANCE_DOCUMENT_CHAIN_ORDER,
)
from app.core.output_schemas import ARCHITECTURE_BRIEF_SCHEMA_REF
from app.core.workflow_progression import build_project_init_kickoff_spec
from app.core.constants import EVENT_BOARD_DIRECTIVE_RECEIVED
from app.core.ids import new_prefixed_id
from app.core.time import now_local


CEO_SHADOW_PROMPT_VERSION = "ceo_shadow_v3"


def build_ceo_shadow_system_prompt(snapshot: dict) -> str:
    trigger_type = str((snapshot.get("trigger") or {}).get("trigger_type") or "")
    workflow = snapshot.get("workflow") or {}
    ticket_summary = snapshot.get("ticket_summary") or {}
    controller_state = controller_state_view(snapshot)
    capability_plan = capability_plan_view(snapshot)
    task_sensemaking = task_sensemaking_view(snapshot)
    projection_snapshot = snapshot.get("projection_snapshot") or {}
    replan_focus = snapshot.get("replan_focus") or {}
    latest_advisory_decision = (snapshot.get("replan_focus") or {}).get("latest_advisory_decision")
    project_map_slices = projection_snapshot.get("project_map_slices") or []
    failure_fingerprints = replan_focus.get("failure_fingerprints") or []
    graph_health_report = projection_snapshot.get("graph_health_report") or {}
    runtime_liveness_report = projection_snapshot.get("runtime_liveness_report") or {}
    kickoff_instruction = ""
    if trigger_type == EVENT_BOARD_DIRECTIVE_RECEIVED and int(ticket_summary.get("total") or 0) == 0:
        kickoff_spec = build_project_init_kickoff_spec(workflow)
        if str(kickoff_spec["output_schema_ref"]) == ARCHITECTURE_BRIEF_SCHEMA_REF:
            kickoff_instruction = (
                "When a new CEO_AUTOPILOT_FINE_GRAINED board directive arrives and no tickets exist yet, propose exactly one CREATE_TICKET "
                f"for the initial governance kickoff using role_profile_ref `{kickoff_spec['role_profile_ref']}`, "
                f"output_schema_ref `{kickoff_spec['output_schema_ref']}`, and node_id `{kickoff_spec['node_id']}`. "
                "The payload must include execution_contract with execution_target_ref `execution_target:frontend_governance_document`, "
                "required_capability_tags [`structured_output`, `planning`], and runtime_contract_version `execution_contract_v1`. "
                "The payload must also include dispatch_intent with one active assignee_employee_id from snapshot.employees and a short selection_reason. "
                "That kickoff ticket should clarify the vague goal, capture slightly more concrete delivery requirements, "
                "and prepare a human-readable architecture brief that decomposes the library system into many atomic tasks with explicit dependencies. "
                "Do not create consensus_document, BUILD, CHECK, or REVIEW tickets before the architecture_brief exists.\n"
            )
        else:
            kickoff_instruction = (
                "When a new board directive arrives and no tickets exist yet, propose exactly one CREATE_TICKET "
                f"for the initial scope kickoff using role_profile_ref `{kickoff_spec['role_profile_ref']}`, "
                f"output_schema_ref `{kickoff_spec['output_schema_ref']}`, and node_id `{kickoff_spec['node_id']}`. "
                "The payload must include execution_contract with execution_target_ref `execution_target:scope_consensus`, "
                "required_capability_tags [`structured_output`, `planning`], and runtime_contract_version `execution_contract_v1`. "
                "The payload must also include dispatch_intent with one active assignee_employee_id from snapshot.employees and a short selection_reason. "
                "That kickoff ticket should produce a startup consensus report plus the first batch of follow-up "
                f"ticket outlines for north star goal: {workflow.get('north_star_goal')}. "
                "Do not create downstream BUILD, CHECK, or REVIEW tickets directly before board approval.\n"
            )
    return (
        "You are the Boardroom OS CEO in shadow mode.\n"
        "You read the current workflow snapshot and propose controlled actions only.\n"
        "You do not execute actions and you do not rewrite workflow history.\n"
        "Prefer the smallest useful next step.\n"
        "Every action must use action_type exactly. Do not use type as an alias.\n"
        "Every CREATE_TICKET payload must include both execution_contract and dispatch_intent.\n"
        "CREATE_TICKET payload must include workflow_id, node_id, role_profile_ref, output_schema_ref, execution_contract, dispatch_intent, summary, and parent_ticket_id.\n"
        "CREATE_TICKET must not place assignee_employee_id, dependency_gate_refs, required_capability_tags, source_ticket_id, or source_node_id at the top level.\n"
        "Only dispatch_intent may carry assignee_employee_id and dependency_gate_refs.\n"
        "Only execution_contract may carry required_capability_tags.\n"
        "HIRE_EMPLOYEE payload must include workflow_id, role_type, role_profile_refs, and request_summary.\n"
        "HIRE_EMPLOYEE must not use role_profile_ref, justification, selection_guidance, or top-level reason.\n"
        "NO_ACTION payload must include payload.reason. Do not use top-level reason.\n"
        "Prefer a governance document first when the workflow still needs architecture, technology, milestone, design, or backlog direction.\n"
        "Governance document outputs available on the current live path are: "
        f"{', '.join(GOVERNANCE_DOCUMENT_CHAIN_ORDER)}.\n"
        "Before directly creating implementation tickets, consider whether one governance document should be created first.\n"
        "Keep the minimal document-first order explicit: architecture_brief -> technology_decision -> milestone_plan -> detailed_design -> backlog_recommendation -> source_code_delivery.\n"
        "If workflow.workflow_profile is CEO_AUTOPILOT_FINE_GRAINED, keep task breakdown fine-grained and prefer atomic tasks with explicit dependency refs over large bundled tickets.\n"
        "Governance document kinds are a shared document family, not a hard role whitelist.\n"
        "Governance documents may stay on current live planning roles, or use architect_primary / cto_primary when those roles already exist in the active board-approved roster.\n"
        "Do not use backend_engineer_primary, database_engineer_primary, or platform_sre_primary for direct CEO CREATE_TICKET unless snapshot.replan_focus.capability_plan.followup_ticket_plans explicitly routes a backlog follow-up there.\n"
        "Read snapshot.projection_snapshot before anything else.\n"
        "Then read snapshot.replan_focus.task_sensemaking, snapshot.replan_focus.capability_plan, and snapshot.replan_focus.controller_state before proposing actions.\n"
        "Then inspect snapshot.projection_snapshot.board_advisory_sessions and snapshot.replan_focus.latest_advisory_decision.\n"
        "Then inspect snapshot.projection_snapshot.project_map_slices, snapshot.replan_focus.failure_fingerprints, "
        "snapshot.projection_snapshot.graph_health_report, and snapshot.projection_snapshot.runtime_liveness_report.\n"
        "If snapshot.replan_focus.latest_advisory_decision exists, treat it as the current execution baseline before proposing any new action.\n"
        "If snapshot.projection_snapshot.graph_health_report.overall_health is CRITICAL or "
        "snapshot.projection_snapshot.runtime_liveness_report.overall_health is CRITICAL, treat stabilization as a blocking risk before proposing new fanout.\n"
        "When snapshot.replan_focus.controller_state.state is GOVERNANCE_REQUIRED, ARCHITECT_REQUIRED, MEETING_REQUIRED, or STAFFING_REQUIRED, satisfy that gate first instead of forcing implementation tickets through.\n"
        "If snapshot.replan_focus.capability_plan.required_governance_ticket_plan exists, only CREATE_TICKET that exact governance ticket before implementation fanout resumes.\n"
        "If snapshot.replan_focus.capability_plan.followup_ticket_plans exists, keep CREATE_TICKET proposals aligned with those planned node_id / role_profile_ref pairs.\n"
        "Before proposing any action, inspect snapshot.projection_snapshot.reuse_candidates.\n"
        "If recent completed tickets or closed meetings already cover the current need, prefer NO_ACTION.\n"
        "If existing work only needs recovery or follow-through, prefer RETRY_TICKET or continued waiting over creating parallel tickets.\n"
        "Meeting requests are a bounded exception path, not the default collaboration mode.\n"
        "You may only propose REQUEST_MEETING when snapshot.replan_focus.meeting_candidates contains an eligible candidate and snapshot.projection_snapshot.reuse_candidates does not already resolve the decision.\n"
        "Do not invent participants, meeting types, or source refs outside snapshot.replan_focus.meeting_candidates.\n"
        "Do not propose HIRE_EMPLOYEE just to collect extra opinions when snapshot.projection_snapshot.reuse_candidates already provides enough guidance.\n"
        "When proposing staffing changes, prefer complementary same-role profiles and avoid hires that duplicate "
        "the active board-approved team on risk posture, challenge style, rigor, and aesthetic preferences.\n"
        "If the workflow is blocked by board review or incident, usually return NO_ACTION.\n"
        f"{kickoff_instruction}"
        f"Current task_sensemaking summary: {task_sensemaking}.\n"
        f"Current controller_state summary: {controller_state}.\n"
        f"Current capability_plan summary: {capability_plan}.\n"
        f"Current latest_advisory_decision summary: {latest_advisory_decision}.\n"
        f"Current project_map_slices summary: {project_map_slices}.\n"
        f"Current failure_fingerprints summary: {failure_fingerprints}.\n"
        f"Current graph_health_report summary: {graph_health_report}.\n"
        f"Current runtime_liveness_report summary: {runtime_liveness_report}.\n"
        "Return strict JSON matching ceo_action_batch_v1 with a short summary and actions array.\n"
        "Supported actions: CREATE_TICKET, RETRY_TICKET, HIRE_EMPLOYEE, REQUEST_MEETING, ESCALATE_TO_BOARD, NO_ACTION."
    )


def build_ceo_shadow_rendered_payload(snapshot: dict) -> RenderedExecutionPayload:
    rendered_at = now_local()
    workflow = snapshot["workflow"]
    trigger = snapshot["trigger"]
    messages = [
        RenderedExecutionMessage(
            role="system",
            channel="SYSTEM_CONTROLS",
            content_type="TEXT",
            content_payload={"text": build_ceo_shadow_system_prompt(snapshot)},
        ),
        RenderedExecutionMessage(
            role="user",
            channel="TASK_DEFINITION",
            content_type="JSON",
            content_payload={
                "task": "Review the workflow snapshot and propose the next controlled CEO actions.",
                "shadow_mode": True,
                "prompt_version": CEO_SHADOW_PROMPT_VERSION,
            },
        ),
        RenderedExecutionMessage(
            role="user",
            channel="CONTEXT_BLOCK",
            content_type="JSON",
            content_payload=snapshot,
            block_id=f"ceo_shadow_snapshot:{workflow['workflow_id']}",
            source_ref=trigger.get("trigger_ref") or workflow["workflow_id"],
        ),
        RenderedExecutionMessage(
            role="user",
            channel="OUTPUT_CONTRACT_REMINDER",
            content_type="JSON",
            content_payload={
                "output_schema_ref": "ceo_action_batch",
                "output_schema_version": 1,
                "must_output_json_only": True,
            },
        ),
    ]
    return RenderedExecutionPayload(
        meta=RenderedExecutionPayloadMeta(
            bundle_id=new_prefixed_id("ctx"),
            compile_id=new_prefixed_id("manifest"),
            compile_request_id=new_prefixed_id("compile"),
            ticket_id=f"ceo-shadow-{workflow['workflow_id']}",
            workflow_id=workflow["workflow_id"],
            node_id="node_ceo_shadow",
            compiler_version=CEO_SHADOW_PROMPT_VERSION,
            model_profile="ceo_shadow",
            render_target="json_messages_v1",
            rendered_at=rendered_at,
        ),
        messages=messages,
        summary=RenderedExecutionPayloadSummary(
            total_message_count=len(messages),
            control_message_count=1,
            data_message_count=3,
            retrieval_message_count=0,
            degraded_data_message_count=0,
            reference_message_count=0,
        ),
    )
