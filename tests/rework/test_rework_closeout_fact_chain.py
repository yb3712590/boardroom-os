from boardroom_os.closeout.gate import CloseoutGateVerdict
from boardroom_os.rework.evidence import recheck_rework_attempt
from boardroom_os.rework.model import ReworkOutcomeStatus
from tests.rework.fixtures import rework_evidence as fx


def test_rework_closeout_consumes_current_attempt_fact_chain() -> None:
    result = recheck_rework_attempt(fx.rework_input_with_closeout_context())

    assert result.closeout_gate_result is not None
    assert result.closeout_gate_result.verdict is CloseoutGateVerdict.PASSED
    assert result.status is ReworkOutcomeStatus.ACCEPTED
    assert result.final_evidence_table.final_evidence_table_id.value in result.checked_refs
    assert result.source_inventory.source_inventory_id.value in result.checked_refs
