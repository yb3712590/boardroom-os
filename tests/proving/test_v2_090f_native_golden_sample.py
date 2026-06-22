from __future__ import annotations

from pathlib import Path


def test_v2_090f_native_golden_sample_delegates_to_generic_prd_delivery(
    tmp_path: Path,
) -> None:
    from boardroom_os.orchestration.prd_delivery import (
        PrdDeliveryResult,
        PrdDeliveryTerminalStatus,
    )
    from boardroom_os.proving.v2_090f_native_golden_sample import (
        V2_090FNativeGoldenSampleInput,
        run_v2_090f_native_golden_sample,
    )

    calls = []

    def fake_delivery_runner(delivery_input):
        calls.append(delivery_input)
        return PrdDeliveryResult(
            terminal_status=PrdDeliveryTerminalStatus.PASSED_AFTER_REWORK,
            run_id="run.v2-090f.native",
            workspace_root=delivery_input.workspace_root,
            output_root=delivery_input.output_root,
            graph_refs=("ticket-graph.generated.v2",),
            provider_attempt_refs=("provider-attempt.worker",),
            evidence_refs=("evidence.live-blackbox",),
            closeout_refs=("closeout-gate.passed",),
            audit_path=delivery_input.output_root / "30-audit" / "prd-delivery.json",
            rework_cycle_refs=("rework-request.live-blackbox",),
        )

    result = run_v2_090f_native_golden_sample(
        V2_090FNativeGoldenSampleInput(
            workspace_root=tmp_path / "workspace",
            output_root=tmp_path / "output",
            require_real_provider=False,
            reset=True,
        ),
        delivery_runner=fake_delivery_runner,
    )

    assert len(calls) == 1
    delivery_input = calls[0]
    assert delivery_input.prd_path == Path("examples/directives/tiny-fullstack-prd.md")
    assert delivery_input.runtime_config_path == Path("config/boardroom-runtime.v2-090f.yaml")
    assert delivery_input.providers_config_path == Path("config/boardroom-providers.v2-090f.yaml")
    assert delivery_input.roles_config_path == Path("config/boardroom-roles.v2-090f.yaml")
    assert delivery_input.reset is True
    assert result.done_candidate is True
    assert result.delivery_result.terminal_status is PrdDeliveryTerminalStatus.PASSED_AFTER_REWORK


def test_v2_090f_native_golden_sample_only_marks_passed_states_as_done_candidate(
    tmp_path: Path,
) -> None:
    from boardroom_os.orchestration.prd_delivery import (
        PrdDeliveryResult,
        PrdDeliveryTerminalStatus,
    )
    from boardroom_os.proving.v2_090f_native_golden_sample import (
        V2_090FNativeGoldenSampleInput,
        run_v2_090f_native_golden_sample,
    )

    def fake_delivery_runner(delivery_input):
        return PrdDeliveryResult(
            terminal_status=PrdDeliveryTerminalStatus.ESCALATED_OR_EXHAUSTED,
            run_id="run.v2-090f.native",
            workspace_root=delivery_input.workspace_root,
            output_root=delivery_input.output_root,
            closeout_refs=("closeout-gate.blocked",),
            checked_refs=("verified_blocker",),
        )

    result = run_v2_090f_native_golden_sample(
        V2_090FNativeGoldenSampleInput(
            workspace_root=tmp_path / "workspace",
            output_root=tmp_path / "output",
            require_real_provider=False,
        ),
        delivery_runner=fake_delivery_runner,
    )

    assert result.done_candidate is False
    assert result.delivery_result.terminal_status is PrdDeliveryTerminalStatus.ESCALATED_OR_EXHAUSTED
