from __future__ import annotations

import hashlib
import json
import re
import sqlite3
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
_TINY_SOURCE_DELIVERY_PROMPT_VERSION = "v2-080f-source-delivery-2026-05-30.9"
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
) -> TinyProviderAttemptFixture:
    if settings is None and not use_fake_results:
        settings = openai_settings_from_test_env()
    resolved_settings = _settings_for_tiny_source_delivery(settings) if settings else _fake_provider_settings()
    artifact_root = resolved_settings.artifact_store_root or Path("20-evidence/provider-artifacts")
    cache_key = _real_provider_fixture_cache_key(resolved_settings, artifact_root)
    if not use_fake_results and cache_key in _REAL_PROVIDER_FIXTURE_CACHE:
        return _REAL_PROVIDER_FIXTURE_CACHE[cache_key]

    compiled = compile_tiny_implementation_execution_packages(model=resolved_settings.model)
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
) -> RuntimeExecutionResult:
    max_attempts = 1 if use_fake_results else max(resolved_settings.max_retries + 1, 3)
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
    return last_result


def _fake_provider_settings() -> OpenAIProviderSettings:
    return OpenAIProviderSettings(
        api_key="sk-unit",
        base_url="https://unit.invalid/v1",
        model="unit-fake-model",
        api_protocol="chat_completions",
        reasoning_effort="high",
        text_verbosity="low",
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
    try:
        typed_files = {str(path): content for path, content in files.items()}
        if not all(isinstance(content, str) for content in typed_files.values()):
            return False
        backend_app = typed_files.get("backend/app.py")
        if backend_app is not None and not _provider_backend_public_api_signatures_are_valid(
            backend_app
        ):
            return False
        backend_db = typed_files.get("backend/db.py")
        if backend_db is not None and not _provider_sqlite_schema_literals_are_valid(backend_db):
            return False
        frontend_app = typed_files.get("frontend/app.js")
        if frontend_app is not None:
            if not _provider_frontend_has_exact_function_signature(
                frontend_app,
                function_name="loadBooks",
                parameters=("fetchImpl",),
            ):
                return False
            if not _provider_frontend_has_exact_function_signature(
                frontend_app,
                function_name="deleteBook",
                parameters=("fetchImpl", "bookId"),
            ):
                return False
            if not _provider_frontend_module_is_node_import_safe(frontend_app):
                return False
        integration_tests = typed_files.get("tests/integration/test_frontend_backend.py")
        if integration_tests is not None:
            if any(marker in integration_tests for marker in (".length = 0", ".splice(0")):
                return False
            if any(
                marker in integration_tests
                for marker in (
                    "part.startswith(\".pytest-tmp\")",
                    "part.startswith('.pytest-tmp')",
                    "startswith(\".pytest-tmp\")",
                    "startswith('.pytest-tmp')",
                )
            ):
                return False
        return True
    except Exception:
        return False


def _provider_sqlite_schema_literals_are_valid(backend_db: str) -> bool:
    create_table_sql = tuple(
        match.group(0)
        for match in re.finditer(
            r"CREATE\s+TABLE[^'\"]+",
            backend_db,
            flags=re.IGNORECASE,
        )
    )
    if "CREATE TABLE" not in backend_db.upper():
        return False
    try:
        tree = __import__("ast").parse(backend_db)
    except SyntaxError:
        return False
    strings = tuple(
        node.value
        for node in __import__("ast").walk(tree)
        if isinstance(node, __import__("ast").Constant)
        and isinstance(node.value, str)
        and "CREATE TABLE" in node.value.upper()
    )
    for sql in strings:
        try:
            connection = sqlite3.connect(":memory:")
            try:
                connection.execute(sql)
            finally:
                connection.close()
        except sqlite3.Error:
            return False
    return bool(strings or create_table_sql)


def _provider_backend_public_api_signatures_are_valid(backend_app: str) -> bool:
    try:
        tree = __import__("ast").parse(backend_app)
    except SyntaxError:
        return False
    functions = {
        node.name: node
        for node in __import__("ast").walk(tree)
        if isinstance(node, (__import__("ast").FunctionDef, __import__("ast").AsyncFunctionDef))
    }
    required = {
        "create_store": ("db_path",),
        "create_book": ("title",),
        "list_books": (),
        "checkout_book": ("book_id",),
        "return_book": ("book_id",),
        "delete_book": ("book_id",),
    }
    for function_name, required_names in required.items():
        node = functions.get(function_name)
        if node is None:
            return False
        if node.args.vararg is not None or node.args.kwarg is not None:
            return False
        positional = tuple(argument.arg for argument in node.args.args)
        keyword_only = tuple(argument.arg for argument in node.args.kwonlyargs)
        available = (*positional, *keyword_only)
        for required_name in required_names:
            if required_name not in available:
                return False
    return True


def _provider_frontend_has_exact_function_signature(
    frontend_app: str,
    *,
    function_name: str,
    parameters: tuple[str, ...],
) -> bool:
    parameter_pattern = r"\s*,\s*".join(re.escape(parameter) for parameter in parameters)
    patterns = (
        rf"(?:export\s+)?async\s+function\s+{re.escape(function_name)}\s*\(\s*{parameter_pattern}\s*\)",
        rf"(?:export\s+)?(?:const|let|var)\s+{re.escape(function_name)}\s*=\s*async\s*\(\s*{parameter_pattern}\s*\)",
        rf"(?:export\s+)?(?:const|let|var)\s+{re.escape(function_name)}\s*=\s*\(\s*{parameter_pattern}\s*\)\s*=>",
    )
    if not any(re.search(pattern, frontend_app) for pattern in patterns):
        return False
    default_pattern = rf"{re.escape(function_name)}\s*\([^)]*="
    return re.search(default_pattern, frontend_app) is None


def _provider_frontend_module_is_node_import_safe(frontend_app: str) -> bool:
    if "window.addEventListener" not in frontend_app:
        return True
    guard_markers = (
        "typeof window.addEventListener === 'function'",
        'typeof window.addEventListener === "function"',
        "'addEventListener' in window",
        '"addEventListener" in window',
    )
    return any(marker in frontend_app for marker in guard_markers)


def _provider_artifact_file_text(*, artifact_root: Path, artifact_ref: str) -> str:
    safe_name = artifact_ref.replace("/", "_").replace("\\", "_").replace(":", "_")
    return (artifact_root / f"{safe_name}.txt").read_text(encoding="utf-8")


def _settings_for_tiny_source_delivery(
    settings: OpenAIProviderSettings,
) -> OpenAIProviderSettings:
    min_output_tokens = max(settings.max_output_tokens, 8_192)
    timeout_seconds = max(settings.timeout_seconds, 240.0)
    instructions = (
        "For this V2-080F proving run, this system instruction replaces any "
        "environment-level audit-summary instruction. "
        f"Prompt version: {_TINY_SOURCE_DELIVERY_PROMPT_VERSION}. "
        "Return only valid minified JSON and no Markdown. The JSON schema is "
        "{\"files\":{\"relative/path\":\"complete UTF-8 file content\"}}. "
        "The files object must contain exactly every path listed in "
        "allowed_write_set except run-manifest.json and package-contract.json, "
        "and no other paths. Generate complete runnable source for each "
        "requested file. Use only Python standard library modules. Do not use "
        "Flask, FastAPI, requests, npm, or other third-party packages. Backend "
        "scope must expose create_store, create_book, list_books, checkout_book, "
        "return_book, delete_book in backend/app.py and a sqlite3-backed "
        "BookStore in backend/db.py. The backend must represent book states as "
        "IN_LIBRARY and CHECKED_OUT. backend/app.py public functions must use "
        "explicit inspectable signatures, not *args or **kwargs: create_store "
        "must accept db_path, create_book must accept title, checkout_book / "
        "return_book / delete_book must accept book_id, and optional store must "
        "be a named keyword or positional parameter. BookStore must use short-lived sqlite3 "
        "connections opened with context managers inside each operation; do not "
        "store sqlite3 Connection objects on self because Windows test cleanup "
        "must be able to remove the SQLite file after each test. Test scope must "
        "verify delete behavior, SQLite file persistence, and frontend fetches "
        "backend API paths. If tests open sqlite3.connect directly, wrap it with "
        "contextlib.closing(...) or explicitly close the connection before "
        "TemporaryDirectory cleanup; a plain 'with sqlite3.connect(...) as conn' "
        "does not close the connection on Windows. delete_book tests must call "
        "delete_book and then assert the deleted id is absent from list_books; "
        "do not route delete_book through a mutation helper that refetches the "
        "same book when delete_book returns bool/int/str or None. checkout_book "
        "and return_book may assert returned state or refetch updated rows, but "
        "delete_book must be verified by absence after deletion. Frontend scope "
        "must export exact "
        "function signatures 'export async function loadBooks(fetchImpl)' and "
        "'export async function deleteBook(fetchImpl, bookId)' with no default "
        "fetchImpl value. loadBooks must call fetchImpl('/books'); deleteBook "
        "must call fetchImpl(`/books/${bookId}` or encoded equivalent) using "
        "method DELETE. The integration test must execute frontend functions "
        "with a fake fetch implementation and capture url/options calls; do not "
        "write a regex-only or source-string-only integration test. Use Node "
        "stdlib via subprocess when testing JavaScript modules from pytest, and "
        "allow encoded equivalents such as encodeURIComponent(String(bookId)). "
        "The integration test must preserve the full fake fetch call list; do "
        "not clear calls.length or otherwise reset the capture before reporting. "
        "The final report/assertions must include both the loadBooks('/books') "
        "call and the deleteBook('/books/<id>', {method:'DELETE'}) call. "
        "Do not write '.length = 0', '.splice(0', or 'calls = []' anywhere in "
        "tests/integration/test_frontend_backend.py. The Python test should "
        "assert calls[0].url == '/books' and calls[1].options.method == 'DELETE' "
        "after one loadBooks call followed by one deleteBook call. Do not exclude "
        "candidate frontend modules because any absolute path segment starts with "
        "'.pytest-tmp'; pytest runs the whole package under such a temporary root. "
        "Prefer testing ROOT / 'frontend' / 'app.js' directly, or only filter "
        "package-relative cache paths such as node_modules and __pycache__. "
        "frontend/app.js must be safe to import in Node without a browser DOM; "
        "do not call window.addEventListener at module top level unless it is "
        "guarded by typeof window.addEventListener === 'function' or an "
        "equivalent addEventListener-in-window check. "
        "Docs scope must include runnable README/AGENTS/docs usage "
        "content. Do not include run-manifest.json or package-contract.json; "
        "the typed assembler writes those files."
    )
    return settings.model_copy(
        update={
            "system_instructions": instructions,
            "response_format": "json_object",
            "max_output_tokens": min_output_tokens,
            "timeout_seconds": timeout_seconds,
            "max_retries": max(settings.max_retries, 2),
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
    "validate_tiny_provider_attempt_results",
]
