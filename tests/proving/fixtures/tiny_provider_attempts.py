from __future__ import annotations

import hashlib
import json
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
from boardroom_os.contracts.methodology import MethodologyProfileRegistry
from boardroom_os.contracts.project import ProjectCharterRegistry
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
    FileProviderOutputStore,
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
from tests.fixtures.execution.role_prompt_hooks import (
    baseline_role_prompt_hook_fields_for_category,
    baseline_role_prompt_hook_registry,
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
class TinyProviderAttemptFixture:
    compiled: TinyCompiledImplementationPackages
    execution_packages: Mapping[TicketId, ExecutionPackage]
    runtime_results: tuple[RuntimeExecutionResult, ...]
    provider_attempts_by_ticket_id: Mapping[TicketId, ProviderAttempt]
    provider_artifact_root: Path


_REAL_PROVIDER_FIXTURE_CACHE: dict[tuple[object, ...], TinyProviderAttemptFixture] = {}
_TINY_SOURCE_DELIVERY_PROMPT_VERSION = "v2-090d-source-delivery-2026-06-02.1"
_PROVIDER_RETRY_GRAPH_VERSION_STRIDE = 10_000


def openai_settings_from_test_env(path: Path = Path(".env.test")) -> OpenAIProviderSettings:
    try:
        candidate_paths = _provider_env_candidate_paths(path)
        return OpenAIProviderSettings.from_env_files(candidate_paths)
    except OpenAIProviderConfigError as error:
        raise TinyProviderAttemptValidationError(str(error)) from error


def _provider_env_candidate_paths(path: Path) -> tuple[Path, ...]:
    if path.name != ".env.test":
        return (path,)
    if path.parent != Path("."):
        return (path, path.with_name(".env"))

    candidates: list[Path] = []
    cwd = Path.cwd()
    for directory in (cwd, *cwd.parents):
        candidates.extend((directory / ".env.test", directory / ".env"))
    seen: set[Path] = set()
    unique_candidates: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_candidates.append(candidate)
    return tuple(unique_candidates)


def compile_tiny_implementation_execution_packages(
    ticket_graph_fixture: TinyTicketGraphFixture | None = None,
    *,
    model: str | None = None,
    settings: OpenAIProviderSettings | None = None,
    context_window: int | None = None,
) -> TinyCompiledImplementationPackages:
    if settings is None:
        if model is None:
            raise TinyProviderAttemptValidationError(
                "model or settings is required for tiny implementation packages"
            )
        model_name = model
        resolved_context_window = (
            context_window
            if context_window is not None
            else _fake_provider_settings().context_window
        )
    else:
        model_name = settings.model
        resolved_context_window = settings.context_window
        if model is not None and model != model_name:
            raise TinyProviderAttemptValidationError(
                "model must match settings.model for tiny implementation packages"
            )
        if context_window is not None and context_window != resolved_context_window:
            raise TinyProviderAttemptValidationError(
                "context_window must match settings.context_window for tiny implementation packages"
            )
    graph_fixture = ticket_graph_fixture or build_tiny_ticket_graph_fixture()
    model_profiles_by_seat_ref = {
        seat.seat_ref: _model_execution_profile_for_seat(
            seat=seat,
            model=model_name,
            context_window=resolved_context_window,
        )
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
            ExecutionPackageCompilerInput.model_validate(
                {
                    "ticket_ref": ticket_id,
                    "seat_assignment_graph": graph_fixture.seat_assignment_graph,
                    "agent_team_projection": agent_team_projection,
                    "acceptance_contract": graph_fixture.contracts.acceptance_contract,
                    "package_contract": graph_fixture.contracts.package_contract,
                    "evidence_obligations": (
                        graph_fixture.contracts.contract_gate.evidence_obligations
                    ),
                    "model_execution_profiles": model_execution_profiles,
                    "role_prompt_hook_registry": baseline_role_prompt_hook_registry(),
                    "workspace_context": workspace_context,
                },
                context={
                    "project_charter_registry": ProjectCharterRegistry.from_charters(
                        graph_fixture.contracts.project_charter,
                    ),
                    "methodology_registry": MethodologyProfileRegistry.from_profiles(
                        graph_fixture.contracts.methodology_profile,
                    ),
                },
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


def build_tiny_provider_attempt_fixture(
    *,
    settings: OpenAIProviderSettings | None = None,
    use_fake_results: bool = False,
    source_delivery_attempt_limit: int = 2,
) -> TinyProviderAttemptFixture:
    if source_delivery_attempt_limit < 1:
        raise TinyProviderAttemptValidationError(
            "source_delivery_attempt_limit must be positive"
        )
    if settings is None and not use_fake_results:
        settings = openai_settings_from_test_env()
    resolved_settings = _settings_for_tiny_source_delivery(settings) if settings else _fake_provider_settings()
    artifact_root = resolved_settings.artifact_store_root or Path("20-evidence/provider-artifacts")
    cache_key = _real_provider_fixture_cache_key(resolved_settings, artifact_root)
    if not use_fake_results and cache_key in _REAL_PROVIDER_FIXTURE_CACHE:
        return _REAL_PROVIDER_FIXTURE_CACHE[cache_key]

    compiled = compile_tiny_implementation_execution_packages(settings=resolved_settings)
    base_graph_version = compiled.ticket_graph_fixture.seat_assignment_graph.graph_version
    execution_items = tuple(compiled.execution_packages.items())
    runtime_results = tuple(
        _execute_tiny_runtime_package_with_real_retries(
            ticket_id=ticket_id,
            execution_package=execution_package,
            compiled=compiled,
            resolved_settings=resolved_settings,
            artifact_root=artifact_root,
            use_fake_results=use_fake_results,
            first_fact_graph_version=(
                base_graph_version
                + (index * _PROVIDER_RETRY_GRAPH_VERSION_STRIDE)
                + 1
            ),
            source_delivery_attempt_limit=source_delivery_attempt_limit,
        )
        for index, (ticket_id, execution_package) in enumerate(execution_items)
    )

    validate_tiny_provider_attempt_results(
        execution_packages=compiled.execution_packages,
        runtime_results=runtime_results,
        allow_fake_provider_attempts=use_fake_results,
        artifact_root=None if use_fake_results else artifact_root,
    )
    fixture = TinyProviderAttemptFixture(
        compiled=compiled,
        execution_packages=compiled.execution_packages,
        runtime_results=runtime_results,
        provider_attempts_by_ticket_id={
            ticket_id: result.provider_attempt
            for ticket_id, result in zip(compiled.execution_packages, runtime_results, strict=True)
        },
        provider_artifact_root=artifact_root,
    )
    if not use_fake_results:
        _REAL_PROVIDER_FIXTURE_CACHE[cache_key] = fixture
    return fixture


def _execute_tiny_runtime_package(
    *,
    ticket_id: TicketId,
    execution_package: ExecutionPackage,
    compiled: TinyCompiledImplementationPackages,
    resolved_settings: OpenAIProviderSettings,
    artifact_root: Path,
    use_fake_results: bool,
    first_fact_graph_version: int,
) -> RuntimeExecutionResult:
    provider_adapter = (
        _fake_provider_transport(ticket_id)
        if use_fake_results
        else OpenAIProviderTransport(
            settings=resolved_settings,
            artifact_store=FileProviderOutputStore(
                root=artifact_root
            ),
        )
    )
    return RuntimeExecutor().execute_package(
        RuntimeExecutionInput.model_validate(
            {
                "execution_package": execution_package,
                "package_contract": compiled.ticket_graph_fixture.contracts.package_contract,
                "agent_team_projection": compiled.agent_team_projection,
                "provider_adapter": provider_adapter,
                "project_ref": PROJECT_REF,
                "runtime_actor_ref": ActorRef(value="actor.runtime.tiny-provider-attempts"),
                "first_fact_graph_version": first_fact_graph_version,
                "package_root": Path("10-project"),
                "runner_ref": RunnerRef(value="runner.tiny-provider-attempts"),
                "environment_profile_ref": EnvironmentProfileRef(
                    value="env.tiny-provider-attempts"
                ),
                "workspace_snapshot_ref": WorkspaceSnapshotRef(
                    value="workspace.snapshot.tiny-provider-attempts"
                ),
                "command_ids": (),
                "timestamp": datetime(2026, 5, 29, 10, 0, tzinfo=UTC),
            },
            context={
                "methodology_registry": MethodologyProfileRegistry.from_profiles(
                    compiled.ticket_graph_fixture.contracts.methodology_profile,
                ),
            },
        )
    )


def _execute_tiny_runtime_package_with_real_retries(
    *,
    ticket_id: TicketId,
    execution_package: ExecutionPackage,
    compiled: TinyCompiledImplementationPackages,
    resolved_settings: OpenAIProviderSettings,
    artifact_root: Path,
    use_fake_results: bool,
    first_fact_graph_version: int,
    source_delivery_attempt_limit: int = 2,
) -> RuntimeExecutionResult:
    if source_delivery_attempt_limit < 1:
        raise TinyProviderAttemptValidationError(
            "source_delivery_attempt_limit must be positive"
        )
    max_attempts = 1 if use_fake_results else source_delivery_attempt_limit
    last_result: RuntimeExecutionResult | None = None
    for attempt_index in range(max_attempts):
        result = _execute_tiny_runtime_package(
            ticket_id=ticket_id,
            execution_package=execution_package,
            compiled=compiled,
            resolved_settings=resolved_settings,
            artifact_root=artifact_root,
            use_fake_results=use_fake_results,
            first_fact_graph_version=first_fact_graph_version + (attempt_index * 1000),
        )
        if result.provider_attempt.status is ProviderAttemptStatus.SUCCEEDED and _provider_source_delivery_artifact_is_valid(
            result=result,
            execution_package=execution_package,
            artifact_root=artifact_root,
        ):
            return result
        last_result = result
    assert last_result is not None
    if not use_fake_results:
        raise TinyProviderAttemptValidationError(
            "provider source delivery did not satisfy execution package after retries: "
            f"ticket={ticket_id.value}; "
            f"attempt={last_result.provider_attempt.provider_attempt_id.value}; "
            f"status={last_result.provider_attempt.status.value}; "
            f"failure_kind={last_result.provider_attempt.failure_kind or 'none'}; "
            f"source_delivery_attempt_limit={source_delivery_attempt_limit}"
        )
    return last_result


def _fake_provider_settings() -> OpenAIProviderSettings:
    return OpenAIProviderSettings(
        api_key="sk-unit",
        base_url="https://unit.invalid/v1",
        model="unit-fake-model",
        api_protocol="chat_completions",
        reasoning_effort="high",
        text_verbosity="low",
        timeout_seconds=600,
        artifact_store_root=Path(".pytest-tmp-provider-artifacts"),
    )


def _provider_source_delivery_artifact_is_valid(
    *,
    result: RuntimeExecutionResult,
    execution_package: ExecutionPackage,
    artifact_root: Path,
) -> bool:
    attempt = result.provider_attempt
    if attempt.parsed_output_ref is None:
        return False
    try:
        text = _provider_artifact_file_text(
            artifact_root=artifact_root,
            artifact_ref=attempt.parsed_output_ref.value,
        )
        data = json.loads(text)
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    files = data.get("files")
    if not isinstance(files, dict):
        return False
    allowed_paths = {
        path.value
        for path in execution_package.allowed_write_set
        if path.value not in {"package-contract.json", "run-manifest.json"}
    }
    if set(files) != allowed_paths:
        return False
    if not all(isinstance(content, str) and content.strip() for content in files.values()):
        return False
    return _provider_source_delivery_files_are_functionally_valid(files)


def _provider_source_delivery_files_are_functionally_valid(files: object) -> bool:
    if not isinstance(files, dict):
        return False
    return all(isinstance(content, str) and content.strip() for content in files.values())


def _provider_artifact_file_text(*, artifact_root: Path, artifact_ref: str) -> str:
    safe_name = artifact_ref.replace("/", "_").replace("\\", "_").replace(":", "_")
    return (artifact_root / f"{safe_name}.txt").read_text(encoding="utf-8")


def tiny_source_delivery_system_instructions() -> str:
    return (
        "For this V2-090D proving run, this system instruction replaces any "
        "environment-level audit-summary instruction. "
        f"Prompt version: {_TINY_SOURCE_DELIVERY_PROMPT_VERSION}. "
        "Return only valid minified JSON and no Markdown. The JSON schema is "
        "{\"files\":{\"relative/path\":\"complete UTF-8 file content\"}}. "
        "The files object must contain exactly every path listed in "
        "allowed_write_set except run-manifest.json and package-contract.json, "
        "and no other paths. Treat allowed_write_set as a hard contract: do "
        "not output backend files for a tests/docs/frontend package, do not "
        "output tests for a backend/frontend/docs package, and do not invent "
        "replacement paths. If allowed_write_set only includes tests, return "
        "only test files; if it only includes README/AGENTS/docs, return only "
        "those documentation files. Generate complete runnable source for "
        "each requested file. Use only Python standard library modules. Do not use "
        "Flask, FastAPI, requests, npm, or other third-party packages. When "
        "allowed_write_set includes backend/app.py, implement backend/app.py "
        "as a standard-library HTTP service using http.server, "
        "BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer, or an "
        "equivalent Python standard-library HTTP server. Running run-backend "
        "must start the same service behavior as python -m backend.app. "
        "backend/app.py must expose a real service entrypoint guarded by if "
        "__name__ == '__main__' or equivalent and must route /health, /books, "
        "/books/<id>/checkout, /books/<id>/return, and DELETE /books/<id> or "
        "a clearly equivalent delete endpoint. The backend must represent "
        "book states as IN_LIBRARY and CHECKED_OUT. When allowed_write_set "
        "includes backend/db.py, implement SQLite persistence for API calls "
        "that create, list, checkout, return, and delete books through "
        "sqlite3 state that survives separate HTTP requests; this is the "
        "SQLite persistence via HTTP requirement. BookStore must "
        "use short-lived sqlite3 connections opened with context managers "
        "inside each operation; do not store sqlite3 Connection objects on "
        "self because Windows test cleanup must be able to remove the SQLite "
        "file after each test. When allowed_write_set includes backend/tests "
        "or tests/integration, tests must verify delete behavior, SQLite file "
        "persistence via HTTP, service startup, and frontend/backend live "
        "integration without outputting backend source files. If tests open "
        "sqlite3.connect directly, wrap it with contextlib.closing(...) or "
        "explicitly close the connection before TemporaryDirectory cleanup; a "
        "plain 'with sqlite3.connect(...) as conn' does not close the "
        "connection on Windows. Delete tests must issue an HTTP DELETE or "
        "equivalent delete endpoint call and then assert the deleted id is "
        "absent from a subsequent HTTP GET /books response. Checkout and "
        "return tests may assert returned state or refetch updated rows, but "
        "delete must be verified by absence after deletion. When "
        "allowed_write_set includes frontend/app.js, frontend code must export "
        "exact function signatures 'export async function loadBooks(fetchImpl)' "
        "and 'export async function deleteBook(fetchImpl, bookId)' with no "
        "default fetchImpl value. Frontend code must include a live backend "
        "probe against /health and must call the real backend HTTP base URL "
        "for /books and delete actions. fakeFetch-only frontend tests are "
        "allowed as narrow unit checks, but fakeFetch-only cannot satisfy "
        "final integration evidence. When allowed_write_set includes "
        "tests/integration/test_frontend_backend.py, the final integration "
        "test must start the backend service with python -m backend.app or "
        "run-backend, wait for a live /health readiness probe, exercise "
        "/books over HTTP, and prove frontend/backend integration against the "
        "live backend. Do not write a regex-only or source-string-only "
        "integration test as final evidence. Use Python standard-library HTTP "
        "clients such as urllib.request or http.client for blackbox HTTP "
        "checks. Do not write "
        "'.length = 0', '.splice(0', or 'calls = []' anywhere in "
        "tests/integration/test_frontend_backend.py. Do not exclude candidate "
        "frontend modules because any absolute path segment starts with "
        "'.pytest-tmp'; pytest runs the whole package under such a temporary "
        "root. Prefer testing ROOT / 'frontend' / 'app.js' directly, or only "
        "filter package-relative cache paths such as node_modules and "
        "__pycache__. frontend/app.js must be safe to import in Node without "
        "a browser DOM; do not call window.addEventListener at module top "
        "level unless it is guarded by typeof window.addEventListener === "
        "'function' or an equivalent addEventListener-in-window check. When "
        "allowed_write_set includes README.md, AGENTS.md, or docs/usage.md, "
        "docs scope must include runnable README/AGENTS/docs usage content "
        "without outputting source or test files. "
        "Do not include run-manifest.json or package-contract.json; the typed "
        "assembler writes those files."
    )


def _settings_for_tiny_source_delivery(
    settings: OpenAIProviderSettings,
) -> OpenAIProviderSettings:
    min_output_tokens = max(settings.max_output_tokens, 8_192)
    instructions = tiny_source_delivery_system_instructions()
    return settings.model_copy(
        update={
            "system_instructions": instructions,
            "response_format": "json_object",
            "max_output_tokens": min_output_tokens,
        }
    )


def _real_provider_fixture_cache_key(
    settings: OpenAIProviderSettings,
    artifact_root: Path,
) -> tuple[object, ...]:
    return (
        settings.base_url,
        settings.model,
        settings.api_protocol,
        settings.reasoning_effort,
        settings.text_verbosity,
        settings.response_format,
        settings.max_output_tokens,
        settings.context_window,
        settings.timeout_seconds,
        settings.max_retries,
        settings.system_instructions,
        _TINY_SOURCE_DELIVERY_PROMPT_VERSION,
        artifact_root.as_posix(),
    )


def validate_tiny_provider_attempt_results(
    *,
    execution_packages: Mapping[TicketId, ExecutionPackage],
    runtime_results: tuple[RuntimeExecutionResult, ...],
    allow_fake_provider_attempts: bool = False,
    artifact_root: Path | None = None,
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
            raise TinyProviderAttemptValidationError(
                "provider attempt must be succeeded"
                + (f": {attempt.failure_kind}" if attempt.failure_kind else "")
            )
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
        _require_hashed_provider_artifact_ref(_ref_value(attempt.raw_output_ref))
        _require_hashed_provider_artifact_ref(_ref_value(attempt.parsed_output_ref))
        if not allow_fake_provider_attempts:
            _reject_fake_provider_attempt(attempt.provider_attempt_id.value)
        if artifact_root is not None:
            _require_provider_artifact_file(
                artifact_root=artifact_root,
                artifact_ref=_ref_value(attempt.raw_output_ref),
            )
            _require_provider_artifact_file(
                artifact_root=artifact_root,
                artifact_ref=_ref_value(attempt.parsed_output_ref),
            )
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
        **baseline_role_prompt_hook_fields_for_category(seat.role_category),
    )


def _model_execution_profile_for_seat(
    *,
    seat: object,
    model: str,
    context_window: int,
) -> ModelExecutionProfile:
    return ModelExecutionProfile(
        model_execution_profile_id=seat.model_execution_profile_ref,
        provider="openai-compatible",
        model=model,
        reasoning_effort="xhigh" if seat.role_category is RoleCategory.ARCHITECTURE else "high",
        context_window=context_window,
        temperature=0.2,
        tool_permissions=("provider.invoke",),
        fallback_policy_ref=ContractId(value="fallback.tiny.record-failure"),
    )


def _fake_provider_transport(ticket_id: TicketId) -> FakeProviderTransport:
    suffix = ticket_id.value.replace("ticket-tiny-", "")
    return FakeProviderTransport(
        response=ProviderResponse(
            raw_output_ref=f"provider-artifact.openai.raw.fake-{suffix}.{'0' * 64}",
            parsed_output_ref=f"provider-artifact.openai.text.fake-{suffix}.{'1' * 64}",
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


def _reject_fake_provider_attempt(value: str) -> None:
    if ".fake." in value or value.endswith(".fake"):
        raise TinyProviderAttemptValidationError("fake provider attempts cannot satisfy implementation evidence")


def _require_hashed_provider_artifact_ref(value: str) -> None:
    digest = value.rsplit(".", 1)[-1]
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise TinyProviderAttemptValidationError("provider artifact refs must include content hash")


def _require_provider_artifact_file(*, artifact_root: Path, artifact_ref: str) -> None:
    safe_name = artifact_ref.replace("/", "_").replace("\\", "_").replace(":", "_")
    path = artifact_root / f"{safe_name}.txt"
    if not path.exists():
        raise TinyProviderAttemptValidationError(
            f"provider artifact file is required: {artifact_ref}"
        )
    content_hash = path.read_bytes()
    digest = artifact_ref.rsplit(".", 1)[-1]
    if digest != hashlib.sha256(content_hash).hexdigest():
        raise TinyProviderAttemptValidationError("provider artifact file hash mismatch")


def _ref_value(value: object) -> str:
    if value is None:
        return ""
    return str(getattr(value, "value", value))


__all__ = [
    "TinyCompiledImplementationPackages",
    "TinyProviderAttemptValidationError",
    "TinyProviderAttemptFixture",
    "build_tiny_provider_attempt_fixture",
    "compile_tiny_implementation_execution_packages",
    "openai_settings_from_test_env",
    "tiny_source_delivery_system_instructions",
    "validate_tiny_provider_attempt_results",
]
