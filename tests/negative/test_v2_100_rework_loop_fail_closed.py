from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
import yaml

from boardroom_os.contracts.evidence_obligation import RequiredArtifactType
from boardroom_os.contracts.types import AcceptanceRef, ContractId, EvidenceObligationRef, SourceSurfaceRef
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import ActorRef, EventId, EventPayloadRef, EventType, ProjectRef
from boardroom_os.agents.seat import AgentSeatRef
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.fallback import FallbackKind
from boardroom_os.providers.openai_adapter import OpenAIProviderSettings
from boardroom_os.agents.profiles import ModelExecutionProfile
from boardroom_os.providers.openai_adapter import FileProviderOutputStore
from boardroom_os.providers.attempt import (
    ProviderAttempt,
    ProviderAttemptOutcome,
    ProviderAttemptStatus,
)
from boardroom_os.reducers.rework import (
    ReworkProjection,
    ReworkReducer,
    ReworkReducerError,
    ReworkTerminalStatus,
    ReworkRequestPayload,
    ReworkTerminalPayload,
)
from boardroom_os.rework.model import (
    BlockerRef,
    ReworkActorKind,
    ReworkCycleId,
    ReworkIssue,
    ReworkIssueCode,
    ReworkIssueId,
    ReworkIssueSeverity,
    ReworkOutcome,
    ReworkOutcomeId,
    ReworkOutcomeStatus,
    ReworkRequest,
    ReworkRequestId,
    ReworkSuspectedDomain,
    ReworkCycleStatus,
    RunId,
)
from tests.config.test_boardroom_config import _write_config_files
from tests.fixtures.execution.role_prompt_hooks import baseline_role_prompt_hook_fields

from boardroom_os.proving.v2_100_rework_loop import (
    V2_100PayloadManifestEntry,
    V2_100ReworkLoopError,
    V2_100ScenarioResult,
    V2_100ScenarioRoundResult,
    V2_100ScenarioInput,
    V2_100ScenarioTerminalStatus,
    _assert_role_package_provider_binding,
    _rebind_recheck_provider_attempt,
    load_v2_100e_openai_settings,
    provider_attempt_manifest_entry,
    project_snapshot_request,
    run_v2_100_rework_round,
    run_v2_100_rework_loop_scenario,
    validate_loop_budget,
    validate_real_provider_attempt,
    validate_real_provider_recheck_input,
    validate_v2_100e_provider_json_settings,
)
from tests.execution.test_provider_executor import _execution_package


NOW = datetime(2026, 6, 15, 8, 0, tzinfo=UTC)
PROJECT = ProjectRef(value="project.v2-100e")
BLOCKER = BlockerRef(value="blocker.v2-100e.behavioral-probe")
CYCLE = ReworkCycleId(value="rework-cycle.v2-100e")
OUTCOME_ID = ReworkOutcomeId(value="rework-outcome.v2-100e.accepted")
ACTIVE_ACCEPTANCE_REFS = (
    "acceptance.v2-100e.rework.blocker",
    "acceptance.v2-100e.rework.provider",
    "acceptance.v2-100e.rework.reducer",
    "acceptance.v2-100e.rework.budget",
)


def _input(tmp_path: Path, **overrides: object) -> V2_100ScenarioInput:
    snapshot = tmp_path / "failure-summary.json"
    snapshot.write_text('{"run_id":"run.v2-100e","failed":true}\n', encoding="utf-8")
    provider_env = Path(overrides.get("provider_env_path", tmp_path / ".env"))
    if "provider_env_path" not in overrides and not provider_env.exists():
        provider_env.write_text("OPENAI_API_KEY=sk-test-secret\n", encoding="utf-8")
    fields: dict[str, object] = {
        "project_ref": "project.v2-100e",
        "snapshot_summary_path": snapshot,
        "run_id": "run.v2-100e",
        "cycle_id": "rework-cycle.v2-100e",
        "package_contract_ref": "package.v2-100e",
        "run_manifest_ref": "run-manifest.v2-100e",
        "active_acceptance_refs": ACTIVE_ACCEPTANCE_REFS,
        "active_source_surface_refs": ("surface.generated.fullstack",),
        "active_evidence_obligation_refs": ("evidence.live.integration",),
        "active_contract_refs": ("acceptance.v2-100e", "package.v2-100e"),
        "initial_graph_version": 40,
        "max_rounds": 2,
        "provider_env_path": provider_env,
        "require_real_provider": True,
    }
    fields.update(overrides)
    return V2_100ScenarioInput(**fields)


def _provider_env(tmp_path: Path, *, stale: bool = False) -> Path:
    paths = _write_config_files(tmp_path)
    _force_json_object_response_format(paths.providers_config)
    env_path = tmp_path / ".env"
    lines = [
        f"BOARDROOM_RUNTIME_CONFIG={paths.runtime_config.as_posix()}",
        f"BOARDROOM_PROVIDERS_CONFIG={paths.providers_config.as_posix()}",
        f"BOARDROOM_ROLES_CONFIG={paths.roles_config.as_posix()}",
        "OPENAI_API_KEY=sk-test-secret",
    ]
    if stale:
        lines.append("BOARDROOM_OPENAI_MODEL=gpt-5.5")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return env_path


def _force_json_object_response_format(path: Path) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("providers config must be a YAML mapping")
    providers = data.get("providers")
    if not isinstance(providers, list):
        raise ValueError("providers config must include providers list")
    for provider in providers:
        if not isinstance(provider, dict):
            raise ValueError("provider entries must be YAML mappings")
        provider["response_format"] = {"type": "json_object"}
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _prepend_decoy_provider(path: Path) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("providers config must be a YAML mapping")
    providers = data.get("providers")
    if not isinstance(providers, list):
        raise ValueError("providers config must include providers list")
    providers.insert(
        0,
        {
            "provider_profile_id": "provider.openai-compatible.decoy",
            "provider_type": "openai_compatible",
            "provider_label": "decoy-openai-compatible",
            "base_url": "https://decoy.example.invalid/v1",
            "api_key_env": "OPENAI_API_KEY",
            "model": "decoy-model",
            "context_window_tokens": 400000,
            "max_output_tokens": 128000,
            "stream_idle_timeout_seconds": 120,
            "total_timeout_seconds": 600,
            "reasoning_effort": "minimal",
            "temperature": None,
            "top_p": None,
            "presence_penalty": None,
            "frequency_penalty": None,
            "seed": None,
            "stop": None,
            "response_format": {"type": "json_object"},
            "stream_options": None,
            "service_tier": None,
            "user": "boardroom-os",
        },
    )
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _event(
    event_type: EventType,
    *,
    graph_version: int,
    actor_ref: str,
    payload_ref: str,
) -> EventRecord:
    return EventRecord(
        event_id=EventId(value=f"event.v2-100e.{event_type.value}.{graph_version}"),
        event_type=event_type,
        project_ref=PROJECT,
        actor_ref=ActorRef(value=actor_ref),
        timestamp=NOW,
        graph_version=graph_version,
        payload_refs=(EventPayloadRef(value=payload_ref),),
    )


def _request() -> ReworkRequest:
    return ReworkRequest(
        rework_request_id=ReworkRequestId(value="rework-request.v2-100e"),
        cycle_id=CYCLE,
        run_id=RunId(value="run.v2-100e"),
        request_source_refs=("final-evidence-table.v2-100e.failed",),
        issues=(
            ReworkIssue(
                issue_id=ReworkIssueId(value="rework-issue.v2-100e.behavioral-probe"),
                blocker_refs=(BLOCKER,),
                issue_code=ReworkIssueCode.PROBE_RESPONSE_SHAPE_MISMATCH,
                severity=ReworkIssueSeverity.BLOCKING,
                acceptance_refs=(AcceptanceRef(value="acceptance.v2-100e.rework.reducer"),),
                source_surface_refs=(SourceSurfaceRef(value="surface.generated.fullstack"),),
                run_manifest_refs=("run-manifest.v2-100e",),
                evidence_obligation_refs=(EvidenceObligationRef(value="evidence.live.integration"),),
                suspected_domains=(ReworkSuspectedDomain.IMPLEMENTATION,),
                required_artifact_types=(RequiredArtifactType(value="live_blackbox_integration"),),
                description="Runtime must not mark rework accepted without governance review.",
            ),
        ),
        requested_by_actor=ReworkActorKind.CHECKER,
        requested_at=NOW,
        active_contract_refs=(ContractId(value="acceptance.v2-100e"),),
        active_graph_version=40,
    )


class _RuntimeDirectAcceptanceResolver:
    def resolve_rework_request(self, payload_ref: EventPayloadRef) -> ReworkRequestPayload:
        if payload_ref.value != "payload:request":
            raise KeyError(payload_ref.value)
        return ReworkRequestPayload(request=_request())

    def resolve_rework_terminal(self, payload_ref: EventPayloadRef) -> ReworkTerminalPayload:
        if payload_ref.value != "payload:rework_accepted":
            raise KeyError(payload_ref.value)
        return ReworkTerminalPayload(
            cycle_id=CYCLE,
            outcome_ref=OUTCOME_ID,
            accepted_blocker_refs=(BLOCKER,),
            remaining_blocker_refs=(),
        )

    def resolve_rework_plan(self, payload_ref: EventPayloadRef) -> object:
        raise AssertionError(f"unexpected rework plan payload: {payload_ref.value}")

    def resolve_graph_patch_review(self, payload_ref: EventPayloadRef) -> object:
        raise AssertionError(f"unexpected graph patch review payload: {payload_ref.value}")

    def resolve_graph_patch_approval(self, payload_ref: EventPayloadRef) -> object:
        raise AssertionError(f"unexpected graph patch approval payload: {payload_ref.value}")

    def resolve_rework_ticket_created(self, payload_ref: EventPayloadRef) -> object:
        raise AssertionError(f"unexpected rework ticket payload: {payload_ref.value}")

    def resolve_rework_attempt(self, payload_ref: EventPayloadRef) -> object:
        raise AssertionError(f"unexpected rework attempt payload: {payload_ref.value}")

    def resolve_rework_review(self, payload_ref: EventPayloadRef) -> object:
        raise AssertionError(f"unexpected rework review payload: {payload_ref.value}")


def _provider_attempt(
    *,
    provider_attempt_id: str = "provider-attempt.v2-100e.worker.1",
    provider: str = "openai-compatible",
    model: str = "gpt-5.5",
    reasoning_effort: str = "high",
    input_package_ref: str = "execution-package.v2-100e.rework.1",
    seat_ref: str = "seat.worker.implementation",
    status: ProviderAttemptStatus = ProviderAttemptStatus.SUCCEEDED,
    outcome: ProviderAttemptOutcome = ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
    fallback_kind: FallbackKind | None = None,
    raw_output_ref: str | None = "provider-artifact.openai.raw.real.0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    parsed_output_ref: str | None = "provider-artifact.openai.parsed.real.abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
    failure_kind: str | None = None,
) -> ProviderAttempt:
    fields: dict[str, object] = {
        "provider_attempt_id": ProviderAttemptRef(value=provider_attempt_id),
        "provider": provider,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "input_package_ref": input_package_ref,
        "seat_ref": seat_ref,
        **baseline_role_prompt_hook_fields(),
        "status": status,
        "outcome": outcome,
        "started_at": NOW,
        "finished_at": NOW,
    }
    if fallback_kind is not None:
        fields["fallback_kind"] = fallback_kind
    if raw_output_ref is not None:
        fields["raw_output_ref"] = raw_output_ref
    if parsed_output_ref is not None:
        fields["parsed_output_ref"] = parsed_output_ref
    if failure_kind is not None:
        fields["failure_kind"] = failure_kind
    return ProviderAttempt(**fields)


def test_missing_snapshot_file_is_rejected(tmp_path: Path) -> None:
    missing = tmp_path / "missing" / "failure-summary.json"

    with pytest.raises(ValueError, match="failure-summary.json"):
        _input(tmp_path, snapshot_summary_path=missing)


def test_project_snapshot_request_validates_projected_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import boardroom_os.proving.v2_100_rework_loop as loop_module

    scenario_input = _input(tmp_path)
    bad_request = _request().model_copy(update={"run_id": RunId(value="run.v2-100e.other")})
    monkeypatch.setattr(
        loop_module,
        "project_v2_090k_failure_summary",
        lambda _path, _context: bad_request,
    )

    with pytest.raises(ValueError, match="run_id mismatch"):
        project_snapshot_request(scenario_input)


def test_run_loop_scenario_accepts_round_provider_keyword(tmp_path: Path) -> None:
    from boardroom_os.proving.v2_100_resettable_fixture import build_v2_100_scenario_input

    scenario_input = build_v2_100_scenario_input(
        package_root=tmp_path / "package",
        require_real_provider=False,
    )

    with pytest.raises(ValueError, match="round_provider is required"):
        run_v2_100_rework_loop_scenario(scenario_input, round_provider=None)


def test_role_package_provider_binding_rejects_execution_package_profile_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BOARDROOM_OPENAI_MODEL", raising=False)
    scenario_input = _input(tmp_path, provider_env_path=_provider_env(tmp_path))
    execution_package = _execution_package().model_copy(
        update={
            "seat_ref": AgentSeatRef(value="seat.worker.implementation"),
            "model_execution_profile": ModelExecutionProfile(
                model_execution_profile_id="model-profile.worker.implementation.primary",
                provider="openai-compatible",
                model="wrong-model",
                reasoning_effort="high",
                context_window=400000,
                temperature=0.0,
                tool_permissions=("filesystem.write",),
                fallback_policy_ref="fallback.default",
            ),
        }
    )

    with pytest.raises(ValueError, match="model_execution_profile mismatch"):
        _assert_role_package_provider_binding(scenario_input, execution_package)


def test_role_package_provider_binding_accepts_role_bound_yaml_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BOARDROOM_OPENAI_MODEL", raising=False)
    scenario_input = _input(tmp_path, provider_env_path=_provider_env(tmp_path))
    execution_package = _execution_package().model_copy(
        update={
            "seat_ref": AgentSeatRef(value="seat.worker.implementation"),
            "model_execution_profile": ModelExecutionProfile(
                model_execution_profile_id="model-profile.worker.implementation.primary",
                provider="openai-compatible",
                model="gpt-5.5",
                reasoning_effort="high",
                context_window=400000,
                temperature=0.0,
                tool_permissions=("filesystem.write",),
                fallback_policy_ref="fallback.default",
            ),
        }
    )

    _assert_role_package_provider_binding(scenario_input, execution_package)


def test_provider_attempt_manifest_entry_rejects_wrong_expected_refs(tmp_path: Path) -> None:
    artifact_store = FileProviderOutputStore(root=tmp_path / "provider-artifacts")
    raw = artifact_store.write_text(response_id="real-response", artifact_kind="raw", text='{"raw":true}')
    parsed = artifact_store.write_text(
        response_id="real-response",
        artifact_kind="parsed",
        text='{"parsed":true}',
    )
    attempt = _provider_attempt(
        input_package_ref="execution-package.v2-100e.expected",
        raw_output_ref=raw.artifact_ref.value,
        parsed_output_ref=parsed.artifact_ref.value,
    )

    with pytest.raises(ValueError, match="provider input package mismatch"):
        provider_attempt_manifest_entry(
            attempt,
            artifact_store=artifact_store,
            expected_input_package_ref="execution-package.v2-100e.from-package",
            expected_hook_ref=attempt.role_prompt_hook_ref.value,
        )


def test_provider_attempt_manifest_entry_requires_raw_and_parsed_artifacts(tmp_path: Path) -> None:
    artifact_store = FileProviderOutputStore(root=tmp_path / "provider-artifacts")
    attempt = _provider_attempt()

    with pytest.raises(ValueError, match="provider artifact is missing"):
        provider_attempt_manifest_entry(
            attempt,
            artifact_store=artifact_store,
            expected_input_package_ref=attempt.input_package_ref.value,
            expected_hook_ref=attempt.role_prompt_hook_ref.value,
        )


def test_real_provider_recheck_rejects_rebound_prebuilt_success_evidence(tmp_path: Path) -> None:
    from boardroom_os.proving.v2_100_resettable_fixture import build_v2_100_resettable_fixture

    fixture = build_v2_100_resettable_fixture(package_root=tmp_path / "package")
    rebound = _rebind_recheck_provider_attempt(
        fixture.accepted_recheck_input,
        provider_attempt_ref=ProviderAttemptRef(value="provider-attempt.openai.real.worker"),
        rework_plan_ref=fixture.accepted_recheck_input.attempt.rework_plan_ref,
    )

    with pytest.raises(V2_100ReworkLoopError, match="prebuilt accepted evidence"):
        validate_real_provider_recheck_input(rebound)


def test_round_result_requires_provider_manifest_for_attempt_refs(tmp_path: Path) -> None:
    from boardroom_os.proving.v2_100_resettable_fixture import build_accepted_round_input

    round_build = build_accepted_round_input(tmp_path)
    invalid_build = round_build.model_copy(
        update={"provider_attempt_manifest_entries": ()},
    )

    with pytest.raises(ValueError, match="provider attempt manifest"):
        run_v2_100_rework_round(invalid_build)


@pytest.mark.parametrize(
    "field_name",
    (
        "active_acceptance_refs",
        "active_source_surface_refs",
        "active_evidence_obligation_refs",
        "active_contract_refs",
    ),
)
def test_active_refs_are_required(tmp_path: Path, field_name: str) -> None:
    with pytest.raises(ValueError, match=field_name):
        _input(tmp_path, **{field_name: ()})


def test_duplicate_active_refs_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="duplicate|unique"):
        _input(
            tmp_path,
            active_acceptance_refs=(
                "acceptance.v2-100e.rework.blocker",
                "acceptance.v2-100e.rework.blocker",
            ),
        )


def test_fake_provider_attempt_cannot_satisfy_happy_path(tmp_path: Path) -> None:
    _input(tmp_path)
    attempt = _provider_attempt(
        provider_attempt_id="provider-attempt.fake.v2-100e",
        raw_output_ref="provider-artifact.fake.raw.placeholder",
        parsed_output_ref="provider-artifact.fake.parsed.placeholder",
    )

    with pytest.raises(ValueError, match="fake provider|real provider|placeholder"):
        validate_real_provider_attempt(
            attempt,
            expected_input_package_ref="execution-package.v2-100e.rework.1",
            expected_hook_ref="role-prompt-hook.baseline.worker.v1",
        )


def test_fallback_provider_attempt_cannot_satisfy_happy_path(tmp_path: Path) -> None:
    _input(tmp_path)
    attempt = _provider_attempt(
        outcome=ProviderAttemptOutcome.FALLBACK_ARTIFACT,
        fallback_kind=FallbackKind.TOOLING_PREFLIGHT,
    )

    with pytest.raises(ValueError, match="fallback"):
        validate_real_provider_attempt(
            attempt,
            expected_input_package_ref="execution-package.v2-100e.rework.1",
            expected_hook_ref="role-prompt-hook.baseline.worker.v1",
        )


def test_v2_100e_rejects_responses_protocol_until_json_output_is_supported() -> None:
    settings = OpenAIProviderSettings(
        api_key="sk-test-secret",
        base_url="https://api.example.invalid/v1",
        model="gpt-5.5",
        api_protocol="responses",
        reasoning_effort="high",
        response_format="json_object",
        timeout_seconds=600,
    )

    with pytest.raises(ValueError, match="responses|json output"):
        validate_v2_100e_provider_json_settings(settings)


def test_v2_100e_requires_json_object_response_format() -> None:
    settings = OpenAIProviderSettings(
        api_key="sk-test-secret",
        base_url="https://api.example.invalid/v1",
        model="gpt-5.5",
        api_protocol="chat_completions",
        reasoning_effort="high",
        response_format="text",
        timeout_seconds=600,
    )

    with pytest.raises(ValueError, match="json_object|response_format"):
        validate_v2_100e_provider_json_settings(settings)


def test_v2_100e_rejects_boardroom_openai_env_knobs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    provider_env_path = _provider_env(tmp_path, stale=True)
    scenario_input = _input(tmp_path, provider_env_path=provider_env_path)

    with pytest.raises(ValueError, match="stale env"):
        load_v2_100e_openai_settings(scenario_input, seat_ref="seat.worker.implementation")


def test_v2_100e_provider_secret_must_come_from_env_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _write_config_files(tmp_path)
    _force_json_object_response_format(paths.providers_config)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-ambient-secret")
    provider_env_path = tmp_path / ".env"
    provider_env_path.write_text(
        "\n".join(
            [
                f"BOARDROOM_RUNTIME_CONFIG={paths.runtime_config.as_posix()}",
                f"BOARDROOM_PROVIDERS_CONFIG={paths.providers_config.as_posix()}",
                f"BOARDROOM_ROLES_CONFIG={paths.roles_config.as_posix()}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    scenario_input = _input(tmp_path, provider_env_path=provider_env_path)

    with pytest.raises(ValueError, match="provider api key"):
        load_v2_100e_openai_settings(
            scenario_input,
            seat_ref="seat.worker.implementation",
        )


def test_v2_100e_selects_role_bound_provider_not_first_yaml_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = _write_config_files(tmp_path)
    _force_json_object_response_format(paths.providers_config)
    _prepend_decoy_provider(paths.providers_config)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    provider_env_path = tmp_path / ".env"
    provider_env_path.write_text(
        "\n".join(
            [
                f"BOARDROOM_RUNTIME_CONFIG={paths.runtime_config.as_posix()}",
                f"BOARDROOM_PROVIDERS_CONFIG={paths.providers_config.as_posix()}",
                f"BOARDROOM_ROLES_CONFIG={paths.roles_config.as_posix()}",
                "OPENAI_API_KEY=sk-test-secret",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    scenario_input = _input(tmp_path, provider_env_path=provider_env_path)

    settings = load_v2_100e_openai_settings(
        scenario_input,
        seat_ref="seat.worker.implementation",
    )

    assert settings.model == "gpt-5.5"
    assert settings.model != "decoy-model"


def test_runtime_direct_acceptance_is_rejected_by_reducer() -> None:
    resolver = _RuntimeDirectAcceptanceResolver()

    with pytest.raises(ReworkReducerError, match="runtime/executor/atomic-agent cannot emit governance"):
        ReworkReducer(resolver).reduce(
            (
                _event(
                    EventType.REWORK_REQUESTED,
                    graph_version=41,
                    actor_ref="seat-checker",
                    payload_ref="payload:request",
                ),
                _event(
                    EventType.REWORK_ACCEPTED,
                    graph_version=42,
                    actor_ref="runtime:executor",
                    payload_ref="payload:rework_accepted",
                ),
            )
        )


def test_budget_exhaustion_requires_terminal_decision(tmp_path: Path) -> None:
    _input(tmp_path, max_rounds=1)
    round_results = cast(
        tuple[V2_100ScenarioRoundResult, ...],
        (
            SimpleNamespace(
                round_index=1,
                terminal_status="still_blocked",
                termination_decision_ref=None,
                remaining_blocker_refs=(BLOCKER,),
            ),
        ),
    )

    with pytest.raises(ValueError, match="terminal decision|termination decision"):
        validate_loop_budget(round_results, max_rounds=1, terminal_decision=None)


def test_accepted_scenario_rejects_last_round_projection_with_remaining_blockers() -> None:
    accepted_outcome = ReworkOutcome(
        rework_outcome_id=OUTCOME_ID,
        rework_attempt_ref="rework-attempt.v2-100e.accepted",
        final_evidence_table_ref="final-evidence-table.v2-100e.accepted",
        source_inventory_ref="source-inventory.v2-100e.accepted",
        checker_verdict_ref="checker-verdict.v2-100e.accepted",
        status=ReworkOutcomeStatus.ACCEPTED,
        accepted_blocker_refs=(BLOCKER,),
        created_at=NOW,
    )
    bad_round_projection = ReworkProjection(
        project_ref=PROJECT,
        graph_version=50,
        cycle_id=CYCLE,
        status=ReworkCycleStatus.ACCEPTED,
        terminal_status=ReworkTerminalStatus.ACCEPTED,
        request_ref=ReworkRequestId(value="rework-request.v2-100e"),
        accepted_blocker_refs=(BLOCKER,),
        remaining_blocker_refs=(BLOCKER,),
        committed_event_refs=(EventId(value="event.v2-100e.accepted.50"),),
    )
    final_projection = bad_round_projection.model_copy(update={"remaining_blocker_refs": ()})
    round_result = V2_100ScenarioRoundResult.model_construct(
        round_index=1,
        request=_request(),
        plan_output=SimpleNamespace(),
        review_outputs=(SimpleNamespace(),),
        patch=SimpleNamespace(),
        approval_set=SimpleNamespace(),
        rework_ticket_ref=SimpleNamespace(),
        attempt=SimpleNamespace(),
        recheck_result=SimpleNamespace(),
        outcome=accepted_outcome,
        projection=bad_round_projection,
        events=(SimpleNamespace(payload_refs=(EventPayloadRef(value="payload:v2-100e"),)),),
        payload_refs=(EventPayloadRef(value="payload:v2-100e"),),
        payload_manifest_entries=(
            V2_100PayloadManifestEntry(
                payload_ref=EventPayloadRef(value="payload:v2-100e"),
                payload_kind="ReworkTerminalPayload",
                canonical_json="{}",
                sha256="sha256:" + "a" * 64,
            ),
        ),
        provider_attempt_manifest_entries=(),
        accepted_blocker_refs=(BLOCKER,),
        remaining_blocker_refs=(),
    )

    with pytest.raises(ValueError, match="last round projection"):
        V2_100ScenarioResult(
            scenario_id="scenario.v2-100e.accepted",
            input_hash="sha256:" + "a" * 64,
            terminal_status=V2_100ScenarioTerminalStatus.ACCEPTED,
            request=_request(),
            rounds=(round_result,),
            final_projection=final_projection,
            payload_manifest_entries=(
                V2_100PayloadManifestEntry(
                    payload_ref=EventPayloadRef(value="payload:v2-100e"),
                    payload_kind="ReworkTerminalPayload",
                    canonical_json="{}",
                    sha256="sha256:" + "a" * 64,
                ),
            ),
            provider_attempt_manifest_entries=(),
            audit_export=None,
            created_at=NOW,
        )


def test_second_round_with_round_local_resolver_fails_on_missing_historical_payload(
    tmp_path: Path,
) -> None:
    from boardroom_os.proving.v2_100_resettable_fixture import (
        build_two_round_provider,
        build_v2_100_scenario_input,
    )

    scenario_input = build_v2_100_scenario_input(
        package_root=tmp_path / "package",
        require_real_provider=False,
        max_rounds=2,
    )
    request = project_snapshot_request(scenario_input)
    provider = build_two_round_provider(tmp_path)
    first_build = provider.build_round(
        scenario_input,
        request,
        round_index=1,
        started_at_graph_version=scenario_input.initial_graph_version,
    )
    first_result = run_v2_100_rework_round(first_build)
    second_build = provider.build_round(
        scenario_input,
        request,
        round_index=2,
        started_at_graph_version=first_result.projection.graph_version,
    )

    with pytest.raises((ValueError, ReworkReducerError), match="missing payload"):
        run_v2_100_rework_round(second_build, prior_events=first_result.events)


def test_round_input_attempt_must_match_recheck_and_payload_attempt(tmp_path: Path) -> None:
    from boardroom_os.proving.v2_100_resettable_fixture import build_accepted_round_input
    from boardroom_os.rework.model import ReworkAttemptId

    round_build = build_accepted_round_input(tmp_path)
    mismatched_attempt = round_build.round_input.attempt.model_copy(
        update={"rework_attempt_id": ReworkAttemptId(value="rework-attempt.v2-100e.mismatch")}
    )
    invalid_round_input = round_build.round_input.model_copy(update={"attempt": mismatched_attempt})
    invalid_round_build = round_build.model_copy(update={"round_input": invalid_round_input})

    with pytest.raises(ValueError, match="attempt mismatch"):
        run_v2_100_rework_round(invalid_round_build)


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    (
        ("cycle_id", ReworkCycleId(value="rework-cycle.v2-100e.other")),
        ("blocker_refs", (BlockerRef(value="blocker.v2-100e.other"),)),
        ("evidence_refs", ("evidence.v2-100e.other",)),
        ("decided_by_actor", ReworkActorKind.CEO),
    ),
)
def test_terminal_decision_must_bind_current_round(
    tmp_path: Path,
    field_name: str,
    replacement: object,
) -> None:
    from boardroom_os.proving.v2_100_resettable_fixture import (
        build_exhausted_round_provider,
        build_v2_100_scenario_input,
    )

    scenario_input = build_v2_100_scenario_input(
        package_root=tmp_path / "package",
        require_real_provider=False,
        max_rounds=1,
    )
    request = project_snapshot_request(scenario_input)
    round_build = build_exhausted_round_provider(tmp_path).build_round(
        scenario_input,
        request,
        round_index=1,
        started_at_graph_version=scenario_input.initial_graph_version,
    )
    assert round_build.round_input.terminal_decision is not None
    bad_decision = round_build.round_input.terminal_decision.model_copy(
        update={field_name: replacement}
    )
    invalid_round_input = round_build.round_input.model_copy(
        update={"terminal_decision": bad_decision}
    )
    invalid_round_build = round_build.model_copy(update={"round_input": invalid_round_input})

    with pytest.raises(ValueError, match="termination decision"):
        run_v2_100_rework_round(invalid_round_build)
