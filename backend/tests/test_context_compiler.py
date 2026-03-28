from __future__ import annotations

from app.core.context_compiler import (
    MINIMAL_CONTEXT_COMPILER_VERSION,
    build_compile_request,
    compile_execution_package,
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
