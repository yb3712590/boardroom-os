from __future__ import annotations

from boardroom_os.closeout.gate import CloseoutCommandEvidenceBinding, CloseoutGate, CloseoutGateBlockerCode, CloseoutGateVerdict
from boardroom_os.execution.verification_run import VerificationRunRef
from tests.closeout.test_closeout_gate import _ready_input, _verification_run
from tests.negative.test_run_manifest_command_coverage import _tiny_failure_gate_input


def _command_blockers(result):
    return tuple(
        blocker
        for blocker in result.blockers
        if blocker.code is CloseoutGateBlockerCode.COMMAND_EVIDENCE_NOT_FINAL
    )


def test_closeout_gate_blocks_run_command_with_verification_run_but_no_service_readiness() -> None:
    gate_input = _ready_input().model_copy(update={"service_run_evidence": ()})

    result = CloseoutGate().evaluate(gate_input)

    assert result.verdict is CloseoutGateVerdict.BLOCKED
    blockers = _command_blockers(result)
    assert any(blocker.related_ref == "run-app" for blocker in blockers)
    assert any("RUN_MANIFEST_SERVICE_NOT_READY" in blocker.message for blocker in blockers)


def test_tiny_run_backend_and_frontend_remain_blocked_without_service_readiness() -> None:
    gate_input = _tiny_failure_gate_input().model_copy(update={"service_run_evidence": ()})

    result = CloseoutGate().evaluate(gate_input)

    assert result.verdict is CloseoutGateVerdict.BLOCKED
    blockers = _command_blockers(result)
    assert {blocker.related_ref for blocker in blockers} >= {"run-backend", "run-frontend"}


def test_closeout_gate_rejects_run_command_bound_to_verification_run() -> None:
    ready = _ready_input()
    run_verification = _verification_run(
        verification_run_id="verification-run.run-app",
        command_id="run-app",
        command=("python", "app.py"),
    )
    replaced_run_binding = CloseoutCommandEvidenceBinding(
        verification_run_ref=VerificationRunRef(value=run_verification.verification_run_id.value),
        run_manifest_ref=ready.final_command_bindings[0].run_manifest_ref,
        package_contract_ref=ready.final_command_bindings[0].package_contract_ref,
        command_id=ready.final_command_bindings[0].command_id,
        binding_kind=ready.final_command_bindings[0].binding_kind,
    )
    gate_input = ready.model_copy(
        update={
            "verification_runs": (*ready.verification_runs, run_verification),
            "service_run_evidence": (),
            "workspace_evidence_bundle": ready.workspace_evidence_bundle.model_copy(
                update={
                    "verification_run_refs": (
                        *ready.workspace_evidence_bundle.verification_run_refs,
                        run_verification.verification_run_id,
                    ),
                    "service_run_refs": (),
                }
            ),
            "final_command_bindings": (replaced_run_binding, ready.final_command_bindings[1]),
        }
    )

    result = CloseoutGate().evaluate(gate_input)

    assert result.verdict is CloseoutGateVerdict.BLOCKED
    blockers = _command_blockers(result)
    assert any(blocker.related_ref == "run-app" for blocker in blockers)
    assert any("RUN_MANIFEST_SERVICE_NOT_READY" in blocker.message for blocker in blockers)
