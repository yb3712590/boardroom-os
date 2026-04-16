from __future__ import annotations

from datetime import datetime

import app.core.process_assets as process_assets_module
import tests.test_api as api_test_helpers
from app.contracts.runtime import CompiledExecutionPackage
from app.core.constants import EVENT_INCIDENT_OPENED
from app.core.process_assets import (
    build_compiled_execution_package_process_asset_ref,
    build_result_process_assets,
    resolve_process_asset,
)
from app.core.versioning import build_process_asset_canonical_ref
from app.db.repository import ControlPlaneRepository


def test_build_result_process_assets_adds_governance_document_asset() -> None:
    created_spec = {
        "output_schema_ref": "architecture_brief",
    }
    result_payload = {
        "title": "Architecture brief for governance chain",
        "summary": "Keep the next slice aligned to the MVP boundary.",
        "document_kind_ref": "architecture_brief",
        "linked_document_refs": ["doc://governance/technology-decision/current"],
        "linked_artifact_refs": ["art://inputs/board-brief.md"],
        "source_process_asset_refs": ["pa://artifact/art%3A%2F%2Finputs%2Fboard-brief.md"],
        "decisions": ["Keep the next slice local-first."],
        "constraints": ["Do not widen into remote handoff."],
        "sections": [],
        "followup_recommendations": [
            {
                "recommendation_id": "rec_followup_build",
                "summary": "Prepare the next implementation ticket without widening scope.",
                "target_role": "frontend_engineer",
            }
        ],
    }

    produced_assets = build_result_process_assets(
        ticket_id="tkt_gov_doc_source",
        created_spec=created_spec,
        result_payload=result_payload,
        artifact_refs=["art://runtime/tkt_gov_doc_source/architecture-brief.json"],
    )

    governance_assets = [
        asset for asset in produced_assets if asset["process_asset_kind"] == "GOVERNANCE_DOCUMENT"
    ]

    assert governance_assets == [
        {
            "process_asset_ref": "pa://governance-document/tkt_gov_doc_source@1",
            "canonical_ref": "pa://governance-document/tkt_gov_doc_source@1",
            "version_int": 1,
            "process_asset_kind": "GOVERNANCE_DOCUMENT",
            "producer_ticket_id": "tkt_gov_doc_source",
            "summary": "Keep the next slice aligned to the MVP boundary.",
            "consumable_by": ["context_compiler", "followup_ticket", "review"],
            "source_metadata": {
                "document_kind_ref": "architecture_brief",
                "source_artifact_ref": "art://runtime/tkt_gov_doc_source/architecture-brief.json",
            },
        }
    ]


def test_resolve_failure_fingerprint_and_project_map_slice_process_assets(client) -> None:
    workflow_id = "wf_process_asset_project_map"
    repository = client.app.state.repository

    assert hasattr(process_assets_module, "build_failure_fingerprint_process_asset_ref")
    assert hasattr(process_assets_module, "build_project_map_slice_process_asset_ref")

    api_test_helpers._ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Resolve project map and failure fingerprint process assets.",
    )

    api_test_helpers._create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_architecture_project_map",
        node_id="node_architecture_project_map",
        output_schema_ref="architecture_brief",
        allowed_write_set=["artifacts/governance/*"],
        input_artifact_refs=[],
    )
    governance_payload = {
        "title": "Architecture brief for project map coverage",
        "summary": "Keep the workflow map tied to explicit process assets.",
        "document_kind_ref": "architecture_brief",
        "linked_document_refs": ["doc://governance/project-map/current"],
        "linked_artifact_refs": ["art://inputs/board-brief.md"],
        "source_process_asset_refs": ["pa://artifact/art%3A%2F%2Finputs%2Fboard-brief.md"],
        "decisions": ["Track graph health through explicit assets."],
        "constraints": ["Do not hide repeated failures behind fallback."],
        "sections": [],
        "followup_recommendations": [],
    }
    governance_submit = client.post(
        "/api/v1/commands/ticket-result-submit",
        json={
            "workflow_id": workflow_id,
            "ticket_id": "tkt_architecture_project_map",
            "node_id": "node_architecture_project_map",
            "submitted_by": "emp_frontend_2",
            "result_status": "completed",
            "schema_version": "architecture_brief_v1",
            "payload": governance_payload,
            "artifact_refs": [
                "art://runtime/tkt_architecture_project_map/architecture-brief.json",
            ],
            "written_artifacts": [
                {
                    "path": "artifacts/governance/architecture-brief.json",
                    "artifact_ref": "art://runtime/tkt_architecture_project_map/architecture-brief.json",
                    "kind": "JSON",
                    "content_json": governance_payload,
                }
            ],
            "assumptions": [],
            "issues": [],
            "confidence": 0.82,
            "needs_escalation": False,
            "summary": "Governance document recorded for process asset coverage.",
            "failure_kind": None,
            "failure_message": None,
            "failure_detail": None,
            "idempotency_key": (
                "ticket-result-submit:"
                f"{workflow_id}:tkt_architecture_project_map:architecture-brief"
            ),
        },
    )
    assert governance_submit.status_code == 200
    assert governance_submit.json()["status"] == "ACCEPTED"

    api_test_helpers._create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_build_project_map",
        node_id="node_build_project_map",
        output_schema_ref="source_code_delivery",
        delivery_stage="BUILD",
        allowed_write_set=["src/ui/*"],
        input_artifact_refs=[],
    )
    source_submit_payload = api_test_helpers._source_code_delivery_result_submit_payload(
        workflow_id=workflow_id,
        ticket_id="tkt_build_project_map",
        node_id="node_build_project_map",
        artifact_refs=["art://runtime/tkt_build_project_map/source-code.ts"],
        written_artifact_path="src/ui/homepage.ts",
        idempotency_key=f"ticket-result-submit:{workflow_id}:tkt_build_project_map:source",
    )
    source_submit_payload["payload"]["source_files"][0]["path"] = "src/ui/homepage.ts"
    source_submit_payload["payload"]["source_files"][0]["content"] = (
        "export function renderHomepage() {\n"
        "  return 'homepage-ready'\n"
        "}\n"
    )
    source_submit_payload["written_artifacts"][0]["path"] = "src/ui/homepage.ts"
    source_submit_payload["written_artifacts"][0]["content_text"] = (
        "export function renderHomepage() {\n"
        "  return 'homepage-ready'\n"
        "}\n"
    )
    source_submit_payload["payload"]["documentation_updates"] = [
        {
            "doc_ref": "doc://todo/project-map",
            "status": "UPDATED",
            "summary": "Documented the homepage implementation slice.",
        }
    ]
    source_submit = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=source_submit_payload,
    )
    assert source_submit.status_code == 200
    assert source_submit.json()["status"] == "ACCEPTED"

    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_INCIDENT_OPENED,
            actor_type="system",
            actor_id="test-seed",
            workflow_id=workflow_id,
            idempotency_key=f"incident-opened:{workflow_id}:build-project-map",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": "inc_project_map_build_failure",
                "node_id": "node_build_project_map",
                "ticket_id": "tkt_build_project_map",
                "incident_type": "REPEATED_FAILURE_ESCALATION",
                "status": "OPEN",
                "severity": "high",
                "fingerprint": (
                    f"{workflow_id}:node_build_project_map:repeat-failure:build-homepage-timeout"
                ),
                "latest_failure_fingerprint": "build-homepage-timeout",
                "latest_failure_kind": "RUNTIME_TIMEOUT_ESCALATION",
            },
            occurred_at=datetime.fromisoformat("2026-04-15T20:10:00+08:00"),
        )
        repository.refresh_projections(connection)

    failure_ref = process_assets_module.build_failure_fingerprint_process_asset_ref(
        "inc_project_map_build_failure"
    )
    map_ref = process_assets_module.build_project_map_slice_process_asset_ref(workflow_id)
    resolved_failure = resolve_process_asset(repository, failure_ref)
    resolved_map = resolve_process_asset(repository, map_ref)

    assert resolved_failure.process_asset_ref == "pa://failure-fingerprint/inc_project_map_build_failure@1"
    assert resolved_failure.process_asset_kind == "FAILURE_FINGERPRINT"
    assert resolved_failure.json_content["incident_id"] == "inc_project_map_build_failure"
    assert resolved_failure.json_content["ticket_id"] == "tkt_build_project_map"
    assert resolved_failure.json_content["related_process_asset_refs"] == [
        "pa://source-code-delivery/tkt_build_project_map@1"
    ]

    assert resolved_map.process_asset_ref == f"pa://project-map-slice/{workflow_id}@1"
    assert resolved_map.process_asset_kind == "PROJECT_MAP_SLICE"
    assert resolved_map.json_content["workflow_id"] == workflow_id
    assert resolved_map.json_content["module_paths"] == ["src"]
    assert resolved_map.json_content["document_surfaces"] == ["doc://todo/project-map"]
    assert resolved_map.json_content["decision_asset_refs"] == [
        "pa://governance-document/tkt_architecture_project_map@1"
    ]
    assert "pa://failure-fingerprint/inc_project_map_build_failure@1" in (
        resolved_map.json_content["failure_fingerprint_refs"]
    )
    assert resolved_map.json_content["source_process_asset_refs"] == [
        "pa://governance-document/tkt_architecture_project_map@1",
        "pa://source-code-delivery/tkt_build_project_map@1",
    ]


def test_resolve_process_asset_accepts_legacy_short_ref_and_returns_canonical_versioned_ref(
    db_path,
) -> None:
    repository = ControlPlaneRepository(db_path, 1000)
    repository.initialize()

    legacy_ref = build_compiled_execution_package_process_asset_ref("tkt_compile_001")
    versioned_ref = build_process_asset_canonical_ref(legacy_ref, 2)

    with repository.transaction() as connection:
        repository.save_compiled_execution_package(
            connection,
            CompiledExecutionPackage.model_validate(
                {
                        "meta": {
                            "compile_request_id": "creq_001",
                            "ticket_id": "tkt_compile_001",
                            "workflow_id": "wf_compile",
                            "node_id": "node_compile_001",
                            "attempt_no": 1,
                            "tenant_id": "tenant_default",
                            "workspace_id": "ws_default",
                            "lease_owner": "emp_frontend_2",
                            "governance_profile_ref": "gp_compile_runtime",
                            "compiler_version": "context-compiler.min.v1",
                        },
                    "compiled_role": {
                        "role_profile_ref": "frontend_engineer_primary",
                        "employee_id": "emp_frontend_2",
                        "employee_role_type": "frontend_engineer",
                        "skill_profile": {},
                        "personality_profile": {},
                        "aesthetic_profile": {},
                        "persona_summary": "Frontend delivery worker",
                    },
                    "compiled_constraints": {
                        "constraints_ref": "global_constraints_v3",
                        "global_rules": [],
                        "board_constraints": [],
                        "budget_constraints": {},
                    },
                    "governance_mode_slice": {
                        "governance_profile_ref": "gp_compile_runtime",
                        "approval_mode": "AUTO_CEO",
                        "audit_mode": "MINIMAL",
                        "auto_approval_scope": ["scope:mainline_internal"],
                        "expert_review_targets": ["checker", "board"],
                        "audit_materialization_policy": {
                            "ticket_context_archive": False,
                            "full_timeline": False,
                            "closeout_evidence": True,
                        },
                    },
                    "task_frame": {
                        "task_category": "implementation",
                        "goal": "Produce a structured source delivery result.",
                        "completion_definition": ["Emit the source delivery payload."],
                        "failure_definition": ["Raise a runtime failure instead of silently falling back."],
                        "deliverable_kind": "source_code_delivery",
                    },
                    "required_doc_surfaces": [],
                    "context_layer_summary": {
                        "w0_constitution": {
                            "label": "Constitution",
                            "item_count": 1,
                            "notes": [],
                            "governance_profile_ref": "gp_compile_runtime",
                            "allowed_tool_count": 1,
                            "allowed_write_set_count": 1,
                        },
                        "w1_task_frame": {
                            "label": "Task frame",
                            "item_count": 1,
                            "notes": [],
                            "governance_profile_ref": "gp_compile_runtime",
                        },
                        "w2_evidence": {
                            "label": "Evidence",
                            "item_count": 0,
                            "notes": [],
                            "governance_profile_ref": "gp_compile_runtime",
                        },
                        "w3_runtime_guard": {
                            "label": "Runtime guard",
                            "item_count": 1,
                            "notes": [],
                            "governance_profile_ref": "gp_compile_runtime",
                        },
                    },
                    "org_context": {
                        "upstream_provider": None,
                        "downstream_reviewer": None,
                        "collaborators": [],
                        "escalation_path": {
                            "current_blocking_reason": None,
                            "open_review_pack_id": None,
                            "open_incident_id": None,
                            "path": [],
                        },
                        "responsibility_boundary": {
                            "delivery_stage": "BUILD",
                            "output_schema_ref": "source_code_delivery",
                            "allowed_write_set": ["10-project/src/*"],
                            "board_review_possible": True,
                            "incident_path_possible": True,
                        },
                    },
                    "atomic_context_bundle": {
                        "context_blocks": [],
                        "token_budget": 1024,
                    },
                    "rendered_execution_payload": {
                        "meta": {
                            "bundle_id": "bundle_001",
                            "compile_id": "compile_001",
                            "compile_request_id": "creq_001",
                            "ticket_id": "tkt_compile_001",
                            "workflow_id": "wf_compile",
                            "node_id": "node_compile_001",
                            "compiler_version": "context-compiler.min.v1",
                            "model_profile": "boardroom_os.runtime.min",
                            "render_target": "json_messages_v1",
                            "rendered_at": "2026-03-28T02:00:00+00:00",
                        },
                        "messages": [],
                        "summary": {
                            "total_message_count": 0,
                            "control_message_count": 0,
                            "data_message_count": 0,
                            "retrieval_message_count": 0,
                            "degraded_data_message_count": 0,
                            "reference_message_count": 0,
                        },
                    },
                    "execution": {
                        "acceptance_criteria": ["Must produce a structured result"],
                        "allowed_tools": ["read_artifact"],
                        "allowed_write_set": ["10-project/src/*"],
                        "input_artifact_refs": [],
                        "input_process_asset_refs": [],
                        "required_read_refs": [],
                        "doc_update_requirements": [],
                        "project_workspace_ref": None,
                        "project_checkout_ref": None,
                        "project_checkout_path": None,
                        "git_branch_ref": None,
                        "deliverable_kind": "source_code_delivery",
                        "git_policy": "per_ticket_commit_required",
                        "output_schema_ref": "source_code_delivery",
                        "output_schema_version": 1,
                    },
                    "governance": {
                        "retry_budget": 1,
                        "timeout_sla_sec": 1800,
                        "escalation_policy": {
                            "on_timeout": "retry",
                            "on_schema_error": "retry",
                            "on_repeat_failure": "escalate_ceo",
                        },
                    },
                }
            ),
            compiled_at=datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
        )
        repository.save_compiled_execution_package(
            connection,
            CompiledExecutionPackage.model_validate(
                {
                        "meta": {
                            "compile_request_id": "creq_002",
                            "ticket_id": "tkt_compile_001",
                            "workflow_id": "wf_compile",
                            "node_id": "node_compile_001",
                            "attempt_no": 1,
                            "tenant_id": "tenant_default",
                            "workspace_id": "ws_default",
                            "lease_owner": "emp_frontend_2",
                            "governance_profile_ref": "gp_compile_runtime",
                            "compiler_version": "context-compiler.min.v1",
                        },
                    "compiled_role": {
                        "role_profile_ref": "frontend_engineer_primary",
                        "employee_id": "emp_frontend_2",
                        "employee_role_type": "frontend_engineer",
                        "skill_profile": {},
                        "personality_profile": {},
                        "aesthetic_profile": {},
                        "persona_summary": "Frontend delivery worker",
                    },
                    "compiled_constraints": {
                        "constraints_ref": "global_constraints_v3",
                        "global_rules": [],
                        "board_constraints": [],
                        "budget_constraints": {},
                    },
                    "governance_mode_slice": {
                        "governance_profile_ref": "gp_compile_runtime",
                        "approval_mode": "AUTO_CEO",
                        "audit_mode": "MINIMAL",
                        "auto_approval_scope": ["scope:mainline_internal"],
                        "expert_review_targets": ["checker", "board"],
                        "audit_materialization_policy": {
                            "ticket_context_archive": False,
                            "full_timeline": False,
                            "closeout_evidence": True,
                        },
                    },
                    "task_frame": {
                        "task_category": "implementation",
                        "goal": "Produce a structured source delivery result.",
                        "completion_definition": ["Emit the source delivery payload."],
                        "failure_definition": ["Raise a runtime failure instead of silently falling back."],
                        "deliverable_kind": "source_code_delivery",
                    },
                    "required_doc_surfaces": [],
                    "context_layer_summary": {
                        "w0_constitution": {
                            "label": "Constitution",
                            "item_count": 1,
                            "notes": [],
                            "governance_profile_ref": "gp_compile_runtime",
                            "allowed_tool_count": 1,
                            "allowed_write_set_count": 1,
                        },
                        "w1_task_frame": {
                            "label": "Task frame",
                            "item_count": 1,
                            "notes": [],
                            "governance_profile_ref": "gp_compile_runtime",
                        },
                        "w2_evidence": {
                            "label": "Evidence",
                            "item_count": 0,
                            "notes": [],
                            "governance_profile_ref": "gp_compile_runtime",
                        },
                        "w3_runtime_guard": {
                            "label": "Runtime guard",
                            "item_count": 1,
                            "notes": [],
                            "governance_profile_ref": "gp_compile_runtime",
                        },
                    },
                    "org_context": {
                        "upstream_provider": None,
                        "downstream_reviewer": None,
                        "collaborators": [],
                        "escalation_path": {
                            "current_blocking_reason": None,
                            "open_review_pack_id": None,
                            "open_incident_id": None,
                            "path": [],
                        },
                        "responsibility_boundary": {
                            "delivery_stage": "BUILD",
                            "output_schema_ref": "source_code_delivery",
                            "allowed_write_set": ["10-project/src/*"],
                            "board_review_possible": True,
                            "incident_path_possible": True,
                        },
                    },
                    "atomic_context_bundle": {
                        "context_blocks": [],
                        "token_budget": 1024,
                    },
                    "rendered_execution_payload": {
                        "meta": {
                            "bundle_id": "bundle_002",
                            "compile_id": "compile_002",
                            "compile_request_id": "creq_002",
                            "ticket_id": "tkt_compile_001",
                            "workflow_id": "wf_compile",
                            "node_id": "node_compile_001",
                            "compiler_version": "context-compiler.min.v1",
                            "model_profile": "boardroom_os.runtime.min",
                            "render_target": "json_messages_v1",
                            "rendered_at": "2026-03-28T02:05:00+00:00",
                        },
                        "messages": [],
                        "summary": {
                            "total_message_count": 0,
                            "control_message_count": 0,
                            "data_message_count": 0,
                            "retrieval_message_count": 0,
                            "degraded_data_message_count": 0,
                            "reference_message_count": 0,
                        },
                    },
                    "execution": {
                        "acceptance_criteria": ["Must produce a structured result"],
                        "allowed_tools": ["read_artifact"],
                        "allowed_write_set": ["10-project/src/*"],
                        "input_artifact_refs": [],
                        "input_process_asset_refs": [],
                        "required_read_refs": [],
                        "doc_update_requirements": [],
                        "project_workspace_ref": None,
                        "project_checkout_ref": None,
                        "project_checkout_path": None,
                        "git_branch_ref": None,
                        "deliverable_kind": "source_code_delivery",
                        "git_policy": "per_ticket_commit_required",
                        "output_schema_ref": "source_code_delivery",
                        "output_schema_version": 1,
                    },
                    "governance": {
                        "retry_budget": 1,
                        "timeout_sla_sec": 1800,
                        "escalation_policy": {
                            "on_timeout": "retry",
                            "on_schema_error": "retry",
                            "on_repeat_failure": "escalate_ceo",
                        },
                    },
                }
            ),
            compiled_at=datetime.fromisoformat("2026-03-28T10:05:00+08:00"),
        )

    resolved_from_legacy = resolve_process_asset(repository, legacy_ref)
    resolved_from_versioned = resolve_process_asset(repository, versioned_ref)

    assert resolved_from_legacy.process_asset_ref == versioned_ref
    assert resolved_from_legacy.canonical_ref == versioned_ref
    assert resolved_from_legacy.version_int == 2
    assert resolved_from_legacy.supersedes_ref == build_process_asset_canonical_ref(legacy_ref, 1)
    assert resolved_from_versioned.process_asset_ref == versioned_ref


def test_resolve_board_advisory_graph_patch_assets(client) -> None:
    workflow_id = "wf_process_asset_advisory_patch"
    repository = client.app.state.repository

    api_test_helpers._ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Resolve advisory graph patch proposal and applied patch assets.",
    )
    approval = api_test_helpers._seed_review_request(client, workflow_id=workflow_id)

    with api_test_helpers._suppress_ceo_shadow_side_effects():
        enter_response = client.post(
            "/api/v1/commands/modify-constraints",
            json={
                "review_pack_id": approval["review_pack_id"],
                "review_pack_version": approval["review_pack_version"],
                "command_target_version": approval["command_target_version"],
                "approval_id": approval["approval_id"],
                "constraint_patch": {
                    "add_rules": ["Keep the branch frozen until the board confirms the proposal."],
                    "remove_rules": [],
                    "replace_rules": [],
                },
                "board_comment": "Draft a reviewed patch before the next runtime pass.",
                "idempotency_key": f"modify-constraints:{approval['approval_id']}:process-assets",
            },
        )
    assert enter_response.status_code == 200
    assert enter_response.json()["status"] == "ACCEPTED"

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None

    analysis_response = client.post(
        "/api/v1/commands/board-advisory-request-analysis",
        json={
            "session_id": advisory_session["session_id"],
            "idempotency_key": f"board-advisory-analysis:{advisory_session['session_id']}:process-assets",
        },
    )
    assert analysis_response.status_code == 200
    assert analysis_response.json()["status"] == "ACCEPTED"

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None
    proposal_ref = str(advisory_session["latest_patch_proposal_ref"])
    resolved_proposal = resolve_process_asset(repository, proposal_ref)

    assert resolved_proposal.process_asset_kind == "GRAPH_PATCH_PROPOSAL"
    assert resolved_proposal.process_asset_ref == proposal_ref
    assert resolved_proposal.json_content["proposal_ref"] == proposal_ref
    assert resolved_proposal.json_content["freeze_node_ids"] == ["node_homepage_visual"]
    assert resolved_proposal.json_content["focus_node_ids"] == ["node_homepage_visual"]

    apply_response = client.post(
        "/api/v1/commands/board-advisory-apply-patch",
        json={
            "session_id": advisory_session["session_id"],
            "proposal_ref": proposal_ref,
            "idempotency_key": f"board-advisory-apply:{advisory_session['session_id']}:process-assets",
        },
    )
    assert apply_response.status_code == 200
    assert apply_response.json()["status"] == "ACCEPTED"

    advisory_session = repository.get_board_advisory_session_for_approval(approval["approval_id"])
    assert advisory_session is not None
    patch_ref = str(advisory_session["approved_patch_ref"])
    resolved_patch = resolve_process_asset(repository, patch_ref)

    assert resolved_patch.process_asset_kind == "GRAPH_PATCH"
    assert resolved_patch.process_asset_ref == patch_ref
    assert resolved_patch.json_content["patch_ref"] == patch_ref
    assert resolved_patch.json_content["proposal_ref"] == proposal_ref
    assert resolved_patch.json_content["freeze_node_ids"] == ["node_homepage_visual"]
