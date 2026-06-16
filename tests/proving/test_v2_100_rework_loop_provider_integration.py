from __future__ import annotations

import os
from pathlib import Path

import pytest

from boardroom_os.execution.context_index import build_agent_context_snapshot
from boardroom_os.execution.provider_executor import ProviderExecutorResult
from boardroom_os.providers.attempt import ProviderAttempt, ProviderAttemptOutcome, ProviderAttemptStatus
from boardroom_os.providers.openai_adapter import FileProviderOutputStore
from boardroom_os.rework.model import ReworkActorKind
from boardroom_os.proving.v2_100_resettable_fixture import build_v2_100_scenario_input
from boardroom_os.proving.v2_100_rework_loop import (
    V2_100ScenarioTerminalStatus,
    run_v2_100_rework_loop_scenario,
)
from tests.config.test_boardroom_config import _write_config_files


pytestmark = pytest.mark.provider_integration


def test_cli_module_imports() -> None:
    import scripts.run_v2_100_rework_loop_scenario as cli

    assert callable(cli.main)


def test_real_provider_default_round_path_is_wired_without_deterministic_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import boardroom_os.proving.v2_100_rework_loop as loop_module

    paths = _write_config_files(tmp_path)
    roles_text = paths.roles_config.read_text(encoding="utf-8")
    roles_text = roles_text.replace(
        "  - seat_ref: seat.worker.implementation",
        """  - seat_ref: seat.ceo.delivery
    role_profile_ref: role.governance.ceo
    role_category: governance
    model_execution_profile_id: model-profile.ceo.delivery.primary
    provider_profile_ref: provider.openai-compatible.primary
    skill_refs: [skill.governance.ceo]
    default_tools: [read_file, submit_result]
    budget_profile_ref: worker.implementation.default
    budgets_override: {}
  - seat_ref: seat.architect.delivery
    role_profile_ref: role.architecture.lead
    role_category: architecture
    model_execution_profile_id: model-profile.architect.delivery.primary
    provider_profile_ref: provider.openai-compatible.primary
    skill_refs: [skill.architecture.lead]
    default_tools: [read_file, submit_result]
    budget_profile_ref: worker.implementation.default
    budgets_override: {}
  - seat_ref: seat.checker.acceptance
    role_profile_ref: role.verification.checker
    role_category: verification
    model_execution_profile_id: model-profile.checker.acceptance.primary
    provider_profile_ref: provider.openai-compatible.primary
    skill_refs: [skill.verification.checker]
    default_tools: [read_file, submit_result]
    budget_profile_ref: worker.implementation.default
    budgets_override: {}
  - seat_ref: seat.worker.implementation""",
    )
    paths.roles_config.write_text(roles_text, encoding="utf-8")
    providers_text = paths.providers_config.read_text(encoding="utf-8").replace(
        "response_format: null",
        "response_format:\n      type: json_object",
    )
    paths.providers_config.write_text(providers_text, encoding="utf-8")
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            (
                f"BOARDROOM_RUNTIME_CONFIG={paths.runtime_config.as_posix()}",
                f"BOARDROOM_PROVIDERS_CONFIG={paths.providers_config.as_posix()}",
                f"BOARDROOM_ROLES_CONFIG={paths.roles_config.as_posix()}",
                "OPENAI_API_KEY=sk-test-secret",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    scenario_input = build_v2_100_scenario_input(
        package_root=tmp_path / "package",
        export_root=tmp_path / "audit",
        provider_env_path=env_path,
        require_real_provider=True,
        max_rounds=1,
    )

    def fake_execute_role_package(execution_package, scenario_input):
        store = FileProviderOutputStore(root=scenario_input.export_root / "provider-artifacts")
        seat_ref = execution_package.seat_ref.value
        package_ref = execution_package.execution_package_id.value
        if ".review." in package_ref and seat_ref == "seat.ceo.delivery":
            expected_ref = "provider-attempt.v2-100e.review.1.planning"
            patch = loop_module._plan_patch_template(
                scenario_input,
                loop_module.project_snapshot_request(scenario_input),
                round_index=1,
                expected_attempt_ref=loop_module.ProviderAttemptRef(value="provider-attempt.v2-100e.ceo.round-1"),
            ).patch
            parsed_text = loop_module._review_template(
                patch,
                round_index=1,
                domain=loop_module.GraphPatchReviewDomain.PLANNING,
                actor=ReworkActorKind.CEO,
                expected_attempt_ref=loop_module.ProviderAttemptRef(value=expected_ref),
            ).model_dump_json()
        elif seat_ref == "seat.ceo.delivery":
            expected_ref = "provider-attempt.v2-100e.ceo.round-1"
            template = loop_module._plan_patch_template(
                scenario_input,
                loop_module.project_snapshot_request(scenario_input),
                round_index=1,
                expected_attempt_ref=loop_module.ProviderAttemptRef(value=expected_ref),
            )
            parsed_text = template.model_dump_json()
        elif seat_ref == "seat.architect.delivery":
            expected_ref = "provider-attempt.v2-100e.review.1.structural"
            patch = loop_module._plan_patch_template(
                scenario_input,
                loop_module.project_snapshot_request(scenario_input),
                round_index=1,
                expected_attempt_ref=loop_module.ProviderAttemptRef(value="provider-attempt.v2-100e.ceo.round-1"),
            ).patch
            parsed_text = loop_module._review_template(
                patch,
                round_index=1,
                domain=loop_module.GraphPatchReviewDomain.STRUCTURAL,
                actor=ReworkActorKind.ARCHITECT,
                expected_attempt_ref=loop_module.ProviderAttemptRef(value=expected_ref),
            ).model_dump_json()
        elif seat_ref == "seat.checker.acceptance":
            expected_ref = "provider-attempt.v2-100e.review.1.blocker_coverage"
            patch = loop_module._plan_patch_template(
                scenario_input,
                loop_module.project_snapshot_request(scenario_input),
                round_index=1,
                expected_attempt_ref=loop_module.ProviderAttemptRef(value="provider-attempt.v2-100e.ceo.round-1"),
            ).patch
            parsed_text = loop_module._review_template(
                patch,
                round_index=1,
                domain=loop_module.GraphPatchReviewDomain.BLOCKER_COVERAGE,
                actor=ReworkActorKind.CHECKER,
                expected_attempt_ref=loop_module.ProviderAttemptRef(value=expected_ref),
            ).model_dump_json()
        elif seat_ref == "seat.worker.implementation":
            expected_ref = "provider-attempt.worker.rework.v2-100e.1"
            parsed_text = '{"provider_attempt_ref":"provider-attempt.worker.rework.v2-100e.1","evidence_summary":"ack"}'
        else:
            raise AssertionError(f"unexpected execution package: {package_ref}")
        raw = store.write_text(response_id=expected_ref, artifact_kind="raw", text=parsed_text)
        parsed = store.write_text(response_id=expected_ref, artifact_kind="parsed", text=parsed_text)
        real_attempt_ref = f"provider-attempt.openai.{expected_ref}"
        attempt = ProviderAttempt(
            provider_attempt_id=real_attempt_ref,
            provider=execution_package.model_execution_profile.provider,
            model=execution_package.model_execution_profile.model,
            reasoning_effort=execution_package.model_execution_profile.reasoning_effort,
            input_package_ref=execution_package.execution_package_id.value,
            seat_ref=execution_package.seat_ref,
            role_prompt_hook_ref=execution_package.role_prompt_hook.hook_ref,
            role_prompt_hook_version=execution_package.role_prompt_hook.hook_version,
            role_prompt_hook_sha256=execution_package.role_prompt_hook.content_sha256,
            status=ProviderAttemptStatus.SUCCEEDED,
            outcome=ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
            started_at=loop_module.datetime.now(loop_module.UTC),
            finished_at=loop_module.datetime.now(loop_module.UTC),
            raw_output_ref=raw.artifact_ref,
            parsed_output_ref=parsed.artifact_ref,
        )
        return ProviderExecutorResult(
            context_snapshot=build_agent_context_snapshot(execution_package),
            prompt="patched provider prompt",
            provider_attempt=attempt,
        )

    monkeypatch.setattr(loop_module, "_execute_role_package", fake_execute_role_package)

    result = run_v2_100_rework_loop_scenario(scenario_input)

    assert result.terminal_status is V2_100ScenarioTerminalStatus.ACCEPTED
    assert result.provider_attempt_manifest_entries
    assert {
        "provider-attempt.openai.provider-attempt.v2-100e.ceo.round-1",
        "provider-attempt.openai.provider-attempt.v2-100e.review.1.planning",
        "provider-attempt.openai.provider-attempt.v2-100e.review.1.structural",
        "provider-attempt.openai.provider-attempt.v2-100e.review.1.blocker_coverage",
        "provider-attempt.openai.provider-attempt.worker.rework.v2-100e.1",
    }.issubset({entry.provider_attempt_ref for entry in result.provider_attempt_manifest_entries})


def test_audit_payload_manifest_entries_are_unique(tmp_path: Path) -> None:
    import json

    from boardroom_os.proving.v2_100_resettable_fixture import build_accepted_round_input
    from boardroom_os.proving.v2_100_rework_loop import export_v2_100_rework_audit

    result = run_v2_100_rework_loop_scenario(
        build_v2_100_scenario_input(
            package_root=tmp_path / "package",
            export_root=tmp_path / "audit-artifacts",
            require_real_provider=False,
            max_rounds=1,
        ),
        round_provider=type(
            "SingleRoundProvider",
            (),
            {
                "build_round": lambda self, scenario_input, request, *, round_index, started_at_graph_version: build_accepted_round_input(tmp_path),
            },
        )(),
    )
    export = export_v2_100_rework_audit(result, tmp_path / "audit")
    payloads = json.loads(export.payload_manifest_path.read_text(encoding="utf-8"))
    refs = [entry["payload_ref"]["value"] for entry in payloads]

    assert len(refs) == len(set(refs))


def test_v2_100_rework_loop_records_real_provider_attempt_manifest_entries(
    tmp_path: Path,
) -> None:
    if os.environ.get("BOARDROOM_RUN_REAL_PROVIDER_TESTS") != "1":
        pytest.skip("set BOARDROOM_RUN_REAL_PROVIDER_TESTS=1 to run real provider integration")

    scenario_input = build_v2_100_scenario_input(
        package_root=tmp_path / "package",
        export_root=tmp_path / "audit",
        provider_env_path=Path(os.environ.get("BOARDROOM_V2_100E_PROVIDER_ENV", ".env")),
        require_real_provider=True,
    )

    result = run_v2_100_rework_loop_scenario(scenario_input)

    assert result.rounds
    assert all(round_result.plan_output.provider_attempt is not None for round_result in result.rounds)
    assert all(
        review.provider_attempt is not None
        for round_result in result.rounds
        for review in round_result.review_outputs
    )
    assert all(round_result.attempt.provider_attempt_refs for round_result in result.rounds)
    ceo_attempt_refs = {
        round_result.plan_output.provider_attempt.provider_attempt_id.value
        for round_result in result.rounds
        if round_result.plan_output.provider_attempt is not None
    }
    reviewer_attempt_refs = {
        review.provider_attempt.provider_attempt_id.value
        for round_result in result.rounds
        for review in round_result.review_outputs
        if review.provider_attempt is not None
    }
    rework_attempt_refs = {
        ref.value
        for round_result in result.rounds
        for ref in round_result.attempt.provider_attempt_refs
    }
    required_refs = ceo_attempt_refs | reviewer_attempt_refs | rework_attempt_refs
    entries = result.provider_attempt_manifest_entries
    manifest_refs = {entry.provider_attempt_ref for entry in entries}
    assert required_refs
    assert required_refs.issubset(manifest_refs)
    for entry in entries:
        assert entry.raw_output_ref.value
        assert entry.parsed_output_ref.value
        assert entry.raw_output_sha256.startswith("sha256:")
        assert entry.parsed_output_sha256.startswith("sha256:")
