from __future__ import annotations

from datetime import datetime

from app.contracts.runtime import CompiledExecutionPackage
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
