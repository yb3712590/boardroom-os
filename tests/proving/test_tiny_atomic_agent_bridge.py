from __future__ import annotations

from boardroom_os.execution.atomic_agent import AtomicInvocationCompiler
from boardroom_os.providers.openai_adapter import OpenAIProviderSettings
from tests.proving.fixtures.tiny_provider_attempts import (
    compile_tiny_implementation_execution_packages,
)
from tests.proving.fixtures.tiny_ticket_graph import (
    TICKET_BACKEND_API_ID,
    build_tiny_ticket_graph_fixture,
)


def test_tiny_worker_execution_package_can_compile_to_atomic_invocation(tmp_path):
    settings = OpenAIProviderSettings(
        api_key="sk-test-secret",
        base_url="https://api.example.invalid/v1",
        model="gpt-5.5",
        api_protocol="chat_completions",
        reasoning_effort="high",
        text_verbosity="low",
        response_format="json_object",
        max_output_tokens=128000,
        timeout_seconds=600,
        max_retries=0,
        context_window=500000,
        artifact_store_root=tmp_path / "provider-artifacts",
    )
    compiled = compile_tiny_implementation_execution_packages(
        build_tiny_ticket_graph_fixture(),
        settings=settings,
    )
    backend_package = compiled.execution_packages[TICKET_BACKEND_API_ID]

    invocation = AtomicInvocationCompiler(workspace_root=tmp_path).compile(backend_package)

    assert invocation.metadata["ticket_ref"] == "ticket-tiny-backend-api"
    assert "run_command" in invocation.tools
    assert invocation.output_requirements["require_event_stream"] is True
    assert invocation.output_requirements["require_workspace_mutations"] is True
    assert invocation.permission_policy["commands"]
