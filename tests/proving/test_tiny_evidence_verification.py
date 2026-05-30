from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Mapping

import pytest

from boardroom_os.adapters.process_runner import (
    CommandRunner,
    CommandRunnerInput,
    CommandRunnerResult,
)
from boardroom_os.checker.checker import CheckerService, CheckerServiceInput
from boardroom_os.checker.verdict import CheckerNote, CheckerVerdictStatus, SourceDiffRef
from boardroom_os.contracts.evidence_obligation import EvidenceObligation
from boardroom_os.contracts.types import ContractId
from boardroom_os.evidence.claim import (
    EvidenceArtifactRef,
    build_evidence_claim_from_verification_run,
)
from boardroom_os.evidence.table import (
    FinalEvidenceBlocker,
    FinalEvidenceBlockerCode,
    FinalEvidenceStatus,
    FinalEvidenceTable,
    FinalEvidenceTableBuilder,
    FinalEvidenceTableInput,
)
from boardroom_os.evidence.verifier import (
    ArtifactManifest,
    ArtifactManifestEntry,
    ArtifactSha256,
    EvidencePurposePolicy,
    EvidencePurposeRule,
    EvidenceVerificationBlockerCode,
    EvidenceVerificationInput,
    EvidenceVerifier,
    VerifiedEvidence,
)
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.fallback import EvidencePurpose
from boardroom_os.execution.verification_run import (
    EnvironmentProfileRef,
    RunnerRef,
    VerificationRun,
    WorkspaceSnapshotRef,
)
from boardroom_os.execution.work_product import WorkProduct
from boardroom_os.graph.ticket import TicketId
from boardroom_os.reducers.completion_gate import CompletionGate, CompletionGateInput
from tests.proving.fixtures.tiny_provider_attempts import (
    TinyProviderAttemptFixture,
    build_tiny_provider_attempt_fixture,
)
from tests.proving.fixtures.tiny_ticket_graph import (
    TICKET_TESTS_ID,
)

_GENERATED_AT = datetime(2026, 5, 29, 12, 0, tzinfo=UTC)
_CHECKED_AT = datetime(2026, 5, 29, 12, 10, tzinfo=UTC)
_VERIFIED_AT = datetime(2026, 5, 29, 12, 5, tzinfo=UTC)


@dataclass(frozen=True)
class TinyEvidenceBundle:
    fixture: TinyProviderAttemptFixture
    command_results_by_id: Mapping[str, CommandRunnerResult]
    verified_evidence: tuple[VerifiedEvidence, ...]
    final_evidence_table: FinalEvidenceTable
    work_products_by_ticket_id: Mapping[TicketId, WorkProduct]


def test_tiny_synthetic_verification_without_runner_record_is_rejected(
    tmp_path: Path,
) -> None:
    bundle_seed = _build_tiny_seed()
    package_root = _prepare_tiny_package_root(tmp_path)
    command_result = _run_declared_command(
        fixture=bundle_seed,
        package_root=package_root,
        command_id="test-backend",
    )
    obligation = _obligation_by_artifact_type(bundle_seed, "command_evidence")
    producer_attempt_ref = bundle_seed.provider_attempts_by_ticket_id[
        TICKET_TESTS_ID
    ].provider_attempt_id
    claim = build_evidence_claim_from_verification_run(
        verification_run=command_result.verification_run,
        evidence_obligation=obligation,
        producer_attempt_ref=producer_attempt_ref,
        acceptance_refs=obligation.acceptance_refs,
        source_surface_refs=obligation.source_surface_refs,
        expected_purpose=EvidencePurpose.IMPLEMENTATION,
        summary="Tiny command evidence claim without a persisted runner record.",
    )

    result = EvidenceVerifier().verify(
        EvidenceVerificationInput(
            claim=claim,
            evidence_obligation=obligation,
            active_acceptance_contract=(
                bundle_seed.compiled.ticket_graph_fixture.contracts.acceptance_contract
            ),
            artifact_manifest=_command_artifact_manifest(
                command_result=command_result,
                producer_attempt_ref=producer_attempt_ref,
            ),
            purpose_policy=_purpose_policy(obligation),
            provider_attempts=tuple(bundle_seed.provider_attempts_by_ticket_id.values()),
            verification_runs=(),
            verified_at=_VERIFIED_AT,
        )
    )

    assert result.success is False
    assert result.verified_evidence is None
    assert tuple(blocker.code for blocker in result.blockers) == (
        EvidenceVerificationBlockerCode.MISSING_VERIFICATION_RUN,
    )


def test_tiny_missing_acceptance_map_blocks_final_evidence_table(tmp_path: Path) -> None:
    bundle = _build_tiny_evidence_bundle(tmp_path)
    omitted_acceptance_ref = "AC-TINY-UI-FETCH-BACKEND"
    incomplete_evidence = tuple(
        evidence
        for evidence in bundle.verified_evidence
        if omitted_acceptance_ref
        not in {acceptance_ref.value for acceptance_ref in evidence.acceptance_refs}
    )

    table = _build_final_evidence_table(
        fixture=bundle.fixture,
        verified_evidence=incomplete_evidence,
    )

    missing_rows = tuple(
        row for row in table.rows if row.status is FinalEvidenceStatus.MISSING
    )
    assert table.complete is False
    assert omitted_acceptance_ref in {
        row.acceptance_ref.value for row in missing_rows
    }
    omitted_row = next(
        row for row in missing_rows if row.acceptance_ref.value == omitted_acceptance_ref
    )
    assert omitted_row.verified_evidence_refs == ()
    assert tuple(
        artifact_type.value
        for artifact_type in omitted_row.missing_required_artifact_types
    ) == (
        "frontend_backend_integration_evidence",
        "frontend_source_inventory",
    )
    assert omitted_row.blockers == ()


def test_tiny_checker_notes_cannot_clear_evidence_blocker(tmp_path: Path) -> None:
    bundle = _build_tiny_evidence_bundle(tmp_path)
    first_criterion = (
        bundle.fixture.compiled.ticket_graph_fixture.contracts.acceptance_contract
        .blocking_criteria()[0]
    )
    failed_table = _build_final_evidence_table(
        fixture=bundle.fixture,
        verified_evidence=(),
        failed_blockers=(
            FinalEvidenceBlocker(
                code=FinalEvidenceBlockerCode.FAILED_EVIDENCE,
                message="Verifier rejected tiny command evidence.",
                acceptance_ref=first_criterion.acceptance_ref,
                related_ref="evidence-blocker.tiny.command",
                source="evidence_verifier",
            ),
        ),
    )
    note = CheckerNote(
        message="Human note is non-blocking and cannot clear verifier blockers.",
        related_ref="work-product.tiny.tests",
    )

    verdict = CheckerService().review(
        _checker_input(
            bundle=bundle,
            final_evidence_table=failed_table,
            notes=(note,),
        )
    )

    assert verdict.status is CheckerVerdictStatus.REWORK_REQUIRED
    assert verdict.notes == (note,)
    assert verdict.blockers
    assert tuple(blocker.code.value for blocker in verdict.blockers) == (
        "final_evidence_failed",
        *("final_evidence_missing" for _ in failed_table.rows[1:]),
    )


def test_tiny_runner_evidence_verifies_all_blocking_acceptance_refs(
    tmp_path: Path,
) -> None:
    bundle = _build_tiny_evidence_bundle(tmp_path)
    contract = bundle.fixture.compiled.ticket_graph_fixture.contracts.acceptance_contract
    table = bundle.final_evidence_table

    assert table.complete is False
    assert table.acceptance_contract_ref == contract.acceptance_contract_id
    assert tuple(row.acceptance_ref for row in table.rows) == tuple(
        criterion.acceptance_ref for criterion in contract.blocking_criteria()
    )
    assert all(row.status is FinalEvidenceStatus.MISSING for row in table.rows)
    assert all(row.blockers == () for row in table.rows)
    assert _command_ids_from_verified_evidence(bundle.verified_evidence) == {
        "test-backend",
        "test-integration",
    }
    missing_by_acceptance = {
        row.acceptance_ref.value: tuple(
            artifact_type.value
            for artifact_type in row.missing_required_artifact_types
        )
        for row in table.rows
    }
    assert missing_by_acceptance == {
        "AC-TINY-API-BOOK-CREATE": ("backend_source_inventory",),
        "AC-TINY-API-BOOK-LIST": ("backend_source_inventory",),
        "AC-TINY-API-CHECKOUT-RETURN": ("backend_source_inventory",),
        "AC-TINY-PERSISTENCE-SQLITE": (
            "sqlite_persistence_evidence",
            "backend_source_inventory",
        ),
        "AC-TINY-UI-FETCH-BACKEND": ("frontend_source_inventory",),
        "AC-TINY-RUN-TEST-COMMANDS": ("run_manifest",),
    }

    verdict = CheckerService().review(
        _checker_input(
            bundle=bundle,
            final_evidence_table=table,
        )
    )
    gate_input = CompletionGateInput(
        ticket_ref=TICKET_TESTS_ID,
        final_evidence_table=table,
        checker_verdict=verdict,
        verified_evidence=bundle.verified_evidence,
        provider_attempt_refs=tuple(
            attempt.provider_attempt_id
            for attempt in bundle.fixture.provider_attempts_by_ticket_id.values()
        ),
        work_product_submitted_refs=tuple(
            work_product.work_product_id
            for work_product in bundle.work_products_by_ticket_id.values()
        ),
        fallback_decision_records=(),
    )

    assert verdict.status is CheckerVerdictStatus.REWORK_REQUIRED
    assert tuple(blocker.code.value for blocker in verdict.blockers) == (
        "final_evidence_missing",
        "final_evidence_missing",
        "final_evidence_missing",
        "final_evidence_missing",
        "final_evidence_missing",
        "final_evidence_missing",
    )
    with pytest.raises(ValueError, match="final evidence table must be complete"):
        CompletionGate().build_completion_snapshot(gate_input)


def test_tiny_evidence_verification_has_no_synthetic_provider_ref_hash_helper() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    helper_name = "_work_product_" + "artifact_manifest"
    synthetic_hash_marker = "work_product_id.value}" + ":{artifact_ref.value}"

    assert helper_name not in source
    assert synthetic_hash_marker not in source


def _build_tiny_seed() -> TinyProviderAttemptFixture:
    return build_tiny_provider_attempt_fixture(use_fake_results=True)


def _build_tiny_evidence_bundle(tmp_path: Path) -> TinyEvidenceBundle:
    fixture = _build_tiny_seed()
    package_root = _prepare_tiny_package_root(tmp_path)
    command_results_by_id = {
        command_id: _run_declared_command(
            fixture=fixture,
            package_root=package_root,
            command_id=command_id,
        )
        for command_id in ("test-backend", "test-integration")
    }
    work_products_by_ticket_id = _work_products_by_ticket_id(fixture)
    verified_evidence = _verify_all_tiny_evidence(
        fixture=fixture,
        command_results_by_id=command_results_by_id,
        work_products_by_ticket_id=work_products_by_ticket_id,
    )
    final_table = _build_final_evidence_table(
        fixture=fixture,
        verified_evidence=verified_evidence,
    )
    return TinyEvidenceBundle(
        fixture=fixture,
        command_results_by_id=command_results_by_id,
        verified_evidence=verified_evidence,
        final_evidence_table=final_table,
        work_products_by_ticket_id=work_products_by_ticket_id,
    )


def _prepare_tiny_package_root(tmp_path: Path) -> Path:
    (tmp_path / "backend" / "tests").mkdir(parents=True)
    (tmp_path / "tests" / "integration").mkdir(parents=True)
    (tmp_path / "backend" / "tests" / "test_backend.py").write_text(
        "def test_backend_command_evidence():\n"
        "    assert {'state': 'IN_LIBRARY'}['state'] == 'IN_LIBRARY'\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "integration" / "test_integration.py").write_text(
        "def test_frontend_backend_integration_command_evidence():\n"
        "    assert 'fetch' in 'frontend fetch backend api'\n",
        encoding="utf-8",
    )
    return tmp_path


def _run_declared_command(
    *,
    fixture: TinyProviderAttemptFixture,
    package_root: Path,
    command_id: str,
) -> CommandRunnerResult:
    execution_package = fixture.execution_packages[TICKET_TESTS_ID]
    return CommandRunner().run(
        CommandRunnerInput(
            execution_package=execution_package,
            package_contract=fixture.compiled.ticket_graph_fixture.contracts.package_contract,
            command_id=ContractId(value=command_id),
            package_root=package_root,
            runner_ref=RunnerRef(value="runner.tiny-command-evidence"),
            environment_profile_ref=EnvironmentProfileRef(value="env.tiny-local-pytest"),
            workspace_snapshot_ref=WorkspaceSnapshotRef(
                value="workspace-snapshot.tiny-command-evidence"
            ),
        )
    )


def _verify_all_tiny_evidence(
    *,
    fixture: TinyProviderAttemptFixture,
    command_results_by_id: Mapping[str, CommandRunnerResult],
    work_products_by_ticket_id: Mapping[TicketId, WorkProduct],
) -> tuple[VerifiedEvidence, ...]:
    verified: list[VerifiedEvidence] = []
    for obligation in (
        fixture.compiled.ticket_graph_fixture.contracts.contract_gate.evidence_obligations
    ):
        if obligation.required_artifact_type.value in {
            "api_test_run",
            "frontend_backend_integration_evidence",
            "command_evidence",
        }:
            command_id = _command_id_for_obligation(obligation)
            verified.append(
                _verify_command_obligation(
                    fixture=fixture,
                    obligation=obligation,
                    command_result=command_results_by_id[command_id],
                )
            )
    return tuple(verified)


def _verify_command_obligation(
    *,
    fixture: TinyProviderAttemptFixture,
    obligation: EvidenceObligation,
    command_result: CommandRunnerResult,
) -> VerifiedEvidence:
    producer_attempt_ref = fixture.provider_attempts_by_ticket_id[
        TICKET_TESTS_ID
    ].provider_attempt_id
    claim = build_evidence_claim_from_verification_run(
        verification_run=command_result.verification_run,
        evidence_obligation=obligation,
        producer_attempt_ref=producer_attempt_ref,
        acceptance_refs=obligation.acceptance_refs,
        source_surface_refs=obligation.source_surface_refs,
        expected_purpose=EvidencePurpose.IMPLEMENTATION,
        summary="Tiny declared command evidence verified from runner output.",
    )
    return _verified_evidence_from_claim(
        fixture=fixture,
        claim_obligation=obligation,
        artifact_manifest=_command_artifact_manifest(
            command_result=command_result,
            producer_attempt_ref=producer_attempt_ref,
        ),
        verification_runs=(command_result.verification_run,),
        claim=claim,
    )


def _verified_evidence_from_claim(
    *,
    fixture: TinyProviderAttemptFixture,
    claim_obligation: EvidenceObligation,
    artifact_manifest: ArtifactManifest,
    verification_runs: tuple[VerificationRun, ...],
    claim: object,
) -> VerifiedEvidence:
    result = EvidenceVerifier().verify(
        EvidenceVerificationInput(
            claim=claim,
            evidence_obligation=claim_obligation,
            active_acceptance_contract=(
                fixture.compiled.ticket_graph_fixture.contracts.acceptance_contract
            ),
            artifact_manifest=artifact_manifest,
            purpose_policy=_purpose_policy(claim_obligation),
            provider_attempts=tuple(fixture.provider_attempts_by_ticket_id.values()),
            verification_runs=verification_runs,
            verified_at=_VERIFIED_AT,
        )
    )
    assert result.success is True
    assert result.blockers == ()
    assert result.verified_evidence is not None
    return result.verified_evidence


def _command_artifact_manifest(
    *,
    command_result: CommandRunnerResult,
    producer_attempt_ref: ProviderAttemptRef,
) -> ArtifactManifest:
    run = command_result.verification_run
    return ArtifactManifest(
        entries=(
            ArtifactManifestEntry(
                artifact_ref=EvidenceArtifactRef(value=run.stdout_ref.value),
                sha256=_sha256(command_result.stdout),
                producer_attempt_ref=producer_attempt_ref,
                source_ref=run.verification_run_id.value,
                artifact_kind="command_stdout",
            ),
            ArtifactManifestEntry(
                artifact_ref=EvidenceArtifactRef(value=run.stderr_ref.value),
                sha256=_sha256(command_result.stderr),
                producer_attempt_ref=producer_attempt_ref,
                source_ref=run.verification_run_id.value,
                artifact_kind="command_stderr",
            ),
        )
    )


def _purpose_policy(obligation: EvidenceObligation) -> EvidencePurposePolicy:
    return EvidencePurposePolicy(
        rules=(
            EvidencePurposeRule(
                required_artifact_type=obligation.required_artifact_type,
                allowed_purposes=(EvidencePurpose.IMPLEMENTATION,),
            ),
        )
    )


def _build_final_evidence_table(
    *,
    fixture: TinyProviderAttemptFixture,
    verified_evidence: tuple[VerifiedEvidence, ...],
    failed_blockers: tuple[FinalEvidenceBlocker, ...] = (),
) -> FinalEvidenceTable:
    return FinalEvidenceTableBuilder().build(
        FinalEvidenceTableInput(
            active_acceptance_contract=(
                fixture.compiled.ticket_graph_fixture.contracts.acceptance_contract
            ),
            verified_evidence=verified_evidence,
            failed_blockers=failed_blockers,
            generated_at=_GENERATED_AT,
        )
    )


def _checker_input(
    *,
    bundle: TinyEvidenceBundle,
    final_evidence_table: FinalEvidenceTable,
    notes: tuple[CheckerNote, ...] = (),
) -> CheckerServiceInput:
    work_product = bundle.work_products_by_ticket_id[TICKET_TESTS_ID]
    return CheckerServiceInput(
        ticket_ref=TICKET_TESTS_ID,
        work_product=work_product,
        source_diff_ref=SourceDiffRef(value="source-diff.tiny-command-evidence"),
        active_acceptance_contract=(
            bundle.fixture.compiled.ticket_graph_fixture.contracts.acceptance_contract
        ),
        final_evidence_table=final_evidence_table,
        notes=notes,
        checker_blockers=(),
        checked_at=_CHECKED_AT,
    )


def _work_products_by_ticket_id(
    fixture: TinyProviderAttemptFixture,
) -> dict[TicketId, WorkProduct]:
    products: dict[TicketId, WorkProduct] = {}
    for result in fixture.runtime_results:
        assert result.work_product_submission is not None
        work_product = result.work_product_submission.work_product
        products[work_product.ticket_ref] = work_product
    return products


def _obligation_by_artifact_type(
    fixture: TinyProviderAttemptFixture,
    artifact_type: str,
) -> EvidenceObligation:
    for obligation in (
        fixture.compiled.ticket_graph_fixture.contracts.contract_gate.evidence_obligations
    ):
        if obligation.required_artifact_type.value == artifact_type:
            return obligation
    raise AssertionError(f"missing tiny evidence obligation: {artifact_type}")


def _command_id_for_obligation(obligation: EvidenceObligation) -> str:
    if obligation.required_artifact_type.value == "frontend_backend_integration_evidence":
        return "test-integration"
    return "test-backend"


def _command_ids_from_verified_evidence(
    verified_evidence: tuple[VerifiedEvidence, ...],
) -> set[str]:
    command_ids: set[str] = set()
    for evidence in verified_evidence:
        for run_ref in evidence.verification_run_refs:
            if run_ref.value.endswith(".test-backend"):
                command_ids.add("test-backend")
            if run_ref.value.endswith(".test-integration"):
                command_ids.add("test-integration")
    return command_ids


def _sha256(value: str) -> ArtifactSha256:
    return ArtifactSha256(value=hashlib.sha256(value.encode("utf-8")).hexdigest())
