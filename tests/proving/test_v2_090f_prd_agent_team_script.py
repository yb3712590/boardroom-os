from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import pytest
from types import SimpleNamespace


def _hard_crud_acceptance_refs() -> list[str]:
    return ["AC-AGENT-DECLARED-LIBRARY-CRUD"]


def _hard_crud_evidence_obligations() -> list[str]:
    return [
        "Backend HTTP API supports add, list, checkout, return, and delete.",
        "RunManifest declares service startup, readiness, and behavioral probes.",
    ]


def test_v2_090f_loads_non_empty_short_prd(tmp_path: Path) -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import load_v2_090f_prd

    prd = tmp_path / "prd.md"
    prd.write_text("Build a tiny checkout app.", encoding="utf-8")

    loaded = load_v2_090f_prd(prd)

    assert loaded.text == "Build a tiny checkout app."
    assert loaded.sha256.startswith("sha256:")


def test_v2_090f_rejects_empty_prd(tmp_path: Path) -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import load_v2_090f_prd

    prd = tmp_path / "empty.md"
    prd.write_text("   \n", encoding="utf-8")

    with pytest.raises(ValueError, match="PRD must not be empty"):
        load_v2_090f_prd(prd)


def test_v2_090f_reset_rejects_unmarked_workspace(tmp_path: Path) -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import reset_v2_090f_workspace

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "user.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError, match="missing V2-090F marker"):
        reset_v2_090f_workspace(workspace)


def test_v2_090f_reference_examples_do_not_define_ticket_refs() -> None:
    text = Path("examples/directives/v2-090f-reference-examples.md").read_text(
        encoding="utf-8"
    )

    assert "ticket.tiny.backend-api" not in text
    assert "ticket.tiny.frontend-ui" not in text
    assert "ticket.tiny.integration-evidence" not in text


def test_v2_090f_roles_baseline_defines_required_agent_team_seats() -> None:
    import yaml

    from boardroom_os.proving.v2_090f_prd_agent_team import (
        validate_required_agent_team_slots,
    )

    data = yaml.safe_load(
        open("config/boardroom-roles.v2-090f.yaml", encoding="utf-8")
    )

    validate_required_agent_team_slots(data["role_slots"])


def test_v2_090f_runtime_baseline_uses_high_budget_profile() -> None:
    import yaml

    runtime = yaml.safe_load(
        open("config/boardroom-runtime.v2-090f.yaml", encoding="utf-8")
    )
    budget = runtime["atomic_agent"]["budget_profiles"][
        "agent_team.v2_090f.fullstack"
    ]

    assert budget["max_steps"] == 240
    assert budget["max_parse_failures"] == 6
    assert budget["max_observation_chars"] == 64000
    assert budget["max_wall_seconds"] == 10800
    assert budget["max_actions_per_turn"] == 1
    assert runtime["atomic_agent"]["budget_caps"]["max_actions_per_turn"] == 1
    assert (
        runtime["atomic_agent"]["execution_policy"][
            "retry_requires_no_workspace_mutation"
        ]
        is True
    )


def test_v2_090f_provider_baseline_requires_json_object_response_format() -> None:
    import yaml

    providers = yaml.safe_load(
        open("config/boardroom-providers.v2-090f.yaml", encoding="utf-8")
    )

    primary = providers["providers"][0]
    assert primary["provider_profile_id"] == "provider.openai-compatible.v2-090f-primary"
    assert primary["response_format"] == {"type": "json_object"}
    assert primary["max_output_tokens"] <= 20000


def _passed_rework_entry_result(tmp_path):
    report_path = tmp_path / "rework-entry-validation.md"
    report_path.write_text("passed_without_rework_candidate", encoding="utf-8")
    return SimpleNamespace(
        status=SimpleNamespace(value="passed_without_rework_candidate"),
        report_path=report_path,
    )


def test_v2_090f_runner_rework_entry_stage_runs_full_then_validation(
    tmp_path,
    monkeypatch,
):
    from scripts import run_v2_090f_prd_agent_team as runner

    calls = []
    prd = tmp_path / "prd.md"
    prd.write_text("Build the tiny fullstack app.", encoding="utf-8")

    monkeypatch.setenv("BOARDROOM_RUN_REAL_PROVIDER_PROVING", "1")
    monkeypatch.setattr(
        runner,
        "load_boardroom_settings",
        lambda paths, env_values: object(),
    )
    monkeypatch.setattr(
        runner,
        "resolve_v2_090f_config_paths_from_env",
        lambda env_values: object(),
    )
    monkeypatch.setattr(
        runner,
        "run_v2_090f_planning_preflight",
        lambda **kwargs: calls.append("preflight") or {"status": "preflight"},
    )
    monkeypatch.setattr(
        runner,
        "run_v2_090f_provider_planning_stage",
        lambda **kwargs: calls.append("planning") or {"status": "planning"},
    )
    monkeypatch.setattr(
        runner,
        "run_v2_090f_worker_execution_stage",
        lambda **kwargs: calls.append("worker") or {"status": "worker"},
    )
    monkeypatch.setattr(
        runner,
        "run_v2_090f_closeout_stage",
        lambda **kwargs: calls.append("closeout") or {"status": "closeout_gate_passed"},
    )
    monkeypatch.setattr(
        runner,
        "run_v2_090f_rework_entry_validation",
        lambda validation_input: calls.append("rework-entry")
        or _passed_rework_entry_result(tmp_path),
    )

    exit_code = runner.main(
        [
            "--prd",
            str(prd),
            "--reset",
            "--workspace-root",
            str(tmp_path / "workspace"),
            "--output-root",
            str(tmp_path / "tiny-fullstack"),
            "--stage",
            "rework-entry",
        ]
    )

    assert exit_code == 0
    assert calls == ["preflight", "planning", "worker", "closeout", "rework-entry"]


def test_v2_090f_runner_rework_entry_stage_records_raw_closeout_error(
    tmp_path,
    monkeypatch,
):
    from scripts import run_v2_090f_prd_agent_team as runner

    calls = []
    prd = tmp_path / "prd.md"
    output = tmp_path / "tiny-fullstack"
    prd.write_text("Build the tiny fullstack app.", encoding="utf-8")

    monkeypatch.setenv("BOARDROOM_RUN_REAL_PROVIDER_PROVING", "1")
    monkeypatch.setattr(
        runner,
        "load_boardroom_settings",
        lambda paths, env_values: object(),
    )
    monkeypatch.setattr(
        runner,
        "resolve_v2_090f_config_paths_from_env",
        lambda env_values: object(),
    )
    monkeypatch.setattr(
        runner,
        "run_v2_090f_planning_preflight",
        lambda **kwargs: calls.append("preflight") or {"status": "preflight"},
    )
    monkeypatch.setattr(
        runner,
        "run_v2_090f_provider_planning_stage",
        lambda **kwargs: calls.append("planning") or {"status": "planning"},
    )
    monkeypatch.setattr(
        runner,
        "run_v2_090f_worker_execution_stage",
        lambda **kwargs: calls.append("worker") or {"status": "worker"},
    )

    def raise_closeout(**kwargs):
        calls.append("closeout")
        raise ValueError("service readiness probe failed: HTTP 404")

    monkeypatch.setattr(runner, "run_v2_090f_closeout_stage", raise_closeout)
    monkeypatch.setattr(
        runner,
        "run_v2_090f_rework_entry_validation",
        lambda validation_input: calls.append("rework-entry")
        or SimpleNamespace(
            status=SimpleNamespace(value="blocked_by_missing_rework_entry"),
            report_path=output / "30-audit/rework-entry-validation.md",
        ),
    )

    exit_code = runner.main(
        [
            "--prd",
            str(prd),
            "--reset",
            "--workspace-root",
            str(tmp_path / "workspace"),
            "--output-root",
            str(output),
            "--stage",
            "rework-entry",
        ]
    )

    assert exit_code == 5
    assert calls == ["preflight", "planning", "worker", "closeout", "rework-entry"]
    assert "HTTP 404" in (output / "30-audit/raw-closeout-error.txt").read_text(
        encoding="utf-8"
    )


def test_v2_090f_runner_rework_entry_stage_records_raw_planning_error(
    tmp_path,
    monkeypatch,
):
    from scripts import run_v2_090f_prd_agent_team as runner

    calls = []
    prd = tmp_path / "prd.md"
    output = tmp_path / "tiny-fullstack"
    prd.write_text("Build the tiny fullstack app.", encoding="utf-8")

    monkeypatch.setenv("BOARDROOM_RUN_REAL_PROVIDER_PROVING", "1")
    monkeypatch.setattr(
        runner,
        "load_boardroom_settings",
        lambda paths, env_values: object(),
    )
    monkeypatch.setattr(
        runner,
        "resolve_v2_090f_config_paths_from_env",
        lambda env_values: object(),
    )
    monkeypatch.setattr(
        runner,
        "run_v2_090f_planning_preflight",
        lambda **kwargs: calls.append("preflight") or {"status": "preflight"},
    )

    def raise_planning(**kwargs):
        calls.append("planning")
        raise ValueError("RunManifest service entrypoint is not declared")

    monkeypatch.setattr(runner, "run_v2_090f_provider_planning_stage", raise_planning)
    monkeypatch.setattr(
        runner,
        "run_v2_090f_rework_entry_validation",
        lambda validation_input: calls.append("rework-entry")
        or SimpleNamespace(
            status=SimpleNamespace(value="blocked_by_missing_rework_entry"),
            report_path=output / "30-audit/rework-entry-validation.md",
        ),
    )

    exit_code = runner.main(
        [
            "--prd",
            str(prd),
            "--reset",
            "--workspace-root",
            str(tmp_path / "workspace"),
            "--output-root",
            str(output),
            "--stage",
            "rework-entry",
        ]
    )

    assert exit_code == 5
    assert calls == ["preflight", "planning", "rework-entry"]
    assert "RunManifest service entrypoint" in (
        output / "30-audit/raw-run-error.txt"
    ).read_text(encoding="utf-8")


def test_v2_090f_worker_packages_warn_against_dot_list_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from boardroom_os.config.boardroom import (
        BoardroomConfigPaths,
        load_boardroom_settings,
    )
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        build_v2_090f_worker_execution_packages,
    )

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    settings = load_boardroom_settings(
        BoardroomConfigPaths(
            runtime_config=Path("config/boardroom-runtime.v2-090f.yaml"),
            providers_config=Path("config/boardroom-providers.v2-090f.yaml"),
            roles_config=Path("config/boardroom-roles.v2-090f.yaml"),
        ),
        env_values=dict(os.environ),
    )
    packages = build_v2_090f_worker_execution_packages(
        settings=settings,
        ticket_graph_artifact={
            "ticket_graph": {
                "nodes": [
                    {
                        "node_ref": "ticket.impl.backend_api",
                        "node_type": "implementation",
                        "title": "Implement backend API",
                        "owner_seat_ref": "seat.worker.implementation",
                        "acceptance_refs": _hard_crud_acceptance_refs(),
                        "source_surface_refs": ["surface.backend"],
                        "evidence_obligations": _hard_crud_evidence_obligations(),
                        "allowed_write_set": ["app/", "tests/"],
                        "required_outputs": ["app/server.py", "tests/test_api.py"],
                        "commands": [
                            {
                                "command_id": "cmd.backend.tests",
                                "label": "Run backend tests",
                                "command": ["python", "-m", "pytest", "tests/test_api.py"],
                                "cwd": ".",
                            }
                        ],
                    }
                ]
            }
        },
        graph_version=1,
    )

    task_text = "\n".join((packages[0].objective, *packages[0].constraints))

    assert 'list_files with path "." is denied' in task_text
    assert "omit the path field" in task_text
    assert "app/" in task_text
    assert "tests/" in task_text
    assert "Do not read_file a path until list_files has shown that exact file exists" in task_text
    assert "If a required output file does not exist, create it with write_file" in task_text
    assert "Use list_files only for directories, never for file paths" in task_text
    assert "list the parent directory and inspect returned names" in task_text
    assert "submit_result input must contain exactly summary, produced_paths, and evidence_refs" in task_text
    assert "produced_paths must include every required output path" in task_text
    assert "Do not submit_result until you have written or modified at least one required output path" in task_text
    assert "evidence_refs must not be empty" in task_text
    assert "Return exactly one JSON action object per provider turn" in task_text
    assert "Do not append additional JSON objects after that action" in task_text
    assert "Never concatenate JSON objects in one provider response" in task_text
    assert "If you need multiple actions, return only the next single action" in task_text
    assert "Do not use batch protocol to bypass the single-object rule" in task_text
    assert "Do not include submit_result in the same provider turn as write_file or run_command" in task_text
    assert "evidence_refs must use actual artifact:// refs from completed tool observations" in task_text
    assert "Use search_files with input fields query, path, mode, and max_matches" in task_text
    assert "Do not use pattern with search_files" in task_text


def test_v2_090f_baseline_report_records_required_seats(tmp_path: Path) -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        write_v2_090f_baseline_report,
    )

    report = write_v2_090f_baseline_report(
        output_path=tmp_path / "baseline.json",
        prd_sha256="sha256:prd",
        runtime_config_hash="sha256:runtime",
        providers_config_hash="sha256:providers",
        roles_config_hash="sha256:roles",
        seats={
            "seat.ceo.delivery": {
                "role_profile_ref": "role.governance.ceo",
                "skill_refs": ["skill.governance.ceo"],
            },
            "seat.architect.delivery": {
                "role_profile_ref": "role.architecture.lead",
                "skill_refs": ["skill.architecture.lead"],
            },
            "seat.worker.implementation": {
                "role_profile_ref": "role.worker.implementation",
                "skill_refs": ["skill.command.test"],
            },
            "seat.tester.integration": {
                "role_profile_ref": "role.verification.tester",
                "skill_refs": ["skill.verification.tester"],
            },
            "seat.release.devops": {
                "role_profile_ref": "role.integration.release-devops",
                "skill_refs": ["skill.release.run-manifest"],
            },
            "seat.checker.acceptance": {
                "role_profile_ref": "role.verification.checker",
                "skill_refs": ["skill.verification.checker"],
            },
            "seat.closeout.package": {
                "role_profile_ref": "role.audit.closeout",
                "skill_refs": ["skill.audit.closeout"],
            },
        },
    )

    assert report["prd_sha256"] == "sha256:prd"
    assert set(report["seats"]) == {
        "seat.ceo.delivery",
        "seat.architect.delivery",
        "seat.worker.implementation",
        "seat.tester.integration",
        "seat.release.devops",
        "seat.checker.acceptance",
        "seat.closeout.package",
    }
    assert json.loads((tmp_path / "baseline.json").read_text(encoding="utf-8")) == report


def test_v2_090f_runner_requires_real_provider_opt_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.run_v2_090f_prd_agent_team import main

    prd = tmp_path / "prd.md"
    prd.write_text("Build a tiny checkout app.", encoding="utf-8")
    monkeypatch.delenv("BOARDROOM_RUN_REAL_PROVIDER_PROVING", raising=False)

    assert main(["--prd", str(prd), "--reset"]) == 2


def test_v2_090f_run_manifest_planning_package_requires_prior_artifact_consistency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from boardroom_os.config.boardroom import load_boardroom_settings
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        build_v2_090f_planning_execution_package,
        load_v2_090f_prd,
        resolve_v2_090f_config_paths_from_env,
    )

    prd = tmp_path / "prd.md"
    prd.write_text("Build a tiny checkout app.", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    monkeypatch.setenv("BOARDROOM_RUNTIME_CONFIG", "config/boardroom-runtime.v2-090f.yaml")
    monkeypatch.setenv("BOARDROOM_PROVIDERS_CONFIG", "config/boardroom-providers.v2-090f.yaml")
    monkeypatch.setenv("BOARDROOM_ROLES_CONFIG", "config/boardroom-roles.v2-090f.yaml")
    settings = load_boardroom_settings(
        resolve_v2_090f_config_paths_from_env(dict(os.environ)),
        env_values=dict(os.environ),
    )

    package = build_v2_090f_planning_execution_package(
        settings=settings,
        seat_ref="seat.release.devops",
        prd=load_v2_090f_prd(prd),
        output_name="run-manifest",
    )

    context_refs = {ref.value for ref in package.context_refs}
    assert "00-boardroom/generated-contracts.json" in context_refs
    assert "00-boardroom/generated-ticket-graph.json" in context_refs
    assert "00-boardroom/generated-verification-plan.json" in context_refs
    instructions = "\n".join((package.objective, *package.constraints))
    assert "required_outputs" in instructions
    assert "service command" in instructions
    assert "must reference an entrypoint" in instructions


def test_v2_090f_ticket_graph_planning_package_requires_workspace_relative_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from boardroom_os.config.boardroom import load_boardroom_settings
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        build_v2_090f_planning_execution_package,
        load_v2_090f_prd,
        resolve_v2_090f_config_paths_from_env,
    )

    prd = tmp_path / "prd.md"
    prd.write_text("Build a tiny checkout app.", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    monkeypatch.setenv("BOARDROOM_RUNTIME_CONFIG", "config/boardroom-runtime.v2-090f.yaml")
    monkeypatch.setenv("BOARDROOM_PROVIDERS_CONFIG", "config/boardroom-providers.v2-090f.yaml")
    monkeypatch.setenv("BOARDROOM_ROLES_CONFIG", "config/boardroom-roles.v2-090f.yaml")
    settings = load_boardroom_settings(
        resolve_v2_090f_config_paths_from_env(dict(os.environ)),
        env_values=dict(os.environ),
    )

    package = build_v2_090f_planning_execution_package(
        settings=settings,
        seat_ref="seat.architect.delivery",
        prd=load_v2_090f_prd(prd),
        output_name="ticket-graph",
    )

    instructions = "\n".join((package.objective, *package.constraints))
    assert "full workspace-relative paths" in instructions
    assert "bare filenames are not enough" in instructions


def test_tiny_closeout_wrapper_check_does_not_write_output_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts import build_tiny_closeout_sample

    output_root = tmp_path / "tiny-fullstack"
    output_root.mkdir()
    sentinel = output_root / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")

    monkeypatch.setattr(
        build_tiny_closeout_sample, "check_v2_090f_agent_team_sample", lambda root: 0
    )

    assert build_tiny_closeout_sample.main(["--output-root", str(output_root), "--check"]) == 0
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_v2_090f_check_rejects_forbidden_runtime_files(tmp_path: Path) -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import check_v2_090f_sample_tree

    sample = tmp_path / "tiny-fullstack"
    (sample / "10-project/backend/__pycache__").mkdir(parents=True)
    (sample / "10-project/backend/__pycache__/app.pyc").write_bytes(b"bad")

    with pytest.raises(ValueError, match="unregistered runtime file"):
        check_v2_090f_sample_tree(sample)


def test_v2_090f_check_requires_role_context_snapshot(tmp_path: Path) -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import check_v2_090f_sample_tree

    sample = tmp_path / "tiny-fullstack"
    sample.mkdir()
    (sample / "sample-manifest.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="agent-team-role-context"):
        check_v2_090f_sample_tree(sample)


def test_v2_090f_config_paths_must_use_dedicated_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        resolve_v2_090f_config_paths_from_env,
    )

    monkeypatch.setenv("BOARDROOM_RUNTIME_CONFIG", "config/boardroom-runtime.example.yaml")
    monkeypatch.setenv("BOARDROOM_PROVIDERS_CONFIG", "config/boardroom-providers.v2-090f.yaml")
    monkeypatch.setenv("BOARDROOM_ROLES_CONFIG", "config/boardroom-roles.v2-090f.yaml")

    with pytest.raises(ValueError, match="must use V2-090F dedicated config"):
        resolve_v2_090f_config_paths_from_env(dict(os.environ))


def test_v2_090f_planning_preflight_writes_baseline_and_pending_role_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        load_v2_090f_prd,
        run_v2_090f_planning_preflight,
    )

    prd = tmp_path / "prd.md"
    prd.write_text("Build a tiny checkout app.", encoding="utf-8")
    output_root = tmp_path / "tiny-fullstack"
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    monkeypatch.setenv("BOARDROOM_RUNTIME_CONFIG", "config/boardroom-runtime.v2-090f.yaml")
    monkeypatch.setenv("BOARDROOM_PROVIDERS_CONFIG", "config/boardroom-providers.v2-090f.yaml")
    monkeypatch.setenv("BOARDROOM_ROLES_CONFIG", "config/boardroom-roles.v2-090f.yaml")

    result = run_v2_090f_planning_preflight(
        prd=load_v2_090f_prd(prd),
        output_root=output_root,
        env_values=dict(os.environ),
    )

    assert result["status"] == "blocked_before_real_provider_orchestration"
    assert (output_root / "00-boardroom/v2-090f-baseline.json").is_file()
    role_context = json.loads(
        (output_root / "00-boardroom/agent-team-role-context.json").read_text(
            encoding="utf-8"
        )
    )
    assert set(role_context["entries"]) == {
        "seat.ceo.delivery",
        "seat.architect.delivery",
        "seat.worker.implementation",
        "seat.tester.integration",
        "seat.release.devops",
        "seat.checker.acceptance",
        "seat.closeout.package",
    }
    assert all(
        entry["invocation_status"] == "pending_real_provider_orchestration"
        for entry in role_context["entries"].values()
    )

    with pytest.raises(ValueError, match="pending_real_provider_orchestration"):
        from boardroom_os.proving.v2_090f_prd_agent_team import check_v2_090f_sample_tree

        check_v2_090f_sample_tree(output_root)


def test_v2_090f_provider_planning_artifact_requires_successful_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import UTC, datetime

    from boardroom_os.execution.context_index import ProviderAttemptRef
    from boardroom_os.providers.adapter import ProviderRequest
    from boardroom_os.providers.adapter import FakeProviderTransport, ProviderResponse
    from boardroom_os.providers.attempt import (
        ProviderArtifactRef,
        ProviderAttempt,
        ProviderAttemptOutcome,
        ProviderAttemptStatus,
    )
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        build_v2_090f_planning_execution_package,
        invoke_v2_090f_planning_role,
        load_v2_090f_prd,
        resolve_v2_090f_config_paths_from_env,
    )
    from boardroom_os.config.boardroom import load_boardroom_settings

    prd = tmp_path / "prd.md"
    prd.write_text("Build a tiny checkout app.", encoding="utf-8")
    output_root = tmp_path / "tiny-fullstack"
    parsed_artifact = output_root / "20-evidence/provider-artifacts/ceo.json"
    parsed_artifact.parent.mkdir(parents=True)
    parsed_artifact.write_text('{"directive":"ok"}', encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    monkeypatch.setenv("BOARDROOM_RUNTIME_CONFIG", "config/boardroom-runtime.v2-090f.yaml")
    monkeypatch.setenv("BOARDROOM_PROVIDERS_CONFIG", "config/boardroom-providers.v2-090f.yaml")
    monkeypatch.setenv("BOARDROOM_ROLES_CONFIG", "config/boardroom-roles.v2-090f.yaml")
    settings = load_boardroom_settings(
        resolve_v2_090f_config_paths_from_env(dict(os.environ)),
        env_values=dict(os.environ),
    )
    package = build_v2_090f_planning_execution_package(
        settings=settings,
        seat_ref="seat.ceo.delivery",
        prd=load_v2_090f_prd(prd),
        output_name="board-directive",
    )

    result = invoke_v2_090f_planning_role(
        execution_package=package,
        provider_adapter=FakeProviderTransport(
            response=ProviderResponse(
                raw_output_ref=ProviderArtifactRef(value="artifact.raw.ceo"),
                parsed_output_ref=ProviderArtifactRef(value=parsed_artifact.as_posix()),
                summary="CEO directive",
            ),
            attempt_id="provider-attempt.v2-090f.ceo",
            started_at=datetime(2026, 6, 12, tzinfo=UTC),
            finished_at=datetime(2026, 6, 12, 0, 1, tzinfo=UTC),
        ),
        output_path=output_root / "00-boardroom/generated-board-directive.json",
    )

    payload = json.loads(
        (output_root / "00-boardroom/generated-board-directive.json").read_text(
            encoding="utf-8"
        )
    )
    assert result["provider_attempt_ref"] == "provider-attempt.v2-090f.ceo"
    assert payload["provider_attempt_ref"] == "provider-attempt.v2-090f.ceo"
    assert payload["parsed_artifact_ref"] == parsed_artifact.as_posix()
    assert payload["provider_output"] == {"directive": "ok"}

    class FailedPlanningTransport:
        def invoke(self, request: ProviderRequest) -> ProviderAttempt:
            profile = request.model_execution_profile
            return ProviderAttempt(
                provider_attempt_id=ProviderAttemptRef(value="provider-attempt.failed"),
                provider=profile.provider,
                model=profile.model,
                reasoning_effort=profile.reasoning_effort,
                input_package_ref=request.execution_package_ref,
                seat_ref=request.seat_ref,
                role_prompt_hook_ref=request.role_prompt_hook_ref,
                role_prompt_hook_version=request.role_prompt_hook_version,
                role_prompt_hook_sha256=request.role_prompt_hook_sha256,
                status=ProviderAttemptStatus.FAILED,
                outcome=ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
                started_at=datetime(2026, 6, 12, tzinfo=UTC),
                finished_at=datetime(2026, 6, 12, 0, 1, tzinfo=UTC),
                failure_kind="provider_error.test",
            )

    with pytest.raises(ValueError, match="planning provider attempt must succeed"):
        invoke_v2_090f_planning_role(
            execution_package=package,
            provider_adapter=FailedPlanningTransport(),
            output_path=output_root / "00-boardroom/should-not-write.json",
        )
    assert not (output_root / "00-boardroom/should-not-write.json").exists()


def test_v2_090f_provider_planning_stage_records_planning_artifacts_and_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import UTC, datetime

    from boardroom_os.config.boardroom import load_boardroom_settings
    from boardroom_os.providers.adapter import FakeProviderTransport, ProviderResponse
    from boardroom_os.providers.attempt import ProviderArtifactRef
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        load_v2_090f_prd,
        resolve_v2_090f_config_paths_from_env,
        run_v2_090f_planning_preflight,
        run_v2_090f_provider_planning_stage,
    )

    prd = tmp_path / "prd.md"
    prd.write_text("Build a tiny checkout app.", encoding="utf-8")
    output_root = tmp_path / "tiny-fullstack"
    artifact_root = output_root / "20-evidence/provider-artifacts"
    artifact_root.mkdir(parents=True)
    artifact_payloads = {
        "seat.ceo.delivery": ("board-directive", {"directive": "from-ceo"}),
        "seat.architect.delivery": ("contracts", {"contracts": ["from-architect"]}),
        "seat.architect.delivery#ticket": (
            "ticket-graph",
            {
                "ticket_graph": {
                    "nodes": [
                        {
                            "node_ref": "ticket.impl.agent_api",
                            "node_type": "implementation",
                            "owner_seat_ref": "seat.worker.implementation",
                            "acceptance_refs": ["AC-AGENT-DECLARED-LIBRARY-CRUD"],
                            "source_surface_refs": ["surface.agent_api"],
                            "evidence_obligations": [
                                "Backend HTTP API supports add, list, checkout, return, and delete.",
                                "RunManifest declares service startup, readiness, and behavioral probes.",
                            ],
                            "allowed_write_set": ["service/", "tests/"],
                            "required_outputs": ["service/main.py", "tests/test_agent_api.py"],
                            "commands": [
                                {
                                    "command_id": "test-agent-api",
                                    "label": "Run tests",
                                    "command": [sys.executable, "-m", "pytest", "tests"],
                                    "cwd": ".",
                                }
                            ],
                        }
                    ]
                }
            },
        ),
        "seat.tester.integration": (
            "verification-plan",
            {"verification": ["from-tester"]},
        ),
        "seat.release.devops": (
            "run-manifest",
            {
                "run_manifest_id": {"value": "run-manifest.agent"},
                "workspace_manifest_ref": {"value": "workspace-manifest.agent"},
                "package_contract_ref": {"value": "package-contract.agent"},
                "package_root": {"value": "10-project"},
                "commands": [
                    {
                        "command_id": {"value": "serve-agent-api"},
                        "kind": "run",
                        "label": "Serve agent API",
                        "command": [sys.executable, "-m", "service.main"],
                        "cwd": ".",
                    },
                    {
                        "command_id": {"value": "test-agent-api"},
                        "kind": "test",
                        "label": "Run tests",
                        "command": [sys.executable, "-m", "pytest", "tests"],
                        "cwd": ".",
                    },
                ],
                "service_contracts": [
                    {
                        "command_id": {"value": "serve-agent-api"},
                        "role": "backend",
                        "env_bindings": [
                            {"name": "AGENT_HOST", "value_source": "runtime_host"},
                            {"name": "AGENT_PORT", "value_source": "runtime_port"},
                        ],
                        "readiness_probe": {"method": "GET", "path": "/ready", "expect_status": 200},
                    }
                ],
                "frontend_topology": {"mode": "served-by-backend"},
                "behavioral_probes": [
                    {
                        "probe_id": {"value": "probe.agent"},
                        "service_command_id": {"value": "serve-agent-api"},
                        "acceptance_refs": [{"value": "AC-AGENT-DECLARED"}],
                        "steps": [
                            {
                                "step_id": "ready",
                                "method": "GET",
                                "path": "/ready",
                                "json_body": None,
                                "expect_status": 200,
                                "capture": {},
                                "assertions": [],
                            }
                        ],
                    }
                ],
            },
        ),
    }
    for token, (_, payload) in artifact_payloads.items():
        (artifact_root / f"{token}.json").write_text(
            json.dumps(payload, sort_keys=True),
            encoding="utf-8",
        )

    class PlanningTransportFactory:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def __call__(self, *, seat_ref: str, output_name: str):
            token = seat_ref
            if seat_ref == "seat.architect.delivery" and output_name == "ticket-graph":
                token = "seat.architect.delivery#ticket"
            self.calls.append((seat_ref, output_name))
            return FakeProviderTransport(
                response=ProviderResponse(
                    raw_output_ref=ProviderArtifactRef(value=f"artifact.raw.{token}"),
                    parsed_output_ref=ProviderArtifactRef(
                        value=(artifact_root / f"{token}.json").as_posix()
                    ),
                    summary=f"{seat_ref} {output_name}",
                ),
                attempt_id=f"provider-attempt.v2-090f.{output_name}",
                started_at=datetime(2026, 6, 12, tzinfo=UTC),
                finished_at=datetime(2026, 6, 12, 0, 1, tzinfo=UTC),
            )

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    monkeypatch.setenv("BOARDROOM_RUNTIME_CONFIG", "config/boardroom-runtime.v2-090f.yaml")
    monkeypatch.setenv("BOARDROOM_PROVIDERS_CONFIG", "config/boardroom-providers.v2-090f.yaml")
    monkeypatch.setenv("BOARDROOM_ROLES_CONFIG", "config/boardroom-roles.v2-090f.yaml")
    loaded_prd = load_v2_090f_prd(prd)
    run_v2_090f_planning_preflight(
        prd=loaded_prd,
        output_root=output_root,
        env_values=dict(os.environ),
    )
    settings = load_boardroom_settings(
        resolve_v2_090f_config_paths_from_env(dict(os.environ)),
        env_values=dict(os.environ),
    )
    factory = PlanningTransportFactory()

    result = run_v2_090f_provider_planning_stage(
        prd=loaded_prd,
        output_root=output_root,
        settings=settings,
        provider_adapter_factory=factory,
    )

    assert result["status"] == "planning_stage_succeeded"
    assert factory.calls == [
        ("seat.ceo.delivery", "board-directive"),
        ("seat.architect.delivery", "contracts"),
        ("seat.architect.delivery", "ticket-graph"),
        ("seat.tester.integration", "verification-plan"),
        ("seat.release.devops", "run-manifest"),
    ]
    boardroom_root = output_root / "00-boardroom"
    assert json.loads(
        (boardroom_root / "generated-board-directive.json").read_text(encoding="utf-8")
    )["provider_output"] == {"directive": "from-ceo"}
    assert (boardroom_root / "generated-contracts.json").is_file()
    assert (boardroom_root / "generated-ticket-graph.json").is_file()
    assert (boardroom_root / "generated-verification-plan.json").is_file()
    assert (boardroom_root / "generated-run-manifest.json").is_file()

    role_context = json.loads(
        (boardroom_root / "agent-team-role-context.json").read_text(encoding="utf-8")
    )
    assert role_context["status"] == "planning_stage_succeeded"
    assert {
        seat
        for seat, entry in role_context["entries"].items()
        if entry["invocation_status"] == "planning_provider_succeeded"
    } == {
        "seat.ceo.delivery",
        "seat.architect.delivery",
        "seat.tester.integration",
    }
    assert role_context["entries"]["seat.worker.implementation"]["invocation_status"] == (
        "pending_worker_implementation"
    )
    assert role_context["entries"]["seat.checker.acceptance"]["invocation_status"] == (
        "pending_checker_review"
    )
    assert role_context["entries"]["seat.closeout.package"]["invocation_status"] == (
        "pending_closeout"
    )
    assert role_context["entries"]["seat.ceo.delivery"]["provider_attempt_refs"] == [
        "provider-attempt.v2-090f.board-directive"
    ]
    assert role_context["entries"]["seat.architect.delivery"]["provider_attempt_refs"] == [
        "provider-attempt.v2-090f.contracts",
        "provider-attempt.v2-090f.ticket-graph",
    ]


def test_v2_090f_planning_provider_adapter_uses_boardroom_provider_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from boardroom_os.config.boardroom import load_boardroom_settings
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        build_v2_090f_planning_execution_package,
        build_v2_090f_planning_provider_adapter,
        invoke_v2_090f_planning_role,
        load_v2_090f_prd,
        resolve_v2_090f_config_paths_from_env,
    )
    from boardroom_os.execution.package import ExecutionPackageRef
    from boardroom_os.providers.adapter import ProviderRequest

    class _ChatCompletionMessage:
        content = '{"directive":"real-provider-shaped"}'

    class _ChatCompletionChoice:
        message = _ChatCompletionMessage()

    class _ChatCompletionResponse:
        id = "chatcmpl_v2_090f_planning"
        choices = (_ChatCompletionChoice(),)

    class _ChatCompletions:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def create(self, **kwargs: object) -> _ChatCompletionResponse:
            self.calls.append(kwargs)
            return _ChatCompletionResponse()

    class _Chat:
        def __init__(self) -> None:
            self.completions = _ChatCompletions()

    class _Client:
        def __init__(self) -> None:
            self.chat = _Chat()
            self.close_count = 0

        def close(self) -> None:
            self.close_count += 1

    client = _Client()

    prd = tmp_path / "prd.md"
    prd.write_text("Build a tiny checkout app.", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    monkeypatch.setenv("BOARDROOM_RUNTIME_CONFIG", "config/boardroom-runtime.v2-090f.yaml")
    monkeypatch.setenv("BOARDROOM_PROVIDERS_CONFIG", "config/boardroom-providers.v2-090f.yaml")
    monkeypatch.setenv("BOARDROOM_ROLES_CONFIG", "config/boardroom-roles.v2-090f.yaml")
    settings = load_boardroom_settings(
        resolve_v2_090f_config_paths_from_env(dict(os.environ)),
        env_values=dict(os.environ),
    )
    package = build_v2_090f_planning_execution_package(
        settings=settings,
        seat_ref="seat.ceo.delivery",
        prd=load_v2_090f_prd(prd),
        output_name="board-directive",
    )
    adapter = build_v2_090f_planning_provider_adapter(
        settings=settings,
        seat_ref="seat.ceo.delivery",
        output_root=tmp_path / "tiny-fullstack",
        client=client,
    )

    attempt = adapter.invoke(
        ProviderRequest(
            execution_package_ref=ExecutionPackageRef(
                value=package.execution_package_id.value
            ),
            seat_ref=package.seat_ref,
            model_execution_profile=package.model_execution_profile,
            role_prompt_hook_ref=package.role_prompt_hook.hook_ref,
            role_prompt_hook_version=package.role_prompt_hook.hook_version,
            role_prompt_hook_sha256=package.role_prompt_hook.content_sha256,
            prompt="Return planning JSON.",
        )
    )

    assert client.chat.completions.calls
    call = client.chat.completions.calls[0]
    assert call["model"] == "gpt-5.5"
    assert call["timeout"] == 900.0
    assert call["max_completion_tokens"] == 20000
    assert call["response_format"] == {"type": "json_object"}
    assert call["reasoning_effort"] == "high"
    assert "# RolePromptHook" not in call["messages"][0]["content"]
    assert "not inside an agent tool loop" in call["messages"][0]["content"]
    assert "Use one top-level JSON object only" in call["messages"][0]["content"]
    assert attempt.status.value == "succeeded"
    assert attempt.raw_output_ref is not None
    assert attempt.parsed_output_ref is not None
    assert client.close_count == 1
    artifact_files = sorted((tmp_path / "tiny-fullstack/20-evidence/provider-artifacts").glob("*.txt"))
    assert len(artifact_files) == 2

    payload = invoke_v2_090f_planning_role(
        execution_package=package,
        provider_adapter=adapter,
        output_path=tmp_path / "tiny-fullstack/00-boardroom/generated-board-directive.json",
    )

    assert "# RolePromptHook" not in client.chat.completions.calls[-1]["messages"][0]["content"]
    assert payload["provider_output"] == {"directive": "real-provider-shaped"}
    assert client.close_count == 2


def test_v2_090f_extracts_planning_artifact_from_submit_result_wrapper() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import extract_v2_090f_planning_artifact

    provider_output = {
        "action": "submit_result",
        "action_id": "step-0001",
        "reason_summary": "Submit planning artifact.",
        "input": {
            "planning_artifact": {
                "artifact_type": "ticket_graph",
                "ticket_graph": {
                    "nodes": [
                        {
                            "ticket_id": "ticket.generated.backend",
                            "owner_seat_ref": "seat.worker.implementation",
                        }
                    ]
                },
            }
        },
    }

    artifact = extract_v2_090f_planning_artifact(
        provider_output,
        expected_artifact_name="ticket-graph",
    )

    assert artifact["ticket_graph"]["nodes"][0]["ticket_id"] == "ticket.generated.backend"


def test_v2_090f_rejects_planning_artifact_without_generated_ticket_graph() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        extract_v2_090f_planning_artifact,
    )

    with pytest.raises(ValueError, match="ticket graph planning artifact is required"):
        extract_v2_090f_planning_artifact(
            {"action": "submit_result", "input": {"summary": "no graph"}},
            expected_artifact_name="ticket-graph",
        )


def test_v2_090f_rejects_ticket_graph_without_worker_implementation_ticket() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        validate_v2_090f_generated_ticket_graph_for_worker_execution,
    )

    with pytest.raises(ValueError, match="implementation ticket is required"):
        validate_v2_090f_generated_ticket_graph_for_worker_execution(
            {
                "ticket_graph": {
                    "nodes": [
                        {
                            "node_ref": "PLAN-ACCEPTANCE-CONTRACT",
                            "node_type": "planning_contract",
                            "owner_seat_ref": "seat.architect.delivery",
                        }
                    ]
                }
            }
        )


def test_v2_090f_rejects_implementation_ticket_with_shell_string_command() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        validate_v2_090f_generated_ticket_graph_for_worker_execution,
    )

    graph = {
        "ticket_graph": {
            "nodes": [
                {
                    "node_ref": "ticket.impl.backend_api",
                    "node_type": "implementation",
                    "owner_seat_ref": "seat.worker.implementation",
                    "acceptance_refs": _hard_crud_acceptance_refs(),
                    "source_surface_refs": ["surface.backend-api"],
                    "evidence_obligations": _hard_crud_evidence_obligations(),
                    "allowed_write_set": ["10-project/server.py"],
                    "required_outputs": ["10-project/server.py"],
                    "commands": ["python -m unittest discover -s tests"],
                }
            ]
        }
    }

    with pytest.raises(ValueError, match="commands must be structured command objects"):
        validate_v2_090f_generated_ticket_graph_for_worker_execution(graph)


def test_v2_090f_rejects_implementation_ticket_with_glob_write_policy() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        validate_v2_090f_generated_ticket_graph_for_worker_execution,
    )

    graph = {
        "ticket_graph": {
            "nodes": [
                {
                    "node_ref": "ticket.impl.backend_api",
                    "node_type": "implementation",
                    "owner_seat_ref": "seat.worker.implementation",
                    "acceptance_refs": _hard_crud_acceptance_refs(),
                    "source_surface_refs": ["surface.backend-api"],
                    "evidence_obligations": _hard_crud_evidence_obligations(),
                    "allowed_write_set": ["server/**/*.py"],
                    "required_outputs": ["10-project/server.py"],
                    "commands": [
                        {
                            "command_id": "cmd.backend.tests",
                            "label": "Run backend tests",
                            "command": ["python", "-m", "unittest", "discover", "-s", "tests"],
                            "cwd": "10-project",
                        }
                    ],
                }
            ]
        }
    }

    with pytest.raises(ValueError, match="allowed_write_set must not contain glob patterns"):
        validate_v2_090f_generated_ticket_graph_for_worker_execution(graph)


def test_v2_090f_rejects_long_running_worker_service_commands() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        validate_v2_090f_generated_ticket_graph_for_worker_execution,
    )

    graph = {
        "ticket_graph": {
            "nodes": [
                {
                    "node_ref": "ticket.impl.backend_api",
                    "node_type": "implementation",
                    "owner_seat_ref": "seat.worker.implementation",
                    "acceptance_refs": _hard_crud_acceptance_refs(),
                    "source_surface_refs": ["surface.backend-api"],
                    "evidence_obligations": _hard_crud_evidence_obligations(),
                    "allowed_write_set": ["server.py", "tests/"],
                    "required_outputs": ["server.py", "tests/test_backend_api.py"],
                    "commands": [
                        {
                            "command_id": "cmd.backend.tests",
                            "label": "Run backend tests",
                            "command": ["python", "-m", "pytest", "tests/test_backend_api.py"],
                            "cwd": ".",
                        },
                        {
                            "command_id": "cmd.backend.run",
                            "label": "Start backend server",
                            "command": ["python", "server.py"],
                            "cwd": ".",
                        },
                    ],
                }
            ]
        }
    }

    with pytest.raises(ValueError, match="worker commands must be bounded finite"):
        validate_v2_090f_generated_ticket_graph_for_worker_execution(graph)


def test_v2_090f_rejects_ticket_graph_that_omits_add_or_delete_acceptance() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        validate_v2_090f_generated_ticket_graph_for_worker_execution,
    )

    graph = {
        "ticket_graph": {
            "nodes": [
                {
                    "node_ref": "ticket.impl.backend_api",
                    "node_type": "implementation",
                    "owner_seat_ref": "seat.worker.implementation",
                    "acceptance_refs": [
                        "acceptance.api.books_list",
                        "acceptance.api.checkout_return",
                    ],
                    "source_surface_refs": ["surface.backend_api"],
                    "evidence_obligations": [
                        "Implement HTTP routes for listing books, checking out a book, and returning a book."
                    ],
                    "allowed_write_set": ["app/", "tests/"],
                    "required_outputs": ["app/server.py", "tests/test_api.py"],
                    "commands": [
                        {
                            "command_id": "cmd.backend.tests",
                            "label": "Run backend tests",
                            "command": ["python", "-m", "pytest", "tests/test_api.py"],
                            "cwd": ".",
                        }
                    ],
                }
            ]
        }
    }

    with pytest.raises(ValueError, match="hard acceptance must cover add, list, checkout, return, and delete"):
        validate_v2_090f_generated_ticket_graph_for_worker_execution(graph)


def test_v2_090f_rejects_ticket_command_that_references_unwritable_tests() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        validate_v2_090f_generated_ticket_graph_for_worker_execution,
    )

    graph = {
        "ticket_graph": {
            "nodes": [
                {
                    "node_ref": "ticket.impl.backend_api",
                    "node_type": "implementation",
                    "owner_seat_ref": "seat.worker.implementation",
                    "acceptance_refs": _hard_crud_acceptance_refs(),
                    "source_surface_refs": ["surface.backend_api"],
                    "evidence_obligations": _hard_crud_evidence_obligations(),
                    "allowed_write_set": ["server.py", "library_app/"],
                    "required_outputs": ["server.py", "library_app/api.py"],
                    "commands": [
                        {
                            "command_id": "backend.unit",
                            "label": "Run backend API tests",
                            "command": ["python", "-m", "unittest", "tests.test_api"],
                            "cwd": ".",
                        }
                    ],
                }
            ]
        }
    }

    with pytest.raises(ValueError, match="declared test command requires writable test outputs"):
        validate_v2_090f_generated_ticket_graph_for_worker_execution(graph)


def test_v2_090f_allows_agent_declared_backend_entrypoint() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        validate_v2_090f_generated_ticket_graph_for_worker_execution,
    )

    graph = {
        "ticket_graph": {
            "nodes": [
                {
                    "node_ref": "ticket.impl.backend_api",
                    "node_type": "implementation",
                    "owner_seat_ref": "seat.worker.implementation",
                    "acceptance_refs": _hard_crud_acceptance_refs(),
                    "source_surface_refs": ["surface.backend_api"],
                    "evidence_obligations": _hard_crud_evidence_obligations(),
                    "allowed_write_set": ["app.py", "library_app/", "tests/"],
                    "required_outputs": ["app.py", "library_app/api.py", "tests/test_api.py"],
                    "commands": [
                        {
                            "command_id": "backend.unit",
                            "label": "Run backend API tests",
                            "command": ["python", "-m", "unittest", "tests.test_api"],
                            "cwd": ".",
                        }
                    ],
                }
            ]
        }
    }

    nodes = validate_v2_090f_generated_ticket_graph_for_worker_execution(graph)

    assert nodes[0]["required_outputs"] == ["app.py", "library_app/api.py", "tests/test_api.py"]


def test_v2_090f_allows_run_manifest_to_own_runtime_env_contract() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        validate_v2_090f_generated_ticket_graph_for_worker_execution,
    )

    graph = {
        "ticket_graph": {
            "nodes": [
                {
                    "node_ref": "ticket.impl.backend_api",
                    "node_type": "implementation",
                    "owner_seat_ref": "seat.worker.implementation",
                    "acceptance_refs": _hard_crud_acceptance_refs(),
                    "source_surface_refs": ["surface.backend_api"],
                    "evidence_obligations": [
                        "Backend HTTP API supports add, list, checkout, return, and delete.",
                        "Runtime env mapping is declared by RunManifest.",
                    ],
                    "allowed_write_set": ["service/", "tests/"],
                    "required_outputs": ["service/main.py", "tests/test_api.py"],
                    "commands": [
                        {
                            "command_id": "backend.unit",
                            "label": "Run backend API tests",
                            "command": ["python", "-m", "unittest", "tests.test_api"],
                            "cwd": ".",
                        }
                    ],
                }
            ]
        }
    }

    nodes = validate_v2_090f_generated_ticket_graph_for_worker_execution(graph)

    assert nodes[0]["allowed_write_set"] == ["service/", "tests/"]


def test_v2_090k_rejects_run_manifest_service_entrypoint_not_declared_by_ticket_graph() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        _load_v2_090k_run_manifest_artifact,
        validate_v2_090k_run_manifest_planning_consistency,
    )

    ticket_graph = {
        "ticket_graph": {
            "nodes": [
                {
                    "node_ref": "ticket.impl.backend_api",
                    "node_type": "implementation",
                    "owner_seat_ref": "seat.worker.implementation",
                    "acceptance_refs": _hard_crud_acceptance_refs(),
                    "source_surface_refs": ["surface.backend_api"],
                    "evidence_obligations": _hard_crud_evidence_obligations(),
                    "allowed_write_set": ["backend/", "tests/"],
                    "required_outputs": ["backend/app.py", "tests/test_api.py"],
                    "commands": [
                        {
                            "command_id": "backend.unit",
                            "label": "Run backend API tests",
                            "command": ["python", "-m", "unittest", "discover", "-s", "tests"],
                            "cwd": ".",
                        }
                    ],
                }
            ]
        }
    }
    run_manifest = _load_v2_090k_run_manifest_artifact(
        {
            "run_manifest_id": "runmanifest.entrypoint-mismatch",
            "workspace_manifest_ref": "workspacemanifest.entrypoint-mismatch",
            "package_contract_ref": "packagecontract.entrypoint-mismatch",
            "package_root": ".",
            "commands": [
                {
                    "command_id": "cmd.run.backend",
                    "command_type": "service_run",
                    "label": "Run backend",
                    "command": ["python", "backend/server.py"],
                    "cwd": ".",
                },
                {
                    "command_id": "cmd.test.backend",
                    "command_type": "finite_verification",
                    "label": "Run tests",
                    "command": ["python", "-m", "unittest", "discover", "-s", "tests"],
                    "cwd": ".",
                },
            ],
            "service_contracts": [
                {
                    "service_contract_id": "svc.backend",
                    "run_command_id": "cmd.run.backend",
                    "role": "backend",
                    "env_bindings": {
                        "HOST": {"value_source": "runtime_host"},
                        "PORT": {"value_source": "runtime_port"},
                        "DATABASE_PATH": {"value_source": "temp_sqlite_path"},
                    },
                    "readiness_probe": {"method": "GET", "path": "/health", "expect_status": 200},
                }
            ],
            "behavioral_probes": [
                {
                    "probe_id": "probe.health",
                    "service_contract_id": "svc.backend",
                    "acceptance_refs": ["AC-AGENT-DECLARED-LIBRARY-CRUD"],
                    "steps": [
                        {
                            "step_id": "health",
                            "method": "GET",
                            "path": "/health",
                            "json_body": None,
                            "expect_status": 200,
                            "assertions": [{"type": "body_contains", "value": "ok"}],
                        }
                    ],
                }
            ],
        }
    )

    with pytest.raises(ValueError, match="RunManifest service entrypoint is not declared"):
        validate_v2_090k_run_manifest_planning_consistency(
            run_manifest=run_manifest,
            ticket_graph_artifact=ticket_graph,
        )


def test_v2_090k_accepts_run_manifest_service_entrypoint_declared_by_ticket_graph() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        _load_v2_090k_run_manifest_artifact,
        validate_v2_090k_run_manifest_planning_consistency,
    )

    ticket_graph = {
        "ticket_graph": {
            "nodes": [
                {
                    "node_ref": "ticket.impl.backend_api",
                    "node_type": "implementation",
                    "owner_seat_ref": "seat.worker.implementation",
                    "acceptance_refs": _hard_crud_acceptance_refs(),
                    "source_surface_refs": ["surface.backend_api"],
                    "evidence_obligations": _hard_crud_evidence_obligations(),
                    "allowed_write_set": ["backend/"],
                    "required_outputs": ["backend/app.py", "tests/test_api.py"],
                    "commands": [
                        {
                            "command_id": "backend.unit",
                            "label": "Run backend API tests",
                            "command": ["python", "-m", "unittest", "discover", "-s", "tests"],
                            "cwd": ".",
                        }
                    ],
                }
            ]
        }
    }
    run_manifest = _load_v2_090k_run_manifest_artifact(
        {
            "run_manifest_id": "runmanifest.entrypoint-match",
            "workspace_manifest_ref": "workspacemanifest.entrypoint-match",
            "package_contract_ref": "packagecontract.entrypoint-match",
            "package_root": ".",
            "commands": [
                {
                    "command_id": "cmd.run.backend",
                    "command_type": "service_run",
                    "label": "Run backend",
                    "command": ["python", "-m", "backend.app"],
                    "cwd": ".",
                },
                {
                    "command_id": "cmd.test.backend",
                    "command_type": "finite_verification",
                    "label": "Run tests",
                    "command": ["python", "-m", "unittest", "discover", "-s", "tests"],
                    "cwd": ".",
                },
            ],
            "service_contracts": [
                {
                    "service_contract_id": "svc.backend",
                    "run_command_id": "cmd.run.backend",
                    "role": "backend",
                    "env_bindings": {
                        "HOST": {"value_source": "runtime_host"},
                        "PORT": {"value_source": "runtime_port"},
                        "DATABASE_PATH": {"value_source": "temp_sqlite_path"},
                    },
                    "readiness_probe": {"method": "GET", "path": "/health", "expect_status": 200},
                }
            ],
            "behavioral_probes": [
                {
                    "probe_id": "probe.health",
                    "service_contract_id": "svc.backend",
                    "acceptance_refs": ["AC-AGENT-DECLARED-LIBRARY-CRUD"],
                    "steps": [
                        {
                            "step_id": "health",
                            "method": "GET",
                            "path": "/health",
                            "json_body": None,
                            "expect_status": 200,
                            "assertions": [{"type": "body_contains", "value": "ok"}],
                        }
                    ],
                }
            ],
        }
    )

    validate_v2_090k_run_manifest_planning_consistency(
        run_manifest=run_manifest,
        ticket_graph_artifact=ticket_graph,
    )


def test_v2_090f_accepts_worker_test_command_id_ending_in_run() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        validate_v2_090f_generated_ticket_graph_for_worker_execution,
    )

    nodes = validate_v2_090f_generated_ticket_graph_for_worker_execution(
        {
            "ticket_graph": {
                "nodes": [
                    {
                        "node_ref": "ticket.impl.tests",
                        "node_type": "implementation",
                        "title": "Implement finite tests",
                        "owner_seat_ref": "seat.worker.implementation",
                        "acceptance_refs": _hard_crud_acceptance_refs(),
                        "source_surface_refs": ["surface.tests"],
                        "evidence_obligations": _hard_crud_evidence_obligations(),
                        "allowed_write_set": ["tests/"],
                        "required_outputs": ["tests/test_backend.py"],
                        "commands": [
                            {
                                "command_id": "cmd.impl.tests.run",
                                "label": "Run finite unittest suite",
                                "command": ["python", "-m", "unittest", "discover", "-s", "tests"],
                                "cwd": ".",
                            }
                        ],
                    }
                ]
            }
        }
    )

    assert nodes[0]["node_ref"] == "ticket.impl.tests"


def test_v2_090f_direct_planning_prompt_forbids_service_commands_in_worker_tickets() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import _direct_planning_prompt

    prompt = _direct_planning_prompt("Objective mentions ticket-graph")

    assert "worker implementation commands must be bounded finite verification commands" in prompt
    assert "do not include long-running service startup, run, serve, watch, or dev commands" in prompt
    assert "Service startup, readiness, live behavior probes" in prompt
    assert "python -m app.server" not in prompt
    assert "app/server.py" not in prompt
    assert "LIBRARY_API_HOST" not in prompt
    assert "LIBRARY_API_PORT" not in prompt
    assert "LIBRARY_DB_PATH" not in prompt


def test_v2_090f_direct_planning_prompt_preserves_execution_package_constraints() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import _direct_planning_prompt

    prompt = _direct_planning_prompt(
        "# RolePromptHook\n"
        "Release DevOps\n"
        "# ExecutionPackageFacts\n"
        + json.dumps(
            {
                "objective": "Produce V2-090F planning artifact run-manifest",
                "context_refs": [
                    "00-boardroom/generated-contracts.json",
                    "00-boardroom/generated-ticket-graph.json",
                ],
                "constraints": [
                    "Every service command must reference an entrypoint from required_outputs.",
                ],
                "allowed_read_refs": [
                    "00-boardroom/generated-contracts.json",
                    "00-boardroom/generated-ticket-graph.json",
                ],
            }
        )
    )

    assert "Every service command must reference an entrypoint from required_outputs" in prompt
    assert "00-boardroom/generated-ticket-graph.json" in prompt
    assert "Directory-only required_outputs are not enough for service entrypoints" in prompt


def test_v2_090f_worker_constraints_forbid_empty_search_files_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from boardroom_os.config.boardroom import load_boardroom_settings
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        build_v2_090f_worker_execution_packages,
        resolve_v2_090f_config_paths_from_env,
    )

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    monkeypatch.setenv("BOARDROOM_RUNTIME_CONFIG", "config/boardroom-runtime.v2-090f.yaml")
    monkeypatch.setenv("BOARDROOM_PROVIDERS_CONFIG", "config/boardroom-providers.v2-090f.yaml")
    monkeypatch.setenv("BOARDROOM_ROLES_CONFIG", "config/boardroom-roles.v2-090f.yaml")
    settings = load_boardroom_settings(
        resolve_v2_090f_config_paths_from_env(dict(os.environ)),
        env_values=dict(os.environ),
    )

    package = build_v2_090f_worker_execution_packages(
        settings=settings,
        ticket_graph_artifact={
            "ticket_graph": {
                "nodes": [
                    {
                        "node_ref": "ticket.impl.integration_tests",
                        "node_type": "implementation",
                        "title": "Implement integration tests",
                        "depends_on": ["ticket.impl.backend_api"],
                        "owner_seat_ref": "seat.worker.implementation",
                        "acceptance_refs": ["AC-V2-090F-TESTS"],
                        "source_surface_refs": ["surface.integration-tests"],
                        "evidence_obligations": ["Automated tests cover required backend CRUD operations."],
                        "allowed_write_set": ["tests/"],
                        "required_outputs": ["tests/test_integration.py"],
                        "commands": [
                            {
                                "command_id": "cmd.integration.tests",
                                "label": "Run integration tests",
                                "command": ["python", "-m", "unittest", "discover", "-s", "tests"],
                                "cwd": ".",
                            }
                        ],
                    },
                    {
                        "node_ref": "ticket.impl.backend_api",
                        "node_type": "implementation",
                        "title": "Implement backend API",
                        "depends_on": [],
                        "owner_seat_ref": "seat.worker.implementation",
                        "acceptance_refs": _hard_crud_acceptance_refs(),
                        "source_surface_refs": ["surface.backend-api"],
                        "evidence_obligations": _hard_crud_evidence_obligations(),
                        "allowed_write_set": ["app/"],
                        "required_outputs": ["app/server.py"],
                        "commands": [
                            {
                                "command_id": "cmd.backend.compile",
                                "label": "Compile backend server",
                                "command": ["python", "-m", "py_compile", "app/server.py"],
                                "cwd": ".",
                            }
                        ],
                    }
                ]
            }
        },
        graph_version=2,
    )[0]

    constraints = "\n".join(package.constraints)

    assert "search_files query must be a non-empty string" in constraints
    assert "use list_files instead of search_files" in constraints
    assert "Every declared command must have a latest observed exit_code of 0" in constraints


def test_v2_090f_compiles_worker_execution_packages_from_generated_ticket_graph(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from boardroom_os.config.boardroom import load_boardroom_settings
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        build_v2_090f_worker_execution_packages,
        resolve_v2_090f_config_paths_from_env,
    )

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    monkeypatch.setenv("BOARDROOM_RUNTIME_CONFIG", "config/boardroom-runtime.v2-090f.yaml")
    monkeypatch.setenv("BOARDROOM_PROVIDERS_CONFIG", "config/boardroom-providers.v2-090f.yaml")
    monkeypatch.setenv("BOARDROOM_ROLES_CONFIG", "config/boardroom-roles.v2-090f.yaml")
    settings = load_boardroom_settings(
        resolve_v2_090f_config_paths_from_env(dict(os.environ)),
        env_values=dict(os.environ),
    )
    ticket_graph_artifact = {
        "ticket_graph": {
            "nodes": [
                {
                    "node_ref": "ticket.impl.backend_api",
                    "node_type": "implementation",
                    "title": "Implement backend API",
                    "depends_on": [],
                    "owner_seat_ref": "seat.worker.implementation",
                    "acceptance_refs": _hard_crud_acceptance_refs(),
                    "source_surface_refs": ["surface.backend-api"],
                    "evidence_obligations": _hard_crud_evidence_obligations(),
                        "allowed_write_set": ["app/", "tests/"],
                        "required_outputs": ["app/server.py", "tests/test_api.py"],
                    "commands": [
                        {
                            "command_id": "cmd.backend.tests",
                            "label": "Run backend tests",
                            "command": ["python", "-m", "pytest", "tests/test_api.py"],
                            "cwd": "10-project",
                        }
                    ],
                }
            ]
        }
    }

    packages = build_v2_090f_worker_execution_packages(
        settings=settings,
        ticket_graph_artifact=ticket_graph_artifact,
        graph_version=2,
    )

    assert len(packages) == 1
    package = packages[0]
    assert package.ticket_ref.value == "ticket.impl.backend_api"
    assert package.seat_ref.value == "seat.worker.implementation"
    assert package.model_execution_profile.model == "gpt-5.5"
    assert package.role_prompt_hook.hook_ref.value == "role-prompt-hook.baseline.worker.v1"
    assert [ref.value for ref in package.acceptance_refs] == _hard_crud_acceptance_refs()
    assert [ref.value for ref in package.source_surface_refs] == ["surface.backend-api"]
    assert [path.value for path in package.allowed_write_set] == [
        "app/",
        "tests/",
    ]
    assert package.commands[0].command == (
        sys.executable,
        "-m",
        "pytest",
        "tests/test_api.py",
    )
    assert package.evidence_obligations[0].evidence_obligation_id.value == (
        "Backend HTTP API supports add, list, checkout, return, and delete."
    )


def test_v2_090f_worker_execution_package_binds_python_command_to_current_interpreter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from boardroom_os.config.boardroom import load_boardroom_settings
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        build_v2_090f_worker_execution_packages,
        resolve_v2_090f_config_paths_from_env,
    )

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    monkeypatch.setenv("BOARDROOM_RUNTIME_CONFIG", "config/boardroom-runtime.v2-090f.yaml")
    monkeypatch.setenv("BOARDROOM_PROVIDERS_CONFIG", "config/boardroom-providers.v2-090f.yaml")
    monkeypatch.setenv("BOARDROOM_ROLES_CONFIG", "config/boardroom-roles.v2-090f.yaml")
    settings = load_boardroom_settings(
        resolve_v2_090f_config_paths_from_env(dict(os.environ)),
        env_values=dict(os.environ),
    )

    packages = build_v2_090f_worker_execution_packages(
        settings=settings,
        ticket_graph_artifact={
            "ticket_graph": {
                "nodes": [
                    {
                        "node_ref": "ticket.impl.backend_api",
                        "node_type": "implementation",
                        "title": "Implement backend API",
                        "depends_on": [],
                        "owner_seat_ref": "seat.worker.implementation",
                        "acceptance_refs": _hard_crud_acceptance_refs(),
                        "source_surface_refs": ["surface.backend-api"],
                        "evidence_obligations": _hard_crud_evidence_obligations(),
                        "allowed_write_set": ["app/", "tests/"],
                        "required_outputs": ["app/server.py", "tests/test_api.py"],
                        "commands": [
                            {
                                "command_id": "cmd.backend.tests",
                                "label": "Run backend tests",
                                "command": ["python3", "-m", "unittest", "discover", "-s", "tests"],
                                "cwd": "10-project",
                            }
                        ],
                    }
                ]
            }
        },
        graph_version=2,
    )

    assert packages[0].commands[0].command[0] == sys.executable


def test_v2_090f_worker_execution_stage_records_atomic_evidence_without_closeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import dataclass

    from boardroom_os.config.boardroom import load_boardroom_settings
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        resolve_v2_090f_config_paths_from_env,
        run_v2_090f_worker_execution_stage,
    )

    @dataclass(frozen=True)
    class FakeProviderAttempt:
        provider_attempt_id: object

    @dataclass(frozen=True)
    class FakeProjection:
        atomic_run_id: str
        source_lineage_inputs: tuple[dict[str, object], ...]
        event_stream_ref: str
        events_hash: str

    @dataclass(frozen=True)
    class FakeExecutionResult:
        atomic_run_id: str
        provider_attempt: object
        projection: object

    class ProviderAttemptId:
        def __init__(self, value: str) -> None:
            self.value = value

    class FakeAtomicExecutor:
        def __init__(self) -> None:
            self.requests = []

        def execute(self, request, *, provider_transport_kind: str = "real"):
            self.requests.append((request, provider_transport_kind))
            assert (request.workspace_root / "app").is_dir()
            assert (request.workspace_root / "tests").is_dir()
            ticket = request.execution_package.ticket_ref.value
            return FakeExecutionResult(
                atomic_run_id=f"atomic-run.{ticket}",
                provider_attempt=FakeProviderAttempt(
                    provider_attempt_id=ProviderAttemptId(
                        f"provider-attempt.atomic.{ticket}"
                    )
                ),
                projection=FakeProjection(
                    atomic_run_id=f"atomic-run.{ticket}",
                    source_lineage_inputs=(
                        {
                            "path": "app/server.py",
                            "producer_ticket_ref": ticket,
                        },
                    ),
                    event_stream_ref=f"{ticket}.jsonl",
                    events_hash="sha256:" + "a" * 64,
                ),
            )

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    monkeypatch.setenv("BOARDROOM_RUNTIME_CONFIG", "config/boardroom-runtime.v2-090f.yaml")
    monkeypatch.setenv("BOARDROOM_PROVIDERS_CONFIG", "config/boardroom-providers.v2-090f.yaml")
    monkeypatch.setenv("BOARDROOM_ROLES_CONFIG", "config/boardroom-roles.v2-090f.yaml")
    settings = load_boardroom_settings(
        resolve_v2_090f_config_paths_from_env(dict(os.environ)),
        env_values=dict(os.environ),
    )
    output_root = tmp_path / "tiny-fullstack"
    (output_root / "00-boardroom").mkdir(parents=True)
    ticket_graph = {
        "ticket_graph": {
            "nodes": [
                {
                    "node_ref": "ticket.impl.backend_api",
                    "node_type": "implementation",
                    "title": "Implement backend API",
                    "depends_on": [],
                    "owner_seat_ref": "seat.worker.implementation",
                    "acceptance_refs": _hard_crud_acceptance_refs(),
                    "source_surface_refs": ["surface.backend-api"],
                    "evidence_obligations": _hard_crud_evidence_obligations(),
                    "allowed_write_set": ["app/", "tests/"],
                    "required_outputs": ["app/server.py", "tests/test_api.py"],
                    "commands": [
                        {
                            "command_id": "cmd.backend.tests",
                            "label": "Run backend tests",
                            "command": ["python", "-m", "pytest", "tests/test_api.py"],
                            "cwd": "10-project",
                        }
                    ],
                }
            ]
        }
    }
    (output_root / "00-boardroom/generated-ticket-graph.json").write_text(
        json.dumps({"provider_output": ticket_graph}),
        encoding="utf-8",
    )
    fake_executor = FakeAtomicExecutor()

    result = run_v2_090f_worker_execution_stage(
        output_root=output_root,
        workspace_root=tmp_path / "workspace",
        settings=settings,
        atomic_executor=fake_executor,
    )

    assert result["status"] == "worker_execution_succeeded"
    assert len(fake_executor.requests) == 1
    request, provider_kind = fake_executor.requests[0]
    assert provider_kind == "real"
    assert request.execution_package.ticket_ref.value == "ticket.impl.backend_api"
    configured_event_root = Path(settings.runtime.atomic_agent.event_stream_root)
    assert request.event_stream_root.parent == configured_event_root
    assert request.event_stream_root.name.startswith("run-")
    worker_evidence = json.loads(
        (output_root / "20-evidence/worker-execution.json").read_text(
            encoding="utf-8"
        )
    )
    assert worker_evidence["status"] == "worker_execution_succeeded"
    assert worker_evidence["tickets"][0]["atomic_run_id"] == (
        "atomic-run.ticket.impl.backend_api"
    )
    assert not (output_root / "closeout-package.json").exists()


def test_v2_090f_worker_execution_stage_uses_run_scoped_event_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import dataclass

    from boardroom_os.config.boardroom import load_boardroom_settings
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        resolve_v2_090f_config_paths_from_env,
        run_v2_090f_worker_execution_stage,
    )

    @dataclass(frozen=True)
    class FakeProviderAttempt:
        provider_attempt_id: object

    @dataclass(frozen=True)
    class FakeProjection:
        source_lineage_inputs: tuple[dict[str, object], ...]
        event_stream_ref: str
        events_hash: str

    @dataclass(frozen=True)
    class FakeExecutionResult:
        atomic_run_id: str
        provider_attempt: object
        projection: object

    class ProviderAttemptId:
        def __init__(self, value: str) -> None:
            self.value = value

    class RecordingExecutor:
        def __init__(self) -> None:
            self.event_stream_roots = []

        def execute(self, request, *, provider_transport_kind: str = "real"):
            self.event_stream_roots.append(request.event_stream_root)
            ticket = request.execution_package.ticket_ref.value
            return FakeExecutionResult(
                atomic_run_id=f"atomic-run.{ticket}",
                provider_attempt=FakeProviderAttempt(
                    provider_attempt_id=ProviderAttemptId(f"provider-attempt.atomic.{ticket}")
                ),
                projection=FakeProjection(
                    source_lineage_inputs=(
                        {"path": "app/db.py", "producer_ticket_ref": ticket},
                    ),
                    event_stream_ref=f"{ticket}.jsonl",
                    events_hash="sha256:" + "c" * 64,
                ),
            )

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    monkeypatch.setenv("BOARDROOM_RUNTIME_CONFIG", "config/boardroom-runtime.v2-090f.yaml")
    monkeypatch.setenv("BOARDROOM_PROVIDERS_CONFIG", "config/boardroom-providers.v2-090f.yaml")
    monkeypatch.setenv("BOARDROOM_ROLES_CONFIG", "config/boardroom-roles.v2-090f.yaml")
    settings = load_boardroom_settings(
        resolve_v2_090f_config_paths_from_env(dict(os.environ)),
        env_values=dict(os.environ),
    )
    output_root = tmp_path / "tiny-fullstack"
    (output_root / "00-boardroom").mkdir(parents=True)
    ticket_graph = {
        "ticket_graph": {
            "nodes": [
                {
                    "node_ref": "ticket.backend",
                    "node_type": "implementation",
                    "title": "Implement backend",
                    "depends_on": [],
                    "owner_seat_ref": "seat.worker.implementation",
                    "acceptance_refs": _hard_crud_acceptance_refs(),
                    "source_surface_refs": ["surface.backend"],
                    "evidence_obligations": _hard_crud_evidence_obligations(),
                    "allowed_write_set": ["app/", "tests/"],
                    "required_outputs": ["app/server.py", "tests/test_api.py"],
                    "commands": [
                        {
                            "command_id": "cmd.backend.tests",
                            "label": "Run backend tests",
                            "command": ["python", "-m", "unittest", "tests.test_api"],
                            "cwd": ".",
                        }
                    ],
                }
            ]
        }
    }
    (output_root / "00-boardroom/generated-ticket-graph.json").write_text(
        json.dumps({"provider_output": ticket_graph}),
        encoding="utf-8",
    )
    first_executor = RecordingExecutor()
    second_executor = RecordingExecutor()

    run_v2_090f_worker_execution_stage(
        output_root=output_root,
        workspace_root=tmp_path / "workspace-a",
        settings=settings,
        atomic_executor=first_executor,
    )
    run_v2_090f_worker_execution_stage(
        output_root=output_root,
        workspace_root=tmp_path / "workspace-b",
        settings=settings,
        atomic_executor=second_executor,
    )

    assert first_executor.event_stream_roots
    assert second_executor.event_stream_roots
    assert first_executor.event_stream_roots[0] != second_executor.event_stream_roots[0]
    configured_event_root = Path(settings.runtime.atomic_agent.event_stream_root)
    assert first_executor.event_stream_roots[0].parent == configured_event_root
    assert second_executor.event_stream_roots[0].parent == configured_event_root


def test_v2_090f_worker_execution_stage_writes_partial_evidence_on_later_ticket_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import dataclass

    from boardroom_os.config.boardroom import load_boardroom_settings
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        resolve_v2_090f_config_paths_from_env,
        run_v2_090f_worker_execution_stage,
    )

    @dataclass(frozen=True)
    class FakeProviderAttempt:
        provider_attempt_id: object

    @dataclass(frozen=True)
    class FakeProjection:
        atomic_run_id: str
        source_lineage_inputs: tuple[dict[str, object], ...]
        event_stream_ref: str
        events_hash: str

    @dataclass(frozen=True)
    class FakeExecutionResult:
        atomic_run_id: str
        provider_attempt: object
        projection: object

    class ProviderAttemptId:
        def __init__(self, value: str) -> None:
            self.value = value

    class FailingSecondTicketExecutor:
        def __init__(self) -> None:
            self.calls = 0

        def execute(self, request, *, provider_transport_kind: str = "real"):
            self.calls += 1
            ticket = request.execution_package.ticket_ref.value
            if self.calls == 2:
                raise ValueError("atomic-agent result must be completed")
            return FakeExecutionResult(
                atomic_run_id=f"atomic-run.{ticket}",
                provider_attempt=FakeProviderAttempt(
                    provider_attempt_id=ProviderAttemptId(
                        f"provider-attempt.atomic.{ticket}"
                    )
                ),
                projection=FakeProjection(
                    atomic_run_id=f"atomic-run.{ticket}",
                    source_lineage_inputs=(
                        {
                            "path": "app/db.py",
                            "producer_ticket_ref": ticket,
                        },
                    ),
                    event_stream_ref=f"{ticket}.jsonl",
                    events_hash="sha256:" + "b" * 64,
                ),
            )

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    monkeypatch.setenv("BOARDROOM_RUNTIME_CONFIG", "config/boardroom-runtime.v2-090f.yaml")
    monkeypatch.setenv("BOARDROOM_PROVIDERS_CONFIG", "config/boardroom-providers.v2-090f.yaml")
    monkeypatch.setenv("BOARDROOM_ROLES_CONFIG", "config/boardroom-roles.v2-090f.yaml")
    settings = load_boardroom_settings(
        resolve_v2_090f_config_paths_from_env(dict(os.environ)),
        env_values=dict(os.environ),
    )
    output_root = tmp_path / "tiny-fullstack"
    (output_root / "00-boardroom").mkdir(parents=True)
    ticket_graph = {
        "ticket_graph": {
            "nodes": [
                {
                    "node_ref": "ticket.sqlite",
                    "node_type": "implementation",
                    "title": "Implement SQLite",
                    "depends_on": [],
                    "owner_seat_ref": "seat.worker.implementation",
                    "acceptance_refs": _hard_crud_acceptance_refs(),
                    "source_surface_refs": ["surface.sqlite"],
                    "evidence_obligations": _hard_crud_evidence_obligations(),
                    "allowed_write_set": ["app/db.py", "tests/test_db.py"],
                    "required_outputs": ["app/db.py", "tests/test_db.py"],
                    "commands": [
                        {
                            "command_id": "cmd.sqlite.tests",
                            "label": "Run SQLite tests",
                            "command": ["python", "-m", "unittest", "tests.test_db"],
                            "cwd": ".",
                        }
                    ],
                },
                {
                    "node_ref": "ticket.backend",
                    "node_type": "implementation",
                    "title": "Implement backend",
                    "depends_on": ["ticket.sqlite"],
                    "owner_seat_ref": "seat.worker.implementation",
                    "acceptance_refs": _hard_crud_acceptance_refs(),
                    "source_surface_refs": ["surface.backend"],
                    "evidence_obligations": _hard_crud_evidence_obligations(),
                    "allowed_write_set": ["app/server.py", "tests/test_api.py"],
                    "required_outputs": ["app/server.py", "tests/test_api.py"],
                    "commands": [
                        {
                            "command_id": "cmd.backend.tests",
                            "label": "Run backend tests",
                            "command": ["python", "-m", "unittest", "tests.test_api"],
                            "cwd": ".",
                        }
                    ],
                },
            ]
        }
    }
    (output_root / "00-boardroom/generated-ticket-graph.json").write_text(
        json.dumps({"provider_output": ticket_graph}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="atomic-agent result must be completed"):
        run_v2_090f_worker_execution_stage(
            output_root=output_root,
            workspace_root=tmp_path / "workspace",
            settings=settings,
            atomic_executor=FailingSecondTicketExecutor(),
        )

    assert not (output_root / "20-evidence/worker-execution.json").exists()
    partial = json.loads(
        (output_root / "20-evidence/worker-execution.partial.json").read_text(
            encoding="utf-8"
        )
    )
    assert partial["status"] == "worker_execution_failed"
    assert partial["completed_ticket_count"] == 1
    assert partial["tickets"][0]["ticket_ref"] == "ticket.sqlite"
    assert partial["failed_ticket_ref"] == "ticket.backend"
    assert partial["failure_kind"] == "ValueError"
