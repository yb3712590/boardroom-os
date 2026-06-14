import pytest

from boardroom_os.rework.evidence import ReworkEvidenceError, evaluate_rework_closeout
from tests.rework.fixtures import rework_evidence as fx


def test_rework_closeout_rejects_old_run_manifest_ref() -> None:
    recheck_input = fx.rework_input_with_closeout_context(old_run_manifest=True)
    fresh = fx.fresh_recheck_parts()

    with pytest.raises(ReworkEvidenceError, match="run manifest namespace"):
        evaluate_rework_closeout(
            recheck_input,
            fresh.source_inventory,
            fresh.final_evidence_table,
            fresh.checker_verdict,
        )


def test_rework_closeout_rejects_old_source_inventory() -> None:
    recheck_input = fx.rework_input_with_closeout_context()
    fresh = fx.fresh_recheck_parts()

    with pytest.raises(ReworkEvidenceError, match="source inventory namespace"):
        evaluate_rework_closeout(
            recheck_input,
            fresh.old_source_inventory,
            fresh.final_evidence_table,
            fresh.checker_verdict,
        )


def test_rework_closeout_rejects_old_checker_verdict() -> None:
    recheck_input = fx.rework_input_with_closeout_context()
    fresh = fx.fresh_recheck_parts()

    with pytest.raises(ReworkEvidenceError, match="checker verdict namespace"):
        evaluate_rework_closeout(
            recheck_input,
            fresh.source_inventory,
            fresh.final_evidence_table,
            fresh.old_checker_verdict,
        )
