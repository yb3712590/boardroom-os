from datetime import timedelta

import pytest
from pydantic import ValidationError

from boardroom_os.evidence.table import EvidenceNamespaceRef, FinalEvidenceTable
from boardroom_os.rework.evidence import (
    ReworkEnvironmentUsage,
    ReworkEvidenceError,
    build_rework_checker_verdict,
    build_rework_final_evidence_table,
    validate_rework_evidence_freshness,
    validate_rework_final_evidence_table_freshness,
    validate_rework_run_manifest_readiness,
)
from tests.rework.fixtures import rework_evidence as fx


def test_old_final_evidence_table_cannot_satisfy_rework_attempt() -> None:
    recheck_input = fx.rework_input_with_verified_evidence()
    current_table = build_rework_final_evidence_table(recheck_input)
    old_table = current_table.model_copy(
        update={"evidence_namespace_ref": EvidenceNamespaceRef(value="rework-evidence.run-old.cycle-old.attempt-old.g1")}
    )
    verified = tuple(
        result.verified_evidence
        for result in recheck_input.evidence_verification_results
        if result.verified_evidence is not None
    )

    with pytest.raises(ReworkEvidenceError, match="final evidence table namespace"):
        validate_rework_final_evidence_table_freshness(
            old_table,
            namespace=recheck_input.namespace,
            verified_evidence=verified,
        )


def test_checker_verdict_cannot_use_old_final_evidence_table_namespace() -> None:
    recheck_input = fx.rework_input_with_verified_evidence()
    current_table = build_rework_final_evidence_table(recheck_input)
    old_table = FinalEvidenceTable(
        acceptance_contract_ref=current_table.acceptance_contract_ref,
        evidence_namespace_ref=EvidenceNamespaceRef(
            value="rework-evidence.run-old.cycle-old.attempt-old.g1"
        ),
        generated_at=current_table.generated_at,
        rows=current_table.rows,
    )

    with pytest.raises(ReworkEvidenceError, match="final evidence table namespace"):
        build_rework_checker_verdict(recheck_input, old_table)


def test_workspace_mutation_without_provider_attempt_fails() -> None:
    recheck_input = fx.rework_input_with_verified_evidence()
    attempt = recheck_input.attempt.model_copy(update={"provider_attempt_refs": ()})
    stale_input = recheck_input.model_copy(update={"attempt": attempt})

    with pytest.raises((ReworkEvidenceError, ValidationError), match="provider_attempt"):
        validate_rework_evidence_freshness(stale_input)


def test_source_edits_without_source_lineage_records_fail() -> None:
    recheck_input = fx.rework_input_with_verified_evidence().model_copy(
        update={"source_lineage_records": ()}
    )

    with pytest.raises((ReworkEvidenceError, ValidationError), match="source lineage"):
        validate_rework_evidence_freshness(recheck_input)


def test_checker_review_before_current_evidence_verification_fails() -> None:
    recheck_input = fx.rework_input_with_verified_evidence()
    stale_input = recheck_input.model_copy(update={"checked_at": fx.NOW - timedelta(minutes=5)})

    with pytest.raises(ReworkEvidenceError, match="checker.*after.*verified evidence"):
        validate_rework_evidence_freshness(stale_input)


def test_behavioral_probe_failure_omitted_from_final_evidence_table_fails() -> None:
    recheck_input = fx.rework_input_with_behavioral_probe_failure().model_copy(
        update={"failed_final_evidence_blockers": ()}
    )

    with pytest.raises(ReworkEvidenceError, match="behavioral probe.*final evidence"):
        build_rework_final_evidence_table(recheck_input)


def test_run_commands_require_explicit_service_contracts() -> None:
    with pytest.raises(ReworkEvidenceError, match="service contracts"):
        validate_rework_run_manifest_readiness(
            fx.run_manifest_with_run_command_and_no_service_contracts(),
            active_acceptance_refs=(fx.ACCEPTANCE_REF,),
            environment_usage=(),
        )


def test_implementation_env_usage_must_be_declared_in_run_manifest() -> None:
    with pytest.raises(ReworkEvidenceError, match="undeclared environment"):
        validate_rework_run_manifest_readiness(
            fx.run_manifest_with_host_port_only(),
            active_acceptance_refs=(fx.ACCEPTANCE_REF,),
            environment_usage=(
                ReworkEnvironmentUsage(
                    source_ref="source-file.backend.app",
                    env_names=("LIBRARY_DB_PATH",),
                ),
            ),
        )
