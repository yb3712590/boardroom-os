from __future__ import annotations

import hashlib
import json
from pathlib import Path
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from tests.proving.fixtures import tiny_provider_attempts
from boardroom_os.events.types import EventType
from boardroom_os.execution.fallback import FallbackKind
from boardroom_os.providers.attempt import (
    ProviderAttemptOutcome,
    ProviderAttemptStatus,
)
from tests.proving.fixtures.tiny_provider_attempts import (
    TinyProviderAttemptValidationError,
    build_tiny_provider_attempt_fixture,
    compile_tiny_implementation_execution_packages,
    openai_settings_from_test_env,
    validate_tiny_provider_attempt_results,
)
from boardroom_os.providers.openai_adapter import OpenAIProviderSettings
from boardroom_os.execution.runtime_executor import RuntimeExecutionResult
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.package import ExecutionPackageRef
from boardroom_os.providers.attempt import ProviderArtifactRef, ProviderAttempt
from tests.proving.fixtures.tiny_ticket_graph import (
    TICKET_ARCHITECTURE_ID,
    build_tiny_ticket_graph_fixture,
)


def test_tiny_openai_settings_fail_closed_without_test_env(tmp_path: Path) -> None:
    missing_env = tmp_path / ".env.test"

    with pytest.raises(TinyProviderAttemptValidationError, match="OPENAI_API_KEY|env"):
        openai_settings_from_test_env(missing_env)


def test_tiny_openai_settings_reads_ignored_env_fallback(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            (
                "OPENAI_API_KEY=sk-test-secret",
                "OPENAI_BASE_URL=https://api.example.invalid/v1",
                "BOARDROOM_OPENAI_MODEL=gpt-5.4",
                "BOARDROOM_OPENAI_API_PROTOCOL=chat_completions",
                "BOARDROOM_OPENAI_TIMEOUT_SECONDS=600",
            )
        ),
        encoding="utf-8",
    )

    settings = openai_settings_from_test_env(tmp_path / ".env.test")

    assert settings.base_url == "https://api.example.invalid/v1"
    assert settings.model == "gpt-5.4"
    assert settings.api_protocol == "chat_completions"
    assert settings.timeout_seconds == 600
    assert settings.context_window == 400000


def test_tiny_implementation_execution_packages_use_provider_context_window(
    tmp_path: Path,
) -> None:
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

    compiled = compile_tiny_implementation_execution_packages(settings=settings)

    assert {
        package.model_execution_profile.context_window
        for package in compiled.execution_packages.values()
    } == {500000}


def test_tiny_implementation_execution_packages_reject_invalid_context_window() -> None:
    with pytest.raises((TinyProviderAttemptValidationError, ValidationError)):
        compile_tiny_implementation_execution_packages(
            model="gpt-5.5",
            context_window=0,
        )


def test_tiny_source_delivery_settings_force_json_object_response_format(
    tmp_path: Path,
) -> None:
    settings = OpenAIProviderSettings(
        api_key="sk-test-secret",
        base_url="https://api.example.invalid/v1",
        model="gpt-5.5",
        api_protocol="chat_completions",
        reasoning_effort="high",
        text_verbosity="low",
        response_format="text",
        max_output_tokens=128,
        timeout_seconds=30,
        max_retries=0,
        system_instructions=(
            "Return a short audit summary. Do not generate full source files."
        ),
        artifact_store_root=tmp_path / "provider-artifacts",
    )

    tuned = tiny_provider_attempts._settings_for_tiny_source_delivery(settings)
    expected_instructions = (
        tiny_provider_attempts.tiny_source_delivery_system_instructions()
    )

    assert tuned.response_format == "json_object"
    assert tuned.max_output_tokens >= 8192
    assert tuned.timeout_seconds == 30
    assert tuned.max_retries == 0
    assert "Do not generate full source files" not in tuned.system_instructions
    assert tuned.system_instructions == expected_instructions
    assert "Return only valid minified JSON" in tuned.system_instructions


def test_tiny_source_delivery_prompt_targets_v2_090d_http_backend() -> None:
    instructions = tiny_provider_attempts.tiny_source_delivery_system_instructions()

    assert "Prompt version: v2-090d-" in instructions
    assert "Treat allowed_write_set as a hard contract" in instructions
    assert "do not output backend files for a tests/docs/frontend package" in instructions
    assert "without outputting backend source files" in instructions
    assert "without outputting source or test files" in instructions
    assert "Python standard library modules" in instructions
    assert "http.server" in instructions
    assert "BaseHTTPRequestHandler" in instructions
    assert "python -m backend.app" in instructions
    assert "run-backend" in instructions
    assert "/health" in instructions
    assert "/books" in instructions
    assert "checkout" in instructions
    assert "return" in instructions
    assert "DELETE" in instructions
    assert "SQLite persistence via HTTP" in instructions
    assert "fakeFetch-only" in instructions
    assert "create_store" not in instructions
    assert "checkout_book" not in instructions


def test_tiny_source_delivery_validator_accepts_schema_valid_package_without_tiny_shape_markers() -> None:
    files = {
        "backend/app.py": (
            "from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer\n"
            "from backend.storage import Library\n\n"
            "class Handler(BaseHTTPRequestHandler):\n"
            "    def do_GET(self):\n"
            "        parts = [part for part in self.path.split('/') if part]\n"
            "        if parts == ['health']:\n"
            "            self.send_response(200); self.end_headers()\n"
            "        elif parts == ['books']:\n"
            "            self.send_response(200); self.end_headers()\n"
            "    def do_POST(self):\n"
            "        self.send_response(201); self.end_headers()\n"
            "    def do_DELETE(self):\n"
            "        Library('books.sqlite3').remove(int(self.path.rsplit('/', 1)[-1]))\n"
            "        self.send_response(200); self.end_headers()\n\n"
            "def main():\n"
            "    ThreadingHTTPServer(('127.0.0.1', 8000), Handler).serve_forever()\n\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        ),
        "backend/db.py": (
            "from pathlib import Path\n\n"
            "class Library:\n"
            "    def __init__(self, path): self.path = Path(path)\n"
            "    def remove(self, item_id): return {'id': item_id, 'deleted': True}\n"
        ),
        "backend/tests/test_api.py": (
            "import urllib.request\n\n"
            "def test_http_delete_contract():\n"
            "    request = urllib.request.Request('http://127.0.0.1:8000/books/1', method='DELETE')\n"
            "    assert request.get_method() == 'DELETE'\n"
        ),
        "frontend/app.js": (
            "export async function browse(fetchImpl) { return fetchImpl('/books'); }\n"
        ),
        "tests/integration/test_frontend_backend.py": (
            "import urllib.request\n"
            "def test_live_backend_probe():\n"
            "    urllib.request.urlopen('http://127.0.0.1:8000/health')\n"
            "    urllib.request.urlopen('http://127.0.0.1:8000/books')\n"
        ),
    }

    assert tiny_provider_attempts._provider_source_delivery_files_are_functionally_valid(
        files
    ) is True


def test_tiny_fixture_does_not_bypass_runtime_or_compiler_validation() -> None:
    source = Path(tiny_provider_attempts.__file__).read_text(encoding="utf-8")

    assert ".model_construct(" not in source
    assert "build_tiny_real_provider_attempt_fixture" not in source


def test_tiny_execution_packages_compile_from_ticket_graph_contracts() -> None:
    compiled = compile_tiny_implementation_execution_packages(
        build_tiny_ticket_graph_fixture(),
        model="gpt-5.5",
    )

    assert set(compiled.execution_packages) == set(compiled.ticket_graph_fixture.implementation_ticket_ids)
    for ticket_id, execution_package in compiled.execution_packages.items():
        assert execution_package.ticket_ref == ticket_id
        assert execution_package.model_execution_profile.reasoning_effort == "high"
        assert execution_package.model_execution_profile.model == "gpt-5.5"
        assert execution_package.allowed_write_set
        assert all(not path.value.startswith("10-project/") for path in execution_package.allowed_write_set)

    architecture_profile = compiled.model_execution_profiles_by_ticket_id[TICKET_ARCHITECTURE_ID]
    assert architecture_profile.reasoning_effort == "xhigh"


def test_provider_zero_attempt_rejected() -> None:
    compiled = compile_tiny_implementation_execution_packages(
        build_tiny_ticket_graph_fixture(),
        model="gpt-5.5",
    )

    with pytest.raises(TinyProviderAttemptValidationError, match="provider attempt"):
        validate_tiny_provider_attempt_results(
            execution_packages=compiled.execution_packages,
            runtime_results=(),
        )


def test_fallback_source_delivery_rejected() -> None:
    fixture = build_tiny_provider_attempt_fixture(use_fake_results=True)
    first_result = fixture.runtime_results[0]
    fallback_attempt = first_result.provider_attempt.model_copy(
        update={
            "outcome": ProviderAttemptOutcome.FALLBACK_ARTIFACT,
            "fallback_kind": FallbackKind.TOOLING_PREFLIGHT,
        }
    )
    fallback_result = first_result.model_copy(update={"provider_attempt": fallback_attempt})

    with pytest.raises(TinyProviderAttemptValidationError, match="fallback"):
        validate_tiny_provider_attempt_results(
            execution_packages=fixture.execution_packages,
            runtime_results=(fallback_result, *fixture.runtime_results[1:]),
        )


def test_placeholder_artifact_refs_rejected() -> None:
    fixture = build_tiny_provider_attempt_fixture(use_fake_results=True)
    first_result = fixture.runtime_results[0]
    placeholder_attempt = first_result.provider_attempt.model_copy(
        update={
            "raw_output_ref": "provider-artifact.openai.raw.placeholder",
            "parsed_output_ref": "provider-artifact.openai.text.placeholder",
        }
    )
    placeholder_result = first_result.model_copy(update={"provider_attempt": placeholder_attempt})

    with pytest.raises(TinyProviderAttemptValidationError, match="placeholder"):
        validate_tiny_provider_attempt_results(
            execution_packages=fixture.execution_packages,
            runtime_results=(placeholder_result, *fixture.runtime_results[1:]),
        )


def test_fake_fixture_still_proves_runtime_never_emits_ticket_completed() -> None:
    fixture = build_tiny_provider_attempt_fixture(use_fake_results=True)

    for result in fixture.runtime_results:
        assert EventType.PROVIDER_ATTEMPT_RECORDED in tuple(event.event_type for event in result.events)
        assert EventType.WORK_PRODUCT_SUBMITTED in tuple(event.event_type for event in result.events)
        assert EventType.TICKET_COMPLETED not in tuple(event.event_type for event in result.events)


def test_real_provider_retry_reexecutes_failed_ticket_with_real_attempt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    compiled = compile_tiny_implementation_execution_packages(
        build_tiny_ticket_graph_fixture(),
        model="gpt-5.5",
    )
    ticket_id, execution_package = next(iter(compiled.execution_packages.items()))
    artifact_root = tmp_path / "provider-artifacts"
    calls: list[int] = []

    def write_artifact(ref_prefix: str, text: str) -> ProviderArtifactRef:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        ref = ProviderArtifactRef(value=f"{ref_prefix}.{digest}")
        safe_name = ref.value.replace("/", "_").replace("\\", "_").replace(":", "_")
        artifact_root.mkdir(parents=True, exist_ok=True)
        (artifact_root / f"{safe_name}.txt").write_text(text, encoding="utf-8")
        return ref

    def fake_execute(**kwargs):
        calls.append(kwargs["first_fact_graph_version"])
        attempt_id = (
            "provider-attempt.openai.failed.retry-once"
            if len(calls) == 1
            else "provider-attempt.openai.real.retry-success"
        )
        status = (
            ProviderAttemptStatus.FAILED
            if len(calls) == 1
            else ProviderAttemptStatus.SUCCEEDED
        )
        attempt = ProviderAttempt(
            provider_attempt_id=ProviderAttemptRef(value=attempt_id),
            provider=execution_package.model_execution_profile.provider,
            model=execution_package.model_execution_profile.model,
            reasoning_effort=execution_package.model_execution_profile.reasoning_effort,
            input_package_ref=ExecutionPackageRef(
                value=execution_package.execution_package_id.value
            ),
            seat_ref=execution_package.seat_ref,
            role_prompt_hook_ref=execution_package.role_prompt_hook.hook_ref,
            role_prompt_hook_version=execution_package.role_prompt_hook.hook_version,
            role_prompt_hook_sha256=execution_package.role_prompt_hook.content_sha256,
            status=status,
            outcome=ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
            started_at=datetime(2026, 5, 30, 12, 0, tzinfo=UTC),
            finished_at=datetime(2026, 5, 30, 12, 0, 1, tzinfo=UTC),
            raw_output_ref=(
                None
                if status is ProviderAttemptStatus.FAILED
                else write_artifact("provider-artifact.openai.raw.retry", "raw retry success")
            ),
            parsed_output_ref=(
                None
                if status is ProviderAttemptStatus.FAILED
                else write_artifact(
                    "provider-artifact.openai.parsed.retry",
                    json.dumps(
                        {
                            "files": {
                                path.value: _valid_source_file_for_retry(path.value)
                                for path in execution_package.allowed_write_set
                                if path.value
                                not in {"package-contract.json", "run-manifest.json"}
                            }
                        }
                    ),
                )
            ),
            failure_kind=(
                "provider_error.InternalServerError"
                if status is ProviderAttemptStatus.FAILED
                else None
            ),
        )
        if len(calls) == 1:
            return RuntimeExecutionResult(
                provider_attempt=attempt,
                work_product_submission=None,
                verification_runs=(),
                events=(),
                stdout_by_verification_run={},
                stderr_by_verification_run={},
            )
        return RuntimeExecutionResult(
            provider_attempt=attempt,
            work_product_submission=None,
            verification_runs=(),
            events=(),
            stdout_by_verification_run={},
            stderr_by_verification_run={},
        )

    monkeypatch.setattr(tiny_provider_attempts, "_execute_tiny_runtime_package", fake_execute)

    result = tiny_provider_attempts._execute_tiny_runtime_package_with_real_retries(
        ticket_id=ticket_id,
        execution_package=execution_package,
        compiled=compiled,
        resolved_settings=OpenAIProviderSettings(
            api_key="sk-test-secret",
            base_url="https://api.example.invalid/v1",
            model="gpt-5.5",
            api_protocol="chat_completions",
            reasoning_effort="high",
            text_verbosity="low",
            timeout_seconds=60,
        ),
        artifact_root=artifact_root,
        use_fake_results=False,
        first_fact_graph_version=100,
        source_delivery_attempt_limit=2,
    )

    assert result.provider_attempt.status is ProviderAttemptStatus.SUCCEEDED
    assert calls == [100, 1100]


def test_real_provider_retry_reexecutes_invalid_source_delivery_artifact(
    tmp_path: Path,
    monkeypatch,
) -> None:
    compiled = compile_tiny_implementation_execution_packages(
        build_tiny_ticket_graph_fixture(),
        model="gpt-5.5",
    )
    ticket_id, execution_package = next(iter(compiled.execution_packages.items()))
    artifact_root = tmp_path / "provider-artifacts"
    calls: list[int] = []

    def write_artifact(ref_prefix: str, text: str) -> ProviderArtifactRef:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        ref = ProviderArtifactRef(value=f"{ref_prefix}.{digest}")
        safe_name = ref.value.replace("/", "_").replace("\\", "_").replace(":", "_")
        artifact_root.mkdir(parents=True, exist_ok=True)
        (artifact_root / f"{safe_name}.txt").write_text(text, encoding="utf-8")
        return ref

    def fake_execute(**kwargs):
        calls.append(kwargs["first_fact_graph_version"])
        attempt_number = len(calls)
        raw_ref = write_artifact(
            f"provider-artifact.openai.raw.retry-json-{attempt_number}",
            f"raw response {attempt_number}",
        )
        parsed_ref = write_artifact(
            f"provider-artifact.openai.parsed.retry-json-{attempt_number}",
            (
                '{"files":{"backend/app.py":"unterminated"'
                if attempt_number == 1
                else json.dumps(
                    {
                        "files": {
                            path.value: _valid_source_file_for_retry(path.value)
                            for path in execution_package.allowed_write_set
                            if path.value
                            not in {"package-contract.json", "run-manifest.json"}
                        }
                    }
                )
            ),
        )
        attempt = ProviderAttempt(
            provider_attempt_id=ProviderAttemptRef(
                value=f"provider-attempt.openai.real.retry-json-{attempt_number}"
            ),
            provider=execution_package.model_execution_profile.provider,
            model=execution_package.model_execution_profile.model,
            reasoning_effort=execution_package.model_execution_profile.reasoning_effort,
            input_package_ref=ExecutionPackageRef(
                value=execution_package.execution_package_id.value
            ),
            seat_ref=execution_package.seat_ref,
            role_prompt_hook_ref=execution_package.role_prompt_hook.hook_ref,
            role_prompt_hook_version=execution_package.role_prompt_hook.hook_version,
            role_prompt_hook_sha256=execution_package.role_prompt_hook.content_sha256,
            status=ProviderAttemptStatus.SUCCEEDED,
            outcome=ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
            started_at=datetime(2026, 5, 30, 12, 0, tzinfo=UTC),
            finished_at=datetime(2026, 5, 30, 12, 0, 1, tzinfo=UTC),
            raw_output_ref=raw_ref,
            parsed_output_ref=parsed_ref,
        )
        return RuntimeExecutionResult(
            provider_attempt=attempt,
            work_product_submission=None,
            verification_runs=(),
            events=(),
            stdout_by_verification_run={},
            stderr_by_verification_run={},
        )

    monkeypatch.setattr(tiny_provider_attempts, "_execute_tiny_runtime_package", fake_execute)

    result = tiny_provider_attempts._execute_tiny_runtime_package_with_real_retries(
        ticket_id=ticket_id,
        execution_package=execution_package,
        compiled=compiled,
        resolved_settings=OpenAIProviderSettings(
            api_key="sk-test-secret",
            base_url="https://api.example.invalid/v1",
            model="gpt-5.5",
            api_protocol="chat_completions",
            reasoning_effort="high",
            text_verbosity="low",
            timeout_seconds=60,
            max_retries=1,
        ),
        artifact_root=artifact_root,
        use_fake_results=False,
        first_fact_graph_version=100,
        source_delivery_attempt_limit=2,
    )

    assert result.provider_attempt.parsed_output_ref is not None
    assert result.provider_attempt.parsed_output_ref.value.startswith(
        "provider-artifact.openai.parsed.retry-json-2"
    )
    assert calls == [100, 1100]


def test_real_provider_retry_fails_closed_when_all_source_delivery_attempts_invalid(
    tmp_path: Path,
    monkeypatch,
) -> None:
    compiled = compile_tiny_implementation_execution_packages(
        build_tiny_ticket_graph_fixture(),
        model="gpt-5.5",
    )
    ticket_id, execution_package = next(iter(compiled.execution_packages.items()))
    artifact_root = tmp_path / "provider-artifacts"
    calls: list[int] = []

    def write_artifact(ref_prefix: str, text: str) -> ProviderArtifactRef:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        ref = ProviderArtifactRef(value=f"{ref_prefix}.{digest}")
        safe_name = ref.value.replace("/", "_").replace("\\", "_").replace(":", "_")
        artifact_root.mkdir(parents=True, exist_ok=True)
        (artifact_root / f"{safe_name}.txt").write_text(text, encoding="utf-8")
        return ref

    def fake_execute(**kwargs):
        calls.append(kwargs["first_fact_graph_version"])
        attempt_number = len(calls)
        attempt = ProviderAttempt(
            provider_attempt_id=ProviderAttemptRef(
                value=f"provider-attempt.openai.real.always-invalid-{attempt_number}"
            ),
            provider=execution_package.model_execution_profile.provider,
            model=execution_package.model_execution_profile.model,
            reasoning_effort=execution_package.model_execution_profile.reasoning_effort,
            input_package_ref=ExecutionPackageRef(
                value=execution_package.execution_package_id.value
            ),
            seat_ref=execution_package.seat_ref,
            role_prompt_hook_ref=execution_package.role_prompt_hook.hook_ref,
            role_prompt_hook_version=execution_package.role_prompt_hook.hook_version,
            role_prompt_hook_sha256=execution_package.role_prompt_hook.content_sha256,
            status=ProviderAttemptStatus.SUCCEEDED,
            outcome=ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
            started_at=datetime(2026, 5, 30, 12, 0, tzinfo=UTC),
            finished_at=datetime(2026, 5, 30, 12, 0, 1, tzinfo=UTC),
            raw_output_ref=write_artifact(
                f"provider-artifact.openai.raw.always-invalid-{attempt_number}",
                f"raw response {attempt_number}",
            ),
            parsed_output_ref=write_artifact(
                f"provider-artifact.openai.parsed.always-invalid-{attempt_number}",
                '{"files":{"backend/app.py":"missing required files"}}',
            ),
        )
        return RuntimeExecutionResult(
            provider_attempt=attempt,
            work_product_submission=None,
            verification_runs=(),
            events=(),
            stdout_by_verification_run={},
            stderr_by_verification_run={},
        )

    monkeypatch.setattr(tiny_provider_attempts, "_execute_tiny_runtime_package", fake_execute)

    with pytest.raises(TinyProviderAttemptValidationError, match="source delivery"):
        tiny_provider_attempts._execute_tiny_runtime_package_with_real_retries(
            ticket_id=ticket_id,
            execution_package=execution_package,
            compiled=compiled,
            resolved_settings=OpenAIProviderSettings(
                api_key="sk-test-secret",
                base_url="https://api.example.invalid/v1",
                model="gpt-5.5",
                api_protocol="chat_completions",
                reasoning_effort="high",
                text_verbosity="low",
                timeout_seconds=60,
                max_retries=1,
            ),
            artifact_root=artifact_root,
            use_fake_results=False,
            first_fact_graph_version=100,
            source_delivery_attempt_limit=2,
        )

    assert calls == [100, 1100]


def test_sample_provider_attempt_fixture_can_disable_source_delivery_retries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    artifact_root = tmp_path / "provider-artifacts"
    calls_by_input_ref: dict[str, int] = {}

    def write_artifact(ref_prefix: str, text: str) -> ProviderArtifactRef:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        ref = ProviderArtifactRef(value=f"{ref_prefix}.{digest}")
        safe_name = ref.value.replace("/", "_").replace("\\", "_").replace(":", "_")
        artifact_root.mkdir(parents=True, exist_ok=True)
        (artifact_root / f"{safe_name}.txt").write_text(text, encoding="utf-8")
        return ref

    def fake_execute(**kwargs):
        execution_package = kwargs["execution_package"]
        input_ref = execution_package.execution_package_id.value
        calls_by_input_ref[input_ref] = calls_by_input_ref.get(input_ref, 0) + 1
        attempt_number = calls_by_input_ref[input_ref]
        attempt = ProviderAttempt(
            provider_attempt_id=ProviderAttemptRef(
                value=(
                    "provider-attempt.openai.real.sample-invalid-"
                    f"{input_ref}-{attempt_number}"
                )
            ),
            provider=execution_package.model_execution_profile.provider,
            model=execution_package.model_execution_profile.model,
            reasoning_effort=execution_package.model_execution_profile.reasoning_effort,
            input_package_ref=ExecutionPackageRef(value=input_ref),
            seat_ref=execution_package.seat_ref,
            role_prompt_hook_ref=execution_package.role_prompt_hook.hook_ref,
            role_prompt_hook_version=execution_package.role_prompt_hook.hook_version,
            role_prompt_hook_sha256=execution_package.role_prompt_hook.content_sha256,
            status=ProviderAttemptStatus.SUCCEEDED,
            outcome=ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
            started_at=datetime(2026, 5, 30, 12, 0, tzinfo=UTC),
            finished_at=datetime(2026, 5, 30, 12, 0, 1, tzinfo=UTC),
            raw_output_ref=write_artifact(
                f"provider-artifact.openai.raw.sample-invalid-{input_ref}-{attempt_number}",
                f"raw response {input_ref} {attempt_number}",
            ),
            parsed_output_ref=write_artifact(
                f"provider-artifact.openai.parsed.sample-invalid-{input_ref}-{attempt_number}",
                '{"files":{"backend/app.py":"missing required files"}}',
            ),
        )
        return RuntimeExecutionResult(
            provider_attempt=attempt,
            work_product_submission=None,
            verification_runs=(),
            events=(),
            stdout_by_verification_run={},
            stderr_by_verification_run={},
        )

    monkeypatch.setattr(tiny_provider_attempts, "_execute_tiny_runtime_package", fake_execute)

    with pytest.raises(TinyProviderAttemptValidationError, match="source delivery"):
        build_tiny_provider_attempt_fixture(
            settings=OpenAIProviderSettings(
                api_key="sk-test-secret",
                base_url="https://api.example.invalid/v1",
                model="gpt-5.5",
                api_protocol="chat_completions",
                reasoning_effort="high",
                text_verbosity="low",
                timeout_seconds=60,
                max_retries=9,
                artifact_store_root=artifact_root,
            ),
            use_fake_results=False,
            source_delivery_attempt_limit=1,
        )

    assert calls_by_input_ref
    assert set(calls_by_input_ref.values()) == {1}


def test_real_provider_retry_error_reports_ticket_and_failure_kind(
    tmp_path: Path,
    monkeypatch,
) -> None:
    compiled = compile_tiny_implementation_execution_packages(
        build_tiny_ticket_graph_fixture(),
        model="gpt-5.5",
    )
    ticket_id, execution_package = next(iter(compiled.execution_packages.items()))

    def fake_execute(**kwargs):
        attempt = ProviderAttempt(
            provider_attempt_id=ProviderAttemptRef(
                value="provider-attempt.openai.failed.timeout"
            ),
            provider=execution_package.model_execution_profile.provider,
            model=execution_package.model_execution_profile.model,
            reasoning_effort=execution_package.model_execution_profile.reasoning_effort,
            input_package_ref=ExecutionPackageRef(
                value=execution_package.execution_package_id.value
            ),
            seat_ref=execution_package.seat_ref,
            role_prompt_hook_ref=execution_package.role_prompt_hook.hook_ref,
            role_prompt_hook_version=execution_package.role_prompt_hook.hook_version,
            role_prompt_hook_sha256=execution_package.role_prompt_hook.content_sha256,
            status=ProviderAttemptStatus.FAILED,
            outcome=ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
            started_at=datetime(2026, 5, 30, 12, 0, tzinfo=UTC),
            finished_at=datetime(2026, 5, 30, 12, 4, tzinfo=UTC),
            failure_kind="provider_error.APITimeoutError",
        )
        return RuntimeExecutionResult(
            provider_attempt=attempt,
            work_product_submission=None,
            verification_runs=(),
            events=(),
            stdout_by_verification_run={},
            stderr_by_verification_run={},
        )

    monkeypatch.setattr(tiny_provider_attempts, "_execute_tiny_runtime_package", fake_execute)

    with pytest.raises(
        TinyProviderAttemptValidationError,
        match=(
            "ticket-tiny-backend-api.*provider-attempt.openai.failed.timeout"
            ".*provider_error.APITimeoutError"
        ),
    ):
        tiny_provider_attempts._execute_tiny_runtime_package_with_real_retries(
            ticket_id=ticket_id,
            execution_package=execution_package,
            compiled=compiled,
            resolved_settings=OpenAIProviderSettings(
                api_key="sk-test-secret",
                base_url="https://api.example.invalid/v1",
                model="gpt-5.5",
                api_protocol="chat_completions",
                reasoning_effort="high",
                text_verbosity="low",
                timeout_seconds=60,
                max_retries=0,
            ),
            artifact_root=tmp_path / "provider-artifacts",
            use_fake_results=False,
            first_fact_graph_version=100,
            source_delivery_attempt_limit=1,
        )


def _valid_source_file_for_retry(path: str) -> str:
    if path == "backend/app.py":
        return (
            "from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer\n"
            "import json\n"
            "import os\n"
            "from urllib.parse import urlparse\n"
            "from backend.db import BookStore\n\n"
            "DB_PATH = os.environ.get('BOOKS_DB_PATH', 'books.sqlite3')\n\n"
            "def _store():\n"
            "    return BookStore(DB_PATH)\n\n"
            "def create_book(title):\n"
            "    return _store().add_book(title)\n\n"
            "def list_books():\n"
            "    return _store().list_books()\n\n"
            "def checkout_book(book_id):\n"
            "    return _store().set_book_state(book_id, 'CHECKED_OUT')\n\n"
            "def return_book(book_id):\n"
            "    return _store().set_book_state(book_id, 'IN_LIBRARY')\n\n"
            "def delete_book(book_id):\n"
            "    return _store().delete_book(book_id)\n\n"
            "class LibraryHandler(BaseHTTPRequestHandler):\n"
            "    def _send_json(self, status, payload):\n"
            "        body = json.dumps(payload).encode('utf-8')\n"
            "        self.send_response(status)\n"
            "        self.send_header('Content-Type', 'application/json')\n"
            "        self.send_header('Content-Length', str(len(body)))\n"
            "        self.end_headers()\n"
            "        self.wfile.write(body)\n\n"
            "    def do_GET(self):\n"
            "        path = urlparse(self.path).path\n"
            "        if path == '/health':\n"
            "            self._send_json(200, {'status': 'ok'})\n"
            "        elif path == '/books':\n"
            "            self._send_json(200, {'books': _store().list_books()})\n"
            "        else:\n"
            "            self._send_json(404, {'error': 'not found'})\n\n"
            "    def do_POST(self):\n"
            "        path = urlparse(self.path).path\n"
            "        if path == '/books':\n"
            "            self._send_json(201, _store().add_book('Generated'))\n"
            "        elif path.startswith('/books/') and path.endswith('/checkout'):\n"
            "            book_id = int(path.split('/')[2])\n"
            "            self._send_json(200, _store().set_book_state(book_id, 'CHECKED_OUT'))\n"
            "        elif path.startswith('/books/') and path.endswith('/return'):\n"
            "            book_id = int(path.split('/')[2])\n"
            "            self._send_json(200, _store().set_book_state(book_id, 'IN_LIBRARY'))\n"
            "        else:\n"
            "            self._send_json(404, {'error': 'not found'})\n\n"
            "    def do_DELETE(self):\n"
            "        path = urlparse(self.path).path\n"
            "        if path.startswith('/books/'):\n"
            "            book_id = int(path.split('/')[2])\n"
            "            self._send_json(200, {'deleted': _store().delete_book(book_id)})\n"
            "        else:\n"
            "            self._send_json(404, {'error': 'not found'})\n\n"
            "def run():\n"
            "    port = int(os.environ.get('PORT', '8000'))\n"
            "    ThreadingHTTPServer(('127.0.0.1', port), LibraryHandler).serve_forever()\n\n"
            "if __name__ == '__main__':\n"
            "    run()\n"
        )
    if path == "backend/db.py":
        return (
            "import sqlite3\n\n"
            "SCHEMA = \"\"\"\n"
            "CREATE TABLE IF NOT EXISTS books (\n"
            "    id INTEGER PRIMARY KEY,\n"
            "    title TEXT NOT NULL,\n"
            "    state TEXT NOT NULL\n"
            ")\n"
            "\"\"\"\n\n"
            "class BookStore:\n"
            "    def __init__(self, db_path):\n"
            "        self.db_path = str(db_path)\n"
            "    def add_book(self, title):\n"
            "        with sqlite3.connect(self.db_path) as connection:\n"
            "            connection.execute(SCHEMA)\n"
            "            connection.execute('INSERT INTO books(title, state) VALUES (?, ?)', (title, 'IN_LIBRARY'))\n"
            "        return {'id': 1, 'title': title, 'state': 'IN_LIBRARY'}\n"
            "    def list_books(self):\n"
            "        return []\n"
            "    def set_book_state(self, book_id, state):\n"
            "        with sqlite3.connect(self.db_path) as connection:\n"
            "            connection.execute(SCHEMA)\n"
            "            connection.execute('UPDATE books SET state = ? WHERE id = ?', (state, book_id))\n"
            "        return {'id': book_id, 'state': state}\n"
            "    def delete_book(self, book_id):\n"
            "        with sqlite3.connect(self.db_path) as connection:\n"
            "            connection.execute(SCHEMA)\n"
            "            connection.execute('DELETE FROM books WHERE id = ?', (book_id,))\n"
            "        return {'id': book_id, 'deleted': True}\n"
        )
    if path == "frontend/app.js":
        return (
            "const API_BASE = globalThis.BOARDROOM_API_BASE || 'http://127.0.0.1:8000';\n"
            "function apiPath(path) { return `${API_BASE}${path}`; }\n"
            "export async function probeBackend(fetchImpl) { return fetchImpl(apiPath('/health')); }\n"
            "export async function loadBooks(fetchImpl) { return fetchImpl(apiPath('/books')); }\n"
            "export async function deleteBook(fetchImpl, bookId) { "
            "return fetchImpl(apiPath(`/books/${encodeURIComponent(String(bookId))}`), { method: 'DELETE' }); }\n"
        )
    if path == "tests/integration/test_frontend_backend.py":
        return (
            "import os\n"
            "import socket\n"
            "import subprocess\n"
            "import sys\n"
            "import time\n"
            "import urllib.request\n\n"
            "def test_frontend_fetches_live_backend(tmp_path):\n"
            "    sock = socket.socket()\n"
            "    sock.bind(('127.0.0.1', 0))\n"
            "    port = sock.getsockname()[1]\n"
            "    sock.close()\n"
            "    env = dict(os.environ, PORT=str(port), BOOKS_DB_PATH=str(tmp_path / 'books.sqlite3'))\n"
            "    server = subprocess.Popen([sys.executable, '-m', 'backend.app'], env=env)\n"
            "    try:\n"
            "        health_url = f'http://127.0.0.1:{port}/health'\n"
            "        books_url = f'http://127.0.0.1:{port}/books'\n"
            "        for _ in range(50):\n"
            "            try:\n"
            "                urllib.request.urlopen(health_url, timeout=1).read()\n"
            "                break\n"
            "            except OSError:\n"
            "                time.sleep(0.1)\n"
            "        assert urllib.request.urlopen(health_url, timeout=2).status == 200\n"
            "        assert urllib.request.urlopen(books_url, timeout=2).status == 200\n"
            "    finally:\n"
            "        server.terminate()\n"
            "        server.wait(timeout=5)\n"
        )
    if path == "backend/tests/test_api.py":
        return (
            "from backend.app import create_book, delete_book, list_books\n\n"
            "def test_delete_book_removes_book():\n"
            "    book = create_book('Generated')\n"
            "    assert delete_book(book['id'])['deleted'] is True\n"
            "    assert all(item['id'] != book['id'] for item in list_books())\n"
        )
    return f"# generated for {path}\n"


def _valid_source_delivery_files() -> dict[str, str]:
    return {
        path: _valid_source_file_for_retry(path)
        for path in (
            "backend/app.py",
            "backend/db.py",
            "frontend/app.js",
            "backend/tests/test_api.py",
            "tests/integration/test_frontend_backend.py",
        )
    }


def test_provider_source_delivery_accepts_standard_library_http_backend_routes() -> None:
    assert tiny_provider_attempts._provider_source_delivery_files_are_functionally_valid(
        _valid_source_delivery_files()
    ) is True


def test_provider_source_delivery_stage_does_not_enforce_backend_route_shape() -> None:
    files = {
        "backend/app.py": (
            "from backend.db import BookStore\n\n"
            "def create_store(db_path):\n"
            "    return BookStore(db_path)\n\n"
            "def create_book(*args, **kwargs):\n"
            "    raise TypeError('title is required')\n\n"
            "def list_books(*args, **kwargs):\n"
            "    return []\n\n"
            "def checkout_book(*args, **kwargs):\n"
            "    return {}\n\n"
            "def return_book(*args, **kwargs):\n"
            "    return {}\n\n"
            "def delete_book(*args, **kwargs):\n"
            "    return True\n"
        ),
        "backend/db.py": (
            "import sqlite3\n\n"
            "SCHEMA = \"\"\"CREATE TABLE IF NOT EXISTS books ("
            "id INTEGER PRIMARY KEY, title TEXT NOT NULL)\"\"\"\n"
        ),
        "frontend/app.js": (
            "export async function loadBooks(fetchImpl) { return fetchImpl('/books'); }\n"
            "export async function deleteBook(fetchImpl, bookId) { "
            "return fetchImpl(`/books/${bookId}`, { method: 'DELETE' }); }\n"
        ),
        "tests/integration/test_frontend_backend.py": (
            "import subprocess\n\n"
            "def test_frontend_fetches_backend():\n"
            "    calls = []\n"
            "    assert '/books' and 'DELETE'\n"
            "    assert 'loadBooks(' and 'deleteBook('\n"
        ),
    }

    assert tiny_provider_attempts._provider_source_delivery_files_are_functionally_valid(
        files
    ) is True


def test_provider_source_delivery_stage_does_not_enforce_final_integration_evidence() -> None:
    files = _valid_source_delivery_files()
    files["tests/integration/test_frontend_backend.py"] = (
        "import subprocess\n\n"
        "def test_frontend_fetches_backend():\n"
        "    script = \"\"\"\n"
        "import { loadBooks, deleteBook } from './frontend/app.js';\n"
        "const calls = [];\n"
        "const fakeFetch = async (url, options = {}) => { calls.push({ url, options }); return { json: async () => [] }; };\n"
        "await loadBooks(fakeFetch);\n"
        "await deleteBook(fakeFetch, 7);\n"
        "console.log(JSON.stringify(calls));\n"
        "\"\"\"\n"
        "    result = subprocess.run(['node', '--input-type=module', '-e', script], capture_output=True, text=True)\n"
        "    assert result.returncode == 0\n"
        "    assert '/books' in result.stdout\n"
        "    assert 'DELETE' in result.stdout\n"
    )

    assert tiny_provider_attempts._provider_source_delivery_files_are_functionally_valid(
        files
    ) is True


def test_real_provider_retry_graph_versions_stay_globally_monotonic(
    tmp_path: Path,
    monkeypatch,
) -> None:
    artifact_root = tmp_path / "provider-artifacts"
    calls_by_input_ref: dict[str, int] = {}
    first_versions_by_input_ref: dict[str, list[int]] = {}

    def write_artifact(ref_prefix: str, text: str) -> ProviderArtifactRef:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        ref = ProviderArtifactRef(value=f"{ref_prefix}.{digest}")
        safe_name = ref.value.replace("/", "_").replace("\\", "_").replace(":", "_")
        artifact_root.mkdir(parents=True, exist_ok=True)
        (artifact_root / f"{safe_name}.txt").write_text(text, encoding="utf-8")
        return ref

    def fake_execute(**kwargs):
        execution_package = kwargs["execution_package"]
        input_ref = execution_package.execution_package_id.value
        first_versions_by_input_ref.setdefault(input_ref, []).append(
            kwargs["first_fact_graph_version"]
        )
        calls_by_input_ref[input_ref] = calls_by_input_ref.get(input_ref, 0) + 1
        attempt_number = calls_by_input_ref[input_ref]
        raw_ref = write_artifact(
            f"provider-artifact.openai.raw.retry-version-{input_ref}-{attempt_number}",
            f"raw response {input_ref} {attempt_number}",
        )
        parsed_ref = write_artifact(
            f"provider-artifact.openai.parsed.retry-version-{input_ref}-{attempt_number}",
            '{"files":{}}',
        )
        attempt = ProviderAttempt(
            provider_attempt_id=ProviderAttemptRef(
                value=f"provider-attempt.openai.real.retry-version-{input_ref}-{attempt_number}"
            ),
            provider=execution_package.model_execution_profile.provider,
            model=execution_package.model_execution_profile.model,
            reasoning_effort=execution_package.model_execution_profile.reasoning_effort,
            input_package_ref=ExecutionPackageRef(value=input_ref),
            seat_ref=execution_package.seat_ref,
            role_prompt_hook_ref=execution_package.role_prompt_hook.hook_ref,
            role_prompt_hook_version=execution_package.role_prompt_hook.hook_version,
            role_prompt_hook_sha256=execution_package.role_prompt_hook.content_sha256,
            status=ProviderAttemptStatus.SUCCEEDED,
            outcome=ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
            started_at=datetime(2026, 5, 30, 12, 0, tzinfo=UTC),
            finished_at=datetime(2026, 5, 30, 12, 0, 1, tzinfo=UTC),
            raw_output_ref=raw_ref,
            parsed_output_ref=parsed_ref,
        )
        return RuntimeExecutionResult(
            provider_attempt=attempt,
            work_product_submission=None,
            verification_runs=(),
            events=(),
            stdout_by_verification_run={},
            stderr_by_verification_run={},
        )

    monkeypatch.setattr(tiny_provider_attempts, "_execute_tiny_runtime_package", fake_execute)
    first_seen_input_ref: list[str] = []

    def fake_source_delivery_valid(**kwargs):
        input_ref = kwargs["execution_package"].execution_package_id.value
        if input_ref not in first_seen_input_ref:
            first_seen_input_ref.append(input_ref)
        return not (input_ref == first_seen_input_ref[0] and calls_by_input_ref[input_ref] == 1)

    monkeypatch.setattr(
        tiny_provider_attempts,
        "_provider_source_delivery_artifact_is_valid",
        fake_source_delivery_valid,
    )
    monkeypatch.setattr(
        tiny_provider_attempts,
        "validate_tiny_provider_attempt_results",
        lambda **_kwargs: None,
    )

    fixture = build_tiny_provider_attempt_fixture(
        settings=OpenAIProviderSettings(
            api_key="sk-test-secret",
            base_url="https://api.example.invalid/v1",
            model="gpt-5.5",
            api_protocol="chat_completions",
            reasoning_effort="high",
            text_verbosity="low",
            timeout_seconds=60,
            artifact_store_root=artifact_root,
        ),
        use_fake_results=False,
    )

    ordered_input_refs = [
        execution_package.execution_package_id.value
        for execution_package in fixture.execution_packages.values()
    ]
    first_ticket_versions = first_versions_by_input_ref[ordered_input_refs[0]]
    second_ticket_versions = first_versions_by_input_ref[ordered_input_refs[1]]
    assert first_ticket_versions == [
        second_ticket_versions[0] - tiny_provider_attempts._PROVIDER_RETRY_GRAPH_VERSION_STRIDE,
        second_ticket_versions[0]
        - tiny_provider_attempts._PROVIDER_RETRY_GRAPH_VERSION_STRIDE
        + 1000,
    ]
    assert first_ticket_versions[-1] < second_ticket_versions[0]


def test_real_provider_records_attempts_for_every_tiny_implementation_ticket() -> None:
    settings = openai_settings_from_test_env()

    fixture = build_tiny_provider_attempt_fixture(
        settings=settings,
        use_fake_results=False,
    )

    assert set(fixture.provider_attempts_by_ticket_id) == set(fixture.execution_packages)
    assert len(fixture.runtime_results) == 4
    for ticket_id, attempt in fixture.provider_attempts_by_ticket_id.items():
        execution_package = fixture.execution_packages[ticket_id]
        assert attempt.status is ProviderAttemptStatus.SUCCEEDED
        assert attempt.outcome is ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT
        assert attempt.provider == execution_package.model_execution_profile.provider
        assert attempt.model == settings.model
        assert attempt.reasoning_effort == "high"
        assert attempt.input_package_ref.value == execution_package.execution_package_id.value
        assert attempt.seat_ref == execution_package.seat_ref
        assert attempt.raw_output_ref is not None
        assert attempt.parsed_output_ref is not None
        assert len(attempt.raw_output_ref.value.rsplit(".", 1)[-1]) == 64
        assert len(attempt.parsed_output_ref.value.rsplit(".", 1)[-1]) == 64
