from __future__ import annotations

from datetime import datetime

from app.contracts.commands import DeveloperInspectorRefs

from app.core.context_compiler import (
    MINIMAL_CONTEXT_COMPILER_VERSION,
    build_compile_request,
    compile_and_persist_execution_artifacts,
    compile_audit_artifacts,
    compile_execution_package,
    export_latest_compile_artifacts_to_developer_inspector,
)


def _ticket_create_payload(
    *,
    workflow_id: str = "wf_compile",
    ticket_id: str = "tkt_compile_001",
    node_id: str = "node_compile_001",
    input_artifact_refs: list[str] | None = None,
) -> dict:
    return {
        "ticket_id": ticket_id,
        "workflow_id": workflow_id,
        "node_id": node_id,
        "parent_ticket_id": None,
        "attempt_no": 1,
        "role_profile_ref": "ui_designer_primary",
        "constraints_ref": "global_constraints_v3",
        "input_artifact_refs": input_artifact_refs or [
            "art://inputs/brief.md",
            "art://inputs/brand-guide.md",
        ],
        "context_query_plan": {
            "keywords": ["homepage", "brand"],
            "semantic_queries": ["approved direction"],
            "max_context_tokens": 3000,
        },
        "acceptance_criteria": ["Must produce a structured result"],
        "output_schema_ref": "ui_milestone_review",
        "output_schema_version": 1,
        "allowed_tools": ["read_artifact", "write_artifact"],
        "allowed_write_set": ["artifacts/ui/homepage/*"],
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


def test_build_compile_request_translates_runtime_inputs(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_compile_001")

    compile_request = build_compile_request(repository, ticket)

    assert compile_request.meta.ticket_id == "tkt_compile_001"
    assert compile_request.meta.workflow_id == "wf_compile"
    assert compile_request.worker_binding.lease_owner == "emp_frontend_2"
    assert compile_request.worker_binding.employee_role_type == "frontend_engineer"
    assert compile_request.budget_policy.max_input_tokens == 3000
    assert compile_request.budget_policy.overflow_policy == "FAIL_CLOSED"
    assert [source.source_ref for source in compile_request.explicit_sources] == [
        "art://inputs/brief.md",
        "art://inputs/brand-guide.md",
    ]
    assert compile_request.execution.allowed_write_set == ["artifacts/ui/homepage/*"]
    assert compile_request.governance.timeout_sla_sec == 1800


def test_compile_execution_package_builds_minimal_worker_input(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_compile_001")
    compile_request = build_compile_request(repository, ticket)

    compiled_package = compile_execution_package(compile_request)

    assert compiled_package.meta.ticket_id == "tkt_compile_001"
    assert compiled_package.meta.lease_owner == "emp_frontend_2"
    assert compiled_package.meta.compiler_version == MINIMAL_CONTEXT_COMPILER_VERSION
    assert compiled_package.compiled_role.role_profile_ref == "ui_designer_primary"
    assert compiled_package.compiled_role.employee_role_type == "frontend_engineer"
    assert compiled_package.compiled_constraints.constraints_ref == "global_constraints_v3"
    assert compiled_package.compiled_constraints.global_rules == []
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

    assert content_payload["artifact_ref"] == artifact_ref
    assert content_payload["logical_path"] == "artifacts/inputs/brief.md"
    assert content_payload["media_type"] == "text/markdown"
    assert content_payload["materialization_status"] == "MATERIALIZED"
    assert content_payload["lifecycle_status"] == "ACTIVE"
    assert content_payload["content_hash"] == materialized.content_hash
    assert content_payload["size_bytes"] == materialized.size_bytes
    assert "/api/v1/artifacts/content" in content_payload["content_url"]
    assert "/api/v1/artifacts/preview" in content_payload["preview_url"]


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
    assert bundle.context_blocks[0].source_kind == "ARTIFACT_REFERENCE"
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


def test_compile_and_persist_execution_artifacts_writes_bundle_and_manifest(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    repository = client.app.state.repository
    ticket = repository.get_current_ticket_projection("tkt_compile_001")

    compiled_artifacts = compile_and_persist_execution_artifacts(repository, ticket)
    latest_bundle = repository.get_latest_compiled_context_bundle_by_ticket("tkt_compile_001")
    latest_manifest = repository.get_latest_compile_manifest_by_ticket("tkt_compile_001")

    assert latest_bundle is not None
    assert latest_manifest is not None
    assert latest_bundle["bundle_id"] == compiled_artifacts.compiled_context_bundle.meta.bundle_id
    assert latest_bundle["payload"]["meta"]["bundle_id"] == latest_bundle["bundle_id"]
    assert latest_bundle["payload"]["context_blocks"][0]["source_hash"]
    assert repository.get_compiled_context_bundle(latest_bundle["bundle_id"]) is not None
    assert latest_manifest["compile_id"] == compiled_artifacts.compile_manifest.compile_meta.compile_id
    assert latest_manifest["payload"]["compile_meta"]["compile_id"] == latest_manifest["compile_id"]
    assert latest_manifest["payload"]["source_log"][0]["status"] == "USED"
    assert latest_manifest["payload"]["degradation"]["warnings"]
    assert repository.get_compile_manifest(latest_manifest["compile_id"]) is not None


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
        ),
    )

    bundle_payload = developer_inspector_store.read_json("ctx://compile/tkt_compile_001")
    manifest_payload = developer_inspector_store.read_json("manifest://compile/tkt_compile_001")

    assert len(persisted) == 2
    assert bundle_payload is not None
    assert manifest_payload is not None
    assert bundle_payload["meta"]["bundle_id"] == compiled_artifacts.compiled_context_bundle.meta.bundle_id
    assert manifest_payload["compile_meta"]["compile_id"] == compiled_artifacts.compile_manifest.compile_meta.compile_id
    assert manifest_payload["compile_meta"]["bundle_id"] == bundle_payload["meta"]["bundle_id"]
