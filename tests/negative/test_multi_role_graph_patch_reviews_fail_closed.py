from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from boardroom_os.contracts.types import AcceptanceRef, ContractId, EvidenceObligationRef, SourceSurfaceRef
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.providers.attempt import ProviderArtifactRef
from boardroom_os.rework.model import GraphPatchReview, GraphPatchReviewDomain, ReworkActorKind
from boardroom_os.rework.reviewer import (
    GraphPatchReviewerError,
    GraphPatchReviewerOutput,
    architect_graph_patch_review_input,
    parse_graph_patch_review_payload,
)
from boardroom_os.rework.ticket_graph_patch import (
    TicketGraphPatchBoundaryError,
    validate_ticket_graph_patch_scope,
)
from tests.negative.test_ceo_rework_planner_fail_closed import _provider_attempt
from tests.reducers.test_rework_reducer import _patch, _review

NOW = datetime(2026, 6, 14, 14, 0, tzinfo=UTC)


def test_patch_scope_rejects_acceptance_refs_outside_active_contract() -> None:
    operation = _patch().operations[0].model_copy(
        update={"acceptance_refs": (AcceptanceRef(value="acceptance.not-active"),)}
    )
    patch = _patch().model_copy(update={"operations": (operation,)})

    with pytest.raises(TicketGraphPatchBoundaryError, match="unknown acceptance_ref"):
        validate_ticket_graph_patch_scope(
            patch,
            active_acceptance_refs=(AcceptanceRef(value="acceptance.book.add"),),
            active_source_surface_refs=(SourceSurfaceRef(value="surface.backend.api"),),
            active_evidence_obligation_refs=(EvidenceObligationRef(value="evidence.add.api"),),
            active_contract_refs=(ContractId(value="acceptance.v2-090f"),),
        )


def test_patch_scope_rejects_source_surface_refs_outside_active_contract() -> None:
    operation = _patch().operations[0].model_copy(
        update={"source_surface_refs": (SourceSurfaceRef(value="surface.not-active"),)}
    )
    patch = _patch().model_copy(update={"operations": (operation,)})

    with pytest.raises(TicketGraphPatchBoundaryError, match="unknown source_surface_ref"):
        validate_ticket_graph_patch_scope(
            patch,
            active_acceptance_refs=(AcceptanceRef(value="acceptance.book.add"),),
            active_source_surface_refs=(SourceSurfaceRef(value="surface.backend.api"),),
            active_evidence_obligation_refs=(EvidenceObligationRef(value="evidence.add.api"),),
            active_contract_refs=(ContractId(value="acceptance.v2-090f"),),
        )


def test_patch_scope_rejects_evidence_obligation_refs_outside_active_contract() -> None:
    operation = _patch().operations[0].model_copy(
        update={"evidence_obligation_refs": (EvidenceObligationRef(value="evidence.not-active"),)}
    )
    patch = _patch().model_copy(update={"operations": (operation,)})

    with pytest.raises(TicketGraphPatchBoundaryError, match="unknown evidence_obligation_ref"):
        validate_ticket_graph_patch_scope(
            patch,
            active_acceptance_refs=(AcceptanceRef(value="acceptance.book.add"),),
            active_source_surface_refs=(SourceSurfaceRef(value="surface.backend.api"),),
            active_evidence_obligation_refs=(EvidenceObligationRef(value="evidence.add.api"),),
            active_contract_refs=(ContractId(value="acceptance.v2-090f"),),
        )


def test_reviewer_rejects_prose_without_review_schema() -> None:
    with pytest.raises(GraphPatchReviewerError, match="single JSON object"):
        parse_graph_patch_review_payload({"message": "looks good"})


def test_architect_review_cannot_claim_checker_domain() -> None:
    with pytest.raises((ValidationError, GraphPatchReviewerError), match="reviewer_role_kind"):
        review = _review(GraphPatchReviewDomain.BLOCKER_COVERAGE, ReworkActorKind.ARCHITECT)
        GraphPatchReviewerOutput(
            reviewer_input=architect_graph_patch_review_input(
                patch=_patch(),
                expected_provider_attempt_ref=ProviderAttemptRef(value="provider-attempt.architect.review"),
            ),
            provider_attempt=_provider_attempt(),
            review=review,
            parsed_payload_ref=ProviderArtifactRef(value="provider-artifact.parsed.architect-review"),
            validated_at=NOW,
        )


def test_approved_review_requires_checked_invariants() -> None:
    with pytest.raises(ValidationError, match="checked_invariants"):
        GraphPatchReview.model_validate(
            _review(GraphPatchReviewDomain.STRUCTURAL, ReworkActorKind.ARCHITECT).model_dump()
            | {"checked_invariants": ()}
        )
