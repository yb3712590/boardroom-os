from __future__ import annotations

import json
from datetime import datetime

import pytest
import tests.test_api as api_test_helpers

from app.contracts.commands import DeveloperInspectorRefs
from app.contracts.governance import GovernanceProfile

from app.core.constants import EVENT_TICKET_CREATED
from app.core.context_compiler import (
    MINIMAL_CONTEXT_COMPILER_VERSION,
    build_compile_request,
    compile_and_persist_execution_artifacts,
    compile_audit_artifacts,
    compile_execution_package,
    export_latest_compile_artifacts_to_developer_inspector,
)
from app.core.process_assets import (
    build_artifact_process_asset_ref,
    build_compiled_context_bundle_process_asset_ref,
    build_compiled_execution_package_process_asset_ref,
)
from app.core.runtime_provider_config import (
    OPENAI_COMPAT_PROVIDER_ID,
    RuntimeProviderConfigEntry,
    RuntimeProviderStoredConfig,
)
from app.core.versioning import build_process_asset_canonical_ref


def _configure_runtime_provider(client) -> None:
    client.app.state.runtime_provider_store.save_config(
        RuntimeProviderStoredConfig(
            default_provider_id=OPENAI_COMPAT_PROVIDER_ID,
            providers=[
                RuntimeProviderConfigEntry(
                    provider_id=OPENAI_COMPAT_PROVIDER_ID,
                    adapter_kind="openai_compat",
                    label="OpenAI Compat",
                    enabled=True,
                    base_url="https://api-hk.codex-for.me/v1",
                    api_key="test-key",
                    model="gpt-5.4",
                    timeout_sec=30.0,
                    reasoning_effort="high",
                    capability_tags=["structured_output", "planning", "implementation", "review"],
                    fallback_provider_ids=[],
                )
            ],
            role_bindings=[],
        )
    )


@pytest.fixture(autouse=True)
def _configure_runtime_provider_fixture(client):
    _configure_runtime_provider(client)


@pytest.fixture(autouse=True)
def _seed_default_governance_profile_fixture(client, request):
    if "missing_governance_profile" in request.node.name:
        return
    _seed_governance_profile(
        client.app.state.repository,
        workflow_id="wf_compile",
        profile_id="gp_compile_runtime",
    )


def _seed_governance_profile(
    repository,
    *,
    workflow_id: str,
    profile_id: str | None = None,
) -> None:
    existing = repository.get_latest_governance_profile(workflow_id)
    if existing is not None:
        return
    resolved_profile_id = profile_id or f"gp_{workflow_id}"
    with repository.transaction() as connection:
        repository.save_governance_profile(
            connection,
            GovernanceProfile(
                profile_id=resolved_profile_id,
                workflow_id=workflow_id,
                approval_mode="AUTO_CEO",
                audit_mode="MINIMAL",
                auto_approval_scope=["scope:mainline_internal"],
                expert_review_targets=["checker", "board"],
                audit_materialization_policy={
                    "ticket_context_archive": False,
                    "full_timeline": False,
                    "closeout_evidence": True,
                },
                source_ref=f"doc://charter/{workflow_id}",
                supersedes_ref=None,
                effective_from_event=f"evt_governance_{workflow_id}",
                version_int=1,
            ),
        )


def _ticket_create_payload(
    *,
    workflow_id: str = "wf_compile",
    ticket_id: str = "tkt_compile_001",
    node_id: str = "node_compile_001",
    input_artifact_refs: list[str] | None = None,
    input_process_asset_refs: list[str] | None = None,
    role_profile_ref: str = "frontend_engineer_primary",
    output_schema_ref: str = "ui_milestone_review",
    allowed_write_set: list[str] | None = None,
    delivery_stage: str | None = None,
    parent_ticket_id: str | None = None,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
) -> dict:
    payload = {
        "ticket_id": ticket_id,
        "workflow_id": workflow_id,
        "node_id": node_id,
        "parent_ticket_id": parent_ticket_id,
        "attempt_no": 1,
        "role_profile_ref": role_profile_ref,
        "constraints_ref": "global_constraints_v3",
        "input_artifact_refs": input_artifact_refs if input_artifact_refs is not None else [
            "art://inputs/brief.md",
            "art://inputs/brand-guide.md",
        ],
        "context_query_plan": {
            "keywords": ["homepage", "brand"],
            "semantic_queries": ["approved direction"],
            "max_context_tokens": 3000,
        },
        "acceptance_criteria": ["Must produce a structured result"],
        "output_schema_ref": output_schema_ref,
        "output_schema_version": 1,
        "allowed_tools": ["read_artifact", "write_artifact"],
        "allowed_write_set": allowed_write_set or ["artifacts/ui/homepage/*"],
        "retry_budget": 1,
        "priority": "high",
        "timeout_sla_sec": 1800,
        "deadline_at": "2026-03-28T18:00:00+08:00",
        "escalation_policy": {
            "on_timeout": "retry",
            "on_schema_error": "retry",
            "on_repeat_failure": "escalate_ceo",
        },
        "idempotency_key": f"ticket-create:{workflow_id}:{ticket_id}",
    }
    if tenant_id is not None:
        payload["tenant_id"] = tenant_id
    if workspace_id is not None:
        payload["workspace_id"] = workspace_id
    if delivery_stage is not None:
        payload["delivery_stage"] = delivery_stage
    if input_process_asset_refs is not None:
        payload["input_process_asset_refs"] = input_process_asset_refs
    return payload


def _ticket_lease_payload(
    *,
    workflow_id: str = "wf_compile",
    ticket_id: str = "tkt_compile_001",
    node_id: str = "node_compile_001",
) -> dict:
    return {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "leased_by": "emp_frontend_2",
        "lease_timeout_sec": 600,
        "idempotency_key": f"ticket-lease:{workflow_id}:{ticket_id}",
    }


def _ticket_start_payload(
    *,
    workflow_id: str = "wf_compile",
    ticket_id: str = "tkt_compile_001",
    node_id: str = "node_compile_001",
    started_by: str = "emp_frontend_2",
) -> dict:
    return {
        "workflow_id": workflow_id,
        "ticket_id": ticket_id,
        "node_id": node_id,
        "started_by": started_by,
        "idempotency_key": f"ticket-start:{workflow_id}:{ticket_id}",
    }


def _governance_document_payload(document_kind_ref: str = "architecture_brief") -> dict:
    return {
        "title": f"{document_kind_ref} for Boardroom OS",
        "summary": f"{document_kind_ref} keeps the next delivery slice aligned.",
        "document_kind_ref": document_kind_ref,
        "linked_document_refs": ["doc://governance/technology-decision/current"],
        "linked_artifact_refs": ["art://inputs/board-brief.md"],
        "source_process_asset_refs": ["pa://artifact/art%3A%2F%2Finputs%2Fboard-brief.md"],
        "decisions": [
            "Keep the next slice inside the current local MVP boundary.",
            "Preserve explicit governance between board review and worker execution.",
        ],
        "constraints": [
            "Do not widen into remote handoff.",
            "Keep React as a thin governance shell.",
        ],
        "sections": [
            {
                "section_id": "sec_context",
                "label": "Context",
                "summary": "Current boundary and rationale.",
                "content_markdown": "## Context\n\nKeep the scope narrow and auditable.",
            }
        ],
        "followup_recommendations": [
            {
                "recommendation_id": "rec_followup_build",
                "summary": "Prepare the next implementation ticket without widening scope.",
                "target_role": "frontend_engineer",
            }
        ],
    }


def _seed_artifact(
    client,
    *,
    artifact_ref: str,
    logical_path: str,
    kind: str,
    media_type: str,
    content_text: str | None = None,
    content_json: dict | None = None,
    content_bytes: bytes | None = None,
    materialization_status: str = "MATERIALIZED",
    lifecycle_status: str = "ACTIVE",
    deleted_at: str | None = None,
    deleted_by: str | None = None,
    delete_reason: str | None = None,
    workflow_id: str = "wf_seed_inputs",
    ticket_id: str = "tkt_seed_inputs",
    node_id: str = "node_seed_inputs",
) -> None:
    repository = client.app.state.repository
    artifact_store = client.app.state.artifact_store
    storage_relpath = None
    content_hash = None
    size_bytes = None

    if materialization_status == "MATERIALIZED":
        if content_json is not None:
            materialized = artifact_store.materialize_json(logical_path, content_json)
        elif content_bytes is not None:
            materialized = artifact_store.materialize_bytes(logical_path, content_bytes)
        else:
            materialized = artifact_store.materialize_text(logical_path, content_text or "")
        storage_relpath = materialized.storage_relpath
        content_hash = materialized.content_hash
        size_bytes = materialized.size_bytes

    with repository.transaction() as connection:
        repository.save_artifact_record(
            connection,
            artifact_ref=artifact_ref,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            node_id=node_id,
            logical_path=logical_path,
            kind=kind,
            media_type=media_type,
            materialization_status=materialization_status,
            lifecycle_status=lifecycle_status,
            storage_relpath=storage_relpath,
            content_hash=content_hash,
            size_bytes=size_bytes,
            retention_class="PERSISTENT",
            expires_at=None,
            deleted_at=datetime.fromisoformat(deleted_at) if deleted_at is not None else None,
            deleted_by=deleted_by,
            delete_reason=delete_reason,
            created_at=datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
        )


def _seed_historical_review_summary(
    client,
    *,
    workflow_id: str,
    review_pack_id: str,
    title: str,
    summary: str,
) -> None:
    repository = client.app.state.repository
    payload = {
        "review_pack": {
            "meta": {
                "review_pack_id": review_pack_id,
                "workflow_id": workflow_id,
                "review_type": "VISUAL_MILESTONE",
                "created_at": "2026-03-27T10:00:00+08:00",
                "priority": "high",
            },
            "subject": {
                "title": title,
                "source_node_id": "node_history_review",
                "source_ticket_id": f"tkt_{review_pack_id}",
                "blocking_scope": "NODE_ONLY",
            },
            "trigger": {
                "trigger_event_id": f"evt_{review_pack_id}",
                "trigger_reason": "Historical review result",
                "why_now": "Useful for later work",
            },
            "recommendation": {
                "recommended_action": "APPROVE",
                "recommended_option_id": "A",
                "summary": summary,
            },
            "options": [
                {
                    "option_id": "A",
                    "label": "Approved",
                    "summary": summary,
                    "artifact_refs": [],
                    "preview_assets": [],
                    "pros": [],
                    "cons": [],
                    "risks": [],
                    "estimated_budget_impact_range": None,
                }
            ],
            "evidence_summary": [],
            "delta_summary": None,
            "maker_checker_summary": None,
            "risk_summary": None,
            "budget_impact": None,
            "decision_form": {
                "allowed_actions": ["APPROVE", "REJECT", "MODIFY_CONSTRAINTS"],
                "command_target_version": 1,
                "requires_comment_on_reject": True,
                "requires_constraint_patch_on_modify": True,
            },
            "developer_inspector_refs": None,
        },
        "available_actions": [],
        "draft_defaults": {},
        "inbox_title": title,
        "inbox_summary": summary,
        "badges": ["history", "review"],
        "priority": "high",
        "resolution": {
            "selected_option_id": "A",
            "board_comment": "Approved and archived for later retrieval.",
        },
    }
    with repository.transaction() as connection:
        connection.execute(
            """
            INSERT INTO approval_projection (
                approval_id,
                review_pack_id,
                workflow_id,
                approval_type,
                status,
                requested_by,
                resolved_by,
                resolved_at,
                created_at,
                updated_at,
                review_pack_version,
                command_target_version,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"apr_{review_pack_id}",
                review_pack_id,
                workflow_id,
                "VISUAL_MILESTONE",
                "APPROVED",
                "board",
                "board",
                "2026-03-27T10:10:00+08:00",
                "2026-03-27T10:00:00+08:00",
                "2026-03-27T10:10:00+08:00",
                1,
                1,
                json.dumps(payload, sort_keys=True),
            ),
        )


def _seed_historical_incident_summary(
    client,
    *,
    workflow_id: str,
    incident_id: str,
    summary: str,
    ticket_id: str,
) -> None:
    repository = client.app.state.repository
    payload = {
        "incident_id": incident_id,
        "workflow_id": workflow_id,
        "node_id": "node_history_incident",
        "ticket_id": ticket_id,
        "incident_type": "REPEATED_FAILURE_ESCALATION",
        "status": "OPEN",
        "severity": "high",
        "fingerprint": f"{workflow_id}:history:fingerprint",
        "summary": summary,
        "headline": "Repeated checker rejection",
    }
    with repository.transaction() as connection:
        connection.execute(
            """
            INSERT INTO incident_projection (
                incident_id,
                workflow_id,
                node_id,
                ticket_id,
                provider_id,
                incident_type,
                status,
                severity,
                fingerprint,
                circuit_breaker_state,
                opened_at,
                closed_at,
                payload_json,
                updated_at,
                version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                incident_id,
                workflow_id,
                "node_history_incident",
                ticket_id,
                None,
                "REPEATED_FAILURE_ESCALATION",
                "OPEN",
                "high",
                f"{workflow_id}:history:fingerprint",
                "OPEN",
                "2026-03-27T10:20:00+08:00",
                None,
                json.dumps(payload, sort_keys=True),
                "2026-03-27T10:20:00+08:00",
                1,
            ),
        )


def test_build_compile_request_translates_runtime_inputs(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    repository = client.app.state.repository
    _seed_governance_profile(repository, workflow_id="wf_compile")
    ticket = repository.get_current_ticket_projection("tkt_compile_001")

    compile_request = build_compile_request(repository, ticket)

    assert compile_request.meta.ticket_id == "tkt_compile_001"
    assert compile_request.meta.workflow_id == "wf_compile"
    assert compile_request.meta.tenant_id == "tenant_default"
    assert compile_request.meta.workspace_id == "ws_default"
    assert compile_request.worker_binding.lease_owner == "emp_frontend_2"
    assert compile_request.worker_binding.employee_role_type == "frontend_engineer"
    assert compile_request.worker_binding.tenant_id == "tenant_default"
    assert compile_request.worker_binding.workspace_id == "ws_default"
    assert compile_request.worker_binding.skill_profile["system_scope"] == "delivery_slice"
    assert compile_request.worker_binding.personality_profile["risk_posture"] == "assertive"
    assert compile_request.worker_binding.aesthetic_profile["surface_preference"] == "functional"
    assert compile_request.budget_policy.max_input_tokens == 3000
    assert compile_request.budget_policy.overflow_policy == "FAIL_CLOSED"
    assert compile_request.meta.governance_profile_ref == "gp_compile_runtime"
    assert [source.source_ref for source in compile_request.explicit_sources] == [
        build_artifact_process_asset_ref("art://inputs/brief.md"),
        build_artifact_process_asset_ref("art://inputs/brand-guide.md"),
    ]
    assert compile_request.execution.allowed_write_set == ["artifacts/ui/homepage/*"]
    assert compile_request.governance.timeout_sla_sec == 1800


def test_build_compile_request_includes_cross_workflow_retrieval_plan(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    repository = client.app.state.repository
    _seed_governance_profile(repository, workflow_id="wf_compile")
    ticket = repository.get_current_ticket_projection("tkt_compile_001")

    compile_request = build_compile_request(repository, ticket)

    assert compile_request.retrieval_plan.scope_tenant_id == "tenant_default"
    assert compile_request.retrieval_plan.scope_workspace_id == "ws_default"
    assert compile_request.retrieval_plan.exclude_workflow_id == "wf_compile"
    assert compile_request.retrieval_plan.normalized_terms == [
        "approved",
        "brand",
        "direction",
        "homepage",
    ]
    assert compile_request.retrieval_plan.max_hits_by_channel == {
        "review_summaries": 2,
        "incident_summaries": 2,
        "artifact_summaries": 3,
    }


def test_compile_execution_package_builds_minimal_worker_input(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    repository = client.app.state.repository
    _seed_governance_profile(repository, workflow_id="wf_compile")
    ticket = repository.get_current_ticket_projection("tkt_compile_001")
    compile_request = build_compile_request(repository, ticket)

    compiled_package = compile_execution_package(compile_request)

    assert compiled_package.meta.ticket_id == "tkt_compile_001"
    assert compiled_package.meta.lease_owner == "emp_frontend_2"
    assert compiled_package.meta.tenant_id == "tenant_default"
    assert compiled_package.meta.workspace_id == "ws_default"
    assert compiled_package.meta.compiler_version == MINIMAL_CONTEXT_COMPILER_VERSION
    assert compiled_package.meta.governance_profile_ref == "gp_compile_runtime"
    assert compiled_package.compiled_role.role_profile_ref == "frontend_engineer_primary"
    assert compiled_package.compiled_role.employee_role_type == "frontend_engineer"
    assert compiled_package.compiled_role.persona_summary.startswith("Skill frontend")
    assert compiled_package.compiled_constraints.constraints_ref == "global_constraints_v3"
    assert compiled_package.compiled_constraints.global_rules == []
    assert compiled_package.governance_mode_slice.governance_profile_ref == "gp_compile_runtime"
    assert compiled_package.governance_mode_slice.approval_mode == "AUTO_CEO"
    assert compiled_package.governance_mode_slice.audit_mode == "MINIMAL"
    assert compiled_package.required_doc_surfaces == []
    assert compiled_package.task_frame.task_category == "review"
    assert compiled_package.context_layer_summary.w0_constitution.governance_profile_ref == "gp_compile_runtime"
    assert compiled_package.context_layer_summary.w3_runtime_guard.allowed_tool_count == 2
    assert compiled_package.skill_binding is not None
    assert compiled_package.skill_binding.resolved_skill_ids == ["review"]
    assert compiled_package.org_context.upstream_provider is None
    assert compiled_package.org_context.downstream_reviewer is not None
    assert compiled_package.org_context.downstream_reviewer.ticket_id == "tkt_compile_001"
    assert compiled_package.org_context.downstream_reviewer.role_profile_ref == "checker_primary"
    assert compiled_package.org_context.downstream_reviewer.role_type == "checker"
    assert compiled_package.org_context.collaborators == []
    assert compiled_package.org_context.escalation_path.current_blocking_reason is None
    assert compiled_package.org_context.responsibility_boundary.delivery_stage is None
    assert compiled_package.org_context.responsibility_boundary.output_schema_ref == "ui_milestone_review"
    assert compiled_package.org_context.responsibility_boundary.allowed_write_set == [
        "artifacts/ui/homepage/*"
    ]
    assert compiled_package.org_context.responsibility_boundary.board_review_possible is False
    assert compiled_package.org_context.responsibility_boundary.incident_path_possible is True
    assert compiled_package.execution.output_schema_ref == "ui_milestone_review"
    assert compiled_package.execution.allowed_tools == ["read_artifact", "write_artifact"]
    assert compiled_package.governance.retry_budget == 1
    assert compiled_package.atomic_context_bundle.token_budget == 3000
    assert [block.source_ref for block in compiled_package.atomic_context_bundle.context_blocks] == [
        "art://inputs/brief.md",
        "art://inputs/brand-guide.md",
    ]
    assert all(
        block.content_type == "SOURCE_DESCRIPTOR"
        for block in compiled_package.atomic_context_bundle.context_blocks
    )
    assert compiled_package.rendered_execution_payload.messages[0].content_payload["role_profile"]["persona_summary"].startswith(
        "Skill frontend"
    )
    assert (
        compiled_package.rendered_execution_payload.messages[0].content_payload["governance_mode_slice"][
            "governance_profile_ref"
        ]
        == "gp_compile_runtime"
    )
    assert (
        compiled_package.rendered_execution_payload.messages[0].content_payload["skill_binding"]["resolved_skill_ids"]
        == ["review"]
    )
    assert (
        compiled_package.rendered_execution_payload.messages[0].content_payload["organization_context"]
        == compiled_package.org_context.model_dump(mode="json")
    )


def test_build_compile_request_rejects_missing_governance_profile(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_compile_001")

    with pytest.raises(ValueError, match="GovernanceProfile"):
        build_compile_request(repository, ticket)


def test_compile_execution_package_builds_dynamic_org_context_for_parent_child_and_siblings(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            ticket_id="tkt_parent_001",
            node_id="node_parent_001",
            role_profile_ref="ui_designer_primary",
            output_schema_ref="consensus_document",
            allowed_write_set=["artifacts/ui/scope/*"],
        ),
    )
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            ticket_id="tkt_compile_001",
            node_id="node_compile_001",
            parent_ticket_id="tkt_parent_001",
            delivery_stage="BUILD",
        ),
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            ticket_id="tkt_check_001",
            node_id="node_check_001",
            parent_ticket_id="tkt_compile_001",
            role_profile_ref="checker_primary",
            output_schema_ref="delivery_check_report",
            delivery_stage="CHECK",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            ticket_id="tkt_sibling_001",
            node_id="node_sibling_001",
            parent_ticket_id="tkt_parent_001",
            role_profile_ref="checker_primary",
            output_schema_ref="delivery_check_report",
            delivery_stage="CHECK",
        ),
    )

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_compile_001")
    compile_request = build_compile_request(repository, ticket)
    compiled_package = compile_execution_package(compile_request)
    org_context = compiled_package.org_context

    assert org_context.upstream_provider is not None
    assert org_context.upstream_provider.ticket_id == "tkt_parent_001"
    assert org_context.upstream_provider.node_id == "node_parent_001"
    assert org_context.upstream_provider.role_profile_ref == "ui_designer_primary"
    assert org_context.upstream_provider.role_type == "frontend_engineer"
    assert org_context.downstream_reviewer is not None
    assert org_context.downstream_reviewer.ticket_id == "tkt_check_001"
    assert org_context.downstream_reviewer.node_id == "node_check_001"
    assert org_context.downstream_reviewer.role_profile_ref == "checker_primary"
    assert org_context.downstream_reviewer.role_type == "checker"
    assert [item.ticket_id for item in org_context.collaborators] == ["tkt_sibling_001"]
    assert org_context.collaborators[0].node_id == "node_sibling_001"
    assert org_context.collaborators[0].relation_reason == "ACTIVE_SIBLING_TICKET"
    assert org_context.escalation_path.path == ["retry", "retry", "escalate_ceo"]
    assert org_context.responsibility_boundary.delivery_stage == "BUILD"
    assert org_context.responsibility_boundary.allowed_write_set == ["artifacts/ui/homepage/*"]


def test_compile_execution_package_maps_new_runtime_live_role_types_in_org_context(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-04-08T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            ticket_id="tkt_architect_parent",
            node_id="node_architect_parent",
            role_profile_ref="architect_primary",
            output_schema_ref="architecture_brief",
            allowed_write_set=["reports/governance/*"],
            input_artifact_refs=[],
        ),
    )
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            ticket_id="tkt_backend_current",
            node_id="node_backend_current",
            parent_ticket_id="tkt_architect_parent",
            role_profile_ref="backend_engineer_primary",
            output_schema_ref="source_code_delivery",
            delivery_stage="BUILD",
            input_artifact_refs=[],
        ),
    )
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            ticket_id="tkt_platform_sibling",
            node_id="node_platform_sibling",
            parent_ticket_id="tkt_architect_parent",
            role_profile_ref="platform_sre_primary",
            output_schema_ref="source_code_delivery",
            delivery_stage="BUILD",
            input_artifact_refs=[],
        ),
    )
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            ticket_id="tkt_backend_current",
            node_id="node_backend_current",
        ),
    )

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_backend_current")
    compile_request = build_compile_request(repository, ticket)
    compiled_package = compile_execution_package(compile_request)
    org_context = compiled_package.org_context

    assert org_context.upstream_provider is not None
    assert org_context.upstream_provider.role_profile_ref == "architect_primary"
    assert org_context.upstream_provider.role_type == "governance_architect"
    assert org_context.downstream_reviewer is not None
    assert org_context.downstream_reviewer.role_profile_ref == "checker_primary"
    assert org_context.downstream_reviewer.role_type == "checker"
    assert [item.ticket_id for item in org_context.collaborators] == ["tkt_platform_sibling"]
    assert org_context.collaborators[0].role_profile_ref == "platform_sre_primary"
    assert org_context.collaborators[0].role_type == "platform_sre"


def test_compile_execution_package_includes_indexed_artifact_access_descriptors(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    artifact_ref = "art://inputs/brief.md"
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(input_artifact_refs=[artifact_ref]),
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    repository = client.app.state.repository
    artifact_store = client.app.state.artifact_store
    materialized = artifact_store.materialize_text("artifacts/inputs/brief.md", "# Brief\n\nMaterialized input.\n")
    with repository.transaction() as connection:
        repository.save_artifact_record(
            connection,
            artifact_ref=artifact_ref,
            workflow_id="wf_seed_inputs",
            ticket_id="tkt_seed_inputs",
            node_id="node_seed_inputs",
            logical_path="artifacts/inputs/brief.md",
            kind="MARKDOWN",
            media_type="text/markdown",
            materialization_status="MATERIALIZED",
            lifecycle_status="ACTIVE",
            storage_relpath=materialized.storage_relpath,
            content_hash=materialized.content_hash,
            size_bytes=materialized.size_bytes,
            retention_class="PERSISTENT",
            expires_at=None,
            deleted_at=None,
            deleted_by=None,
            delete_reason=None,
            created_at=datetime.fromisoformat("2026-03-28T10:00:00+08:00"),
        )

    ticket = repository.get_current_ticket_projection("tkt_compile_001")
    compile_request = build_compile_request(repository, ticket)
    compiled_package = compile_execution_package(compile_request)
    content_payload = compiled_package.atomic_context_bundle.context_blocks[0].content_payload
    artifact_access = content_payload["artifact_access"]

    assert content_payload["artifact_ref"] == artifact_ref
    assert artifact_access["logical_path"] == "artifacts/inputs/brief.md"
    assert artifact_access["media_type"] == "text/markdown"
    assert artifact_access["materialization_status"] == "MATERIALIZED"
    assert artifact_access["lifecycle_status"] == "ACTIVE"
    assert artifact_access["content_hash"] == materialized.content_hash
    assert artifact_access["size_bytes"] == materialized.size_bytes
    assert "/api/v1/artifacts/content" in artifact_access["content_url"]
    assert "/api/v1/artifacts/preview" in artifact_access["preview_url"]


def test_compile_execution_package_inlines_materialized_markdown_and_json_sources(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            input_artifact_refs=[
                "art://inputs/brief.md",
                "art://inputs/spec.json",
            ]
        ),
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    _seed_artifact(
        client,
        artifact_ref="art://inputs/brief.md",
        logical_path="artifacts/inputs/brief.md",
        kind="MARKDOWN",
        media_type="text/markdown",
        content_text="# Brief\n\nInline me.\n",
    )
    _seed_artifact(
        client,
        artifact_ref="art://inputs/spec.json",
        logical_path="artifacts/inputs/spec.json",
        kind="JSON",
        media_type="application/json",
        content_json={"goal": "Ship homepage", "constraints": ["Keep it local"]},
    )

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_compile_001")
    compile_request = build_compile_request(repository, ticket)

    compiled_package = compile_execution_package(compile_request)
    markdown_block = compiled_package.atomic_context_bundle.context_blocks[0]
    json_block = compiled_package.atomic_context_bundle.context_blocks[1]

    assert markdown_block.content_type == "TEXT"
    assert markdown_block.content_payload["display_hint"] == "INLINE_BODY"
    assert markdown_block.content_payload["content_text"] == "# Brief\n\nInline me.\n"
    assert markdown_block.content_payload["artifact_access"]["artifact_ref"] == "art://inputs/brief.md"
    assert markdown_block.content_payload["artifact_access"]["display_hint"] == "INLINE_BODY"

    assert json_block.content_type == "JSON"
    assert json_block.content_payload["display_hint"] == "INLINE_BODY"
    assert json_block.content_payload["content_json"] == {
        "goal": "Ship homepage",
        "constraints": ["Keep it local"],
    }
    assert json_block.content_payload["artifact_access"]["artifact_ref"] == "art://inputs/spec.json"
    assert json_block.content_payload["artifact_access"]["display_hint"] == "INLINE_BODY"


def test_compile_execution_package_marks_image_artifact_as_media_reference_only(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(input_artifact_refs=["art://inputs/mock.png"]),
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    _seed_artifact(
        client,
        artifact_ref="art://inputs/mock.png",
        logical_path="artifacts/inputs/mock.png",
        kind="IMAGE",
        media_type="image/png",
        content_bytes=b"\x89PNG\r\n\x1a\nmock-image",
    )

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_compile_001")
    compile_request = build_compile_request(repository, ticket)

    compiled_artifacts = compile_audit_artifacts(compile_request)
    block = compiled_artifacts.compiled_execution_package.atomic_context_bundle.context_blocks[0]
    source_log = compiled_artifacts.compile_manifest.source_log[0]

    assert block.content_type == "SOURCE_DESCRIPTOR"
    assert block.content_mode == "REFERENCE_ONLY"
    assert block.degradation_reason_code == "MEDIA_REFERENCE_ONLY"
    assert block.content_payload["display_hint"] == "OPEN_PREVIEW_URL"
    assert block.content_payload["artifact_access"]["kind"] == "IMAGE"
    assert block.content_payload["artifact_access"]["preview_kind"] == "INLINE_MEDIA"
    assert block.content_payload["artifact_access"]["display_hint"] == "OPEN_PREVIEW_URL"
    assert source_log.reason_code == "MEDIA_REFERENCE_ONLY"


def test_compile_execution_package_marks_pdf_artifact_as_media_reference_only(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(input_artifact_refs=["art://inputs/spec.pdf"]),
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    _seed_artifact(
        client,
        artifact_ref="art://inputs/spec.pdf",
        logical_path="artifacts/inputs/spec.pdf",
        kind="PDF",
        media_type="application/pdf",
        content_bytes=b"%PDF-1.7 mock pdf",
    )

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_compile_001")
    compile_request = build_compile_request(repository, ticket)

    compiled_artifacts = compile_audit_artifacts(compile_request)
    block = compiled_artifacts.compiled_execution_package.atomic_context_bundle.context_blocks[0]
    source_log = compiled_artifacts.compile_manifest.source_log[0]

    assert block.content_type == "SOURCE_DESCRIPTOR"
    assert block.content_mode == "REFERENCE_ONLY"
    assert block.degradation_reason_code == "MEDIA_REFERENCE_ONLY"
    assert block.content_payload["display_hint"] == "OPEN_PREVIEW_URL"
    assert block.content_payload["artifact_access"]["kind"] == "PDF"
    assert block.content_payload["artifact_access"]["preview_kind"] == "INLINE_MEDIA"
    assert block.content_payload["artifact_access"]["display_hint"] == "OPEN_PREVIEW_URL"
    assert source_log.reason_code == "MEDIA_REFERENCE_ONLY"


def test_compile_execution_package_marks_zip_artifact_as_binary_reference_only(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(input_artifact_refs=["art://inputs/archive.zip"]),
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    _seed_artifact(
        client,
        artifact_ref="art://inputs/archive.zip",
        logical_path="artifacts/inputs/archive.zip",
        kind="BINARY",
        media_type="application/zip",
        content_bytes=b"PK\x03\x04mock-zip",
    )

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_compile_001")
    compile_request = build_compile_request(repository, ticket)

    compiled_artifacts = compile_audit_artifacts(compile_request)
    block = compiled_artifacts.compiled_execution_package.atomic_context_bundle.context_blocks[0]
    source_log = compiled_artifacts.compile_manifest.source_log[0]

    assert block.content_type == "SOURCE_DESCRIPTOR"
    assert block.content_mode == "REFERENCE_ONLY"
    assert block.degradation_reason_code == "BINARY_REFERENCE_ONLY"
    assert block.content_payload["display_hint"] == "DOWNLOAD_ATTACHMENT"
    assert block.content_payload["artifact_access"]["kind"] == "BINARY"
    assert block.content_payload["artifact_access"]["preview_kind"] == "DOWNLOAD_ONLY"
    assert block.content_payload["artifact_access"]["display_hint"] == "DOWNLOAD_ATTACHMENT"
    assert source_log.reason_code == "BINARY_REFERENCE_ONLY"


def test_compile_audit_artifacts_falls_back_to_descriptor_when_source_exceeds_budget(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json={
                **_ticket_create_payload(input_artifact_refs=["art://inputs/brief.md"]),
                "context_query_plan": {
                    "keywords": ["homepage"],
                    "semantic_queries": ["approved direction"],
                    "max_context_tokens": 250,
                },
                "acceptance_criteria": ["Must preserve structured result integrity."],
            },
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    _seed_artifact(
        client,
        artifact_ref="art://inputs/brief.md",
        logical_path="artifacts/inputs/brief.md",
        kind="TEXT",
        media_type="text/plain",
        content_text="Neutral source content without keyword matches. " * 40,
    )

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_compile_001")
    compile_request = build_compile_request(repository, ticket)

    compiled_artifacts = compile_audit_artifacts(compile_request)
    block = compiled_artifacts.compiled_execution_package.atomic_context_bundle.context_blocks[0]
    source_log = compiled_artifacts.compile_manifest.source_log[0]

    assert block.content_type == "SOURCE_DESCRIPTOR"
    assert block.content_mode == "REFERENCE_ONLY"
    assert block.degradation_reason_code == "INLINE_BUDGET_EXCEEDED"
    assert block.content_payload["display_hint"] == "OPEN_CONTENT_URL"
    assert block.content_payload["artifact_access"]["artifact_ref"] == "art://inputs/brief.md"
    assert block.content_payload["artifact_access"]["display_hint"] == "OPEN_CONTENT_URL"
    assert "content_text" not in block.content_payload
    assert compiled_artifacts.compile_manifest.degradation.is_degraded is True
    assert any("token budget" in warning.lower() for warning in compiled_artifacts.compile_manifest.degradation.warnings)
    assert source_log.status == "TRUNCATED"
    assert source_log.reason_code == "INLINE_BUDGET_EXCEEDED"
    assert "token budget" in (source_log.reason or "").lower()
    assert compiled_artifacts.compile_manifest.budget_actual.final_bundle_tokens <= 250
    assert compiled_artifacts.compile_manifest.budget_actual.truncated_tokens > 0
    assert compiled_artifacts.compile_manifest.final_bundle_stats.reference_block_count == 1
    assert compiled_artifacts.compile_manifest.final_bundle_stats.hydrated_block_count == 0
    assert compiled_artifacts.compile_manifest.final_bundle_stats.partially_hydrated_block_count == 0


def test_compile_audit_artifacts_keeps_multiple_large_sources_within_budget_when_partial_previews_would_overflow(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json={
            **_ticket_create_payload(
                input_artifact_refs=["art://inputs/brief.md", "art://inputs/brand-guide.md"]
            ),
            "context_query_plan": {
                "keywords": ["homepage"],
                "semantic_queries": ["approved direction"],
                "max_context_tokens": 470,
            },
            "acceptance_criteria": ["Must preserve structured result integrity."],
        },
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    filler = "Neutral source content without keyword matches. " * 40
    _seed_artifact(
        client,
        artifact_ref="art://inputs/brief.md",
        logical_path="artifacts/inputs/brief.md",
        kind="TEXT",
        media_type="text/plain",
        content_text=filler,
    )
    _seed_artifact(
        client,
        artifact_ref="art://inputs/brand-guide.md",
        logical_path="artifacts/inputs/brand-guide.md",
        kind="TEXT",
        media_type="text/plain",
        content_text=filler,
    )

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_compile_001")
    compile_request = build_compile_request(repository, ticket)

    compiled_artifacts = compile_audit_artifacts(compile_request)
    blocks = compiled_artifacts.compiled_execution_package.atomic_context_bundle.context_blocks
    manifest = compiled_artifacts.compile_manifest

    assert [block.content_mode for block in blocks] == ["REFERENCE_ONLY", "REFERENCE_ONLY"]
    assert manifest.budget_plan.total_budget_tokens == 470
    assert manifest.budget_actual.final_bundle_tokens <= 470
    assert manifest.budget_actual.used_p1 == manifest.budget_actual.final_bundle_tokens
    assert manifest.budget_actual.truncated_tokens > 0
    assert manifest.final_bundle_stats.reference_block_count == 2
    assert [entry.status for entry in manifest.source_log[:2]] == ["TRUNCATED", "TRUNCATED"]


def test_compile_audit_artifacts_fails_closed_when_mandatory_source_descriptor_exceeds_budget(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json={
            **_ticket_create_payload(input_artifact_refs=["art://inputs/brief.md"]),
            "context_query_plan": {
                "keywords": ["homepage"],
                "semantic_queries": ["approved direction"],
                "max_context_tokens": 1,
            },
        },
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    _seed_artifact(
        client,
        artifact_ref="art://inputs/brief.md",
        logical_path="artifacts/inputs/brief.md",
        kind="MARKDOWN",
        media_type="text/markdown",
        content_text="# Brief\n\nThis source cannot fit even as a descriptor under the tiny budget.\n",
    )

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_compile_001")
    compile_request = build_compile_request(repository, ticket)

    with pytest.raises(ValueError, match="art://inputs/brief.md"):
        compile_audit_artifacts(compile_request)


def test_compile_request_records_structured_reason_for_deleted_artifact(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(input_artifact_refs=["art://inputs/deleted.md"]),
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    _seed_artifact(
        client,
        artifact_ref="art://inputs/deleted.md",
        logical_path="artifacts/inputs/deleted.md",
        kind="MARKDOWN",
        media_type="text/markdown",
        content_text="# Deleted\n\nShould not be readable.\n",
        lifecycle_status="DELETED",
        deleted_at="2026-03-28T10:05:00+08:00",
        deleted_by="ops@example.com",
        delete_reason="cleanup",
    )

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_compile_001")
    compile_request = build_compile_request(repository, ticket)
    compiled_artifacts = compile_audit_artifacts(compile_request)
    block = compiled_artifacts.compiled_execution_package.atomic_context_bundle.context_blocks[0]
    source_log = compiled_artifacts.compile_manifest.source_log[0]

    assert compile_request.explicit_sources[0].inline_fallback_reason_code == "ARTIFACT_NOT_READABLE"
    assert block.content_mode == "REFERENCE_ONLY"
    assert block.degradation_reason_code == "ARTIFACT_NOT_READABLE"
    assert source_log.reason_code == "ARTIFACT_NOT_READABLE"


def test_compile_audit_artifacts_builds_partial_text_preview_when_source_exceeds_budget(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json={
            **_ticket_create_payload(input_artifact_refs=["art://inputs/notes.txt"]),
            "context_query_plan": {
                "keywords": ["homepage"],
                "semantic_queries": ["approved direction"],
                "max_context_tokens": 400,
            },
            "acceptance_criteria": ["Must preserve structured result integrity."],
        },
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    _seed_artifact(
        client,
        artifact_ref="art://inputs/notes.txt",
        logical_path="artifacts/inputs/notes.txt",
        kind="TEXT",
        media_type="text/plain",
        content_text="Neutral source content without keyword matches. " * 40,
    )

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_compile_001")
    compile_request = build_compile_request(repository, ticket)

    compiled_artifacts = compile_audit_artifacts(compile_request)
    block = compiled_artifacts.compiled_execution_package.atomic_context_bundle.context_blocks[0]
    source_log = compiled_artifacts.compile_manifest.source_log[0]

    assert block.content_type == "TEXT"
    assert block.content_mode == "INLINE_PARTIAL"
    assert block.degradation_reason_code == "INLINE_BUDGET_EXCEEDED"
    assert block.content_payload["content_truncated"] is True
    assert "Neutral source content" in block.content_payload["content_text"]
    assert block.content_payload["content_preview_strategy"] == "HEAD_EXCERPT"
    assert source_log.status == "TRUNCATED"
    assert source_log.reason_code == "INLINE_BUDGET_EXCEEDED"
    assert compiled_artifacts.compile_manifest.budget_actual.final_bundle_tokens <= 400
    assert compiled_artifacts.compile_manifest.budget_actual.truncated_tokens > 0


def test_compile_audit_artifacts_builds_markdown_fragment_when_budget_fits_section_excerpt(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json={
            **_ticket_create_payload(input_artifact_refs=["art://inputs/brief.md"]),
                "context_query_plan": {
                    "keywords": ["acceptance", "output", "review"],
                    "semantic_queries": ["contract risk"],
                    "max_context_tokens": 500,
                },
            "acceptance_criteria": ["Must keep acceptance contract and review risk explicit."],
        },
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    _seed_artifact(
        client,
        artifact_ref="art://inputs/brief.md",
        logical_path="artifacts/inputs/brief.md",
        kind="MARKDOWN",
        media_type="text/markdown",
        content_text=(
            "# Intro\n\n"
            + ("This introduction is intentionally verbose and non-actionable. " * 20)
            + "\n\n## Acceptance Contract\n\n"
            "This section defines the output contract, review path, and risk reminders.\n\n"
            "## Delivery Notes\n\nShip the homepage option with explicit review evidence.\n"
        ),
    )

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_compile_001")
    compile_request = build_compile_request(repository, ticket)

    compiled_artifacts = compile_audit_artifacts(compile_request)
    block = compiled_artifacts.compiled_execution_package.atomic_context_bundle.context_blocks[0]
    source_log = compiled_artifacts.compile_manifest.source_log[0]

    assert block.content_type == "TEXT"
    assert block.content_mode == "INLINE_FRAGMENT"
    assert block.selector.selector_type == "MARKDOWN_SECTION"
    assert "Acceptance Contract" in block.selector.selector_value
    assert block.content_payload["content_fragment_strategy"] == "MARKDOWN_SECTION_MATCH"
    assert block.content_payload["selected_sections"] == ["Acceptance Contract", "Delivery Notes"]
    assert "## Acceptance Contract" in block.content_payload["content_text"]
    assert source_log.status == "SUMMARIZED"
    assert source_log.selector_used.startswith("MARKDOWN_SECTION:")


def test_compile_audit_artifacts_builds_text_fragment_windows_when_budget_fits_keyword_windows(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json={
            **_ticket_create_payload(input_artifact_refs=["art://inputs/notes.txt"]),
                "context_query_plan": {
                    "keywords": ["review", "risk", "brand"],
                    "semantic_queries": ["output contract"],
                    "max_context_tokens": 500,
                },
        },
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    _seed_artifact(
        client,
        artifact_ref="art://inputs/notes.txt",
        logical_path="artifacts/inputs/notes.txt",
        kind="TEXT",
        media_type="text/plain",
        content_text=(
            ("General project background that does not help execution. " * 24)
            + "\nREVIEW WINDOW: Keep the homepage brand direction aligned with the approved review path.\n"
            + ("Neutral filler. " * 12)
            + "\nRISK WINDOW: Preserve the output contract and do not hide blocking review risk.\n"
        ),
    )

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_compile_001")
    compile_request = build_compile_request(repository, ticket)

    compiled_artifacts = compile_audit_artifacts(compile_request)
    block = compiled_artifacts.compiled_execution_package.atomic_context_bundle.context_blocks[0]
    source_log = compiled_artifacts.compile_manifest.source_log[0]

    assert block.content_type == "TEXT"
    assert block.content_mode == "INLINE_FRAGMENT"
    assert block.selector.selector_type == "TEXT_WINDOW"
    assert block.content_payload["content_fragment_strategy"] == "TEXT_KEYWORD_WINDOWS"
    assert len(block.content_payload["selected_windows"]) >= 2
    assert "REVIEW WINDOW" in block.content_payload["content_text"]
    assert "RISK WINDOW" in block.content_payload["content_text"]
    assert source_log.status == "SUMMARIZED"
    assert source_log.selector_used.startswith("TEXT_WINDOW:")


def test_compile_audit_artifacts_builds_json_fragment_paths_when_budget_fits_relevant_subtrees(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json={
            **_ticket_create_payload(input_artifact_refs=["art://inputs/spec.json"]),
                "context_query_plan": {
                    "keywords": ["hero", "contract", "risk"],
                    "semantic_queries": ["review output"],
                    "max_context_tokens": 500,
                },
        },
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    _seed_artifact(
        client,
        artifact_ref="art://inputs/spec.json",
        logical_path="artifacts/inputs/spec.json",
        kind="JSON",
        media_type="application/json",
        content_json={
            "intro": "Background " * 80,
            "sections": {
                "hero": {
                    "headline": "Boardroom OS",
                    "summary": "Keep the hero aligned with the approved review direction.",
                },
                "secondary": {
                    "headline": "Archive",
                    "summary": "Secondary supporting panel.",
                },
            },
            "output_contract": {
                "schema": "ui_milestone_review",
                "must_include": ["options", "risks", "rationale"],
            },
            "risk_summary": {
                "headline": "Do not hide approval risk.",
                "level": "medium",
            },
        },
    )

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_compile_001")
    compile_request = build_compile_request(repository, ticket)

    compiled_artifacts = compile_audit_artifacts(compile_request)
    block = compiled_artifacts.compiled_execution_package.atomic_context_bundle.context_blocks[0]
    source_log = compiled_artifacts.compile_manifest.source_log[0]

    assert block.content_type == "JSON"
    assert block.content_mode == "INLINE_FRAGMENT"
    assert block.selector.selector_type == "JSON_PATH"
    assert block.content_payload["content_fragment_strategy"] == "JSON_PATH_MATCH"
    assert block.content_payload["selected_json_paths"] == [
        "$.output_contract",
        "$.risk_summary",
        "$.sections.hero",
    ]
    assert block.content_payload["content_json"]["output_contract"]["schema"] == "ui_milestone_review"
    assert block.content_payload["content_json"]["sections"]["hero"]["headline"] == "Boardroom OS"
    assert source_log.status == "SUMMARIZED"
    assert source_log.selector_used.startswith("JSON_PATH:")


def test_compile_audit_artifacts_fails_closed_when_fragment_and_descriptor_still_exceed_budget(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json={
            **_ticket_create_payload(input_artifact_refs=["art://inputs/brief.md"]),
            "context_query_plan": {
                "keywords": ["acceptance", "output", "review"],
                "semantic_queries": ["contract risk"],
                "max_context_tokens": 30,
            },
        },
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    _seed_artifact(
        client,
        artifact_ref="art://inputs/brief.md",
        logical_path="artifacts/inputs/brief.md",
        kind="MARKDOWN",
        media_type="text/markdown",
        content_text=(
            "# Intro\n\n"
            + ("This introduction is intentionally verbose and non-actionable. " * 20)
            + "\n\n## Acceptance Contract\n\n"
            "This section defines the output contract, review path, and risk reminders.\n"
        ),
    )

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_compile_001")
    compile_request = build_compile_request(repository, ticket)

    with pytest.raises(ValueError, match="art://inputs/brief.md"):
        compile_audit_artifacts(compile_request)


def test_compile_audit_artifacts_build_bundle_manifest_and_execution_package(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_compile_001")
    compile_request = build_compile_request(repository, ticket)

    compiled_artifacts = compile_audit_artifacts(compile_request)
    bundle = compiled_artifacts.compiled_context_bundle
    manifest = compiled_artifacts.compile_manifest
    compiled_package = compiled_artifacts.compiled_execution_package

    assert bundle.meta.compile_request_id == compile_request.meta.compile_request_id
    assert bundle.meta.compiler_version == MINIMAL_CONTEXT_COMPILER_VERSION
    assert bundle.meta.is_degraded is True
    assert bundle.system_controls.output_contract.schema_ref == "ui_milestone_review"
    assert bundle.context_blocks[0].source_kind == "PROCESS_ASSET"
    assert bundle.context_blocks[0].selector.selector_type == "SOURCE_REF"
    assert bundle.context_blocks[0].transform_chain == ["NORMALIZE_REFERENCE_DESCRIPTOR"]
    assert bundle.context_blocks[0].trust_note
    assert manifest.compile_meta.bundle_id == bundle.meta.bundle_id
    assert manifest.compile_meta.compile_request_id == compile_request.meta.compile_request_id
    assert manifest.source_log[0].status == "USED"
    assert manifest.source_log[0].selector_used == "SOURCE_REF:art://inputs/brief.md"
    assert manifest.transform_log[0].operation_type == "NORMALIZE"
    assert manifest.degradation.is_degraded is True
    assert manifest.budget_actual.final_bundle_tokens > 0
    assert compiled_package.meta.compile_request_id == compile_request.meta.compile_request_id
    assert compiled_package.atomic_context_bundle.context_blocks[0].block_id == bundle.context_blocks[0].block_id
    assert compiled_package.rendered_execution_payload.meta.render_target == "json_messages_v1"


def test_compile_audit_artifacts_builds_rendered_execution_payload_with_stable_channel_order(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_compile_001")
    compile_request = build_compile_request(repository, ticket)

    compiled_artifacts = compile_audit_artifacts(compile_request)
    compiled_package = compiled_artifacts.compiled_execution_package
    rendered_payload = compiled_package.rendered_execution_payload

    assert rendered_payload.meta.render_target == "json_messages_v1"
    assert [message.channel for message in rendered_payload.messages[:2]] == [
        "SYSTEM_CONTROLS",
        "TASK_DEFINITION",
    ]
    assert [message.channel for message in rendered_payload.messages[2:-1]] == [
        "CONTEXT_BLOCK"
        for _ in compiled_package.atomic_context_bundle.context_blocks
    ]
    assert rendered_payload.messages[-1].channel == "OUTPUT_CONTRACT_REMINDER"
    assert rendered_payload.messages[0].role == "system"
    assert rendered_payload.messages[1].role == "user"
    assert rendered_payload.summary.control_message_count == 3
    assert rendered_payload.summary.data_message_count == len(
        compiled_package.atomic_context_bundle.context_blocks
    )

    context_messages = [
        message for message in rendered_payload.messages if message.channel == "CONTEXT_BLOCK"
    ]
    assert [message.block_id for message in context_messages] == [
        block.block_id for block in compiled_package.atomic_context_bundle.context_blocks
    ]
    assert [message.source_ref for message in context_messages] == [
        block.source_ref for block in compiled_package.atomic_context_bundle.context_blocks
    ]


def test_compile_audit_artifacts_render_summary_counts_degraded_and_reference_messages(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json={
                **_ticket_create_payload(input_artifact_refs=["art://inputs/brief.md", "art://inputs/mock.png"]),
                "context_query_plan": {
                    "keywords": ["acceptance", "output", "review"],
                    "semantic_queries": ["contract risk"],
                    "max_context_tokens": 700,
                },
            },
        )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    _seed_artifact(
        client,
        artifact_ref="art://inputs/brief.md",
        logical_path="artifacts/inputs/brief.md",
        kind="MARKDOWN",
        media_type="text/markdown",
        content_text=(
            "# Intro\n\n"
            + ("This introduction is intentionally verbose and non-actionable. " * 20)
            + "\n\n## Acceptance Contract\n\n"
            "This section defines the output contract, review path, and risk reminders.\n\n"
            "## Delivery Notes\n\nShip the homepage option with explicit review evidence.\n"
        ),
    )
    _seed_artifact(
        client,
        artifact_ref="art://inputs/mock.png",
        logical_path="artifacts/inputs/mock.png",
        kind="IMAGE",
        media_type="image/png",
        content_bytes=b"\x89PNG\r\n\x1a\nmock-image",
    )

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_compile_001")
    compile_request = build_compile_request(repository, ticket)

    rendered_summary = compile_audit_artifacts(compile_request).compiled_execution_package.rendered_execution_payload.summary

    assert rendered_summary.data_message_count == 2
    assert rendered_summary.degraded_data_message_count == 2
    assert rendered_summary.reference_message_count == 1
    assert rendered_summary.retrieval_message_count == 0


def test_compile_audit_artifacts_render_output_contract_reminder_tracks_schema_ref(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json={
            **_ticket_create_payload(
                ticket_id="tkt_checker_compile_001",
                node_id="node_checker_compile_001",
                input_artifact_refs=["art://inputs/checker-brief.md"],
            ),
            "role_profile_ref": "checker_primary",
            "output_schema_ref": "maker_checker_verdict",
            "idempotency_key": "ticket-create:wf_compile:tkt_checker_compile_001",
        },
    )
    client.post(
        "/api/v1/commands/ticket-lease",
        json={
            **_ticket_lease_payload(
                ticket_id="tkt_checker_compile_001",
                node_id="node_checker_compile_001",
            ),
            "leased_by": "emp_checker_1",
            "idempotency_key": "ticket-lease:wf_compile:tkt_checker_compile_001",
        },
    )
    _seed_artifact(
        client,
        artifact_ref="art://inputs/checker-brief.md",
        logical_path="artifacts/inputs/checker-brief.md",
        kind="MARKDOWN",
        media_type="text/markdown",
        content_text="# Checker Brief\n\nReturn a structured verdict.\n",
    )

    repository = client.app.state.repository
    checker_ticket = repository.get_current_ticket_projection("tkt_checker_compile_001")
    checker_rendered_payload = compile_audit_artifacts(
        build_compile_request(repository, checker_ticket)
    ).compiled_execution_package.rendered_execution_payload

    default_ticket = repository.get_current_ticket_projection("tkt_compile_001")
    if default_ticket is None:
        client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())
        client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())
        default_ticket = repository.get_current_ticket_projection("tkt_compile_001")
    default_rendered_payload = compile_audit_artifacts(
        build_compile_request(repository, default_ticket)
    ).compiled_execution_package.rendered_execution_payload

    assert (
        checker_rendered_payload.messages[-1].content_payload["output_schema_ref"]
        == "maker_checker_verdict"
    )
    assert (
        default_rendered_payload.messages[-1].content_payload["output_schema_ref"]
        == "ui_milestone_review"
    )


def test_compile_execution_package_adds_cross_workflow_retrieval_summary_cards(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(input_artifact_refs=[]),
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    _seed_historical_review_summary(
        client,
        workflow_id="wf_history_review",
        review_pack_id="brp_history_review",
        title="Homepage review approval",
        summary="Approved homepage direction with strong brand hierarchy.",
    )
    _seed_historical_incident_summary(
        client,
        workflow_id="wf_history_incident",
        incident_id="inc_history_brand",
        ticket_id="tkt_history_brand",
        summary="Homepage run failed after checker rejected weak brand alignment.",
    )
    _seed_artifact(
        client,
        artifact_ref="art://history/homepage-notes.md",
        logical_path="reports/review/homepage-notes.md",
        kind="MARKDOWN",
        media_type="text/markdown",
        content_text="# Homepage\n\nApproved direction keeps brand visible in the hero.\n",
        workflow_id="wf_history_artifact",
        ticket_id="tkt_history_artifact",
        node_id="node_history_artifact",
    )

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_compile_001")
    compile_request = build_compile_request(repository, ticket)

    compiled_package = compile_execution_package(compile_request)
    retrieval_blocks = [
        block
        for block in compiled_package.atomic_context_bundle.context_blocks
        if block.source_kind == "RETRIEVAL"
    ]

    assert [block.content_type for block in retrieval_blocks] == ["JSON", "JSON", "JSON"]
    assert [block.content_payload["channel"] for block in retrieval_blocks] == [
        "review_summaries",
        "incident_summaries",
        "artifact_summaries",
    ]
    assert retrieval_blocks[0].content_payload["review_pack_id"] == "brp_history_review"
    assert retrieval_blocks[1].content_payload["incident_id"] == "inc_history_brand"
    assert retrieval_blocks[2].content_payload["artifact_ref"] == "art://history/homepage-notes.md"
    assert retrieval_blocks[0].content_payload["matched_terms"] == [
        "approved",
        "brand",
        "direction",
        "homepage",
    ]
    assert "matched" in retrieval_blocks[0].content_payload["why_it_matched"].lower()


def test_compile_audit_artifacts_drops_low_priority_retrieval_cards_when_budget_is_tight(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json={
            **_ticket_create_payload(input_artifact_refs=[]),
            "context_query_plan": {
                "keywords": ["homepage", "brand"],
                "semantic_queries": ["approved direction"],
                "max_context_tokens": 1000,
            },
        },
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    _seed_historical_review_summary(
        client,
        workflow_id="wf_history_review",
        review_pack_id="brp_budget_review",
        title="Budget review approval",
        summary="Approved homepage direction and clear brand hierarchy.",
    )
    _seed_historical_incident_summary(
        client,
        workflow_id="wf_history_incident",
        incident_id="inc_budget_incident",
        ticket_id="tkt_budget_incident",
        summary="Homepage work was rejected after brand guidance was ignored twice.",
    )
    _seed_artifact(
        client,
        artifact_ref="art://history/budget-notes.md",
        logical_path="reports/review/homepage-budget-notes.md",
        kind="MARKDOWN",
        media_type="text/markdown",
        content_text=(
            "# Homepage Budget\n\nThis historical homepage artifact is intentionally verbose so "
            "brand-focused artifact retrieval gets dropped before higher-value summaries under a "
            "tight token budget while still matching the retrieval terms.\n"
        ),
        workflow_id="wf_history_artifact",
        ticket_id="tkt_history_artifact",
        node_id="node_history_artifact",
    )

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_compile_001")
    compile_request = build_compile_request(repository, ticket)

    compiled_artifacts = compile_audit_artifacts(compile_request)
    retrieval_blocks = [
        block
        for block in compiled_artifacts.compiled_execution_package.atomic_context_bundle.context_blocks
        if block.source_kind == "RETRIEVAL"
    ]
    dropped_entries = [
        entry
        for entry in compiled_artifacts.compile_manifest.source_log
        if entry.reason_code == "RETRIEVAL_DROPPED_FOR_BUDGET"
    ]

    assert [block.content_payload["channel"] for block in retrieval_blocks] == [
        "review_summaries",
        "incident_summaries",
    ]
    assert [entry.source_ref for entry in dropped_entries] == ["art://history/budget-notes.md"]
    assert compiled_artifacts.compile_manifest.final_bundle_stats.retrieved_block_count == 2
    assert compiled_artifacts.compile_manifest.final_bundle_stats.dropped_retrieval_count == 1


def test_build_compile_request_converts_input_artifact_refs_to_process_asset_refs(client, set_ticket_time):
    set_ticket_time("2026-04-07T18:20:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(input_artifact_refs=["art://inputs/brief.md"]),
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_compile_001")
    compile_request = build_compile_request(repository, ticket)

    assert compile_request.execution.input_process_asset_refs == [
        build_artifact_process_asset_ref("art://inputs/brief.md")
    ]
    assert compile_request.explicit_sources[0].source_kind == "PROCESS_ASSET"
    assert compile_request.explicit_sources[0].process_asset_kind == "ARTIFACT"


def test_build_compile_request_resolves_compiled_context_bundle_process_asset(client, set_ticket_time):
    set_ticket_time("2026-04-07T18:20:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(input_artifact_refs=["art://inputs/brief.md"]),
    )
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    repository = client.app.state.repository
    source_ticket = repository.get_current_ticket_projection("tkt_compile_001")
    compile_and_persist_execution_artifacts(repository, source_ticket)

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_compile_process_assets",
            ticket_id="tkt_compile_process_assets",
            node_id="node_compile_process_assets",
            input_artifact_refs=[],
            input_process_asset_refs=[
                build_compiled_context_bundle_process_asset_ref("tkt_compile_001")
            ],
        ),
    )
    _seed_governance_profile(repository, workflow_id="wf_compile_process_assets")
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id="wf_compile_process_assets",
            ticket_id="tkt_compile_process_assets",
            node_id="node_compile_process_assets",
        ),
    )

    ticket = repository.get_current_ticket_projection("tkt_compile_process_assets")
    compile_request = build_compile_request(repository, ticket)

    assert compile_request.execution.input_process_asset_refs == [
        build_compiled_context_bundle_process_asset_ref("tkt_compile_001")
    ]
    assert compile_request.explicit_sources[0].process_asset_kind == "COMPILED_CONTEXT_BUNDLE"
    assert compile_request.explicit_sources[0].inline_content_type == "JSON"
    assert (
        compile_request.explicit_sources[0].inline_content_json["meta"]["ticket_id"]
        == "tkt_compile_001"
    )


def test_build_compile_request_resolves_governance_document_process_asset(client, set_ticket_time):
    set_ticket_time("2026-04-07T18:30:00+08:00")
    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_governance_source",
            ticket_id="tkt_gov_doc_source",
            node_id="node_gov_doc_source",
            output_schema_ref="architecture_brief",
            allowed_write_set=["artifacts/ui/homepage/*"],
            input_artifact_refs=[],
        ),
    )
    repository = client.app.state.repository
    _seed_governance_profile(repository, workflow_id="wf_governance_source")
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id="wf_governance_source",
            ticket_id="tkt_gov_doc_source",
            node_id="node_gov_doc_source",
        ),
    )
    client.post(
        "/api/v1/commands/ticket-start",
        json=_ticket_start_payload(
            workflow_id="wf_governance_source",
            ticket_id="tkt_gov_doc_source",
            node_id="node_gov_doc_source",
        ),
    )
    source_payload = _governance_document_payload("architecture_brief")
    client.post(
        "/api/v1/commands/ticket-result-submit",
        json={
            "workflow_id": "wf_governance_source",
            "ticket_id": "tkt_gov_doc_source",
            "node_id": "node_gov_doc_source",
            "submitted_by": "emp_frontend_2",
            "result_status": "completed",
            "schema_version": "architecture_brief_v1",
            "payload": source_payload,
            "artifact_refs": ["art://runtime/tkt_gov_doc_source/architecture-brief.json"],
            "written_artifacts": [
                {
                    "path": "artifacts/ui/homepage/architecture-brief.json",
                    "artifact_ref": "art://runtime/tkt_gov_doc_source/architecture-brief.json",
                    "kind": "JSON",
                    "content_json": source_payload,
                }
            ],
            "assumptions": [],
            "issues": [],
            "confidence": 0.81,
            "needs_escalation": False,
            "summary": "Structured governance document submitted.",
            "failure_kind": None,
            "failure_message": None,
            "failure_detail": None,
            "idempotency_key": "ticket-result-submit:wf_governance_source:tkt_gov_doc_source:architecture-brief",
        },
    )
    with repository.connection() as connection:
        terminal_event = repository.get_latest_ticket_terminal_event(connection, "tkt_gov_doc_source")
    produced_assets = list((terminal_event or {}).get("payload", {}).get("produced_process_assets") or [])
    assert "pa://governance-document/tkt_gov_doc_source@1" in [
        asset.get("process_asset_ref") for asset in produced_assets
    ]

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_governance_consumer",
            ticket_id="tkt_gov_doc_consumer",
            node_id="node_gov_doc_consumer",
            input_artifact_refs=[],
            input_process_asset_refs=["pa://governance-document/tkt_gov_doc_source"],
        ),
    )
    _seed_governance_profile(repository, workflow_id="wf_governance_consumer")
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id="wf_governance_consumer",
            ticket_id="tkt_gov_doc_consumer",
            node_id="node_gov_doc_consumer",
        ),
    )

    ticket = repository.get_current_ticket_projection("tkt_gov_doc_consumer")
    compile_request = build_compile_request(repository, ticket)

    assert compile_request.execution.input_process_asset_refs == [
        "pa://governance-document/tkt_gov_doc_source"
    ]
    assert compile_request.explicit_sources[0].process_asset_kind == "GOVERNANCE_DOCUMENT"
    assert compile_request.explicit_sources[0].inline_content_type == "JSON"
    assert compile_request.explicit_sources[0].inline_content_json["document_kind_ref"] == "architecture_brief"
    assert compile_request.explicit_sources[0].inline_content_json["linked_document_refs"] == [
        "doc://governance/technology-decision/current"
    ]


def test_compile_and_persist_execution_artifacts_rejects_planned_placeholder_before_materialization(client):
    workflow_id = "wf_compile_planned_placeholder"
    repository = client.app.state.repository
    api_test_helpers._ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Compile should fail closed for graph-only placeholders.",
    )
    api_test_helpers._seed_created_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_compile_placeholder_parent",
        node_id="node_compile_placeholder_parent",
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="source_code_delivery",
        delivery_stage="BUILD",
    )
    api_test_helpers._seed_graph_patch_applied_event(
        client,
        workflow_id=workflow_id,
        patch_index=1,
        freeze_node_ids=[],
        focus_node_ids=["node_compile_placeholder_target"],
        add_nodes=[
            {
                "node_id": "node_compile_placeholder_target",
                "node_kind": "IMPLEMENTATION",
                "deliverable_kind": "source_code_delivery",
                "role_hint": "frontend_engineer_primary",
                "parent_node_id": "node_compile_placeholder_parent",
                "dependency_node_ids": [],
            }
        ],
    )
    _seed_governance_profile(repository, workflow_id=workflow_id, profile_id="gp_compile_placeholder")
    placeholder_projection = repository.get_planned_placeholder_projection(
        workflow_id,
        "node_compile_placeholder_target",
    )
    assert placeholder_projection is not None
    assert placeholder_projection["status"] == "PLANNED"

    created_payload = _ticket_create_payload(
        workflow_id=workflow_id,
        ticket_id="tkt_compile_placeholder_target",
        node_id="node_compile_placeholder_target",
        input_artifact_refs=[],
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref="source_code_delivery",
        delivery_stage="BUILD",
    )
    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_TICKET_CREATED,
            actor_type="system",
            actor_id="test-seed",
            workflow_id=workflow_id,
            idempotency_key="test-compile-placeholder-ticket-created",
            causation_id=None,
            correlation_id=workflow_id,
            payload=created_payload,
            occurred_at=datetime.fromisoformat("2026-04-16T23:10:00+08:00"),
        )

    with pytest.raises(Exception) as exc_info:
        compile_and_persist_execution_artifacts(
            repository,
            {
                "ticket_id": "tkt_compile_placeholder_target",
                "workflow_id": workflow_id,
                "node_id": "node_compile_placeholder_target",
                "lease_owner": "emp_frontend_2",
                "tenant_id": "tenant_default",
                "workspace_id": "ws_default",
                "version": 1,
            },
        )

    assert getattr(exc_info.value, "reason_code", None) == "PLANNED_PLACEHOLDER_NOT_MATERIALIZED"
    assert "node_compile_placeholder_target" in str(exc_info.value)


def test_build_compile_request_auto_injects_project_map_and_failure_fingerprint_assets(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-04-15T20:30:00+08:00")
    workflow_id = "wf_compile_project_map_auto"
    api_test_helpers._ensure_scoped_workflow(
        client,
        workflow_id=workflow_id,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        goal="Compile request should auto-inject project map and failure fingerprints.",
    )

    api_test_helpers._create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_arch_project_map_auto",
        node_id="node_arch_project_map_auto",
        output_schema_ref="architecture_brief",
        allowed_write_set=["artifacts/governance/*"],
        input_artifact_refs=[],
    )
    governance_payload = _governance_document_payload("architecture_brief")
    governance_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json={
            "workflow_id": workflow_id,
            "ticket_id": "tkt_arch_project_map_auto",
            "node_id": "node_arch_project_map_auto",
            "submitted_by": "emp_frontend_2",
            "result_status": "completed",
            "schema_version": "architecture_brief_v1",
            "payload": governance_payload,
            "artifact_refs": ["art://runtime/tkt_arch_project_map_auto/architecture-brief.json"],
            "written_artifacts": [
                {
                    "path": "artifacts/governance/architecture-brief.json",
                    "artifact_ref": "art://runtime/tkt_arch_project_map_auto/architecture-brief.json",
                    "kind": "JSON",
                    "content_json": governance_payload,
                }
            ],
            "assumptions": [],
            "issues": [],
            "confidence": 0.84,
            "needs_escalation": False,
            "summary": "Governance document recorded for compile request coverage.",
            "failure_kind": None,
            "failure_message": None,
            "failure_detail": None,
            "idempotency_key": (
                f"ticket-result-submit:{workflow_id}:tkt_arch_project_map_auto:architecture"
            ),
        },
    )
    assert governance_response.status_code == 200
    assert governance_response.json()["status"] == "ACCEPTED"

    api_test_helpers._create_lease_and_start_ticket(
        client,
        workflow_id=workflow_id,
        ticket_id="tkt_build_project_map_auto",
        node_id="node_build_project_map_auto",
        output_schema_ref="source_code_delivery",
        delivery_stage="BUILD",
        allowed_write_set=["src/ui/*"],
        input_artifact_refs=[],
    )
    source_submit_payload = api_test_helpers._source_code_delivery_result_submit_payload(
        workflow_id=workflow_id,
        ticket_id="tkt_build_project_map_auto",
        node_id="node_build_project_map_auto",
        artifact_refs=["art://runtime/tkt_build_project_map_auto/source-code.ts"],
        written_artifact_path="src/ui/homepage.ts",
        idempotency_key=f"ticket-result-submit:{workflow_id}:tkt_build_project_map_auto:source",
    )
    source_submit_payload["payload"]["source_files"][0]["path"] = "src/ui/homepage.ts"
    source_submit_payload["payload"]["source_files"][0]["content"] = (
        "export function renderHomepageCard() {\n"
        "  return 'project-map-auto'\n"
        "}\n"
    )
    source_submit_payload["written_artifacts"][0]["path"] = "src/ui/homepage.ts"
    source_submit_payload["written_artifacts"][0]["content_text"] = (
        "export function renderHomepageCard() {\n"
        "  return 'project-map-auto'\n"
        "}\n"
    )
    source_submit_payload["payload"]["documentation_updates"] = [
        {
            "doc_ref": "doc://todo/project-map-auto",
            "status": "UPDATED",
            "summary": "Synced project map compile coverage.",
        }
    ]
    source_response = client.post(
        "/api/v1/commands/ticket-result-submit",
        json=source_submit_payload,
    )
    assert source_response.status_code == 200
    assert source_response.json()["status"] == "ACCEPTED"

    repository = client.app.state.repository
    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type="INCIDENT_OPENED",
            actor_type="system",
            actor_id="test-seed",
            workflow_id=workflow_id,
            idempotency_key=f"incident-opened:{workflow_id}:project-map-auto",
            causation_id=None,
            correlation_id=workflow_id,
            payload={
                "incident_id": "inc_compile_project_map_auto",
                "node_id": "node_build_project_map_auto",
                "ticket_id": "tkt_build_project_map_auto",
                "incident_type": "REPEATED_FAILURE_ESCALATION",
                "status": "OPEN",
                "severity": "high",
                "fingerprint": (
                    f"{workflow_id}:node_build_project_map_auto:"
                    "repeat-failure:compile-project-map-auto"
                ),
                "latest_failure_fingerprint": "compile-project-map-auto",
                "latest_failure_kind": "RUNTIME_TIMEOUT_ESCALATION",
            },
            occurred_at=datetime.fromisoformat("2026-04-15T20:35:00+08:00"),
        )
        repository.refresh_projections(connection)

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_consume_project_map_auto",
            node_id="node_consume_project_map_auto",
            output_schema_ref="delivery_check_report",
            input_artifact_refs=[],
        ),
    )
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id=workflow_id,
            ticket_id="tkt_consume_project_map_auto",
            node_id="node_consume_project_map_auto",
        ),
    )

    consumer_ticket = repository.get_current_ticket_projection("tkt_consume_project_map_auto")
    compile_request = build_compile_request(repository, consumer_ticket)

    assert "pa://project-map-slice/wf_compile_project_map_auto" in (
        compile_request.execution.input_process_asset_refs
    )
    assert "pa://failure-fingerprint/inc_compile_project_map_auto" in (
        compile_request.execution.input_process_asset_refs
    )
    assert any(
        source.process_asset_kind == "PROJECT_MAP_SLICE"
        for source in compile_request.explicit_sources
    )
    assert any(
        source.process_asset_kind == "FAILURE_FINGERPRINT"
        for source in compile_request.explicit_sources
    )


def test_compile_and_persist_execution_artifacts_writes_bundle_and_manifest(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_compile_001")

    compiled_artifacts = compile_and_persist_execution_artifacts(repository, ticket)
    latest_bundle = repository.get_latest_compiled_context_bundle_by_ticket("tkt_compile_001")
    latest_manifest = repository.get_latest_compile_manifest_by_ticket("tkt_compile_001")
    latest_execution_package = repository.get_latest_compiled_execution_package_by_ticket(
        "tkt_compile_001"
    )

    assert latest_bundle is not None
    assert latest_manifest is not None
    assert latest_execution_package is not None
    assert latest_bundle["bundle_id"] == compiled_artifacts.compiled_context_bundle.meta.bundle_id
    assert latest_bundle["payload"]["meta"]["bundle_id"] == latest_bundle["bundle_id"]
    assert latest_bundle["payload"]["context_blocks"][0]["source_hash"]
    assert repository.get_compiled_context_bundle(latest_bundle["bundle_id"]) is not None
    assert latest_manifest["compile_id"] == compiled_artifacts.compile_manifest.compile_meta.compile_id
    assert latest_manifest["payload"]["compile_meta"]["compile_id"] == latest_manifest["compile_id"]
    assert latest_manifest["payload"]["source_log"][0]["status"] == "USED"
    assert latest_manifest["payload"]["degradation"]["warnings"]
    assert repository.get_compile_manifest(latest_manifest["compile_id"]) is not None
    assert latest_execution_package["compile_request_id"] == (
        compiled_artifacts.compiled_execution_package.meta.compile_request_id
    )
    assert latest_execution_package["version_int"] == 1
    assert latest_execution_package["version_ref"].startswith("pkg_tkt_compile_001_1_1")
    assert latest_execution_package["payload"]["meta"]["ticket_id"] == "tkt_compile_001"
    assert latest_execution_package["payload"]["meta"]["version_int"] == 1
    assert latest_execution_package["payload"]["execution"]["output_schema_ref"] == "ui_milestone_review"
    assert latest_execution_package["payload"]["rendered_execution_payload"]["meta"]["render_target"] == (
        "json_messages_v1"
    )
    assert repository.get_compiled_execution_package(latest_execution_package["compile_request_id"]) is not None


def test_compile_and_persist_execution_artifacts_versions_compiled_execution_package(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_compile_001")

    first = compile_and_persist_execution_artifacts(repository, ticket)
    set_ticket_time("2026-03-28T10:05:00+08:00")
    second = compile_and_persist_execution_artifacts(repository, ticket)

    latest_execution_package = repository.get_latest_compiled_execution_package_by_ticket("tkt_compile_001")
    first_version = repository.get_compiled_execution_package_version(
        "tkt_compile_001",
        1,
    )

    assert first.compiled_execution_package.meta.version_int == 1
    assert first.compiled_execution_package.meta.supersedes_ref is None
    assert second.compiled_execution_package.meta.version_int == 2
    assert second.compiled_execution_package.meta.supersedes_ref == (
        first.compiled_execution_package.meta.version_ref
    )
    assert latest_execution_package is not None
    assert latest_execution_package["version_int"] == 2
    assert latest_execution_package["supersedes_ref"] == first.compiled_execution_package.meta.version_ref
    assert latest_execution_package["payload"]["meta"]["version_ref"] == (
        second.compiled_execution_package.meta.version_ref
    )
    assert first_version is not None
    assert first_version["payload"]["meta"]["version_ref"] == (
        first.compiled_execution_package.meta.version_ref
    )
    assert first.compiled_execution_package.meta.ticket_projection_version == ticket["version"]
    assert second.compiled_execution_package.meta.ticket_projection_version == ticket["version"]
    assert latest_execution_package["payload"]["meta"]["compile_request_id"] == (
        second.compiled_execution_package.meta.compile_request_id
    )
    assert latest_execution_package["payload"]["meta"]["version_ref"] == (
        second.compiled_execution_package.meta.version_ref
    )


def test_build_compile_request_captures_projection_versions(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_compile_001")
    node = repository.get_current_node_projection("wf_compile", "node_compile_001")
    assert ticket is not None
    assert node is not None

    compile_request = build_compile_request(repository, ticket)

    assert compile_request.meta.ticket_projection_version == int(ticket["version"])
    assert compile_request.meta.node_projection_version == int(node["version"])
    assert compile_request.meta.source_projection_version >= 1


def test_export_latest_compile_artifacts_to_developer_inspector_writes_real_persisted_payloads(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    repository = client.app.state.repository
    developer_inspector_store = client.app.state.developer_inspector_store
    ticket = repository.get_current_ticket_projection("tkt_compile_001")

    compiled_artifacts = compile_and_persist_execution_artifacts(repository, ticket)
    persisted = export_latest_compile_artifacts_to_developer_inspector(
        repository,
        developer_inspector_store,
        "tkt_compile_001",
        DeveloperInspectorRefs(
            compiled_context_bundle_ref="ctx://compile/tkt_compile_001",
            compile_manifest_ref="manifest://compile/tkt_compile_001",
            rendered_execution_payload_ref="render://compile/tkt_compile_001",
        ),
    )

    bundle_payload = developer_inspector_store.read_json("ctx://compile/tkt_compile_001")
    manifest_payload = developer_inspector_store.read_json("manifest://compile/tkt_compile_001")
    rendered_payload = developer_inspector_store.read_json("render://compile/tkt_compile_001")

    assert len(persisted) == 3
    assert bundle_payload is not None
    assert manifest_payload is not None
    assert rendered_payload is not None


def test_build_compile_request_accepts_legacy_process_asset_ref_but_resolves_versioned_source_ref(
    client,
    set_ticket_time,
):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    repository = client.app.state.repository
    source_ticket = repository.get_current_ticket_projection("tkt_compile_001")
    compile_and_persist_execution_artifacts(repository, source_ticket)
    compile_and_persist_execution_artifacts(repository, source_ticket)

    client.post(
        "/api/v1/commands/ticket-create",
        json=_ticket_create_payload(
            workflow_id="wf_compile_consumer",
            ticket_id="tkt_compile_consumer",
            node_id="node_compile_consumer",
            input_artifact_refs=[],
            input_process_asset_refs=[build_compiled_execution_package_process_asset_ref("tkt_compile_001")],
        ),
    )
    _seed_governance_profile(repository, workflow_id="wf_compile_consumer")
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(
            workflow_id="wf_compile_consumer",
            ticket_id="tkt_compile_consumer",
            node_id="node_compile_consumer",
        ),
    )

    consumer_ticket = repository.get_current_ticket_projection("tkt_compile_consumer")
    compile_request = build_compile_request(repository, consumer_ticket)

    assert compile_request.execution.input_process_asset_refs == [
        "pa://compiled-execution-package/tkt_compile_001"
    ]
    assert compile_request.explicit_sources[0].source_ref == build_process_asset_canonical_ref(
        build_compiled_execution_package_process_asset_ref("tkt_compile_001"),
        2,
    )
    assert compile_request.explicit_sources[0].source_metadata["version_int"] == 2
    assert compile_request.explicit_sources[0].source_metadata["supersedes_ref"] == "pa://compiled-execution-package/tkt_compile_001@1"
