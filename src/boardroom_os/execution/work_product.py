from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator, model_validator

from boardroom_os.agents.skills import _normalize_ref_fields
from boardroom_os.contracts.types import AcceptanceRef, NonEmptyTextValue, SourceSurfaceRef
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import (
    ActorRef,
    EventId,
    EventPayloadRef,
    EventRef,
    EventType,
    ProjectRef,
)
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.fallback import FallbackKind
from boardroom_os.execution.package import ExecutionPackage, ExecutionPackageRef
from boardroom_os.graph.ticket import TicketId
from boardroom_os.providers.attempt import (
    ProviderAttempt,
    ProviderAttemptOutcome,
    ProviderAttemptStatus,
)


class WorkProductBuildError(ValueError):
    pass


class WorkProductRef(NonEmptyTextValue):
    pass


class WorkProductArtifactRef(NonEmptyTextValue):
    pass


class WorkProductClaimDraftRef(NonEmptyTextValue):
    pass


class WorkProductClaimDraft(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    claim_draft_ref: WorkProductClaimDraftRef
    producer_attempt_ref: ProviderAttemptRef
    execution_package_ref: ExecutionPackageRef
    ticket_ref: TicketId
    acceptance_refs: tuple[AcceptanceRef, ...]
    source_surface_refs: tuple[SourceSurfaceRef, ...]
    artifact_refs: tuple[WorkProductArtifactRef, ...]
    summary: str

    @model_validator(mode="before")
    @classmethod
    def _normalize_yaml_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {
                "claim_draft_ref": WorkProductClaimDraftRef,
                "producer_attempt_ref": ProviderAttemptRef,
                "execution_package_ref": ExecutionPackageRef,
                "ticket_ref": TicketId,
            },
            {
                "acceptance_refs": AcceptanceRef,
                "source_surface_refs": SourceSurfaceRef,
                "artifact_refs": WorkProductArtifactRef,
            },
        )

    @field_validator("acceptance_refs", "source_surface_refs", "artifact_refs")
    @classmethod
    def _reject_empty_required_refs(
        cls,
        values: tuple[object, ...],
        info: ValidationInfo,
    ) -> tuple[object, ...]:
        if not values:
            raise ValueError(f"{info.field_name} must not be empty")
        return values

    @field_validator("summary")
    @classmethod
    def _reject_empty_summary(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("summary must not be empty")
        return normalized


class WorkProduct(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    work_product_id: WorkProductRef
    execution_package_ref: ExecutionPackageRef
    ticket_ref: TicketId
    producer_attempt_ref: ProviderAttemptRef
    artifact_refs: tuple[WorkProductArtifactRef, ...]
    claim_refs: tuple[WorkProductClaimDraftRef, ...]
    summary: str
    fallback_kind: FallbackKind | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_yaml_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {
                "work_product_id": WorkProductRef,
                "execution_package_ref": ExecutionPackageRef,
                "ticket_ref": TicketId,
                "producer_attempt_ref": ProviderAttemptRef,
            },
            {
                "artifact_refs": WorkProductArtifactRef,
                "claim_refs": WorkProductClaimDraftRef,
            },
        )

    @field_validator("artifact_refs", "claim_refs")
    @classmethod
    def _reject_empty_required_refs(
        cls,
        values: tuple[object, ...],
        info: ValidationInfo,
    ) -> tuple[object, ...]:
        if not values:
            raise ValueError(f"{info.field_name} must not be empty")
        return values

    @field_validator("summary")
    @classmethod
    def _reject_empty_summary(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("summary must not be empty")
        return normalized


class WorkProductSubmission(BaseModel):
    """Typed bundle whose claim_refs order is the claim_drafts order."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    work_product: WorkProduct
    claim_drafts: tuple[WorkProductClaimDraft, ...]

    @field_validator("claim_drafts")
    @classmethod
    def _reject_empty_claim_drafts(
        cls,
        value: tuple[WorkProductClaimDraft, ...],
    ) -> tuple[WorkProductClaimDraft, ...]:
        if not value:
            raise ValueError("claim_drafts must not be empty")
        return value

    @model_validator(mode="after")
    def _validate_claim_ref_alignment(self) -> Self:
        claim_draft_refs = tuple(claim.claim_draft_ref for claim in self.claim_drafts)
        if self.work_product.claim_refs != claim_draft_refs:
            raise ValueError("work_product.claim_refs must match claim_drafts order")
        return self


def _event_id_from_work_product(
    work_product: WorkProduct,
    graph_version: int,
) -> EventId:
    return EventId(
        value=(
            f"event.work-product-submitted."
            f"{work_product.work_product_id.value}.{graph_version}"
        )
    )


def build_work_product_submitted_event(
    *,
    work_product: WorkProduct,
    project_ref: ProjectRef,
    actor_ref: ActorRef,
    graph_version: int,
    timestamp: datetime,
    event_id: EventId | None = None,
    causation_refs: tuple[EventRef, ...] = (),
    correlation_refs: tuple[EventRef, ...] = (),
) -> EventRecord:
    resolved_event_id = event_id or _event_id_from_work_product(work_product, graph_version)
    return EventRecord(
        event_id=resolved_event_id,
        event_type=EventType.WORK_PRODUCT_SUBMITTED,
        project_ref=project_ref,
        actor_ref=actor_ref,
        timestamp=timestamp,
        graph_version=graph_version,
        payload_refs=(EventPayloadRef(value=work_product.work_product_id.value),),
        causation_refs=causation_refs,
        correlation_refs=correlation_refs,
    )


def build_work_product_from_provider_attempt(
    *,
    execution_package: ExecutionPackage,
    provider_attempt: ProviderAttempt,
    summary: str | None = None,
) -> WorkProductSubmission:
    if provider_attempt.status is not ProviderAttemptStatus.SUCCEEDED:
        raise WorkProductBuildError("provider_attempt.status must be succeeded")

    expected_execution_package_ref = ExecutionPackageRef(
        value=execution_package.execution_package_id.value
    )
    if provider_attempt.input_package_ref != expected_execution_package_ref:
        raise WorkProductBuildError(
            "provider_attempt.input_package_ref must match execution_package.execution_package_id"
        )

    if provider_attempt.seat_ref != execution_package.seat_ref:
        raise WorkProductBuildError(
            "provider_attempt.seat_ref must match execution_package.seat_ref"
        )

    if provider_attempt.outcome is ProviderAttemptOutcome.FALLBACK_ARTIFACT:
        if provider_attempt.fallback_kind is None:
            raise WorkProductBuildError(
                "provider_attempt.fallback_kind is required for fallback outcomes"
            )
        fallback_kind = provider_attempt.fallback_kind
    else:
        if provider_attempt.fallback_kind is not None:
            raise WorkProductBuildError(
                "provider_attempt.fallback_kind must be absent for primary outcomes"
            )
        fallback_kind = None

    # Pydantic validation already enforces these refs for ordinary succeeded attempts;
    # keep explicit builder checks so copied or otherwise corrupted facts fail closed here.
    if provider_attempt.raw_output_ref is None:
        raise WorkProductBuildError("provider_attempt.raw_output_ref is required")

    if provider_attempt.parsed_output_ref is None:
        raise WorkProductBuildError("provider_attempt.parsed_output_ref is required")

    if summary is None:
        resolved_summary = "Provider output submitted as work product."
    else:
        resolved_summary = summary.strip()
        if not resolved_summary:
            raise WorkProductBuildError("summary must not be empty")

    artifact_refs = (
        WorkProductArtifactRef(value=provider_attempt.raw_output_ref.value),
        WorkProductArtifactRef(value=provider_attempt.parsed_output_ref.value),
    )
    claim_draft_ref = WorkProductClaimDraftRef(
        value=f"claim-draft.{provider_attempt.provider_attempt_id.value}"
    )

    claim_draft = WorkProductClaimDraft(
        claim_draft_ref=claim_draft_ref,
        producer_attempt_ref=provider_attempt.provider_attempt_id,
        execution_package_ref=expected_execution_package_ref,
        ticket_ref=execution_package.ticket_ref,
        acceptance_refs=execution_package.acceptance_refs,
        source_surface_refs=execution_package.source_surface_refs,
        artifact_refs=artifact_refs,
        summary=resolved_summary,
    )
    work_product = WorkProduct(
        work_product_id=WorkProductRef(
            value=f"work-product.{provider_attempt.provider_attempt_id.value}"
        ),
        execution_package_ref=expected_execution_package_ref,
        ticket_ref=execution_package.ticket_ref,
        producer_attempt_ref=provider_attempt.provider_attempt_id,
        artifact_refs=artifact_refs,
        claim_refs=(claim_draft_ref,),
        summary=resolved_summary,
        fallback_kind=fallback_kind,
    )
    return WorkProductSubmission(
        work_product=work_product,
        claim_drafts=(claim_draft,),
    )


__all__ = [
    "WorkProductBuildError",
    "WorkProductRef",
    "WorkProductArtifactRef",
    "WorkProductClaimDraftRef",
    "WorkProductClaimDraft",
    "WorkProduct",
    "WorkProductSubmission",
    "build_work_product_from_provider_attempt",
    "build_work_product_submitted_event",
]
