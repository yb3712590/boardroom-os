from __future__ import annotations

import pytest


def _slot(
    seat_ref: str,
    role_profile_ref: str,
    role_category: str,
    skill_refs: tuple[str, ...] = ("skill.command.test",),
    default_tools: tuple[str, ...] = ("read_file", "submit_result"),
    provider_profile_ref: str = "provider.openai-compatible.v2-090f-primary",
    budget_profile_ref: str = "agent_team.v2_090f.fullstack",
) -> dict[str, object]:
    return {
        "seat_ref": seat_ref,
        "role_profile_ref": role_profile_ref,
        "role_category": role_category,
        "provider_profile_ref": provider_profile_ref,
        "skill_refs": skill_refs,
        "default_tools": default_tools,
        "budget_profile_ref": budget_profile_ref,
    }


def test_v2_090f_rejects_missing_required_agent_team_seat() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        validate_required_agent_team_slots,
    )

    with pytest.raises(ValueError, match="missing required agent team seats"):
        validate_required_agent_team_slots(
            [_slot("seat.worker.implementation", "role.worker.implementation", "worker")]
        )


def test_v2_090f_rejects_all_roles_reusing_worker_seat() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        validate_required_agent_team_slots,
    )

    slots = [
        _slot(
            required,
            "role.worker.implementation",
            "worker",
            default_tools=("read_file", "write_file", "run_command", "submit_result"),
        )
        for required in (
            "seat.ceo.delivery",
            "seat.architect.delivery",
            "seat.worker.implementation",
            "seat.tester.integration",
            "seat.checker.acceptance",
            "seat.closeout.package",
        )
    ]

    with pytest.raises(
        ValueError, match="required seats must not all reuse worker role profile"
    ):
        validate_required_agent_team_slots(slots)


def test_v2_090f_rejects_non_worker_reusing_worker_role_profile() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        validate_required_agent_team_slots,
    )

    slots = [
        _slot("seat.ceo.delivery", "role.worker.implementation", "governance"),
        _slot("seat.architect.delivery", "role.architecture.lead", "architecture"),
        _slot(
            "seat.worker.implementation",
            "role.worker.implementation",
            "worker",
            default_tools=("read_file", "write_file", "run_command", "submit_result"),
        ),
        _slot("seat.tester.integration", "role.verification.tester", "verification"),
        _slot("seat.checker.acceptance", "role.verification.checker", "verification"),
        _slot("seat.closeout.package", "role.audit.closeout", "audit"),
    ]

    with pytest.raises(
        ValueError, match="non-worker seat must not reuse worker role profile"
    ):
        validate_required_agent_team_slots(slots)


def test_v2_090f_rejects_non_high_budget_or_provider_profile() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        validate_required_agent_team_slots,
    )

    slots = [
        _slot(
            "seat.ceo.delivery",
            "role.governance.ceo",
            "governance",
            provider_profile_ref="provider.openai-compatible.primary",
        ),
        _slot("seat.architect.delivery", "role.architecture.lead", "architecture"),
        _slot(
            "seat.worker.implementation",
            "role.worker.implementation",
            "worker",
            default_tools=("read_file", "write_file", "run_command", "submit_result"),
        ),
        _slot("seat.tester.integration", "role.verification.tester", "verification"),
        _slot("seat.checker.acceptance", "role.verification.checker", "verification"),
        _slot(
            "seat.closeout.package",
            "role.audit.closeout",
            "audit",
            budget_profile_ref="worker.implementation.default",
        ),
    ]

    with pytest.raises(
        ValueError,
        match="required seats must use V2-090F high-budget provider baseline",
    ):
        validate_required_agent_team_slots(slots)


def test_v2_090f_rejects_non_worker_source_write_tools() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        validate_required_agent_team_slots,
    )

    slots = [
        _slot("seat.ceo.delivery", "role.governance.ceo", "governance"),
        _slot("seat.architect.delivery", "role.architecture.lead", "architecture"),
        _slot(
            "seat.worker.implementation",
            "role.worker.implementation",
            "worker",
            default_tools=("read_file", "write_file", "run_command", "submit_result"),
        ),
        _slot("seat.tester.integration", "role.verification.tester", "verification"),
        _slot(
            "seat.checker.acceptance",
            "role.verification.checker",
            "verification",
            default_tools=("read_file", "write_file", "submit_result"),
        ),
        _slot("seat.closeout.package", "role.audit.closeout", "audit"),
    ]

    with pytest.raises(
        ValueError, match="non-worker role must not have implementation write tools"
    ):
        validate_required_agent_team_slots(slots)


def test_v2_090f_rejects_role_context_missing_hook_snapshot() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        validate_role_invocation_context,
    )

    with pytest.raises(ValueError, match="role_context must include RolePromptHook"):
        validate_role_invocation_context(
            seat_ref="seat.ceo.delivery",
            expected_skill_refs=("skill.governance.ceo",),
            invocation_role_context="CEO prompt without audit fields",
            invocation_skill_context={"skill_refs": ["skill.governance.ceo"]},
        )


def test_v2_090f_rejects_skill_context_mismatch() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        validate_role_invocation_context,
    )

    role_context = "\n".join(
        (
            "RolePromptHook ref: role-prompt-hook.baseline.ceo.v1",
            "RolePromptHook version: v1",
            "RolePromptHook sha256: sha256:abc",
            "CEO prompt text",
        )
    )

    with pytest.raises(ValueError, match="skill_context.skill_refs mismatch"):
        validate_role_invocation_context(
            seat_ref="seat.ceo.delivery",
            expected_skill_refs=("skill.governance.ceo",),
            invocation_role_context=role_context,
            invocation_skill_context={"skill_refs": ["skill.command.test"]},
        )


def test_v2_090f_rejects_runner_predefined_ticket_graph() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        validate_agent_team_autonomy_inputs,
    )

    with pytest.raises(
        ValueError, match="runner must not predefine implementation ticket graph"
    ):
        validate_agent_team_autonomy_inputs(
            prd_text="Build a tiny checkout app.",
            predefined_ticket_refs=(
                "ticket.tiny.backend-api",
                "ticket.tiny.frontend-ui",
            ),
        )


def test_v2_090f_allows_prd_only_autonomy_input() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        validate_agent_team_autonomy_inputs,
    )

    validate_agent_team_autonomy_inputs(
        prd_text="Build a tiny checkout app.",
        predefined_ticket_refs=(),
    )


def test_v2_090f_closeout_rejects_missing_worker_execution_evidence(
    tmp_path,
) -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import run_v2_090f_closeout_stage

    with pytest.raises(ValueError, match="worker-execution.json is required"):
        run_v2_090f_closeout_stage(
            output_root=tmp_path / "output",
            workspace_root=tmp_path / "workspace",
        )


def test_v2_090f_closeout_rejects_forbidden_materialized_runtime_files(
    tmp_path,
) -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import run_v2_090f_closeout_stage

    output = tmp_path / "output"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "__pycache__").mkdir()
    (workspace / "__pycache__/module.pyc").write_bytes(b"bad")
    evidence = output / "20-evidence"
    evidence.mkdir(parents=True)
    (evidence / "worker-execution.json").write_text(
        '{"status":"worker_execution_succeeded","tickets":[{"ticket_ref":"ticket.impl","provider_attempt_ref":"provider-attempt.real.impl","declared_command_ids":["cmd.tests"]}]}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="forbidden runtime file"):
        run_v2_090f_closeout_stage(
            output_root=output,
            workspace_root=workspace,
            filter_runtime_files=False,
        )


def test_v2_090f_closeout_rejects_missing_live_blackbox_evidence(
    tmp_path,
) -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import run_v2_090f_closeout_stage

    output = tmp_path / "output"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "README.md").write_text("Run tests with python -m pytest tests\n", encoding="utf-8")
    (workspace / "app").mkdir()
    (workspace / "app/server.py").write_text("print('server')\n", encoding="utf-8")
    (workspace / "tests").mkdir()
    (workspace / "tests/test_api.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    evidence = output / "20-evidence"
    evidence.mkdir(parents=True)
    (evidence / "worker-execution.json").write_text(
        '{"status":"worker_execution_succeeded","tickets":[{"ticket_ref":"ticket.impl","provider_attempt_ref":"provider-attempt.real.impl","declared_command_ids":["cmd.tests"]}]}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="live blackbox evidence is required"):
        run_v2_090f_closeout_stage(
            output_root=output,
            workspace_root=workspace,
            run_live_probe=False,
        )


def test_v2_090f_closeout_rejects_checker_blocker(
    tmp_path,
) -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import run_v2_090f_closeout_stage

    output = tmp_path / "output"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "README.md").write_text("Run tests with python -m pytest tests\n", encoding="utf-8")
    (workspace / "app").mkdir()
    (workspace / "app/server.py").write_text("print('server')\n", encoding="utf-8")
    (workspace / "tests").mkdir()
    (workspace / "tests/test_api.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    evidence = output / "20-evidence"
    evidence.mkdir(parents=True)
    (evidence / "worker-execution.json").write_text(
        '{"status":"worker_execution_succeeded","tickets":[{"ticket_ref":"ticket.impl","provider_attempt_ref":"provider-attempt.real.impl","declared_command_ids":["cmd.tests"]}]}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="checker verdict must be approved"):
        run_v2_090f_closeout_stage(
            output_root=output,
            workspace_root=workspace,
            checker_approved=False,
        )
