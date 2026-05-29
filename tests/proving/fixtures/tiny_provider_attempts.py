from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Mapping

from boardroom_os.agents.categories import RoleCategory
from boardroom_os.agents.policy import RoleProfileProjection
from boardroom_os.agents.profiles import (
    ModelExecutionProfile,
    ModelExecutionProfileRegistry,
    RoleProfile,
)
from boardroom_os.agents.team import AgentTeamProjection
from boardroom_os.contracts.types import ContractId
from boardroom_os.events.types import ActorRef, EventType
from boardroom_os.execution.compiler import (
    ExecutionPackageCompiler,
    ExecutionPackageCompilerInput,
    ExecutionWorkspaceContext,
)
from boardroom_os.execution.package import ContextRef, ExecutionPackage
from boardroom_os.execution.runtime_executor import (
    RuntimeExecutionInput,
    RuntimeExecutionResult,
    RuntimeExecutor,
)
from boardroom_os.execution.verification_run import (
    EnvironmentProfileRef,
    RunnerRef,
    WorkspaceSnapshotRef,
)
from boardroom_os.graph.ticket import TicketId
from boardroom_os.providers.adapter import FakeProviderTransport, ProviderResponse
from boardroom_os.providers.attempt import ProviderAttempt, ProviderAttemptOutcome, ProviderAttemptStatus
from boardroom_os.providers.openai_adapter import (
    OpenAIProviderConfigError,
    OpenAIProviderSettings,
    OpenAIProviderTransport,
)
from tests.proving.fixtures.tiny_ticket_graph import (
    PROJECT_REF,
    TICKET_ARCHITECTURE_ID,
    TinyTicketGraphFixture,
    build_tiny_ticket_graph_fixture,
)


class TinyProviderAttemptValidationError(ValueError):
    pass


@dataclass(frozen=True)
class TinyCompiledImplementationPackages:
    ticket_graph_fixture: TinyTicketGraphFixture
    agent_team_projection: AgentTeamProjection
    model_execution_profiles: ModelExecutionProfileRegistry
    model_execution_profiles_by_ticket_id: Mapping[TicketId, ModelExecutionProfile]
    execution_packages: Mapping[TicketId, ExecutionPackage]


@dataclass(frozen=True)
class TinyRealProviderAttemptFixture:
    compiled: TinyCompiledImplementationPackages
    execution_packages: Mapping[TicketId, ExecutionPackage]
    runtime_results: tuple[RuntimeExecutionResult, ...]
    provider_attempts_by_ticket_id: Mapping[TicketId, ProviderAttempt]


def openai_settings_from_test_env(path: Path = Path(".env.test")) -> OpenAIProviderSettings:
    try:
        return OpenAIProviderSettings.from_env_file(path)
    except OpenAIProviderConfigError as error:
        raise TinyProviderAttemptValidationError(str(error)) from error


def compile_tiny_implementation_execution_packages(
    ticket_graph_fixture: TinyTicketGraphFixture | None = None,
    *,
    model: str,
) -> TinyCompiledImplementationPackages:
    graph_fixture = ticket_graph_fixture or build_tiny_ticket_graph_fixture()
    model_profiles_by_seat_ref = {
        seat.seat_ref: _model_execution_profile_for_seat(seat=seat, model=model)
        for seat in graph_fixture.seats
    }
    model_profiles_by_ticket_id = {
        ticket_id: model_profiles_by_seat_ref[seat_ref]
        for ticket_id, seat_ref in graph_fixture.seat_assignment_graph.seat_assignments.items()
    }
    model_execution_profiles = ModelExecutionProfileRegistry.from_profiles(
        *model_profiles_by_seat_ref.values(),
    )
    agent_team_projection = AgentTeamProjection(
        graph_version=graph_fixture.seat_assignment_graph.graph_version,
        role_profiles=RoleProfileProjection(
            profiles=tuple(_role_profile_for_seat(seat) for seat in graph_fixture.seats),
        ),
        seat_lifecycle=graph_fixture.seat_projection.model_copy(
            update={"graph_version": graph_fixture.seat_assignment_graph.graph_version},
        ),
    )
    compiler = ExecutionPackageCompiler()
    workspace_context = ExecutionWorkspaceContext(
        workspace_ref=ContextRef(value="context.tiny-fullstack.workspace"),
        package_root="10-project",
        context_refs=(
            ContextRef(value="context.tiny-fullstack.provider-attempts"),
        ),
    )
    execution_packages = {
        ticket_id: compiler.compile(
            ExecutionPackageCompilerInput.model_construct(
                ticket_ref=ticket_id,
                seat_assignment_graph=graph_fixture.seat_assignment_graph,
                agent_team_projection=agent_team_projection,
                acceptance_contract=graph_fixture.contracts.acceptance_contract,
                package_contract=graph_fixture.contracts.package_contract,
                evidence_obligations=graph_fixture.contracts.contract_gate.evidence_obligations,
                model_execution_profiles=model_execution_profiles,
                workspace_context=workspace_context,
            )
        )
        for ticket_id in graph_fixture.implementation_ticket_ids
    }

    return TinyCompiledImplementationPackages(
        ticket_graph_fixture=graph_fixture,
        agent_team_projection=agent_team_projection,
        model_execution_profiles=model_execution_profiles,
        model_execution_profiles_by_ticket_id=model_profiles_by_ticket_id,
        execution_packages=execution_packages,
    )


def build_tiny_real_provider_attempt_fixture(
    *,
    settings: OpenAIProviderSettings | None = None,
    use_fake_results: bool = False,
) -> TinyRealProviderAttemptFixture:
    resolved_settings = settings or OpenAIProviderSettings(
        api_key="sk-unit",
        base_url="https://api.truerealbill.com/v1",
        model="gpt-5.5",
        reasoning_effort="high",
        text_verbosity="low",
    )
    compiled = compile_tiny_implementation_execution_packages(model=resolved_settings.model)
    base_graph_version = compiled.ticket_graph_fixture.seat_assignment_graph.graph_version
    execution_items = tuple(compiled.execution_packages.items())
    with ThreadPoolExecutor(max_workers=len(execution_items)) as executor:
        futures = tuple(
            executor.submit(
                _execute_tiny_runtime_package,
                ticket_id=ticket_id,
                execution_package=execution_package,
                compiled=compiled,
                resolved_settings=resolved_settings,
                use_fake_results=use_fake_results,
                first_fact_graph_version=base_graph_version + (index * 10) + 1,
            )
            for index, (ticket_id, execution_package) in enumerate(execution_items)
        )
        runtime_results = tuple(future.result() for future in futures)

    validate_tiny_provider_attempt_results(
        execution_packages=compiled.execution_packages,
        runtime_results=runtime_results,
    )
    return TinyRealProviderAttemptFixture(
        compiled=compiled,
        execution_packages=compiled.execution_packages,
        runtime_results=runtime_results,
        provider_attempts_by_ticket_id={
            ticket_id: result.provider_attempt
            for ticket_id, result in zip(compiled.execution_packages, runtime_results, strict=True)
        },
    )


def _execute_tiny_runtime_package(
    *,
    ticket_id: TicketId,
    execution_package: ExecutionPackage,
    compiled: TinyCompiledImplementationPackages,
    resolved_settings: OpenAIProviderSettings,
    use_fake_results: bool,
    first_fact_graph_version: int,
) -> RuntimeExecutionResult:
    provider_adapter = (
        _fake_provider_transport(ticket_id)
        if use_fake_results
        else OpenAIProviderTransport(settings=resolved_settings)
    )
    return RuntimeExecutor().execute_package(
        RuntimeExecutionInput.model_construct(
            execution_package=execution_package,
            package_contract=compiled.ticket_graph_fixture.contracts.package_contract,
            agent_team_projection=compiled.agent_team_projection,
            provider_adapter=provider_adapter,
            project_ref=PROJECT_REF,
            runtime_actor_ref=ActorRef(value="actor.runtime.tiny-provider-attempts"),
            first_fact_graph_version=first_fact_graph_version,
            package_root=Path("10-project"),
            runner_ref=RunnerRef(value="runner.tiny-provider-attempts"),
            environment_profile_ref=EnvironmentProfileRef(value="env.tiny-provider-attempts"),
            workspace_snapshot_ref=WorkspaceSnapshotRef(value="workspace.snapshot.tiny-provider-attempts"),
            command_ids=(),
            timestamp=datetime(2026, 5, 29, 10, 0, tzinfo=UTC),
        )
    )


def validate_tiny_provider_attempt_results(
    *,
    execution_packages: Mapping[TicketId, ExecutionPackage],
    runtime_results: tuple[RuntimeExecutionResult, ...],
) -> None:
    if not runtime_results:
        raise TinyProviderAttemptValidationError("provider attempt results are required")
    if len(runtime_results) != len(execution_packages):
        raise TinyProviderAttemptValidationError("one provider attempt is required per execution package")

    seen_attempt_refs: set[str] = set()
    for ticket_id, execution_package in execution_packages.items():
        result = next(
            (
                candidate
                for candidate in runtime_results
                if candidate.provider_attempt.input_package_ref.value
                == execution_package.execution_package_id.value
            ),
            None,
        )
        if result is None:
            raise TinyProviderAttemptValidationError(
                f"missing provider attempt for ticket: {ticket_id.value}"
            )

        attempt = result.provider_attempt
        if attempt.provider_attempt_id.value in seen_attempt_refs:
            raise TinyProviderAttemptValidationError("provider attempt refs must be unique")
        seen_attempt_refs.add(attempt.provider_attempt_id.value)

        if attempt.status is not ProviderAttemptStatus.SUCCEEDED:
            raise TinyProviderAttemptValidationError("provider attempt must be succeeded")
        if attempt.outcome is not ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT:
            raise TinyProviderAttemptValidationError("fallback source delivery is not allowed")
        if attempt.fallback_kind is not None:
            raise TinyProviderAttemptValidationError("fallback source delivery is not allowed")
        if attempt.input_package_ref.value != execution_package.execution_package_id.value:
            raise TinyProviderAttemptValidationError("provider attempt input package mismatch")
        if attempt.seat_ref != execution_package.seat_ref:
            raise TinyProviderAttemptValidationError("provider attempt seat mismatch")
        if attempt.reasoning_effort != "high":
            raise TinyProviderAttemptValidationError("implementation attempts must use high reasoning effort")
        _reject_placeholder_ref(_ref_value(attempt.raw_output_ref))
        _reject_placeholder_ref(_ref_value(attempt.parsed_output_ref))
        if result.work_product_submission is None:
            raise TinyProviderAttemptValidationError("work product submission is required")
        if result.work_product_submission.work_product.producer_attempt_ref != attempt.provider_attempt_id:
            raise TinyProviderAttemptValidationError("work product must bind provider attempt")
        event_types = tuple(event.event_type for event in result.events)
        if EventType.PROVIDER_ATTEMPT_RECORDED not in event_types:
            raise TinyProviderAttemptValidationError("provider attempt event is required")
        if EventType.WORK_PRODUCT_SUBMITTED not in event_types:
            raise TinyProviderAttemptValidationError("work product event is required")
        if EventType.TICKET_COMPLETED in event_types:
            raise TinyProviderAttemptValidationError("runtime must not complete tickets")

    graph_versions = tuple(
        event.graph_version
        for result in runtime_results
        for event in result.events
    )
    if graph_versions != tuple(sorted(graph_versions)) or len(set(graph_versions)) != len(graph_versions):
        raise TinyProviderAttemptValidationError("runtime event graph versions must be unique and monotonic")


def _role_profile_for_seat(seat: object) -> RoleProfile:
    return RoleProfile(
        role_profile_id=seat.role_profile_ref,
        role_category=seat.role_category,
        role_name=seat.role_profile_ref.value,
        responsibilities=(f"Perform {seat.role_category.value} work for the tiny scenario.",),
        capability_tags=seat.capability_tags,
        input_contracts=(ContractId(value="contract.execution.package"),),
        output_contracts=(ContractId(value="contract.work.product"),),
        forbidden_actions=("Do not bypass provider attempt evidence.",),
    )


def _model_execution_profile_for_seat(
    *,
    seat: object,
    model: str,
) -> ModelExecutionProfile:
    return ModelExecutionProfile(
        model_execution_profile_id=seat.model_execution_profile_ref,
        provider="openai-compatible",
        model=model,
        reasoning_effort="xhigh" if seat.role_category is RoleCategory.ARCHITECTURE else "high",
        context_window=200000,
        temperature=0.2,
        tool_permissions=("provider.invoke",),
        fallback_policy_ref=ContractId(value="fallback.tiny.record-failure"),
    )


def _fake_provider_transport(ticket_id: TicketId) -> FakeProviderTransport:
    suffix = ticket_id.value.replace("ticket-tiny-", "")
    return FakeProviderTransport(
        response=ProviderResponse(
            raw_output_ref=f"provider-artifact.openai.raw.{suffix}",
            parsed_output_ref=f"provider-artifact.openai.text.{suffix}",
            summary=f"Tiny implementation output for {ticket_id.value}.",
        ),
        attempt_id=f"provider-attempt.openai.fake.{suffix}",
        started_at=datetime(2026, 5, 29, 10, 0, tzinfo=UTC),
        finished_at=datetime(2026, 5, 29, 10, 0, tzinfo=UTC),
    )


def _reject_placeholder_ref(value: str) -> None:
    if not value:
        raise TinyProviderAttemptValidationError("provider artifact refs are required")
    if "placeholder" in value.lower():
        raise TinyProviderAttemptValidationError("placeholder artifact refs are not allowed")


def _ref_value(value: object) -> str:
    if value is None:
        return ""
    return str(getattr(value, "value", value))


__all__ = [
    "TinyCompiledImplementationPackages",
    "TinyProviderAttemptValidationError",
    "TinyRealProviderAttemptFixture",
    "build_tiny_real_provider_attempt_fixture",
    "compile_tiny_implementation_execution_packages",
    "openai_settings_from_test_env",
    "validate_tiny_provider_attempt_results",
]
