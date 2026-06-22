from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from boardroom_os.evidence.blackbox_plan import (
    BlackboxPlanAction,
    BlackboxPlanActionKind,
    BlackboxVerificationPlan,
    BlackboxVerificationPlanRef,
)
from boardroom_os.agents.profiles import ModelExecutionProfile, ModelExecutionProfileId
from boardroom_os.agents.role_prompt_hooks import (
    RolePromptHookRef,
    RolePromptHookSha256,
)
from boardroom_os.agents.seat import AgentSeatRef
from boardroom_os.contracts.evidence_obligation import (
    EvidenceObligation,
    RequiredArtifactType,
    RequiredVerifier,
)
from boardroom_os.contracts.types import (
    AcceptanceRef,
    ContractId,
    EvidenceObligationRef,
    SourceSurfaceRef,
)
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.package import ContextRef, ExecutionPackageRef
from boardroom_os.providers.attempt import (
    ProviderArtifactRef,
    ProviderAttempt,
    ProviderAttemptOutcome,
    ProviderAttemptStatus,
)
from boardroom_os.proving.v2_100f_native_manifest_rework import (
    V2_100FNativeManifestReworkInput,
    V2_100FTerminalStatus,
    _OpenAIBlackboxPlanProviderAdapter,
    _blackbox_provider_prompt,
    run_v2_100f_native_manifest_rework,
)
from boardroom_os.providers.openai_adapter import FileProviderOutputStore


def test_v2_100f_native_orchestration_projects_graph_plan_facts_and_rework(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    workspace_root = tmp_path / "workspace"

    result = run_v2_100f_native_manifest_rework(
        V2_100FNativeManifestReworkInput(
            output_root=output_root,
            workspace_root=workspace_root,
            run_manifest_artifact=_manifest_with_novel_assertion(),
            require_real_provider=False,
            deterministic_provider_fixture=True,
            http_status=404,
        )
    )

    assert result.terminal_status is V2_100FTerminalStatus.REWORK_REQUIRED
    assert result.verify_blackbox_ticket_ref == "ticket.verify-blackbox.generated"
    assert result.before_graph_ref == "ticket-graph.v2-100f.before"
    assert result.seat_assignment_ref == "seat-assignment.v2-100f.graph-2"
    assert result.execution_package_ref.startswith("exec.ticket.verify-blackbox.generated.graph-")
    assert result.provider_attempt_ref.startswith("provider-attempt.v2-100f.blackbox.")
    assert result.blackbox_plan_ref == "blackbox-plan.v2-100f.verify"
    assert result.fact_refs
    assert result.rework_request_ref is not None
    assert result.blocked_reason_code is None
    assert result.raw_assertion_types == ("json_array_contains_field",)
    assert result.verify_blackbox_ready_before_execution is True
    assert result.assigned_seat_ref == "seat.tester.integration"
    assert "context.run-manifest.generated.raw" in result.execution_context_refs
    assert "contract.package.tiny-fullstack" in result.execution_context_refs
    assert "contract.acceptance.tiny-fullstack" in result.execution_context_refs
    assert "docs/README.md" in result.execution_context_refs
    assert "surface.backend-api" in result.execution_context_refs
    assert "failure.raw-run-error" in result.execution_context_refs
    assert result.rework_issue_codes == ("run_manifest_error",)

    request_path = output_root / "20-evidence" / "v2-100f-native" / "rework-request.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    assert request["issues"][0]["issue_code"] == "run_manifest_error"
    assert request["issues"][0]["advisory_context"]["raw_assertion_types"] == [
        "json_array_contains_field"
    ]


def test_v2_100f_native_orchestration_passes_when_approved_fact_passes(
    tmp_path: Path,
) -> None:
    result = run_v2_100f_native_manifest_rework(
        V2_100FNativeManifestReworkInput(
            output_root=tmp_path / "output",
            workspace_root=tmp_path / "workspace",
            run_manifest_artifact=_manifest_with_novel_assertion(),
            require_real_provider=False,
            deterministic_provider_fixture=True,
            http_status=200,
        )
    )

    assert result.terminal_status is V2_100FTerminalStatus.PASSED
    assert result.rework_request_ref is None
    assert result.fact_refs


def test_v2_100f_native_orchestration_blocks_without_provider_permission(
    tmp_path: Path,
) -> None:
    result = run_v2_100f_native_manifest_rework(
        V2_100FNativeManifestReworkInput(
            output_root=tmp_path / "output",
            workspace_root=tmp_path / "workspace",
            run_manifest_artifact=_manifest_with_novel_assertion(),
            require_real_provider=True,
            deterministic_provider_fixture=True,
            http_status=404,
        )
    )

    assert result.terminal_status is V2_100FTerminalStatus.BLOCKED_OR_ESCALATED
    assert result.blocked_reason_code == "real_provider_required"
    assert result.provider_attempt_ref is None
    assert result.blackbox_plan_ref is None
    assert result.fact_refs == ()


def test_v2_100f_native_orchestration_accepts_provider_backed_plan_adapter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOARDROOM_RUN_REAL_PROVIDER_TESTS", "1")
    monkeypatch.setenv("BOARDROOM_RUN_REAL_PROVIDER_PROVING", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")

    result = run_v2_100f_native_manifest_rework(
        V2_100FNativeManifestReworkInput(
            output_root=tmp_path / "output",
            workspace_root=tmp_path / "workspace",
            run_manifest_artifact=_manifest_with_novel_assertion(),
            require_real_provider=True,
            deterministic_provider_fixture=False,
            runtime_config_path="config/boardroom-runtime.v2-090f.yaml",
            providers_config_path="config/boardroom-providers.v2-090f.yaml",
            roles_config_path="config/boardroom-roles.v2-090f.yaml",
        ),
        provider_adapter=_ProviderBackedPlanAdapter(),
    )

    assert result.terminal_status is V2_100FTerminalStatus.REWORK_REQUIRED
    assert result.blocked_reason_code is None
    assert result.execution_package_ref is not None
    assert result.provider_attempt_ref == "provider-attempt.openai.real.v2-100f-test"
    assert result.blackbox_plan_ref == "blackbox-plan.v2-100f.provider-backed-test"
    assert result.raw_error is None


def test_v2_100f_native_orchestration_blocks_real_provider_without_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOARDROOM_RUN_REAL_PROVIDER_TESTS", "1")
    monkeypatch.setenv("BOARDROOM_RUN_REAL_PROVIDER_PROVING", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = run_v2_100f_native_manifest_rework(
        V2_100FNativeManifestReworkInput(
            output_root=tmp_path / "output",
            workspace_root=tmp_path / "workspace",
            run_manifest_artifact=_manifest_with_novel_assertion(),
            require_real_provider=True,
            deterministic_provider_fixture=False,
            runtime_config_path="config/boardroom-runtime.v2-090f.yaml",
            providers_config_path="config/boardroom-providers.v2-090f.yaml",
            roles_config_path="config/boardroom-roles.v2-090f.yaml",
        )
    )

    assert result.terminal_status is V2_100FTerminalStatus.BLOCKED_OR_ESCALATED
    assert result.blocked_reason_code == "provider_secret_missing"
    assert result.provider_attempt_ref is None
    assert result.blackbox_plan_ref is None


def test_v2_100f_native_orchestration_requires_explicit_local_fixture(
    tmp_path: Path,
) -> None:
    result = run_v2_100f_native_manifest_rework(
        V2_100FNativeManifestReworkInput(
            output_root=tmp_path / "output",
            workspace_root=tmp_path / "workspace",
            run_manifest_artifact=_manifest_with_novel_assertion(),
            require_real_provider=False,
            deterministic_provider_fixture=False,
        )
    )

    assert result.terminal_status is V2_100FTerminalStatus.BLOCKED_OR_ESCALATED
    assert result.blocked_reason_code == "deterministic_provider_fixture_required"
    assert result.provider_attempt_ref is None
    assert result.blackbox_plan_ref is None


def test_v2_100f_openai_adapter_reads_provider_authored_plan_json(tmp_path: Path) -> None:
    adapter = object.__new__(_OpenAIBlackboxPlanProviderAdapter)
    store = FileProviderOutputStore(root=tmp_path / "provider-artifacts")
    parsed = store.write_text(
        response_id="resp-v2-100f",
        artifact_kind="parsed",
        text=json.dumps(_provider_plan_payload()),
    )
    adapter._artifact_store = store
    package = _execution_package_for_provider_plan()
    attempt = _ProviderBackedPlanAdapter().invoke(
        _ProviderRequestStub(execution_package_ref=package.execution_package_id)
    )
    attempt = attempt.model_copy(update={"parsed_output_ref": parsed.artifact_ref})

    plan = adapter.blackbox_plan_for_attempt(
        attempt=attempt,
        execution_package=package,
    )

    assert plan.execution_package_ref == package.execution_package_id
    assert plan.producer_attempt_ref == attempt.provider_attempt_id
    assert plan.actions[0].action_kind is BlackboxPlanActionKind.HTTP


def test_v2_100f_openai_adapter_overrides_provider_lineage_fields(tmp_path: Path) -> None:
    adapter = object.__new__(_OpenAIBlackboxPlanProviderAdapter)
    store = FileProviderOutputStore(root=tmp_path / "provider-artifacts")
    payload = {
        **_provider_plan_payload(),
        "execution_package_ref": "exec.provider.hallucinated",
        "producer_attempt_ref": "provider-attempt.provider.hallucinated",
        "producer_seat_ref": "seat.provider.hallucinated",
        "role_prompt_hook_ref": "role-prompt-hook.provider.hallucinated",
    }
    parsed = store.write_text(
        response_id="resp-v2-100f-lineage",
        artifact_kind="parsed",
        text=json.dumps(payload),
    )
    adapter._artifact_store = store
    package = _execution_package_for_provider_plan()
    attempt = _ProviderBackedPlanAdapter().invoke(
        _ProviderRequestStub(execution_package_ref=package.execution_package_id)
    ).model_copy(update={"parsed_output_ref": parsed.artifact_ref})

    plan = adapter.blackbox_plan_for_attempt(
        attempt=attempt,
        execution_package=package,
    )

    assert plan.execution_package_ref == package.execution_package_id
    assert plan.producer_attempt_ref == attempt.provider_attempt_id
    assert plan.producer_seat_ref == package.seat_ref
    assert plan.role_prompt_hook_ref == package.role_prompt_hook.hook_ref


def test_v2_100f_openai_prompt_requests_blackbox_plan_schema() -> None:
    prompt = _blackbox_provider_prompt("baseline tester prompt with negative_tests")

    assert '"plan_id": "blackbox-plan.v2-100f.verify"' in prompt
    assert '"actions": [' in prompt
    assert "Output JSON only" in prompt
    assert "Do not include negative_tests" in prompt


def test_v2_100f_active_path_has_no_forbidden_shortcuts() -> None:
    root = Path(__file__).resolve().parents[2]
    active_paths = (
        root / "src/boardroom_os/proving/v2_100f_native_manifest_rework.py",
        root / "src/boardroom_os/orchestration/prd_delivery.py",
        root / "src/boardroom_os/proving/v2_090f_native_golden_sample.py",
        root / "scripts/run_v2_100f_native_manifest_rework.py",
    )
    forbidden = (
        "run_v2_100_rework_loop_for_request",
        "build_v2_100_resettable_fixture",
        "build_current_run_provider_recheck_input",
        "_write_minimal_package",
        "v2-090k-failure-snapshot",
    )

    for path in active_paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text


def test_v2_100f_cli_rejects_non_v2_090f_config_paths() -> None:
    from scripts.run_v2_100f_native_manifest_rework import _require_expected_config_paths

    with pytest.raises(SystemExit) as error:
        _require_expected_config_paths(
            {
                "BOARDROOM_RUNTIME_CONFIG": "config/other.yaml",
                "BOARDROOM_PROVIDERS_CONFIG": "config/boardroom-providers.v2-090f.yaml",
                "BOARDROOM_ROLES_CONFIG": "config/boardroom-roles.v2-090f.yaml",
            }
        )

    assert "BOARDROOM_RUNTIME_CONFIG" in str(error.value)


def _manifest_with_novel_assertion() -> dict[str, object]:
    return {
        "run_manifest_id": "run-manifest.v2-100f.generated",
        "commands": [
            {
                "command_id": "test.backend",
                "command": ["python", "-m", "pytest"],
                "cwd": ".",
            }
        ],
        "service_contracts": [
            {
                "service_id": "service.backend",
                "command_id": "run.backend",
                "readiness": {"path": "/ready"},
            }
        ],
        "behavioral_probes": [
            {
                "probe_id": "probe.books.list",
                "steps": [
                    {
                        "step_id": "step.books.list",
                        "method": "GET",
                        "path": "/api/books",
                        "expected_status": 200,
                        "assertions": [
                            {
                                "type": "json_array_contains_field",
                                "path": "$",
                                "field": "title",
                            }
                        ],
                    }
                ],
            }
        ],
    }


class _ProviderBackedPlanAdapter:
    def invoke(self, request: Any) -> ProviderAttempt:
        started_at = datetime.now(UTC)
        return ProviderAttempt(
            provider_attempt_id=ProviderAttemptRef(
                value="provider-attempt.openai.real.v2-100f-test"
            ),
            provider=request.model_execution_profile.provider,
            model=request.model_execution_profile.model,
            reasoning_effort=request.model_execution_profile.reasoning_effort,
            input_package_ref=request.execution_package_ref,
            seat_ref=request.seat_ref,
            role_prompt_hook_ref=request.role_prompt_hook_ref,
            role_prompt_hook_version=request.role_prompt_hook_version,
            role_prompt_hook_sha256=request.role_prompt_hook_sha256,
            status=ProviderAttemptStatus.SUCCEEDED,
            outcome=ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            raw_output_ref=ProviderArtifactRef(value="provider-artifact.openai.raw.v2-100f-test"),
            parsed_output_ref=ProviderArtifactRef(
                value="provider-artifact.openai.parsed.v2-100f-test"
            ),
        )

    def blackbox_plan_for_attempt(
        self,
        *,
        attempt: ProviderAttempt,
        execution_package: Any,
    ) -> BlackboxVerificationPlan:
        run_manifest_ref = ContextRef(value="context.run-manifest.generated.raw")
        package_contract_ref = ContextRef(value="contract.package.tiny-fullstack")
        return BlackboxVerificationPlan(
            plan_id=BlackboxVerificationPlanRef(
                value="blackbox-plan.v2-100f.provider-backed-test"
            ),
            execution_package_ref=ExecutionPackageRef(
                value=execution_package.execution_package_id.value
            ),
            producer_attempt_ref=attempt.provider_attempt_id,
            producer_seat_ref=execution_package.seat_ref,
            role_prompt_hook_ref=execution_package.role_prompt_hook.hook_ref,
            objective="Verify generated package behavior through provider-authored blackbox actions.",
            input_context_refs=execution_package.context_refs,
            run_manifest_context_ref=run_manifest_ref,
            acceptance_refs=execution_package.acceptance_refs,
            package_contract_ref=package_contract_ref,
            actions=(
                BlackboxPlanAction(
                    action_id="action.http.books",
                    action_kind=BlackboxPlanActionKind.HTTP,
                    description="Probe the books API declared by the generated run manifest.",
                    acceptance_refs=execution_package.acceptance_refs,
                    input_refs=(run_manifest_ref,),
                    method="GET",
                    url="http://127.0.0.1:8000/api/books",
                    required_permissions=("http.request",),
                    expected_observations=("HTTP status and response body shape.",),
                ),
            ),
            evidence_obligation_refs=tuple(
                obligation.evidence_obligation_id
                for obligation in execution_package.evidence_obligations
            ),
            created_at=datetime.now(UTC),
        )


def _execution_package_for_provider_plan() -> Any:
    return _ExecutionPackageStub()


class _ExecutionPackageStub:
    def __init__(self) -> None:
        self.execution_package_id = ExecutionPackageRef(
            value="exec.ticket.verify-blackbox.generated.graph-2"
        )
        self.seat_ref = AgentSeatRef(value="seat.tester.integration")
        self.role_prompt_hook = _RolePromptHookStub()
        self.context_refs = (
            ContextRef(value="context.run-manifest.generated.raw"),
            ContextRef(value="context.run-manifest.generated.skeleton"),
            ContextRef(value="contract.package.tiny-fullstack"),
            ContextRef(value="contract.acceptance.tiny-fullstack"),
            ContextRef(value="docs/README.md"),
            ContextRef(value="docs/RUNBOOK.md"),
            ContextRef(value="surface.backend-api"),
            ContextRef(value="failure.raw-run-error"),
        )
        self.acceptance_refs = (AcceptanceRef(value="AC-LIVE-BLACKBOX"),)
        self.evidence_obligations = (
            EvidenceObligation(
                evidence_obligation_id=EvidenceObligationRef(
                    value="evidence.live-blackbox"
                ),
                acceptance_refs=self.acceptance_refs,
                source_surface_refs=(SourceSurfaceRef(value="surface.backend-api"),),
                required_artifact_type=RequiredArtifactType(value="live_blackbox_integration"),
                required_verifier=RequiredVerifier(value="live_blackbox"),
                blocking=True,
            ),
        )


class _RolePromptHookStub:
    hook_ref = RolePromptHookRef(value="role-prompt-hook.baseline.tester.v1")


class _ProviderRequestStub:
    def __init__(self, *, execution_package_ref: ExecutionPackageRef) -> None:
        self.execution_package_ref = execution_package_ref
        self.seat_ref = AgentSeatRef(value="seat.tester.integration")
        self.model_execution_profile = ModelExecutionProfile(
            model_execution_profile_id=ModelExecutionProfileId(value="model.tester.integration"),
            provider="openai-compatible",
            model="gpt-verifier",
            reasoning_effort="high",
            context_window=200000,
            temperature=0.2,
            tool_permissions=("http.request",),
            fallback_policy_ref=ContractId(value="fallback.verification.record_failure"),
        )
        self.role_prompt_hook_ref = RolePromptHookRef(value="role-prompt-hook.baseline.tester.v1")
        self.role_prompt_hook_version = "v1"
        self.role_prompt_hook_sha256 = RolePromptHookSha256(value="0" * 64)


def _provider_plan_payload() -> dict[str, Any]:
    return {
        "objective": "Verify generated package behavior through provider-authored blackbox actions.",
        "input_context_refs": [
            "context.run-manifest.generated.raw",
            "context.run-manifest.generated.skeleton",
            "contract.package.tiny-fullstack",
            "contract.acceptance.tiny-fullstack",
            "docs/README.md",
            "docs/RUNBOOK.md",
            "surface.backend-api",
            "failure.raw-run-error",
        ],
        "run_manifest_context_ref": "context.run-manifest.generated.raw",
        "acceptance_refs": ["AC-LIVE-BLACKBOX"],
        "package_contract_ref": "contract.package.tiny-fullstack",
        "actions": [
            {
                "action_id": "action.http.books",
                "action_kind": "http",
                "description": "Probe the books API declared by the generated run manifest.",
                "acceptance_refs": ["AC-LIVE-BLACKBOX"],
                "input_refs": ["context.run-manifest.generated.raw"],
                "method": "GET",
                "url": "http://127.0.0.1:8000/api/books",
                "required_permissions": ["http.request"],
                "expected_observations": ["HTTP status and response body shape."],
            }
        ],
        "evidence_obligation_refs": ["evidence.live-blackbox"],
        "created_at": datetime.now(UTC).isoformat(),
    }
