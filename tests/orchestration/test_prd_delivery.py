from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError


def _delivery_input(tmp_path: Path, *, require_real_provider: bool = False):
    from boardroom_os.orchestration.prd_delivery import PrdDeliveryInput

    prd = tmp_path / "prd.md"
    prd.write_text("Build a tiny checkout app.", encoding="utf-8")
    return PrdDeliveryInput(
        prd_path=prd,
        workspace_root=tmp_path / "workspace",
        output_root=tmp_path / "output",
        runtime_config_path=Path("config/boardroom-runtime.v2-090f.yaml"),
        providers_config_path=Path("config/boardroom-providers.v2-090f.yaml"),
        roles_config_path=Path("config/boardroom-roles.v2-090f.yaml"),
        require_real_provider=require_real_provider,
    )


def test_prd_delivery_input_rejects_stage_switch(tmp_path: Path) -> None:
    from boardroom_os.orchestration.prd_delivery import PrdDeliveryInput

    prd = tmp_path / "prd.md"
    prd.write_text("Build a tiny checkout app.", encoding="utf-8")

    with pytest.raises(ValidationError, match="stage"):
        PrdDeliveryInput(
            prd_path=prd,
            workspace_root=tmp_path / "workspace",
            output_root=tmp_path / "output",
            runtime_config_path=Path("config/boardroom-runtime.v2-090f.yaml"),
            providers_config_path=Path("config/boardroom-providers.v2-090f.yaml"),
            roles_config_path=Path("config/boardroom-roles.v2-090f.yaml"),
            require_real_provider=False,
            stage="rework-entry",
        )


def test_prd_delivery_passes_without_rework_when_closeout_passes(tmp_path: Path) -> None:
    from boardroom_os.orchestration.prd_delivery import (
        PrdDeliveryStageResult,
        PrdDeliveryTerminalStatus,
        run_prd_delivery,
    )

    calls: list[str] = []

    def fake_stage_runner(delivery_input):
        calls.append("full-native-chain")
        return PrdDeliveryStageResult(
            closeout_passed=True,
            graph_refs=("ticket-graph.generated.v1",),
            provider_attempt_refs=("provider-attempt.worker.1",),
            evidence_refs=("evidence.live-blackbox",),
            closeout_refs=("closeout-gate.passed",),
        )

    result = run_prd_delivery(
        _delivery_input(tmp_path),
        stage_runner=fake_stage_runner,
    )

    assert calls == ["full-native-chain"]
    assert result.terminal_status is PrdDeliveryTerminalStatus.PASSED_WITHOUT_REWORK
    assert result.rework_cycle_refs == ()
    assert result.provider_attempt_refs == ("provider-attempt.worker.1",)
    assert result.closeout_refs == ("closeout-gate.passed",)
    assert result.audit_path is not None
    assert result.audit_path.is_file()


def test_prd_delivery_routes_verified_blocker_through_native_rework(
    tmp_path: Path,
) -> None:
    from boardroom_os.orchestration.prd_delivery import (
        PrdDeliveryStageResult,
        PrdDeliveryTerminalStatus,
        run_prd_delivery,
    )
    from boardroom_os.proving.v2_100f_native_manifest_rework import (
        V2_100FNativeManifestReworkResult,
        V2_100FTerminalStatus,
    )

    calls: list[object] = []
    manifest_path = tmp_path / "output" / "20-evidence" / "tests" / "run-manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text('{"commands": []}', encoding="utf-8")

    def fake_stage_runner(delivery_input):
        return PrdDeliveryStageResult(
            closeout_passed=False,
            graph_refs=("ticket-graph.generated.v1",),
            provider_attempt_refs=("provider-attempt.worker.1",),
            evidence_refs=("evidence.closeout.blocker",),
            closeout_refs=("closeout-gate.blocked",),
            verified_blocker_refs=("blocker.live-blackbox",),
            run_manifest_path=manifest_path,
        )

    def fake_native_runner(native_input, **kwargs):
        calls.append(native_input)
        return V2_100FNativeManifestReworkResult(
            terminal_status=V2_100FTerminalStatus.PASSED,
            verify_blackbox_ticket_ref="ticket.verify-blackbox.generated",
            before_graph_ref="ticket-graph.before-rework",
            seat_assignment_ref="seat-assignment.rework",
            execution_package_ref="exec.verify-blackbox",
            provider_attempt_ref="provider-attempt.verify-blackbox",
            blackbox_plan_ref="blackbox-plan.provider-backed",
            fact_refs=("fact.live-blackbox.passed",),
            rework_request_ref=None,
            verify_blackbox_ready_before_execution=True,
            assigned_seat_ref="seat.tester.integration",
        )

    result = run_prd_delivery(
        _delivery_input(tmp_path),
        stage_runner=fake_stage_runner,
        native_manifest_runner=fake_native_runner,
    )

    assert calls
    assert result.terminal_status is PrdDeliveryTerminalStatus.PASSED_AFTER_REWORK
    assert "ticket-graph.before-rework" in result.graph_refs
    assert "provider-attempt.verify-blackbox" in result.provider_attempt_refs
    assert "fact.live-blackbox.passed" in result.evidence_refs
    assert result.rework_cycle_refs == ("v2-100f-native-manifest-rework",)


def test_prd_delivery_maps_unresolved_rework_to_escalated(
    tmp_path: Path,
) -> None:
    from boardroom_os.orchestration.prd_delivery import (
        PrdDeliveryStageResult,
        PrdDeliveryTerminalStatus,
        run_prd_delivery,
    )
    from boardroom_os.proving.v2_100f_native_manifest_rework import (
        V2_100FNativeManifestReworkResult,
        V2_100FTerminalStatus,
    )

    manifest_path = tmp_path / "output" / "20-evidence" / "tests" / "run-manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text('{"commands": []}', encoding="utf-8")

    def fake_stage_runner(delivery_input):
        return PrdDeliveryStageResult(
            closeout_passed=False,
            closeout_refs=("closeout-gate.blocked",),
            verified_blocker_refs=("blocker.live-blackbox",),
            run_manifest_path=manifest_path,
        )

    def fake_native_runner(native_input, **kwargs):
        return V2_100FNativeManifestReworkResult(
            terminal_status=V2_100FTerminalStatus.REWORK_REQUIRED,
            verify_blackbox_ticket_ref="ticket.verify-blackbox.generated",
            rework_request_ref="rework-request.live-blackbox",
            fact_refs=("fact.live-blackbox.failed",),
            rework_issue_codes=("run_manifest_error",),
        )

    result = run_prd_delivery(
        _delivery_input(tmp_path),
        stage_runner=fake_stage_runner,
        native_manifest_runner=fake_native_runner,
    )

    assert result.terminal_status is PrdDeliveryTerminalStatus.ESCALATED_OR_EXHAUSTED
    assert "rework-request.live-blackbox" in result.rework_cycle_refs
    assert "fact.live-blackbox.failed" in result.evidence_refs


def test_prd_delivery_does_not_route_raw_stage_exception_as_verified_rework(
    tmp_path: Path,
) -> None:
    from boardroom_os.orchestration.prd_delivery import (
        PrdDeliveryStageResult,
        PrdDeliveryTerminalStatus,
        run_prd_delivery,
    )
    from boardroom_os.proving.v2_100f_native_manifest_rework import (
        V2_100FNativeManifestReworkResult,
        V2_100FTerminalStatus,
    )

    calls: list[object] = []
    manifest_path = tmp_path / "output" / "20-evidence" / "tests" / "run-manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text('{"commands": []}', encoding="utf-8")

    def fake_stage_runner(delivery_input):
        return PrdDeliveryStageResult(
            closeout_passed=False,
            run_manifest_path=manifest_path,
            raw_error_ref="30-audit/raw-run-error.txt",
            observed_failure_refs=(
                "stage_exception",
                "30-audit/raw-run-error.txt",
            ),
        )

    def fake_native_runner(native_input, **kwargs):
        calls.append(native_input)
        return V2_100FNativeManifestReworkResult(
            terminal_status=V2_100FTerminalStatus.PASSED,
            verify_blackbox_ticket_ref="ticket.verify-blackbox.generated",
            fact_refs=("fact.live-blackbox.passed",),
        )

    result = run_prd_delivery(
        _delivery_input(tmp_path),
        stage_runner=fake_stage_runner,
        native_manifest_runner=fake_native_runner,
    )

    assert calls == []
    assert result.terminal_status is PrdDeliveryTerminalStatus.BLOCKED_FAIL_CLOSED
    assert result.checked_refs == (
        "stage_exception",
        "30-audit/raw-run-error.txt",
        "verified_blocker_missing_for_rework",
    )
    assert result.rework_cycle_refs == ()


def test_prd_delivery_fails_closed_without_real_provider_opt_in(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from boardroom_os.orchestration.prd_delivery import (
        PrdDeliveryTerminalStatus,
        run_prd_delivery,
    )

    monkeypatch.delenv("BOARDROOM_RUN_REAL_PROVIDER_PROVING", raising=False)

    result = run_prd_delivery(_delivery_input(tmp_path, require_real_provider=True))

    assert result.terminal_status is PrdDeliveryTerminalStatus.BLOCKED_FAIL_CLOSED
    assert result.provider_attempt_refs == ()
    assert "real_provider_opt_in_missing" in result.checked_refs
