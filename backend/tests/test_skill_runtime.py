import pytest

from app.core.context_compiler import build_compile_request, compile_execution_package
from tests.test_context_compiler import (
    _configure_runtime_provider,
    _seed_governance_profile,
    _ticket_create_payload,
    _ticket_lease_payload,
)


def test_compile_execution_package_binds_review_skill_for_review_deliverable(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _configure_runtime_provider(client)
    client.post("/api/v1/commands/ticket-create", json=_ticket_create_payload())
    client.post("/api/v1/commands/ticket-lease", json=_ticket_lease_payload())

    repository = client.app.state.repository
    _seed_governance_profile(repository, workflow_id="wf_compile")
    ticket = repository.get_current_ticket_projection("tkt_compile_001")

    compiled_package = compile_execution_package(build_compile_request(repository, ticket))

    assert compiled_package.skill_binding is not None
    assert compiled_package.skill_binding.task_category == "review"
    assert compiled_package.skill_binding.resolved_skill_ids == ["review"]


def test_compile_execution_package_binds_debugging_skill_for_retry_attempt(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _configure_runtime_provider(client)
    client.post(
        "/api/v1/commands/ticket-create",
        json={
            **_ticket_create_payload(ticket_id="tkt_debug_001", node_id="node_debug_001"),
            "attempt_no": 2,
        },
    )
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(ticket_id="tkt_debug_001", node_id="node_debug_001"),
    )

    repository = client.app.state.repository
    _seed_governance_profile(repository, workflow_id="wf_compile")
    ticket = repository.get_current_ticket_projection("tkt_debug_001")
    compiled_package = compile_execution_package(build_compile_request(repository, ticket))

    assert compiled_package.skill_binding is not None
    assert compiled_package.skill_binding.task_category == "debugging"
    assert compiled_package.skill_binding.resolved_skill_ids == ["debugging"]


def test_compile_execution_package_rejects_unknown_forced_skill_id(client, set_ticket_time):
    set_ticket_time("2026-03-28T10:00:00+08:00")
    _configure_runtime_provider(client)
    client.post(
        "/api/v1/commands/ticket-create",
        json={
            **_ticket_create_payload(ticket_id="tkt_forced_skill_001", node_id="node_forced_skill_001"),
            "forced_skill_ids": ["unknown_skill"],
        },
    )
    client.post(
        "/api/v1/commands/ticket-lease",
        json=_ticket_lease_payload(ticket_id="tkt_forced_skill_001", node_id="node_forced_skill_001"),
    )

    repository = client.app.state.repository
    _seed_governance_profile(repository, workflow_id="wf_compile")
    ticket = repository.get_current_ticket_projection("tkt_forced_skill_001")

    with pytest.raises(ValueError, match="SkillBinding"):
        compile_execution_package(build_compile_request(repository, ticket))
