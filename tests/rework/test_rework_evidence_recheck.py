from boardroom_os.checker.verdict import CheckerVerdictStatus
from boardroom_os.evidence.table import FinalEvidenceStatus
from boardroom_os.rework.evidence import recheck_rework_attempt, rework_evidence_namespace_ref
from boardroom_os.rework.model import ReworkOutcomeStatus
from tests.rework.fixtures import rework_evidence as fx


def test_rework_attempt_rebuilds_source_inventory_table_and_checker() -> None:
    recheck_input = fx.rework_input_with_verified_evidence()
    result = recheck_rework_attempt(recheck_input)
    namespace_ref = rework_evidence_namespace_ref(recheck_input.namespace)

    assert result.final_evidence_table.evidence_namespace_ref == namespace_ref
    assert all(row.status is FinalEvidenceStatus.SATISFIED for row in result.final_evidence_table.rows)
    assert result.source_inventory.entries
    assert result.checker_verdict.status is CheckerVerdictStatus.APPROVED
    assert result.status is ReworkOutcomeStatus.ACCEPTED
    assert result.accepted_blocker_refs == (fx.TARGET_BLOCKER_REF,)

    outcome = result.to_rework_outcome()
    assert outcome.status is ReworkOutcomeStatus.ACCEPTED
    assert outcome.final_evidence_table_ref == result.final_evidence_table.final_evidence_table_id.value
