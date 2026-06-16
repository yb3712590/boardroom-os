from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterator, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import yaml

from boardroom_os.config.boardroom import (
    BoardroomConfigPaths,
    BoardroomSettings,
    load_boardroom_settings,
)
from boardroom_os.contracts.types import (
    AcceptanceRef,
    ContractId,
    EvidenceObligationRef,
    SourceSurfaceRef,
)
from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import ActorRef, EventId, EventPayloadRef, EventType, ProjectRef
from boardroom_os.agents.profiles import ModelExecutionProfile
from boardroom_os.agents.role_prompt_hooks import (
    RolePromptHookRef,
    build_baseline_role_prompt_hook_registry,
)
from boardroom_os.agents.seat import AgentSeatRef, SeatDemand
from boardroom_os.agents.categories import RoleCategory
from boardroom_os.agents.skills import CapabilityTag
from boardroom_os.contracts.evidence_obligation import (
    EvidenceObligation,
    RequiredArtifactType,
    RequiredVerifier,
)
from boardroom_os.contracts.package import PackageCommand
from boardroom_os.evidence.verifier import EvidenceVerificationResult
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.package import (
    AuditRequirement,
    AllowedReadRef,
    AllowedWritePath,
    ContextRef,
    ExecutionPackage,
    ExecutionPackageRef,
    FallbackPolicyRef,
    RequiredOutput,
)
from boardroom_os.execution.provider_executor import (
    ProviderExecutor,
    ProviderExecutorInput,
    ProviderExecutorResult,
)
from boardroom_os.graph.ticket import TicketCreatedPayload, TicketId
from boardroom_os.providers.attempt import (
    ProviderArtifactRef,
    ProviderAttempt,
    ProviderAttemptOutcome,
    ProviderAttemptStatus,
)
from boardroom_os.providers.openai_adapter import (
    FileProviderOutputStore,
    OpenAIProviderSettings,
    OpenAIProviderTransport,
)
from boardroom_os.rework.blocker_projection import (
    BlockerProjectionContext,
    project_v2_090k_failure_summary,
)
from boardroom_os.reducers.rework import (
    GraphPatchApprovalPayload,
    GraphPatchReviewPayload,
    ReworkAttemptPayload,
    ReworkPlanPayload,
    ReworkProjection,
    ReworkReducer,
    ReworkReducerPayloadResolver,
    ReworkRequestPayload,
    ReworkReviewPayload,
    ReworkTerminalStatus,
    ReworkTerminalPayload,
)
from boardroom_os.rework.evidence import (
    ReworkEvidenceRecheckInput,
    ReworkEvidenceRecheckResult,
    recheck_rework_attempt,
    validate_rework_attempt_fact_refs,
)
from boardroom_os.rework.model import (
    BlockerRef,
    GraphPatchApprovalSet,
    GraphPatchApprovalStatus,
    GraphPatchOperationKind,
    GraphPatchReview,
    GraphPatchReviewId,
    GraphPatchReviewStatus,
    ReworkActorKind,
    ReworkAttempt,
    ReworkAttemptId,
    ReworkCycleId,
    ReworkDecision,
    ReworkDecisionId,
    ReworkDecisionKind,
    ReworkOutcome,
    ReworkOutcomeStatus,
    ReworkPlanId,
    ReworkPlan,
    ReworkRequest,
    ReworkTerminationDecision,
    ReworkTerminationDecisionId,
    ReworkTerminationReason,
    RunId,
    TicketGraphPatch,
    TicketGraphPatchId,
    TicketGraphPatchOperation,
    TicketGraphPatchOperationId,
    GraphPatchApprovalSetId,
    GraphPatchReviewDomain,
)
from boardroom_os.rework.planner import (
    CeoPlannerParsedPayload,
    CeoReworkPlannerInput,
    CeoReworkPlannerOutput,
    parse_ceo_rework_planner_payload,
    validate_ceo_rework_plan,
)
from boardroom_os.rework.reviewer import (
    GraphPatchReviewParsedPayload,
    GraphPatchReviewerInput,
    GraphPatchReviewerOutput,
    parse_graph_patch_review_payload,
    validate_graph_patch_review,
)


CEO_JSON_CONSTRAINTS = (
    "Return exactly one JSON object and no Markdown, no prose, no code fence.",
    'The JSON object must have exactly two top-level keys: "plan" and "patch".',
    '"plan" must contain the ReworkPlan fields required by parse_ceo_rework_planner_payload.',
    '"patch" must contain the TicketGraphPatch fields required by parse_ceo_rework_planner_payload.',
    'Every typed ref field must be encoded as {"value":"..."} rather than a bare string.',
    "Do not include run_id, graph_version, package_contract_ref, project_goal, actions, risks, unresolved_questions, or other fields not present in ReworkPlan or TicketGraphPatch.",
    "Every blocker_ref, acceptance_ref, source_surface_ref, evidence_obligation_ref, ticket_ref, and graph_version must match the supplied planner input; do not invent refs.",
)
CEO_REQUIRED_OUTPUTS = (RequiredOutput(value="json:ceo_rework_planner:{plan,patch}"),)
CEO_AUDIT_REQUIREMENTS = (
    AuditRequirement(value="provider.output.strict_json.no_markdown"),
    AuditRequirement(value="provider.output.refs.match_planner_input"),
    AuditRequirement(value="provider.output.parse_with.parse_ceo_rework_planner_payload"),
)
REVIEWER_JSON_CONSTRAINTS = (
    "Return exactly one JSON object and no Markdown, no prose, no code fence.",
    'The JSON object must have exactly one top-level key: "review".',
    '"review" must contain the GraphPatchReview fields required by parse_graph_patch_review_payload.',
    'Every typed ref field must be encoded as {"value":"..."} rather than a bare string.',
    "Do not include fields not present in GraphPatchReview.",
    'If blockers are present, each blockers item must be only {"value":"blocker-ref"}; do not use blocker_ref, rationale, message, or nested objects.',
    "Every ticket_graph_patch_ref, review_domain, reviewer_role_kind, blocker_ref, checked invariant, and provider attempt binding must match the supplied reviewer input; do not invent refs.",
)
REVIEWER_REQUIRED_OUTPUTS = (RequiredOutput(value="json:graph_patch_review:{review}"),)
REVIEWER_AUDIT_REQUIREMENTS = (
    AuditRequirement(value="provider.output.strict_json.no_markdown"),
    AuditRequirement(value="provider.output.refs.match_reviewer_input"),
    AuditRequirement(value="provider.output.parse_with.parse_graph_patch_review_payload"),
)


class V2_100ReworkLoopError(ValueError):
    pass


class V2_100ScenarioTerminalStatus(StrEnum):
    ACCEPTED = "accepted"
    STILL_BLOCKED = "still_blocked"
    ESCALATED = "escalated"
    EXHAUSTED = "exhausted"


class V2_100PayloadManifestEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    payload_ref: EventPayloadRef
    payload_kind: str
    canonical_json: str
    sha256: str

    @field_validator("payload_ref", mode="before")
    @classmethod
    def _normalize_payload_ref(cls, value: Any) -> Any:
        if isinstance(value, str):
            return EventPayloadRef(value=value)
        return value

    @field_validator("payload_kind", "canonical_json", "sha256")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("payload manifest text fields must not be empty")
        return normalized


class V2_100ProviderAttemptManifestEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_attempt_ref: str
    provider: str
    model: str
    input_package_ref: str
    raw_output_ref: ProviderArtifactRef
    parsed_output_ref: ProviderArtifactRef
    raw_output_sha256: str
    parsed_output_sha256: str

    @field_validator(
        "provider_attempt_ref",
        "provider",
        "model",
        "input_package_ref",
        "raw_output_sha256",
        "parsed_output_sha256",
    )
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("provider attempt manifest text fields must not be empty")
        return normalized


class V2_100ScenarioInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    project_ref: ProjectRef
    snapshot_summary_path: Path
    run_id: RunId
    cycle_id: ReworkCycleId
    package_contract_ref: str
    run_manifest_ref: str
    active_acceptance_refs: tuple[str, ...]
    active_source_surface_refs: tuple[str, ...]
    active_evidence_obligation_refs: tuple[str, ...]
    active_contract_refs: tuple[str, ...]
    initial_graph_version: int = Field(gt=0)
    max_rounds: int = Field(gt=0)
    provider_env_path: Path = Path(".env")
    export_root: Path | None = None
    require_real_provider: bool = True

    @model_validator(mode="before")
    @classmethod
    def _normalize_ref_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        ref_fields = {
            "project_ref": ProjectRef,
            "run_id": RunId,
            "cycle_id": ReworkCycleId,
        }
        for field_name, ref_type in ref_fields.items():
            value = normalized.get(field_name)
            if isinstance(value, str):
                normalized[field_name] = ref_type(value=value)
        return normalized

    @field_validator(
        "active_acceptance_refs",
        "active_source_surface_refs",
        "active_evidence_obligation_refs",
        "active_contract_refs",
    )
    @classmethod
    def _validate_active_refs(cls, values: tuple[str, ...], info: Any) -> tuple[str, ...]:
        return _non_empty_unique_strings(values, info.field_name)

    @field_validator("package_contract_ref", "run_manifest_ref")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("scenario input text fields must not be empty")
        return normalized

    @field_validator("snapshot_summary_path")
    @classmethod
    def _validate_snapshot_path(cls, value: Path) -> Path:
        if value.name != "failure-summary.json":
            raise ValueError("snapshot_summary_path must point to failure-summary.json")
        if not value.exists() or not value.is_file():
            raise ValueError("failure-summary.json snapshot file is required")
        return value


class V2_100ScenarioRoundInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    round_index: int = Field(gt=0)
    project_ref: ProjectRef
    request: ReworkRequest
    planner_output: CeoReworkPlannerOutput
    reviewer_outputs: tuple[GraphPatchReviewerOutput, ...]
    approval_set: GraphPatchApprovalSet
    rework_ticket_payload: TicketCreatedPayload
    attempt: ReworkAttempt
    recheck_input: ReworkEvidenceRecheckInput
    terminal_decision: ReworkTerminationDecision | None = None
    started_at_graph_version: int = Field(gt=0)

    @field_validator("project_ref", mode="before")
    @classmethod
    def _normalize_project_ref(cls, value: Any) -> Any:
        if isinstance(value, str):
            return ProjectRef(value=value)
        return value

    @field_validator("reviewer_outputs")
    @classmethod
    def _reject_empty_reviewers(cls, values: tuple[GraphPatchReviewerOutput, ...]) -> tuple[GraphPatchReviewerOutput, ...]:
        if not values:
            raise ValueError("reviewer_outputs must not be empty")
        return values


class V2_100ScenarioRoundResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    round_index: int = Field(gt=0)
    request: ReworkRequest
    plan_output: CeoReworkPlannerOutput
    review_outputs: tuple[GraphPatchReviewerOutput, ...]
    patch: TicketGraphPatch
    approval_set: GraphPatchApprovalSet
    rework_ticket_ref: TicketId
    attempt: ReworkAttempt
    recheck_result: ReworkEvidenceRecheckResult
    outcome: ReworkOutcome
    projection: ReworkProjection
    events: tuple[EventRecord, ...]
    payload_refs: tuple[EventPayloadRef, ...]
    payload_manifest_entries: tuple[V2_100PayloadManifestEntry, ...]
    provider_attempt_manifest_entries: tuple[V2_100ProviderAttemptManifestEntry, ...]
    accepted_blocker_refs: tuple[BlockerRef, ...] = ()
    remaining_blocker_refs: tuple[BlockerRef, ...] = ()

    @field_validator(
        "review_outputs",
        "events",
        "payload_refs",
        "payload_manifest_entries",
    )
    @classmethod
    def _reject_empty_tuples(cls, values: tuple[Any, ...], info: Any) -> tuple[Any, ...]:
        if not values:
            raise ValueError(f"{info.field_name} must not be empty")
        return values


class V2_100ScenarioAuditExport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    export_root: Path
    summary_path: Path
    event_log_path: Path
    payload_manifest_path: Path
    provider_attempts_path: Path
    evidence_summary_path: Path
    process_timeline_path: Path
    checked_refs: tuple[str, ...]

    @field_validator("checked_refs")
    @classmethod
    def _reject_empty_checked_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _non_empty_unique_strings(values, "checked_refs")


class V2_100ScenarioResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    scenario_id: str
    input_hash: str
    terminal_status: V2_100ScenarioTerminalStatus
    request: ReworkRequest
    rounds: tuple[V2_100ScenarioRoundResult, ...]
    final_projection: ReworkProjection
    termination_decision: ReworkTerminationDecision | None = None
    payload_manifest_entries: tuple[V2_100PayloadManifestEntry, ...]
    provider_attempt_manifest_entries: tuple[V2_100ProviderAttemptManifestEntry, ...]
    audit_export: V2_100ScenarioAuditExport | None = None
    created_at: datetime

    @field_validator("scenario_id", "input_hash")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("scenario result text fields must not be empty")
        return normalized

    @field_validator("rounds", "payload_manifest_entries")
    @classmethod
    def _reject_empty_tuples(cls, values: tuple[Any, ...], info: Any) -> tuple[Any, ...]:
        if not values:
            raise ValueError(f"{info.field_name} must not be empty")
        return values

    @field_validator("created_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _validate_terminal_state(self) -> "V2_100ScenarioResult":
        last_round = self.rounds[-1]
        if self.terminal_status is V2_100ScenarioTerminalStatus.ACCEPTED:
            if last_round.remaining_blocker_refs:
                raise ValueError("accepted terminal status must not include remaining blockers")
            if last_round.outcome.status is not ReworkOutcomeStatus.ACCEPTED:
                raise ValueError("accepted terminal status requires accepted rework outcome")
            if last_round.outcome.remaining_blocker_refs:
                raise ValueError("accepted rework outcome must not include remaining blockers")
            if last_round.projection.terminal_status.value != "accepted":
                raise ValueError("accepted terminal status requires accepted last round projection")
            if last_round.projection.remaining_blocker_refs:
                raise ValueError("accepted last round projection must not include remaining blockers")
            if self.final_projection.terminal_status.value != "accepted":
                raise ValueError("accepted terminal status requires accepted final projection")
            if self.final_projection.remaining_blocker_refs:
                raise ValueError("accepted final projection must not include remaining blockers")
            if self.termination_decision is not None:
                raise ValueError("accepted terminal status must not include termination_decision")
            return self
        if self.terminal_status is V2_100ScenarioTerminalStatus.ESCALATED:
            if self.termination_decision is None:
                raise ValueError("escalated terminal status requires termination_decision")
            if self.final_projection.terminal_status.value != "escalated":
                raise ValueError("escalated terminal status requires escalated final projection")
            return self
        if self.terminal_status is V2_100ScenarioTerminalStatus.EXHAUSTED:
            if self.termination_decision is None:
                raise ValueError("exhausted terminal status requires termination_decision")
            if self.final_projection.terminal_status.value != "exhausted":
                raise ValueError("exhausted terminal status requires exhausted final projection")
            return self
        if self.terminal_status is V2_100ScenarioTerminalStatus.STILL_BLOCKED:
            if self.termination_decision is None:
                raise ValueError("still_blocked terminal status requires termination_decision")
            if self.final_projection.terminal_status.value != "open":
                raise ValueError("still_blocked terminal status requires open final projection")
            return self
        raise ValueError("unknown terminal_status")


@runtime_checkable
class ScenarioPayloadResolver(ReworkReducerPayloadResolver, Protocol):
    def resolve_rework_request(self, payload_ref: EventPayloadRef) -> ReworkRequestPayload: ...

    def resolve_rework_plan(self, payload_ref: EventPayloadRef) -> ReworkPlanPayload: ...

    def resolve_graph_patch_review(self, payload_ref: EventPayloadRef) -> GraphPatchReviewPayload: ...

    def resolve_graph_patch_approval(self, payload_ref: EventPayloadRef) -> GraphPatchApprovalPayload: ...

    def resolve_rework_ticket_created(self, payload_ref: EventPayloadRef) -> TicketCreatedPayload: ...

    def resolve_rework_attempt(self, payload_ref: EventPayloadRef) -> ReworkAttemptPayload: ...

    def resolve_rework_review(self, payload_ref: EventPayloadRef) -> ReworkReviewPayload: ...

    def resolve_rework_terminal(self, payload_ref: EventPayloadRef) -> ReworkTerminalPayload: ...

    def payloads(self) -> dict[str, "V2_100ReducerPayload"]: ...

    def payload_manifest_entries_for(
        self,
        events: tuple[EventRecord, ...],
    ) -> tuple[V2_100PayloadManifestEntry, ...]: ...


class ScenarioRoundBuild(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    round_input: V2_100ScenarioRoundInput
    payload_resolver: ScenarioPayloadResolver
    provider_attempt_manifest_entries: tuple[V2_100ProviderAttemptManifestEntry, ...]


class ScenarioRoundProvider(Protocol):
    def build_round(
        self,
        scenario_input: V2_100ScenarioInput,
        request: ReworkRequest,
        *,
        round_index: int,
        started_at_graph_version: int,
    ) -> ScenarioRoundBuild: ...


V2_100ReducerPayload = (
    ReworkRequestPayload
    | ReworkPlanPayload
    | GraphPatchReviewPayload
    | GraphPatchApprovalPayload
    | TicketCreatedPayload
    | ReworkAttemptPayload
    | ReworkReviewPayload
    | ReworkTerminalPayload
)


def _non_empty_unique_strings(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    normalized = tuple(value.strip() for value in values)
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if any(not value for value in normalized):
        raise ValueError(f"{field_name} must not contain empty values")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must be unique; duplicate values are not allowed")
    return normalized


def canonical_payload_manifest_entry(
    payload_ref: EventPayloadRef,
    payload: V2_100ReducerPayload,
) -> V2_100PayloadManifestEntry:
    canonical_json = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return V2_100PayloadManifestEntry(
        payload_ref=payload_ref,
        payload_kind=type(payload).__name__,
        canonical_json=canonical_json,
        sha256=f"sha256:{digest}",
    )


class _ScenarioPayloadResolver:
    def __init__(self, payloads: dict[str, V2_100ReducerPayload]) -> None:
        self._payloads = dict(payloads)

    def payloads(self) -> dict[str, V2_100ReducerPayload]:
        return dict(self._payloads)

    def _get(self, payload_ref: EventPayloadRef) -> V2_100ReducerPayload:
        try:
            return self._payloads[payload_ref.value]
        except KeyError as error:
            raise V2_100ReworkLoopError(f"missing payload: {payload_ref.value}") from error

    def resolve_rework_request(self, payload_ref: EventPayloadRef) -> ReworkRequestPayload:
        payload = self._get(payload_ref)
        if not isinstance(payload, ReworkRequestPayload):
            raise V2_100ReworkLoopError(f"payload type mismatch: {payload_ref.value}")
        return payload

    def resolve_rework_plan(self, payload_ref: EventPayloadRef) -> ReworkPlanPayload:
        payload = self._get(payload_ref)
        if not isinstance(payload, ReworkPlanPayload):
            raise V2_100ReworkLoopError(f"payload type mismatch: {payload_ref.value}")
        return payload

    def resolve_graph_patch_review(self, payload_ref: EventPayloadRef) -> GraphPatchReviewPayload:
        payload = self._get(payload_ref)
        if not isinstance(payload, GraphPatchReviewPayload):
            raise V2_100ReworkLoopError(f"payload type mismatch: {payload_ref.value}")
        return payload

    def resolve_graph_patch_approval(self, payload_ref: EventPayloadRef) -> GraphPatchApprovalPayload:
        payload = self._get(payload_ref)
        if not isinstance(payload, GraphPatchApprovalPayload):
            raise V2_100ReworkLoopError(f"payload type mismatch: {payload_ref.value}")
        return payload

    def resolve_rework_ticket_created(self, payload_ref: EventPayloadRef) -> TicketCreatedPayload:
        payload = self._get(payload_ref)
        if not isinstance(payload, TicketCreatedPayload):
            raise V2_100ReworkLoopError(f"payload type mismatch: {payload_ref.value}")
        return payload

    def resolve_rework_attempt(self, payload_ref: EventPayloadRef) -> ReworkAttemptPayload:
        payload = self._get(payload_ref)
        if not isinstance(payload, ReworkAttemptPayload):
            raise V2_100ReworkLoopError(f"payload type mismatch: {payload_ref.value}")
        return payload

    def resolve_rework_review(self, payload_ref: EventPayloadRef) -> ReworkReviewPayload:
        payload = self._get(payload_ref)
        if not isinstance(payload, ReworkReviewPayload):
            raise V2_100ReworkLoopError(f"payload type mismatch: {payload_ref.value}")
        return payload

    def resolve_rework_terminal(self, payload_ref: EventPayloadRef) -> ReworkTerminalPayload:
        payload = self._get(payload_ref)
        if not isinstance(payload, ReworkTerminalPayload):
            raise V2_100ReworkLoopError(f"payload type mismatch: {payload_ref.value}")
        return payload

    def payload_manifest_entries_for(
        self,
        events: tuple[EventRecord, ...],
    ) -> tuple[V2_100PayloadManifestEntry, ...]:
        entries: dict[str, V2_100PayloadManifestEntry] = {}
        for event in events:
            for payload_ref in event.payload_refs:
                entry = canonical_payload_manifest_entry(payload_ref, self._get(payload_ref))
                existing = entries.get(payload_ref.value)
                if existing is not None and existing.canonical_json != entry.canonical_json:
                    raise V2_100ReworkLoopError(f"payload ref conflict: {payload_ref.value}")
                entries[payload_ref.value] = entry
        return tuple(entries[key] for key in sorted(entries))


def merge_payload_resolvers(*resolvers: ScenarioPayloadResolver) -> ScenarioPayloadResolver:
    merged: dict[str, V2_100ReducerPayload] = {}
    manifests: dict[str, V2_100PayloadManifestEntry] = {}
    for resolver in resolvers:
        for payload_ref, payload in resolver.payloads().items():
            entry = canonical_payload_manifest_entry(EventPayloadRef(value=payload_ref), payload)
            existing = manifests.get(payload_ref)
            if existing is not None and existing.canonical_json != entry.canonical_json:
                raise V2_100ReworkLoopError(f"payload ref conflict: {payload_ref}")
            merged[payload_ref] = payload
            manifests[payload_ref] = entry
    return _ScenarioPayloadResolver(merged)


def project_snapshot_request(scenario_input: V2_100ScenarioInput) -> ReworkRequest:
    context = BlockerProjectionContext(
        cycle_id=scenario_input.cycle_id,
        run_id=scenario_input.run_id,
        package_contract_ref=ContractId(value=scenario_input.package_contract_ref),
        run_manifest_ref=scenario_input.run_manifest_ref,
        active_acceptance_refs=tuple(
            AcceptanceRef(value=value) for value in scenario_input.active_acceptance_refs
        ),
        active_source_surface_refs=tuple(
            SourceSurfaceRef(value=value) for value in scenario_input.active_source_surface_refs
        ),
        active_evidence_obligation_refs=tuple(
            EvidenceObligationRef(value=value)
            for value in scenario_input.active_evidence_obligation_refs
        ),
        active_graph_version=scenario_input.initial_graph_version,
        requested_by_actor=ReworkActorKind.GOVERNANCE_ADAPTER,
        requested_at=datetime.now(UTC),
    )
    request = project_v2_090k_failure_summary(scenario_input.snapshot_summary_path, context)
    return validate_scenario_request(request, scenario_input)


def validate_scenario_request(
    request: ReworkRequest,
    scenario_input: V2_100ScenarioInput,
) -> ReworkRequest:
    if request.run_id != scenario_input.run_id:
        raise ValueError("scenario request run_id mismatch")
    if request.cycle_id != scenario_input.cycle_id:
        raise ValueError("scenario request cycle_id mismatch")
    if not request.issues:
        raise ValueError("scenario request issues must not be empty")
    return request


def validate_v2_100e_provider_json_settings(
    settings: OpenAIProviderSettings,
) -> OpenAIProviderSettings:
    if settings.api_protocol != "chat_completions":
        raise ValueError("responses protocol is rejected until json output support is audited")
    if settings.response_format != "json_object":
        raise ValueError("response_format must be json_object")
    return settings


def _load_v2_100e_env_values(path: Path) -> dict[str, str]:
    if not path.exists():
        raise ValueError(f"provider env file is required: {path}")
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    stale = sorted(
        key
        for key, value in values.items()
        if key.startswith("BOARDROOM_OPENAI_") and value.strip()
    )
    if stale:
        raise ValueError("stale env BOARDROOM_OPENAI_* keys are not allowed: " + ", ".join(stale))
    ambient_stale = sorted(
        key
        for key, value in os.environ.items()
        if key.startswith("BOARDROOM_OPENAI_") and value.strip()
    )
    if ambient_stale:
        raise ValueError(
            "stale env BOARDROOM_OPENAI_* keys are not allowed: "
            + ", ".join(ambient_stale)
        )
    return values


def _config_paths_from_v2_100e_env(values: dict[str, str]) -> BoardroomConfigPaths:
    required = (
        "BOARDROOM_RUNTIME_CONFIG",
        "BOARDROOM_PROVIDERS_CONFIG",
        "BOARDROOM_ROLES_CONFIG",
    )
    missing = tuple(name for name in required if not values.get(name, "").strip())
    if missing:
        raise ValueError(
            "stale env or missing boardroom config path env values: " + ", ".join(missing)
        )
    return BoardroomConfigPaths(
        runtime_config=Path(values["BOARDROOM_RUNTIME_CONFIG"]),
        providers_config=Path(values["BOARDROOM_PROVIDERS_CONFIG"]),
        roles_config=Path(values["BOARDROOM_ROLES_CONFIG"]),
    )


def _provider_secret_env_names(providers_config: Path) -> tuple[str, ...]:
    data = yaml.safe_load(providers_config.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("providers config must contain a YAML mapping")
    providers = data.get("providers")
    if not isinstance(providers, list):
        raise ValueError("providers config must include providers list")
    names: list[str] = []
    for provider in providers:
        if not isinstance(provider, dict):
            raise ValueError("provider entries must be YAML mappings")
        api_key_env = str(provider.get("api_key_env", "")).strip()
        if not api_key_env:
            raise ValueError("provider api_key_env is required")
        names.append(api_key_env)
    return tuple(dict.fromkeys(names))


def _require_provider_secrets_from_env_file(
    env_values: dict[str, str],
    *,
    providers_config: Path,
) -> tuple[str, ...]:
    secret_names = _provider_secret_env_names(providers_config)
    missing = tuple(name for name in secret_names if not env_values.get(name, "").strip())
    if missing:
        raise ValueError(
            "provider api key must be supplied by provider_env_path: "
            + ", ".join(missing)
        )
    return secret_names


@contextmanager
def _temporary_env_overlay(
    values: dict[str, str],
    *,
    clear_keys: tuple[str, ...] = (),
) -> Iterator[None]:
    touched_keys = tuple(dict.fromkeys((*clear_keys, *values)))
    previous: dict[str, str | None] = {key: os.environ.get(key) for key in touched_keys}
    for key in clear_keys:
        os.environ.pop(key, None)
    os.environ.update(values)
    try:
        yield
    finally:
        for key, old_value in previous.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


def load_v2_100e_boardroom_settings(
    scenario_input: V2_100ScenarioInput,
) -> BoardroomSettings:
    env_values = _load_v2_100e_env_values(scenario_input.provider_env_path)
    paths = _config_paths_from_v2_100e_env(env_values)
    secret_names = _require_provider_secrets_from_env_file(
        env_values,
        providers_config=paths.providers_config,
    )
    with _temporary_env_overlay(env_values, clear_keys=secret_names):
        return load_boardroom_settings(paths, env_values=env_values)


def load_v2_100e_openai_settings(
    scenario_input: V2_100ScenarioInput,
    *,
    seat_ref: str,
) -> OpenAIProviderSettings:
    env_values = _load_v2_100e_env_values(scenario_input.provider_env_path)
    settings = load_v2_100e_boardroom_settings(scenario_input)
    slot = settings.role_slot_by_seat(seat_ref)
    provider = settings.provider_by_id(slot.provider_profile_ref)
    if provider.response_format != {"type": "json_object"}:
        raise ValueError("provider response_format must be {'type': 'json_object'}")
    if provider.reasoning_effort is None:
        raise ValueError("provider reasoning_effort is required")
    api_key = env_values.get(provider.api_key_env, "")
    if not api_key.strip():
        raise ValueError("provider api key must be supplied by provider_env_path")
    resolved = OpenAIProviderSettings(
        api_key=api_key,
        base_url=provider.base_url,
        model=provider.model,
        api_protocol="chat_completions",
        reasoning_effort=provider.reasoning_effort,
        response_format="json_object",
        max_output_tokens=provider.max_output_tokens,
        context_window=provider.context_window_tokens,
        timeout_seconds=provider.total_timeout_seconds,
    )
    return validate_v2_100e_provider_json_settings(resolved)


def apply_ceo_json_output_contract(
    execution_package: ExecutionPackage,
) -> ExecutionPackage:
    return execution_package.model_copy(
        update={
            "constraints": execution_package.constraints + CEO_JSON_CONSTRAINTS,
            "required_outputs": execution_package.required_outputs + CEO_REQUIRED_OUTPUTS,
            "audit_requirements": execution_package.audit_requirements
            + CEO_AUDIT_REQUIREMENTS,
        }
    )


def apply_reviewer_json_output_contract(
    execution_package: ExecutionPackage,
) -> ExecutionPackage:
    return execution_package.model_copy(
        update={
            "constraints": execution_package.constraints + REVIEWER_JSON_CONSTRAINTS,
            "required_outputs": execution_package.required_outputs
            + REVIEWER_REQUIRED_OUTPUTS,
            "audit_requirements": execution_package.audit_requirements
            + REVIEWER_AUDIT_REQUIREMENTS,
        }
    )


def _assert_role_package_provider_binding(
    scenario_input: V2_100ScenarioInput,
    execution_package: ExecutionPackage,
) -> None:
    settings = load_v2_100e_boardroom_settings(scenario_input)
    role_slot = settings.role_slot_by_seat(execution_package.seat_ref.value)
    provider = settings.provider_by_id(role_slot.provider_profile_ref)
    profile = execution_package.model_execution_profile
    mismatches: list[str] = []
    if profile.model_execution_profile_id.value != role_slot.model_execution_profile_id:
        mismatches.append("model_execution_profile_id")
    if profile.provider != provider.provider_type.replace("_", "-"):
        mismatches.append("provider")
    if profile.model != provider.model:
        mismatches.append("model")
    if provider.reasoning_effort is None:
        raise ValueError("role-bound provider reasoning_effort is required")
    if profile.reasoning_effort != provider.reasoning_effort:
        mismatches.append("reasoning_effort")
    if profile.context_window != provider.context_window_tokens:
        mismatches.append("context_window")
    expected_temperature = 0.0 if provider.temperature is None else provider.temperature
    if profile.temperature != expected_temperature:
        mismatches.append("temperature")
    if mismatches:
        raise ValueError(
            "ExecutionPackage model_execution_profile mismatch with role-bound YAML provider profile: "
            + ", ".join(mismatches)
        )


def _real_provider_transport(
    scenario_input: V2_100ScenarioInput,
    *,
    seat_ref: str,
) -> OpenAIProviderTransport:
    settings = load_v2_100e_openai_settings(scenario_input, seat_ref=seat_ref)
    store_root = (
        scenario_input.export_root / "provider-artifacts"
        if scenario_input.export_root is not None
        else Path("20-evidence/provider-artifacts")
    )
    return OpenAIProviderTransport(
        settings=settings.model_copy(update={"artifact_store_root": store_root})
    )


def _execute_role_package(
    execution_package: ExecutionPackage,
    scenario_input: V2_100ScenarioInput,
) -> ProviderExecutorResult:
    _assert_role_package_provider_binding(scenario_input, execution_package)
    transport = _real_provider_transport(
        scenario_input,
        seat_ref=execution_package.seat_ref.value,
    )
    return ProviderExecutor().execute(
        ProviderExecutorInput(
            execution_package=execution_package,
            provider_adapter=transport,
        )
    )


def _parse_ceo_output(
    provider_result: ProviderExecutorResult,
    planner_input: CeoReworkPlannerInput,
    artifact_reader: FileProviderOutputStore,
) -> CeoReworkPlannerOutput:
    parsed_ref = provider_result.provider_attempt.parsed_output_ref
    if parsed_ref is None:
        raise ValueError("CEO provider parsed_output_ref is required")
    parsed = _parse_ceo_payload_ref(parsed_ref, artifact_reader)
    output = CeoReworkPlannerOutput(
        planner_input=planner_input,
        provider_attempt=provider_result.provider_attempt,
        plan=parsed.plan,
        patch=parsed.patch,
        parsed_payload_ref=parsed_ref,
        validated_at=provider_result.provider_attempt.finished_at,
    )
    return validate_ceo_rework_plan(output)


def _parse_ceo_payload_ref(
    parsed_ref: ProviderArtifactRef,
    artifact_reader: FileProviderOutputStore,
) -> CeoPlannerParsedPayload:
    payload = json.loads(artifact_reader.read_text(parsed_ref))
    if not isinstance(payload, dict):
        raise ValueError("CEO provider parsed output must be a JSON object")
    return parse_ceo_rework_planner_payload(payload)


def _parse_graph_patch_review_output(
    provider_result: ProviderExecutorResult,
    reviewer_input: GraphPatchReviewerInput,
    artifact_reader: FileProviderOutputStore,
) -> GraphPatchReviewerOutput:
    parsed_ref = provider_result.provider_attempt.parsed_output_ref
    if parsed_ref is None:
        raise ValueError("graph patch reviewer parsed_output_ref is required")
    parsed = _parse_graph_patch_review_payload_ref(parsed_ref, artifact_reader)
    output = GraphPatchReviewerOutput(
        reviewer_input=reviewer_input,
        provider_attempt=provider_result.provider_attempt,
        review=parsed.review,
        parsed_payload_ref=parsed_ref,
        validated_at=provider_result.provider_attempt.finished_at,
    )
    return validate_graph_patch_review(output)


def _parse_graph_patch_review_payload_ref(
    parsed_ref: ProviderArtifactRef,
    artifact_reader: FileProviderOutputStore,
) -> GraphPatchReviewParsedPayload:
    payload = json.loads(artifact_reader.read_text(parsed_ref))
    if not isinstance(payload, dict):
        raise ValueError("graph patch reviewer parsed output must be a JSON object")
    return parse_graph_patch_review_payload(payload)


def _provider_artifact_store(scenario_input: V2_100ScenarioInput) -> FileProviderOutputStore:
    store_root = (
        scenario_input.export_root / "provider-artifacts"
        if scenario_input.export_root is not None
        else Path("20-evidence/provider-artifacts")
    )
    return FileProviderOutputStore(root=store_root)


def _model_profile_for_seat(
    scenario_input: V2_100ScenarioInput,
    *,
    seat_ref: str,
) -> ModelExecutionProfile:
    settings = load_v2_100e_boardroom_settings(scenario_input)
    slot = settings.role_slot_by_seat(seat_ref)
    provider = settings.provider_by_id(slot.provider_profile_ref)
    if provider.reasoning_effort is None:
        raise ValueError("role-bound provider reasoning_effort is required")
    temperature = 0.0 if provider.temperature is None else provider.temperature
    return ModelExecutionProfile(
        model_execution_profile_id=slot.model_execution_profile_id,
        provider=provider.provider_type.replace("_", "-"),
        model=provider.model,
        reasoning_effort=provider.reasoning_effort,
        context_window=provider.context_window_tokens,
        temperature=temperature,
        tool_permissions=tuple(slot.default_tools),
        fallback_policy_ref="fallback.v2-100e.real-provider.fail-closed",
    )


def _role_hook(hook_ref: str):
    return build_baseline_role_prompt_hook_registry().require(
        RolePromptHookRef(value=hook_ref)
    )


def _execution_package_for_role(
    scenario_input: V2_100ScenarioInput,
    *,
    execution_package_ref: str,
    ticket_ref: TicketId,
    graph_version: int,
    seat_ref: str,
    hook_ref: str,
    objective: str,
    context_refs: tuple[str, ...],
    constraints: tuple[str, ...],
    required_outputs: tuple[str, ...],
    audit_requirements: tuple[str, ...],
    acceptance_refs: tuple[str, ...] | None = None,
    source_surface_refs: tuple[str, ...] | None = None,
    allowed_write_set: tuple[str, ...] = ("audit/v2-100e-provider-output.json",),
) -> ExecutionPackage:
    active_acceptance_refs = acceptance_refs or scenario_input.active_acceptance_refs
    active_source_surface_refs = source_surface_refs or scenario_input.active_source_surface_refs
    evidence_obligation_ref = scenario_input.active_evidence_obligation_refs[0]
    return ExecutionPackage(
        execution_package_id=execution_package_ref,
        ticket_ref=ticket_ref,
        graph_version=graph_version,
        seat_ref=seat_ref,
        model_execution_profile=_model_profile_for_seat(scenario_input, seat_ref=seat_ref),
        role_prompt_hook=_role_hook(hook_ref),
        objective=objective,
        context_refs=tuple(ContextRef(value=value) for value in context_refs),
        constraints=constraints,
        acceptance_refs=tuple(AcceptanceRef(value=value) for value in active_acceptance_refs),
        source_surface_refs=tuple(SourceSurfaceRef(value=value) for value in active_source_surface_refs),
        allowed_read_refs=(
            AllowedReadRef(value=scenario_input.snapshot_summary_path.as_posix()),
        ),
        allowed_write_set=tuple(AllowedWritePath(value=value) for value in allowed_write_set),
        required_outputs=tuple(RequiredOutput(value=value) for value in required_outputs),
        commands=(
            PackageCommand(
                command_id=ContractId(value="cmd.v2-100e.provider-json"),
                label="produce strict V2-100E JSON",
                command=("provider", "strict-json"),
                cwd=".",
            ),
        ),
        evidence_obligations=(
            EvidenceObligation(
                evidence_obligation_id=EvidenceObligationRef(value=evidence_obligation_ref),
                acceptance_refs=tuple(AcceptanceRef(value=value) for value in active_acceptance_refs),
                source_surface_refs=tuple(SourceSurfaceRef(value=value) for value in active_source_surface_refs),
                required_artifact_type=RequiredArtifactType(value="provider_json"),
                required_verifier=RequiredVerifier(value="provider_output_parser"),
                blocking=True,
            ),
        ),
        fallback_policy_ref=FallbackPolicyRef(value="fallback.v2-100e.real-provider.fail-closed"),
        audit_requirements=tuple(AuditRequirement(value=value) for value in audit_requirements),
    )


def _canonical_json_template(value: BaseModel) -> str:
    return json.dumps(
        value.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _canonical_json_mapping(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _ceo_json_shape_example() -> str:
    return _canonical_json_mapping(
        {
            "plan": {
                "rework_plan_id": {"value": "rework-plan.example"},
                "cycle_id": {"value": "rework-cycle.example"},
                "rework_request_id": {"value": "rework-request.example"},
                "planner_actor": "ceo",
                "planner_attempt_ref": {"value": "provider-attempt.example"},
                "decisions": [
                    {
                        "decision_id": {"value": "rework-decision.example"},
                        "decision_kind": "fix_implementation",
                        "blocker_refs": [{"value": "blocker.example"}],
                        "issue_ids": [{"value": "rework-issue.example"}],
                        "target_ticket_refs": [{"value": "ticket.example"}],
                        "target_graph_operation_refs": [
                            {"value": "ticket-graph-patch-operation.example"}
                        ],
                        "rationale": "Short rationale.",
                    }
                ],
                "ticket_graph_patch_ref": {"value": "ticket-graph-patch.example"},
                "risk_notes": ["Short risk note."],
                "stop_or_escalation_conditions": ["Short stop condition."],
            },
            "patch": {
                "ticket_graph_patch_id": {"value": "ticket-graph-patch.example"},
                "base_graph_version": 1,
                "proposed_by_plan_ref": {"value": "rework-plan.example"},
                "operations": [
                    {
                        "operation_id": {"value": "ticket-graph-patch-operation.example"},
                        "operation_kind": "create_rework_ticket",
                        "target_ticket_refs": [{"value": "ticket.example"}],
                        "acceptance_refs": [{"value": "acceptance.example"}],
                        "source_surface_refs": [{"value": "surface.example"}],
                        "evidence_obligation_refs": [{"value": "evidence.example"}],
                        "rationale": "Short rationale.",
                    }
                ],
                "affected_ticket_refs": [{"value": "ticket.example"}],
                "affected_contract_refs": [{"value": "contract.example"}],
                "affected_source_surface_refs": [{"value": "surface.example"}],
                "required_review_domains": ["planning", "structural", "blocker_coverage"],
                "patch_hash": "sha256:"
                + "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            },
        }
    )


def _review_json_shape_example() -> str:
    return _canonical_json_mapping(
        {
            "review": {
                "graph_patch_review_id": {"value": "graph-patch-review.example"},
                "ticket_graph_patch_ref": {"value": "ticket-graph-patch.example"},
                "review_domain": "planning",
                "reviewer_actor": "ceo",
                "reviewer_role_kind": "ceo",
                "reviewer_attempt_ref": {"value": "provider-attempt.example"},
                "status": "approved",
                "checked_invariants": ["contract-bound"],
                "blockers": [{"value": "blocker.example"}],
                "non_blocking_notes": [],
                "created_at": "2026-06-15T09:00:00Z",
            }
        }
    )


def _plan_patch_template(
    scenario_input: V2_100ScenarioInput,
    request: ReworkRequest,
    *,
    round_index: int,
    expected_attempt_ref: ProviderAttemptRef,
) -> CeoPlannerParsedPayload:
    plan_id = ReworkPlanId(value=f"rework-plan.v2-100e.{round_index}")
    patch_id = TicketGraphPatchId(value=f"ticket-graph-patch.v2-100e.{round_index}")
    operation_id = TicketGraphPatchOperationId(
        value=f"ticket-graph-patch-operation.v2-100e.{round_index}"
    )
    blocker_refs = tuple(blocker for issue in request.issues for blocker in issue.blocker_refs)
    issue_ids = tuple(issue.issue_id for issue in request.issues)
    ticket_ref = TicketId(value="ticket.v2-100e.backend")
    decision = ReworkDecision(
        decision_id=ReworkDecisionId(value=f"rework-decision.v2-100e.{round_index}"),
        decision_kind=ReworkDecisionKind.FIX_IMPLEMENTATION,
        blocker_refs=blocker_refs,
        issue_ids=issue_ids,
        target_ticket_refs=(ticket_ref,),
        target_graph_operation_refs=(operation_id,),
        rationale="Create a contract-bound rework ticket for the verified blocker set.",
    )
    plan = ReworkPlan(
        rework_plan_id=plan_id,
        cycle_id=request.cycle_id,
        rework_request_id=request.rework_request_id,
        planner_actor=ReworkActorKind.CEO,
        planner_attempt_ref=expected_attempt_ref,
        decisions=(decision,),
        ticket_graph_patch_ref=patch_id,
        risk_notes=("Evidence must be regenerated in the current round.",),
        stop_or_escalation_conditions=("Escalate or exhaust when budget is reached with blockers.",),
    )
    active_acceptance_refs = tuple(
        AcceptanceRef(value=value) for value in scenario_input.active_acceptance_refs[:1]
    )
    active_source_surface_refs = tuple(
        SourceSurfaceRef(value=value) for value in scenario_input.active_source_surface_refs[:2]
    )
    active_evidence_refs = tuple(
        EvidenceObligationRef(value=value)
        for value in scenario_input.active_evidence_obligation_refs[:1]
    )
    patch_hash_body = {
        "round_index": round_index,
        "request_ref": request.rework_request_id.value,
        "blockers": tuple(ref.value for ref in blocker_refs),
        "acceptance_refs": tuple(ref.value for ref in active_acceptance_refs),
        "source_surface_refs": tuple(ref.value for ref in active_source_surface_refs),
        "evidence_obligation_refs": tuple(ref.value for ref in active_evidence_refs),
    }
    patch_hash = "sha256:" + hashlib.sha256(
        _canonical_json_mapping(patch_hash_body).encode("utf-8")
    ).hexdigest()
    patch = TicketGraphPatch(
        ticket_graph_patch_id=patch_id,
        base_graph_version=request.active_graph_version,
        proposed_by_plan_ref=plan_id,
        operations=(
            TicketGraphPatchOperation(
                operation_id=operation_id,
                operation_kind=GraphPatchOperationKind.CREATE_REWORK_TICKET,
                target_ticket_refs=(ticket_ref,),
                acceptance_refs=active_acceptance_refs,
                source_surface_refs=active_source_surface_refs,
                evidence_obligation_refs=active_evidence_refs,
                rationale="Bind the rework ticket to active acceptance and evidence obligations.",
            ),
        ),
        affected_ticket_refs=(ticket_ref,),
        affected_contract_refs=request.active_contract_refs,
        affected_source_surface_refs=active_source_surface_refs,
        required_review_domains=(
            GraphPatchReviewDomain.PLANNING,
            GraphPatchReviewDomain.STRUCTURAL,
            GraphPatchReviewDomain.BLOCKER_COVERAGE,
        ),
        patch_hash=patch_hash,
    )
    return CeoPlannerParsedPayload(plan=plan, patch=patch)


def _build_planner_input(
    scenario_input: V2_100ScenarioInput,
    request: ReworkRequest,
    *,
    execution_package_ref: ExecutionPackageRef,
    role_prompt_hook_ref: RolePromptHookRef,
) -> CeoReworkPlannerInput:
    return CeoReworkPlannerInput(
        rework_request=request,
        current_graph_version=request.active_graph_version,
        active_contract_refs=request.active_contract_refs,
        active_acceptance_refs=tuple(
            AcceptanceRef(value=value) for value in scenario_input.active_acceptance_refs
        ),
        active_source_surface_refs=tuple(
            SourceSurfaceRef(value=value) for value in scenario_input.active_source_surface_refs
        ),
        active_evidence_obligation_refs=tuple(
            EvidenceObligationRef(value=value)
            for value in scenario_input.active_evidence_obligation_refs
        ),
        package_contract_ref=ContractId(value=scenario_input.package_contract_ref),
        run_manifest_ref=scenario_input.run_manifest_ref,
        planner_execution_package_ref=execution_package_ref,
        planner_role_prompt_hook_ref=role_prompt_hook_ref,
    )


def _validate_real_provider_patch_target(
    patch: TicketGraphPatch,
    *,
    expected_ticket_ref: TicketId,
) -> TicketGraphPatch:
    affected = {ref.value for ref in patch.affected_ticket_refs}
    if affected != {expected_ticket_ref.value}:
        raise V2_100ReworkLoopError(
            "real provider patch must target the active rework ticket: "
            f"{expected_ticket_ref.value}"
        )
    for operation in patch.operations:
        operation_targets = {ref.value for ref in operation.target_ticket_refs}
        if operation_targets != {expected_ticket_ref.value}:
            raise V2_100ReworkLoopError(
                "real provider patch operation must target the active rework ticket: "
                f"{expected_ticket_ref.value}"
            )
    return patch


def _execute_real_ceo_planner(
    scenario_input: V2_100ScenarioInput,
    request: ReworkRequest,
    *,
    round_index: int,
    graph_version: int,
) -> CeoReworkPlannerOutput:
    expected_attempt_ref = ProviderAttemptRef(
        value=f"provider-attempt.v2-100e.ceo.round-{round_index}"
    )
    planner_context = {
        "expected_planner_attempt_ref": expected_attempt_ref.value,
        "required_target_ticket_ref": "ticket.v2-100e.backend",
        "required_target_ticket_policy": "All ReworkDecision.target_ticket_refs, TicketGraphPatch.affected_ticket_refs, and every operation.target_ticket_refs must contain only required_target_ticket_ref; do not create new rework-ticket ids in this proving scenario.",
        "rework_request": request.model_dump(mode="json"),
        "current_graph_version": request.active_graph_version,
        "active_contract_refs": tuple(ref.value for ref in request.active_contract_refs),
        "active_acceptance_refs": scenario_input.active_acceptance_refs,
        "active_source_surface_refs": scenario_input.active_source_surface_refs,
        "active_evidence_obligation_refs": scenario_input.active_evidence_obligation_refs,
        "package_contract_ref": scenario_input.package_contract_ref,
        "run_manifest_ref": scenario_input.run_manifest_ref,
        "required_review_domains": (
            GraphPatchReviewDomain.PLANNING.value,
            GraphPatchReviewDomain.STRUCTURAL.value,
            GraphPatchReviewDomain.BLOCKER_COVERAGE.value,
        ),
        "allowed_operation_kinds": (GraphPatchOperationKind.CREATE_REWORK_TICKET.value,),
    }
    execution_package = apply_ceo_json_output_contract(
        _execution_package_for_role(
            scenario_input,
            execution_package_ref=f"execution-package.v2-100e.ceo.round-{round_index}",
            ticket_ref=TicketId(value=f"ticket.v2-100e.ceo.round-{round_index}"),
            graph_version=graph_version,
            seat_ref="seat.ceo.delivery",
            hook_ref="role-prompt-hook.baseline.ceo.v1",
            objective="Author a V2-100E ReworkPlan and TicketGraphPatch as strict JSON from the supplied verified blocker request.",
            context_refs=(
                "context:v2-100e:rework-request",
                "context:v2-100e:planner-input:" + _canonical_json_mapping(planner_context),
                "context:v2-100e:ceo-json-shape-example:" + _ceo_json_shape_example(),
            ),
            constraints=(
                "Return only one JSON object with top-level keys plan and patch, with no prose.",
                "Use typed value-object refs: every *_ref, *_id, and ref tuple item must be an object with a value key.",
                "Use the expected_planner_attempt_ref exactly as plan.planner_attempt_ref.value.",
                "Use required_target_ticket_ref exactly for every decision target_ticket_refs item, patch affected_ticket_refs item, and operation target_ticket_refs item.",
                "Do not create any rework-ticket.* ids; this proving scenario repairs the existing origin/backend ticket.",
                "Bind every decision to the supplied verified blocker refs and issue ids.",
                "Use only supplied active acceptance refs, source surface refs, evidence obligation refs, active contract refs, and current graph version.",
                "Use create_rework_ticket as the operation kind unless escalation is required.",
                "Include a non-empty sha256-prefixed patch_hash derived from your proposed patch content.",
            ),
            required_outputs=("json:ceo_rework_planner:{plan,patch}",),
            audit_requirements=("provider.output.strict_json.no_markdown",),
        )
    )
    planner_input = _build_planner_input(
        scenario_input,
        request,
        execution_package_ref=ExecutionPackageRef(value=execution_package.execution_package_id.value),
        role_prompt_hook_ref=execution_package.role_prompt_hook.hook_ref,
    )
    provider_result = _execute_role_package(execution_package, scenario_input)
    parsed_ref = provider_result.provider_attempt.parsed_output_ref
    if parsed_ref is None:
        raise ValueError("CEO provider parsed_output_ref is required")
    parsed_payload = _parse_ceo_payload_ref(
        parsed_ref,
        _provider_artifact_store(scenario_input),
    )
    plan = parsed_payload.plan.model_copy(
        update={"planner_attempt_ref": provider_result.provider_attempt.provider_attempt_id}
    )
    patch = _validate_real_provider_patch_target(
        parsed_payload.patch,
        expected_ticket_ref=TicketId(value="ticket.v2-100e.backend"),
    )
    return validate_ceo_rework_plan(
        CeoReworkPlannerOutput(
            planner_input=planner_input,
            provider_attempt=provider_result.provider_attempt,
            plan=plan,
            patch=patch,
            parsed_payload_ref=parsed_ref,
            validated_at=provider_result.provider_attempt.finished_at,
        )
    )


def _reviewer_specs() -> tuple[tuple[GraphPatchReviewDomain, ReworkActorKind, str, str], ...]:
    return (
        (GraphPatchReviewDomain.PLANNING, ReworkActorKind.CEO, "seat.ceo.delivery", "role-prompt-hook.baseline.ceo.v1"),
        (GraphPatchReviewDomain.STRUCTURAL, ReworkActorKind.ARCHITECT, "seat.architect.delivery", "role-prompt-hook.baseline.architect.v1"),
        (GraphPatchReviewDomain.BLOCKER_COVERAGE, ReworkActorKind.CHECKER, "seat.checker.acceptance", "role-prompt-hook.baseline.checker.v1"),
    )


def _review_template(
    patch: TicketGraphPatch,
    *,
    round_index: int,
    domain: GraphPatchReviewDomain,
    actor: ReworkActorKind,
    expected_attempt_ref: ProviderAttemptRef,
) -> GraphPatchReviewParsedPayload:
    return GraphPatchReviewParsedPayload(
        review=GraphPatchReview(
            graph_patch_review_id=GraphPatchReviewId(
                value=f"graph-patch-review.v2-100e.{round_index}.{domain.value}"
            ),
            ticket_graph_patch_ref=patch.ticket_graph_patch_id,
            review_domain=domain,
            reviewer_actor=actor,
            reviewer_role_kind=actor,
            reviewer_attempt_ref=expected_attempt_ref,
            status=GraphPatchReviewStatus.APPROVED,
            checked_invariants=(f"{domain.value}.contract-bound",),
            created_at=datetime.now(UTC),
        )
    )


def _execute_real_graph_patch_review(
    scenario_input: V2_100ScenarioInput,
    patch: TicketGraphPatch,
    *,
    round_index: int,
    graph_version: int,
    domain: GraphPatchReviewDomain,
    actor: ReworkActorKind,
    seat_ref: str,
    hook_ref: str,
) -> GraphPatchReviewerOutput:
    expected_attempt_ref = ProviderAttemptRef(
        value=f"provider-attempt.v2-100e.review.{round_index}.{domain.value}"
    )
    reviewer_context = {
        "expected_provider_attempt_ref": expected_attempt_ref.value,
        "review_domain": domain.value,
        "reviewer_actor": actor.value,
        "reviewer_role_kind": actor.value,
        "patch": patch.model_dump(mode="json"),
        "allowed_status": GraphPatchReviewStatus.APPROVED.value,
        "approval_rule": "Approve when every operation targets ticket.v2-100e.backend and uses only the supplied active refs. Multiple operations for multiple verified blockers are allowed when all target the active ticket.",
    }
    execution_package = apply_reviewer_json_output_contract(
        _execution_package_for_role(
            scenario_input,
            execution_package_ref=f"execution-package.v2-100e.review.{round_index}.{domain.value}",
            ticket_ref=TicketId(value=f"ticket.v2-100e.review.{round_index}.{domain.value}"),
            graph_version=graph_version,
            seat_ref=seat_ref,
            hook_ref=hook_ref,
            objective=f"Author a V2-100E {domain.value} GraphPatchReview as strict JSON for the supplied TicketGraphPatch.",
            context_refs=(
                "context:v2-100e:ticket-graph-patch",
                "context:v2-100e:review-input:" + _canonical_json_mapping(reviewer_context),
                "context:v2-100e:review-json-shape-example:" + _review_json_shape_example(),
            ),
            constraints=(
                "Return only one JSON object with top-level key review, with no prose.",
                "Use typed value-object refs: every *_ref and *_id must be an object with a value key.",
                "Use expected_provider_attempt_ref exactly as review.reviewer_attempt_ref.value.",
                "Use the supplied review_domain, reviewer_actor, reviewer_role_kind, and patch ticket_graph_patch_id exactly.",
                "Approve if every patch operation targets ticket.v2-100e.backend and all referenced acceptance/source/evidence refs are from the supplied patch; multiple operations are allowed.",
                'If you cannot approve, blockers must be a list of {"value":"..."} objects only.',
                "Approved reviews must include checked_invariants.",
            ),
            required_outputs=("json:graph_patch_review:{review}",),
            audit_requirements=("provider.output.strict_json.no_markdown",),
        )
    )
    reviewer_input = GraphPatchReviewerInput(
        patch=patch,
        review_domain=domain,
        reviewer_role_kind=actor,
        expected_provider_attempt_ref=expected_attempt_ref,
        reviewer_execution_package_ref=ExecutionPackageRef(value=execution_package.execution_package_id.value),
        reviewer_role_prompt_hook_ref=execution_package.role_prompt_hook.hook_ref,
    )
    provider_result = _execute_role_package(execution_package, scenario_input)
    parsed_ref = provider_result.provider_attempt.parsed_output_ref
    if parsed_ref is None:
        raise ValueError("graph patch reviewer parsed_output_ref is required")
    parsed_payload = _parse_graph_patch_review_payload_ref(
        parsed_ref,
        _provider_artifact_store(scenario_input),
    )
    review = parsed_payload.review.model_copy(
        update={"reviewer_attempt_ref": provider_result.provider_attempt.provider_attempt_id}
    )
    return validate_graph_patch_review(
        GraphPatchReviewerOutput(
            reviewer_input=reviewer_input.model_copy(
                update={
                    "expected_provider_attempt_ref": provider_result.provider_attempt.provider_attempt_id
                }
            ),
            provider_attempt=provider_result.provider_attempt,
            review=review,
            parsed_payload_ref=parsed_ref,
            validated_at=provider_result.provider_attempt.finished_at,
        )
    )


def _real_worker_provider_attempt(
    scenario_input: V2_100ScenarioInput,
    *,
    round_index: int,
    graph_version: int,
) -> ProviderAttempt:
    expected_attempt_ref = ProviderAttemptRef(
        value="provider-attempt.worker.rework.v2-100e.1"
    )
    execution_package = _execution_package_for_role(
        scenario_input,
        execution_package_ref="execution-package.v2-100e.backend",
        ticket_ref=TicketId(value=f"ticket.v2-100e.worker.round-{round_index}"),
        graph_version=graph_version,
        seat_ref="seat.worker.implementation",
        hook_ref="role-prompt-hook.baseline.worker.v1",
        objective="Acknowledge the V2-100E worker evidence package. Return strict JSON with provider_attempt_ref and evidence_summary.",
        context_refs=("context:v2-100e:worker-evidence",),
        constraints=(
            "Return JSON only.",
            "Do not claim closeout success; command evidence and recheck gates decide acceptance.",
        ),
        required_outputs=("json:worker_rework_evidence_ack",),
        audit_requirements=("provider.output.strict_json.no_markdown",),
        acceptance_refs=scenario_input.active_acceptance_refs[:1],
        source_surface_refs=scenario_input.active_source_surface_refs[:2],
        allowed_write_set=("app/main.py", "tests/test_books.py"),
    )
    provider_result = _execute_role_package(execution_package, scenario_input)
    return provider_result.provider_attempt


def _rebind_recheck_provider_attempt(
    recheck_input: ReworkEvidenceRecheckInput,
    *,
    provider_attempt_ref: ProviderAttemptRef,
    rework_plan_ref: ReworkPlanId,
) -> ReworkEvidenceRecheckInput:
    attempt = recheck_input.attempt.model_copy(
        update={
            "provider_attempt_refs": (provider_attempt_ref,),
            "rework_plan_ref": rework_plan_ref,
        }
    )
    work_product = recheck_input.work_product.model_copy(
        update={"producer_attempt_ref": provider_attempt_ref}
    )
    evidence_results: list[EvidenceVerificationResult] = []
    for result in recheck_input.evidence_verification_results:
        if result.verified_evidence is None:
            evidence_results.append(result)
            continue
        verified_evidence = result.verified_evidence
        verified_artifacts = tuple(
            artifact.model_copy(update={"producer_attempt_ref": provider_attempt_ref})
            for artifact in verified_evidence.verified_artifacts
        )
        evidence_results.append(
            result.model_copy(
                update={
                    "verified_evidence": verified_evidence.model_copy(
                        update={
                            "producer_attempt_ref": provider_attempt_ref,
                            "verified_artifacts": verified_artifacts,
                        }
                    )
                }
            )
        )
    source_lineage_records = tuple(
        lineage.model_copy(update={"producer_attempt_ref": provider_attempt_ref})
        for lineage in recheck_input.source_lineage_records
    )
    return recheck_input.model_copy(
        update={
            "attempt": attempt,
            "work_product": work_product,
            "evidence_verification_results": tuple(evidence_results),
            "source_lineage_records": source_lineage_records,
        }
    )


def validate_real_provider_recheck_input(
    recheck_input: ReworkEvidenceRecheckInput,
) -> ReworkEvidenceRecheckInput:
    attempt_refs = {
        attempt_ref.value for attempt_ref in recheck_input.attempt.provider_attempt_refs
    }
    if not attempt_refs:
        raise V2_100ReworkLoopError("real provider recheck requires provider attempt refs")
    if len(attempt_refs) != 1:
        raise V2_100ReworkLoopError("real provider recheck requires one worker attempt ref")
    worker_attempt_ref = next(iter(attempt_refs))
    if not worker_attempt_ref.startswith("provider-attempt.openai."):
        raise V2_100ReworkLoopError("real provider recheck requires openai provider attempt")

    for result in recheck_input.evidence_verification_results:
        evidence = result.verified_evidence
        if evidence is None:
            continue
        if evidence.producer_attempt_ref.value != worker_attempt_ref:
            raise V2_100ReworkLoopError("real provider evidence producer mismatch")
        if "provider-attempt.v2-100e.worker" in evidence.source_ref:
            raise V2_100ReworkLoopError("prebuilt accepted evidence cannot satisfy real provider recheck")
        if evidence.evidence_claim_ref.value.startswith(
            "claim.verified-evidence.rework-evidence."
        ):
            raise V2_100ReworkLoopError("prebuilt accepted evidence cannot satisfy real provider recheck")
        for artifact in evidence.verified_artifacts:
            if artifact.producer_attempt_ref.value != worker_attempt_ref:
                raise V2_100ReworkLoopError("real provider artifact producer mismatch")

    for lineage in recheck_input.source_lineage_records:
        if lineage.producer_attempt_ref.value != worker_attempt_ref:
            raise V2_100ReworkLoopError("real provider source lineage producer mismatch")

    if recheck_input.work_product.producer_attempt_ref.value != worker_attempt_ref:
        raise V2_100ReworkLoopError("real provider work product producer mismatch")
    return recheck_input


class _RealProviderRoundProvider:
    def __init__(self, *, package_root: Path) -> None:
        self._package_root = package_root

    def build_round(
        self,
        scenario_input: V2_100ScenarioInput,
        request: ReworkRequest,
        *,
        round_index: int,
        started_at_graph_version: int,
    ) -> ScenarioRoundBuild:
        from boardroom_os.proving.v2_100_resettable_fixture import (
            build_real_provider_recheck_input,
            build_v2_100_resettable_fixture,
        )

        fixture = build_v2_100_resettable_fixture(package_root=self._package_root)
        planner_output = _execute_real_ceo_planner(
            scenario_input,
            request,
            round_index=round_index,
            graph_version=started_at_graph_version,
        )
        review_outputs = tuple(
            _execute_real_graph_patch_review(
                scenario_input,
                planner_output.patch,
                round_index=round_index,
                graph_version=started_at_graph_version,
                domain=domain,
                actor=actor,
                seat_ref=seat_ref,
                hook_ref=hook_ref,
            )
            for domain, actor, seat_ref, hook_ref in _reviewer_specs()
        )
        approval_set = GraphPatchApprovalSet(
            approval_set_id=GraphPatchApprovalSetId(
                value=f"graph-patch-approval.v2-100e.real.round-{round_index}"
            ),
            ticket_graph_patch_ref=planner_output.patch.ticket_graph_patch_id,
            required_domains=planner_output.patch.required_review_domains,
            reviews=tuple(output.review for output in review_outputs),
            status=GraphPatchApprovalStatus.READY_TO_COMMIT,
            computed_at=datetime.now(UTC),
        )
        rework_ticket_ref = planner_output.patch.affected_ticket_refs[0]
        ticket_payload = TicketCreatedPayload(
            ticket_id=rework_ticket_ref,
            purpose="Fix V2-100E verified blocker set under active contract refs.",
            seat_demand=SeatDemand(
                required_role_category=RoleCategory.IMPLEMENTATION,
                required_capability_tags=(CapabilityTag(value="task.implementation"),),
            ),
            depends_on=(),
            acceptance_refs=tuple(ref.value for ref in planner_output.patch.operations[0].acceptance_refs),
            source_surface_refs=tuple(ref.value for ref in planner_output.patch.operations[0].source_surface_refs),
            evidence_obligations=tuple(ref.value for ref in planner_output.patch.operations[0].evidence_obligation_refs),
            allowed_read_refs=("contract:acceptance.v2-100e",),
            allowed_write_set=("app/main.py", "tests/test_books.py"),
            attempt_count=0,
        )
        worker_attempt = _real_worker_provider_attempt(
            scenario_input,
            round_index=round_index,
            graph_version=started_at_graph_version,
        )
        recheck_input = validate_real_provider_recheck_input(
            build_real_provider_recheck_input(
                package_root=self._package_root,
                attempt_id=ReworkAttemptId(value=f"rework-attempt.v2-100e.{round_index + 1}"),
                graph_version=started_at_graph_version + 16,
                provider_attempt_ref=worker_attempt.provider_attempt_id,
                rework_plan_ref=planner_output.plan.rework_plan_id,
            )
        )
        round_input = V2_100ScenarioRoundInput(
            round_index=round_index,
            project_ref=scenario_input.project_ref,
            request=request,
            planner_output=planner_output,
            reviewer_outputs=review_outputs,
            approval_set=approval_set,
            rework_ticket_payload=ticket_payload,
            attempt=recheck_input.attempt,
            recheck_input=recheck_input,
            terminal_decision=None,
            started_at_graph_version=started_at_graph_version,
        )
        payloads: dict[str, V2_100ReducerPayload] = {
            _round_payload_ref(round_index, "request").value: ReworkRequestPayload(request=request),
            _round_payload_ref(round_index, "plan").value: ReworkPlanPayload(
                request_ref=request.rework_request_id,
                plan=planner_output.plan,
                patch=planner_output.patch,
            ),
            _round_payload_ref(round_index, "approval").value: GraphPatchApprovalPayload(
                patch_ref=planner_output.patch.ticket_graph_patch_id,
                approval_set=approval_set,
            ),
            _round_payload_ref(round_index, "ticket").value: ticket_payload,
            _round_payload_ref(round_index, "attempt").value: ReworkAttemptPayload(attempt=recheck_input.attempt),
        }
        for index, output in enumerate(review_outputs, start=1):
            payloads[_round_payload_ref(round_index, f"review-{index}").value] = GraphPatchReviewPayload(
                patch_ref=planner_output.patch.ticket_graph_patch_id,
                review=output.review,
            )
        artifact_store = _provider_artifact_store(scenario_input)
        provider_manifest_entries = tuple(
            provider_attempt_manifest_entry(
                attempt,
                artifact_store=artifact_store,
                expected_input_package_ref=expected_package,
                expected_hook_ref=expected_hook,
            )
            for attempt, expected_package, expected_hook in (
                (
                    planner_output.provider_attempt,
                    planner_output.planner_input.planner_execution_package_ref.value,
                    planner_output.planner_input.planner_role_prompt_hook_ref.value,
                ),
                *(
                    (
                        review.provider_attempt,
                        review.reviewer_input.reviewer_execution_package_ref.value,
                        review.reviewer_input.reviewer_role_prompt_hook_ref.value,
                    )
                    for review in review_outputs
                ),
                (
                    worker_attempt,
                    "execution-package.v2-100e.backend",
                    "role-prompt-hook.baseline.worker.v1",
                ),
            )
            if attempt is not None
        )
        return ScenarioRoundBuild(
            round_input=round_input,
            payload_resolver=_ScenarioPayloadResolver(payloads),
            provider_attempt_manifest_entries=provider_manifest_entries,
        )


def provider_attempt_manifest_entry(
    attempt: ProviderAttempt,
    *,
    artifact_store: FileProviderOutputStore,
    expected_input_package_ref: str,
    expected_hook_ref: str,
) -> V2_100ProviderAttemptManifestEntry:
    validate_real_provider_attempt(
        attempt,
        expected_input_package_ref=expected_input_package_ref,
        expected_hook_ref=expected_hook_ref,
    )
    if attempt.raw_output_ref is None or attempt.parsed_output_ref is None:
        raise ValueError("provider artifact refs are required")
    raw_artifact = artifact_store.get(attempt.raw_output_ref)
    parsed_artifact = artifact_store.get(attempt.parsed_output_ref)
    return V2_100ProviderAttemptManifestEntry(
        provider_attempt_ref=attempt.provider_attempt_id.value,
        provider=attempt.provider,
        model=attempt.model,
        input_package_ref=attempt.input_package_ref.value,
        raw_output_ref=attempt.raw_output_ref,
        parsed_output_ref=attempt.parsed_output_ref,
        raw_output_sha256=f"sha256:{raw_artifact.content_hash.value}",
        parsed_output_sha256=f"sha256:{parsed_artifact.content_hash.value}",
    )


def validate_real_provider_attempt(
    attempt: ProviderAttempt,
    *,
    expected_input_package_ref: str,
    expected_hook_ref: str,
) -> ProviderAttempt:
    suspect_text = " ".join(
        str(value)
        for value in (
            attempt.provider_attempt_id.value,
            attempt.provider,
            attempt.model,
            attempt.raw_output_ref.value if attempt.raw_output_ref is not None else "",
            attempt.parsed_output_ref.value if attempt.parsed_output_ref is not None else "",
        )
    ).lower()
    if any(marker in suspect_text for marker in ("fake", "mock", "deterministic")):
        raise ValueError("fake provider attempt is not real provider evidence")
    if attempt.outcome is ProviderAttemptOutcome.FALLBACK_ARTIFACT:
        raise ValueError("fallback provider attempt cannot satisfy rework evidence")
    if attempt.status is not ProviderAttemptStatus.SUCCEEDED:
        raise ValueError("provider attempt must be succeeded")
    if attempt.input_package_ref.value != expected_input_package_ref:
        raise ValueError("provider input package mismatch")
    if attempt.role_prompt_hook_ref.value != expected_hook_ref:
        raise ValueError("provider role prompt hook mismatch")
    artifact_refs = (attempt.raw_output_ref, attempt.parsed_output_ref)
    for artifact_ref in artifact_refs:
        if artifact_ref is None:
            raise ValueError("provider artifact refs are required")
        lowered = artifact_ref.value.lower()
        if "fake" in lowered or "placeholder" in lowered:
            raise ValueError("provider artifact refs must not be fake or placeholder")
    return attempt


def validate_agent_authored_plan(output: CeoReworkPlannerOutput) -> CeoReworkPlannerOutput:
    return validate_ceo_rework_plan(output)


def validate_agent_authored_review(output: GraphPatchReviewerOutput) -> GraphPatchReviewerOutput:
    return validate_graph_patch_review(output)


def validate_round_input(round_input: V2_100ScenarioRoundInput) -> V2_100ScenarioRoundInput:
    validate_agent_authored_plan(round_input.planner_output)
    for review_output in round_input.reviewer_outputs:
        validate_agent_authored_review(review_output)
    if round_input.approval_set.status is not GraphPatchApprovalStatus.READY_TO_COMMIT:
        raise ValueError("graph patch approval set must be ready_to_commit")
    if round_input.attempt != round_input.recheck_input.attempt:
        raise ValueError("round input attempt mismatch with recheck input attempt")
    validate_rework_attempt_fact_refs(round_input.attempt)
    return round_input


def _validate_attempt_payload_binding(round_build: ScenarioRoundBuild) -> None:
    attempt_ref = _round_payload_ref(round_build.round_input.round_index, "attempt")
    payload = round_build.payload_resolver.resolve_rework_attempt(attempt_ref)
    if payload.attempt != round_build.round_input.attempt:
        raise ValueError("round input attempt mismatch with attempt payload")


def _validate_provider_attempt_manifest_bindings(round_build: ScenarioRoundBuild) -> None:
    required_refs: set[str] = set()
    planner_attempt = round_build.round_input.planner_output.provider_attempt
    if planner_attempt is not None:
        required_refs.add(planner_attempt.provider_attempt_id.value)
    for review_output in round_build.round_input.reviewer_outputs:
        if review_output.provider_attempt is not None:
            required_refs.add(review_output.provider_attempt.provider_attempt_id.value)
    required_refs.update(ref.value for ref in round_build.round_input.attempt.provider_attempt_refs)
    if not required_refs:
        raise ValueError("provider attempt manifest requires provider attempt refs")
    manifest_refs = {
        entry.provider_attempt_ref
        for entry in round_build.provider_attempt_manifest_entries
    }
    missing = tuple(sorted(required_refs - manifest_refs))
    if missing:
        raise ValueError(
            "provider attempt manifest is missing required refs: " + ", ".join(missing)
        )


def _round_payload_ref(round_index: int, suffix: str) -> EventPayloadRef:
    return EventPayloadRef(value=f"payload:v2-100e:round-{round_index}:{suffix}")


def _round_event(
    round_input: V2_100ScenarioRoundInput,
    event_type: EventType,
    *,
    graph_version: int,
    actor_ref: str,
    payload_ref: EventPayloadRef,
) -> EventRecord:
    return EventRecord(
        event_id=EventId(
            value=f"event:v2-100e:round-{round_input.round_index}:{event_type.value}:{graph_version}"
        ),
        event_type=event_type,
        project_ref=round_input.project_ref,
        actor_ref=ActorRef(value=actor_ref),
        timestamp=round_input.recheck_input.checked_at,
        graph_version=graph_version,
        payload_refs=(payload_ref,),
    )


def build_rework_reducer_events(
    round_input: V2_100ScenarioRoundInput,
    *,
    outcome: ReworkOutcome,
    prior_projection: ReworkProjection | None = None,
) -> tuple[EventRecord, ...]:
    if prior_projection is not None:
        if round_input.project_ref != prior_projection.project_ref:
            raise V2_100ReworkLoopError("prior projection project_ref mismatch")
        if round_input.started_at_graph_version < prior_projection.graph_version:
            raise V2_100ReworkLoopError("round started_at_graph_version is behind prior projection")
    graph_version = round_input.started_at_graph_version + 1
    if prior_projection is not None and prior_projection.request_ref != round_input.request.rework_request_id:
        raise V2_100ReworkLoopError("prior projection request_ref mismatch")

    events: list[EventRecord] = []

    def append(
        event_type: EventType,
        *,
        actor_ref: str,
        payload_ref: EventPayloadRef,
    ) -> None:
        nonlocal graph_version
        events.append(
            _round_event(
                round_input,
                event_type,
                graph_version=graph_version,
                actor_ref=actor_ref,
                payload_ref=payload_ref,
            )
        )
        graph_version += 1

    if prior_projection is None:
        append(
            EventType.REWORK_REQUESTED,
            actor_ref=round_input.request.requested_by_actor.value,
            payload_ref=_round_payload_ref(round_input.round_index, "request"),
        )

    append(
        EventType.REWORK_PLANNED,
        actor_ref="seat-ceo:v2-100e",
        payload_ref=_round_payload_ref(round_input.round_index, "plan"),
    )
    for index, review_output in enumerate(round_input.reviewer_outputs, start=1):
        append(
            EventType.REWORK_GRAPH_PATCH_REVIEWED,
            actor_ref=f"seat-{review_output.review.reviewer_actor.value}:v2-100e",
            payload_ref=_round_payload_ref(round_input.round_index, f"review-{index}"),
        )
    append(
        EventType.REWORK_GRAPH_PATCH_APPROVED,
        actor_ref="governance-graph-patch-review-gate:v2-100e",
        payload_ref=_round_payload_ref(round_input.round_index, "approval"),
    )
    append(
        EventType.REWORK_TICKET_CREATED,
        actor_ref="governance-command-handler:v2-100e",
        payload_ref=_round_payload_ref(round_input.round_index, "ticket"),
    )
    append(
        EventType.REWORK_ATTEMPT_STARTED,
        actor_ref="runtime:executor:v2-100e",
        payload_ref=_round_payload_ref(round_input.round_index, "attempt"),
    )
    append(
        EventType.REWORK_ATTEMPT_SUBMITTED,
        actor_ref="runtime:executor:v2-100e",
        payload_ref=_round_payload_ref(round_input.round_index, "attempt"),
    )
    append(
        EventType.REWORK_REVIEWED,
        actor_ref="seat-checker:v2-100e",
        payload_ref=_round_payload_ref(round_input.round_index, "outcome"),
    )

    if outcome.status is ReworkOutcomeStatus.REWORK_REQUIRED:
        return tuple(events)
    if outcome.status is ReworkOutcomeStatus.ACCEPTED:
        if outcome.remaining_blocker_refs:
            raise V2_100ReworkLoopError("accepted outcome must not include remaining blockers")
        append(
            EventType.REWORK_ACCEPTED,
            actor_ref="governance-command-handler:v2-100e",
            payload_ref=_round_payload_ref(round_input.round_index, "terminal"),
        )
        return tuple(events)
    if round_input.terminal_decision is None:
        raise V2_100ReworkLoopError("terminal decision is required for terminal rework outcome")
    if outcome.status is ReworkOutcomeStatus.EXHAUSTED:
        append(
            EventType.REWORK_EXHAUSTED,
            actor_ref="governance-command-handler:v2-100e",
            payload_ref=_round_payload_ref(round_input.round_index, "terminal"),
        )
        return tuple(events)
    if outcome.status is ReworkOutcomeStatus.ESCALATED:
        append(
            EventType.REWORK_ESCALATED,
            actor_ref="governance-command-handler:v2-100e",
            payload_ref=_round_payload_ref(round_input.round_index, "terminal"),
        )
        return tuple(events)
    raise V2_100ReworkLoopError(f"unsupported rework outcome status: {outcome.status.value}")


def _round_result_payload_resolver(
    round_build: ScenarioRoundBuild,
    *,
    outcome: ReworkOutcome,
) -> ScenarioPayloadResolver:
    payloads = round_build.payload_resolver.payloads()
    round_index = round_build.round_input.round_index
    payloads[_round_payload_ref(round_index, "outcome").value] = ReworkReviewPayload(outcome=outcome)
    if outcome.status is ReworkOutcomeStatus.ACCEPTED:
        payloads[_round_payload_ref(round_index, "terminal").value] = ReworkTerminalPayload(
            cycle_id=round_build.round_input.request.cycle_id,
            outcome_ref=outcome.rework_outcome_id,
            accepted_blocker_refs=outcome.accepted_blocker_refs,
            remaining_blocker_refs=(),
        )
    elif outcome.status in {ReworkOutcomeStatus.EXHAUSTED, ReworkOutcomeStatus.ESCALATED}:
        if round_build.round_input.terminal_decision is None:
            raise V2_100ReworkLoopError("terminal decision is required for terminal rework outcome")
        payloads[_round_payload_ref(round_index, "terminal").value] = ReworkTerminalPayload(
            cycle_id=round_build.round_input.request.cycle_id,
            outcome_ref=outcome.rework_outcome_id,
            termination_decision_ref=round_build.round_input.terminal_decision.termination_decision_id,
            remaining_blocker_refs=outcome.remaining_blocker_refs,
            termination_decision=round_build.round_input.terminal_decision,
        )
    return _ScenarioPayloadResolver(payloads)


def _outcome_for_round(
    round_input: V2_100ScenarioRoundInput,
    recheck_result: ReworkEvidenceRecheckResult,
) -> ReworkOutcome:
    outcome = recheck_result.to_rework_outcome()
    if outcome.status is not ReworkOutcomeStatus.REWORK_REQUIRED:
        return outcome
    decision = round_input.terminal_decision
    if decision is None:
        return outcome
    _validate_termination_decision(round_input, outcome, decision)
    if decision.reason is ReworkTerminationReason.EXHAUSTED_BUDGET:
        status = ReworkOutcomeStatus.EXHAUSTED
    elif decision.reason is ReworkTerminationReason.ESCALATED_HUMAN_REVIEW:
        status = ReworkOutcomeStatus.ESCALATED
    else:
        return outcome
    return ReworkOutcome(
        rework_outcome_id=outcome.rework_outcome_id,
        rework_attempt_ref=outcome.rework_attempt_ref,
        final_evidence_table_ref=outcome.final_evidence_table_ref,
        source_inventory_ref=outcome.source_inventory_ref,
        checker_verdict_ref=outcome.checker_verdict_ref,
        closeout_gate_ref=outcome.closeout_gate_ref,
        status=status,
        remaining_blocker_refs=outcome.remaining_blocker_refs,
        accepted_blocker_refs=(),
        termination_decision_ref=decision.termination_decision_id,
        created_at=outcome.created_at,
    )


def _validate_termination_decision(
    round_input: V2_100ScenarioRoundInput,
    outcome: ReworkOutcome,
    decision: ReworkTerminationDecision,
) -> None:
    if decision.cycle_id != round_input.request.cycle_id:
        raise ValueError("termination decision cycle_id mismatch")
    if set(decision.blocker_refs) != set(outcome.remaining_blocker_refs):
        raise ValueError("termination decision blocker_refs mismatch")
    if not set(decision.evidence_refs).issubset(set(round_input.attempt.command_evidence_refs)):
        raise ValueError("termination decision evidence_refs mismatch")
    if decision.decided_by_actor is not ReworkActorKind.GOVERNANCE_COMMAND_HANDLER:
        raise ValueError("termination decision actor mismatch")


def run_v2_100_rework_round(
    round_build: ScenarioRoundBuild,
    *,
    prior_events: tuple[EventRecord, ...] = (),
    payload_resolver: ScenarioPayloadResolver | None = None,
) -> V2_100ScenarioRoundResult:
    round_input = validate_round_input(round_build.round_input)
    _validate_attempt_payload_binding(round_build)
    _validate_provider_attempt_manifest_bindings(round_build)
    recheck_result = recheck_rework_attempt(round_input.recheck_input)
    outcome = _outcome_for_round(round_input, recheck_result)
    round_payload_resolver = _round_result_payload_resolver(round_build, outcome=outcome)
    active_payload_resolver = (
        merge_payload_resolvers(payload_resolver, round_payload_resolver)
        if payload_resolver is not None
        else round_payload_resolver
    )
    if prior_events:
        active_payload_resolver.payload_manifest_entries_for(prior_events)
    prior_projection = (
        ReworkReducer(active_payload_resolver).reduce(prior_events)
        if prior_events
        else None
    )
    round_events = build_rework_reducer_events(
        round_input,
        outcome=outcome,
        prior_projection=prior_projection,
    )
    all_events = prior_events + round_events
    active_payload_resolver.payload_manifest_entries_for(all_events)
    projection = ReworkReducer(active_payload_resolver).reduce(all_events)
    if outcome.status is ReworkOutcomeStatus.ACCEPTED:
        if projection.terminal_status is not ReworkTerminalStatus.ACCEPTED:
            raise V2_100ReworkLoopError("accepted outcome requires accepted projection")
    elif outcome.status is ReworkOutcomeStatus.REWORK_REQUIRED:
        if projection.terminal_status is not ReworkTerminalStatus.OPEN:
            raise V2_100ReworkLoopError("blocked outcome requires open projection")
    payload_refs = tuple(payload_ref for event in round_events for payload_ref in event.payload_refs)
    payload_manifest_entries = active_payload_resolver.payload_manifest_entries_for(round_events)
    return V2_100ScenarioRoundResult(
        round_index=round_input.round_index,
        request=round_input.request,
        plan_output=round_input.planner_output,
        review_outputs=round_input.reviewer_outputs,
        patch=round_input.planner_output.patch,
        approval_set=round_input.approval_set,
        rework_ticket_ref=round_input.rework_ticket_payload.ticket_id,
        attempt=round_input.attempt,
        recheck_result=recheck_result,
        outcome=outcome,
        projection=projection,
        events=round_events,
        payload_refs=payload_refs,
        payload_manifest_entries=payload_manifest_entries,
        provider_attempt_manifest_entries=round_build.provider_attempt_manifest_entries,
        accepted_blocker_refs=recheck_result.accepted_blocker_refs,
        remaining_blocker_refs=recheck_result.remaining_blocker_refs,
    )


def validate_loop_budget(
    rounds: tuple[V2_100ScenarioRoundResult, ...],
    *,
    max_rounds: int,
    terminal_decision: ReworkTerminationDecision | None,
) -> tuple[V2_100ScenarioRoundResult, ...]:
    if max_rounds <= 0:
        raise ValueError("max_rounds must be greater than zero")
    if len(rounds) > max_rounds:
        raise ValueError("round count exceeds max_rounds")
    if len(rounds) >= max_rounds and rounds:
        last_round = rounds[-1]
        has_remaining_blockers = bool(last_round.remaining_blocker_refs)
        if has_remaining_blockers and terminal_decision is None:
            raise ValueError("termination decision is required when loop budget is exhausted")
    return rounds


def _scenario_input_hash(scenario_input: V2_100ScenarioInput) -> str:
    canonical_json = json.dumps(
        scenario_input.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _scenario_id(scenario_input: V2_100ScenarioInput, input_hash: str) -> str:
    return (
        "scenario:v2-100e:"
        f"{scenario_input.project_ref.value}:"
        f"{scenario_input.run_id.value}:"
        f"{input_hash.removeprefix('sha256:')[:16]}"
    )


def _scenario_terminal_status(
    outcome: ReworkOutcome,
) -> V2_100ScenarioTerminalStatus:
    if outcome.status is ReworkOutcomeStatus.ACCEPTED:
        return V2_100ScenarioTerminalStatus.ACCEPTED
    if outcome.status is ReworkOutcomeStatus.EXHAUSTED:
        return V2_100ScenarioTerminalStatus.EXHAUSTED
    if outcome.status is ReworkOutcomeStatus.ESCALATED:
        return V2_100ScenarioTerminalStatus.ESCALATED
    if outcome.status is ReworkOutcomeStatus.REWORK_REQUIRED:
        return V2_100ScenarioTerminalStatus.STILL_BLOCKED
    raise V2_100ReworkLoopError(f"unsupported rework outcome status: {outcome.status.value}")


def _assert_still_blocked_round_open(round_result: V2_100ScenarioRoundResult) -> None:
    if round_result.projection.terminal_status is not ReworkTerminalStatus.OPEN:
        raise V2_100ReworkLoopError("still-blocked round requires open projection")
    terminal_events = {
        EventType.REWORK_ACCEPTED,
        EventType.REWORK_ESCALATED,
        EventType.REWORK_EXHAUSTED,
    }
    emitted_terminal_events = tuple(
        event.event_type for event in round_result.events if event.event_type in terminal_events
    )
    if emitted_terminal_events:
        names = ", ".join(event_type.value for event_type in emitted_terminal_events)
        raise V2_100ReworkLoopError(
            "still-blocked round must not emit terminal events: " + names
        )


def _dedupe_provider_attempt_manifest_entries(
    entries: tuple[V2_100ProviderAttemptManifestEntry, ...],
) -> tuple[V2_100ProviderAttemptManifestEntry, ...]:
    by_ref: dict[str, V2_100ProviderAttemptManifestEntry] = {}
    canonical_by_ref: dict[str, str] = {}
    for entry in entries:
        canonical_json = json.dumps(
            entry.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        existing = canonical_by_ref.get(entry.provider_attempt_ref)
        if existing is not None and existing != canonical_json:
            raise V2_100ReworkLoopError(
                f"provider attempt manifest ref conflict: {entry.provider_attempt_ref}"
            )
        by_ref[entry.provider_attempt_ref] = entry
        canonical_by_ref[entry.provider_attempt_ref] = canonical_json
    return tuple(by_ref[key] for key in sorted(by_ref))


def _write_json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    )
    path.write_text(encoded + "\n", encoding="utf-8")
    return path


def _ref_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _round_evidence_summary(round_result: V2_100ScenarioRoundResult) -> dict[str, Any]:
    recheck = round_result.recheck_result
    source_inventory = recheck.source_inventory
    closeout_gate_result = recheck.closeout_gate_result
    return {
        "accepted_blocker_refs": tuple(_ref_value(ref) for ref in round_result.accepted_blocker_refs),
        "checker_verdict_ref": recheck.checker_verdict.checker_verdict_id.value,
        "checked_refs": tuple(sorted(recheck.checked_refs)),
        "closeout_gate_result_ref": (
            closeout_gate_result.closeout_gate_result_id.value
            if closeout_gate_result is not None
            else None
        ),
        "closeout_gate_checked_refs": (
            tuple(sorted(closeout_gate_result.checked_refs))
            if closeout_gate_result is not None
            else ()
        ),
        "final_evidence_table_ref": recheck.final_evidence_table.final_evidence_table_id.value,
        "remaining_blocker_refs": tuple(_ref_value(ref) for ref in round_result.remaining_blocker_refs),
        "round_index": round_result.round_index,
        "source_inventory_entries": tuple(
            {
                "path": entry.path.value,
                "sha256": entry.sha256.value,
            }
            for entry in source_inventory.entries
        ),
        "source_inventory_ref": source_inventory.source_inventory_id.value,
    }


def _audit_checked_refs(result: V2_100ScenarioResult) -> tuple[str, ...]:
    refs: list[str] = [
        result.scenario_id,
        result.input_hash,
        result.request.rework_request_id.value,
        result.final_projection.project_ref.value,
    ]
    refs.extend(event_ref.value for event_ref in result.final_projection.committed_event_refs)
    refs.extend(result.final_projection.checked_refs)
    refs.extend(event.event_id.value for round_result in result.rounds for event in round_result.events)
    refs.extend(ref.value for round_result in result.rounds for ref in round_result.payload_refs)
    refs.extend(entry.payload_ref.value for entry in result.payload_manifest_entries)
    refs.extend(entry.provider_attempt_ref for entry in result.provider_attempt_manifest_entries)
    for round_result in result.rounds:
        recheck = round_result.recheck_result
        refs.extend(
            (
                round_result.patch.ticket_graph_patch_id.value,
                round_result.approval_set.approval_set_id.value,
                round_result.rework_ticket_ref.value,
                round_result.attempt.rework_attempt_id.value,
                recheck.source_inventory.source_inventory_id.value,
                recheck.final_evidence_table.final_evidence_table_id.value,
                recheck.checker_verdict.checker_verdict_id.value,
            )
        )
        refs.extend(recheck.checked_refs)
        refs.extend(ref.value for ref in round_result.accepted_blocker_refs)
        refs.extend(ref.value for ref in round_result.remaining_blocker_refs)
        if recheck.closeout_gate_result is not None:
            refs.append(recheck.closeout_gate_result.closeout_gate_result_id.value)
            refs.extend(recheck.closeout_gate_result.checked_refs)
    if result.termination_decision is not None:
        refs.append(result.termination_decision.termination_decision_id.value)
        refs.extend(ref.value for ref in result.termination_decision.blocker_refs)
        refs.extend(result.termination_decision.evidence_refs)
    return tuple(dict.fromkeys(ref for ref in refs if ref.strip()))


def _process_timeline(result: V2_100ScenarioResult) -> str:
    lines = [
        f"# V2-100E Rework Timeline",
        "",
        f"- Scenario: {result.scenario_id}",
        f"- Terminal status: {result.terminal_status.value}",
        f"- Rounds: {len(result.rounds)}",
        "",
    ]
    for round_result in result.rounds:
        lines.extend(
            (
                f"## Round {round_result.round_index}",
                "",
                f"- Outcome: {round_result.outcome.status.value}",
                f"- Accepted blockers: {', '.join(ref.value for ref in round_result.accepted_blocker_refs) or 'none'}",
                f"- Remaining blockers: {', '.join(ref.value for ref in round_result.remaining_blocker_refs) or 'none'}",
                f"- SourceInventory: {round_result.recheck_result.source_inventory.source_inventory_id.value}",
                f"- FinalEvidenceTable: {round_result.recheck_result.final_evidence_table.final_evidence_table_id.value}",
                f"- CheckerVerdict: {round_result.recheck_result.checker_verdict.checker_verdict_id.value}",
                "",
            )
        )
        for event in round_result.events:
            lines.append(
                f"- g{event.graph_version} {event.event_type.value}: "
                f"{event.event_id.value} payloads="
                f"{', '.join(payload_ref.value for payload_ref in event.payload_refs)}"
            )
        lines.append("")
    if result.termination_decision is not None:
        lines.extend(
            (
                "## Termination",
                "",
                f"- Decision: {result.termination_decision.termination_decision_id.value}",
                f"- Reason: {result.termination_decision.reason.value}",
                f"- Rationale: {result.termination_decision.rationale}",
                "",
            )
        )
    return "\n".join(lines).rstrip() + "\n"


def export_v2_100_rework_audit(
    result: V2_100ScenarioResult,
    export_root: Path,
) -> V2_100ScenarioAuditExport:
    result = V2_100ScenarioResult.model_validate(result)
    export_root = Path(export_root)
    checked_refs = _audit_checked_refs(result)

    summary_path = _write_json(
        export_root / "summary.json",
        {
            "accepted_blockers": tuple(
                ref.value for ref in result.rounds[-1].accepted_blocker_refs
            ),
            "checked_refs": checked_refs,
            "remaining_blockers": tuple(
                ref.value for ref in result.rounds[-1].remaining_blocker_refs
            ),
            "round_count": len(result.rounds),
            "scenario_id": result.scenario_id,
            "terminal_status": result.terminal_status.value,
            "termination_decision": (
                result.termination_decision.model_dump(mode="json")
                if result.termination_decision is not None
                else None
            ),
        },
    )
    event_log_path = _write_json(
        export_root / "event-log.json",
        tuple(
            event.stable_dump()
            for round_result in result.rounds
            for event in round_result.events
        ),
    )
    payload_manifest_path = _write_json(
        export_root / "payload-manifest.json",
        tuple(entry.model_dump(mode="json") for entry in result.payload_manifest_entries),
    )
    provider_attempts_path = _write_json(
        export_root / "provider-attempts.json",
        tuple(
            entry.model_dump(mode="json")
            for entry in result.provider_attempt_manifest_entries
        ),
    )
    evidence_summary_path = _write_json(
        export_root / "evidence-summary.json",
        tuple(_round_evidence_summary(round_result) for round_result in result.rounds),
    )
    process_timeline_path = export_root / "process-timeline.md"
    process_timeline_path.parent.mkdir(parents=True, exist_ok=True)
    process_timeline_path.write_text(_process_timeline(result), encoding="utf-8")

    return V2_100ScenarioAuditExport(
        export_root=export_root,
        summary_path=summary_path,
        event_log_path=event_log_path,
        payload_manifest_path=payload_manifest_path,
        provider_attempts_path=provider_attempts_path,
        evidence_summary_path=evidence_summary_path,
        process_timeline_path=process_timeline_path,
        checked_refs=checked_refs,
    )


def run_v2_100_rework_loop_scenario(
    scenario_input: V2_100ScenarioInput,
    *,
    round_provider: ScenarioRoundProvider | None = None,
) -> V2_100ScenarioResult:
    scenario_input = V2_100ScenarioInput.model_validate(scenario_input)
    request = project_snapshot_request(scenario_input)
    if round_provider is None:
        if not scenario_input.require_real_provider:
            raise V2_100ReworkLoopError(
                "round_provider is required when require_real_provider=False"
            )
        provider_package_root = (
            scenario_input.export_root / "real-provider-package"
            if scenario_input.export_root is not None
            else scenario_input.snapshot_summary_path.parent / "v2-100e-real-provider-package"
        )
        round_provider = _RealProviderRoundProvider(package_root=provider_package_root)
    if scenario_input.require_real_provider:
        if not isinstance(round_provider, _RealProviderRoundProvider):
            raise V2_100ReworkLoopError(
                "explicit round_provider is not allowed when require_real_provider=True"
            )

    events: tuple[EventRecord, ...] = ()
    rounds: tuple[V2_100ScenarioRoundResult, ...] = ()
    cumulative_payload_resolver: ScenarioPayloadResolver = _ScenarioPayloadResolver({})
    provider_attempt_manifest_entries: tuple[V2_100ProviderAttemptManifestEntry, ...] = ()
    termination_decision: ReworkTerminationDecision | None = None
    final_projection: ReworkProjection | None = None
    terminal_status: V2_100ScenarioTerminalStatus | None = None
    started_at_graph_version = scenario_input.initial_graph_version

    for round_index in range(1, scenario_input.max_rounds + 1):
        round_build = round_provider.build_round(
            scenario_input,
            request,
            round_index=round_index,
            started_at_graph_version=started_at_graph_version,
        )
        round_result = run_v2_100_rework_round(
            round_build,
            prior_events=events,
            payload_resolver=cumulative_payload_resolver,
        )
        rounds = rounds + (round_result,)
        events = events + round_result.events
        cumulative_payload_resolver = merge_payload_resolvers(
            cumulative_payload_resolver,
            _round_result_payload_resolver(round_build, outcome=round_result.outcome),
        )
        provider_attempt_manifest_entries = _dedupe_provider_attempt_manifest_entries(
            provider_attempt_manifest_entries
            + round_result.provider_attempt_manifest_entries
        )
        final_projection = round_result.projection
        started_at_graph_version = final_projection.graph_version

        if round_result.outcome.status is ReworkOutcomeStatus.REWORK_REQUIRED:
            _assert_still_blocked_round_open(round_result)
            if round_index >= scenario_input.max_rounds:
                termination_decision = round_build.round_input.terminal_decision
                validate_loop_budget(
                    rounds,
                    max_rounds=scenario_input.max_rounds,
                    terminal_decision=termination_decision,
                )
                raise V2_100ReworkLoopError(
                    "loop budget exhausted with remaining blockers but no "
                    "exhausted_budget or escalated_human_review terminal decision"
                )
            continue

        terminal_status = _scenario_terminal_status(round_result.outcome)
        termination_decision = round_build.round_input.terminal_decision
        if terminal_status is V2_100ScenarioTerminalStatus.EXHAUSTED:
            if termination_decision is None:
                raise V2_100ReworkLoopError("exhausted rework requires termination decision")
            if termination_decision.reason is not ReworkTerminationReason.EXHAUSTED_BUDGET:
                raise V2_100ReworkLoopError("exhausted rework requires exhausted_budget decision")
        elif terminal_status is V2_100ScenarioTerminalStatus.ESCALATED:
            if termination_decision is None:
                raise V2_100ReworkLoopError("escalated rework requires termination decision")
            if termination_decision.reason is not ReworkTerminationReason.ESCALATED_HUMAN_REVIEW:
                raise V2_100ReworkLoopError(
                    "escalated rework requires escalated_human_review decision"
                )
        else:
            termination_decision = None
        validate_loop_budget(
            rounds,
            max_rounds=scenario_input.max_rounds,
            terminal_decision=termination_decision,
        )
        break

    if not rounds or final_projection is None:
        raise V2_100ReworkLoopError("rework loop produced no rounds")
    if terminal_status is None:
        raise V2_100ReworkLoopError("rework loop ended without terminal status")

    payload_manifest_entries = cumulative_payload_resolver.payload_manifest_entries_for(events)
    input_hash = _scenario_input_hash(scenario_input)
    return V2_100ScenarioResult(
        scenario_id=_scenario_id(scenario_input, input_hash),
        input_hash=input_hash,
        terminal_status=terminal_status,
        request=request,
        rounds=rounds,
        final_projection=final_projection,
        termination_decision=termination_decision,
        payload_manifest_entries=payload_manifest_entries,
        provider_attempt_manifest_entries=provider_attempt_manifest_entries,
        audit_export=None,
        created_at=datetime.now(UTC),
    )


__all__ = [
    "CEO_AUDIT_REQUIREMENTS",
    "CEO_JSON_CONSTRAINTS",
    "CEO_REQUIRED_OUTPUTS",
    "REVIEWER_AUDIT_REQUIREMENTS",
    "REVIEWER_JSON_CONSTRAINTS",
    "REVIEWER_REQUIRED_OUTPUTS",
    "ScenarioPayloadResolver",
    "ScenarioRoundBuild",
    "ScenarioRoundProvider",
    "V2_100PayloadManifestEntry",
    "V2_100ProviderAttemptManifestEntry",
    "V2_100ReducerPayload",
    "V2_100ReworkLoopError",
    "V2_100ScenarioAuditExport",
    "V2_100ScenarioInput",
    "V2_100ScenarioResult",
    "V2_100ScenarioRoundInput",
    "V2_100ScenarioRoundResult",
    "V2_100ScenarioTerminalStatus",
    "_config_paths_from_v2_100e_env",
    "_assert_role_package_provider_binding",
    "_execute_role_package",
    "_ScenarioPayloadResolver",
    "_load_v2_100e_env_values",
    "_non_empty_unique_strings",
    "_parse_ceo_output",
    "_parse_graph_patch_review_output",
    "_real_provider_transport",
    "_temporary_env_overlay",
    "apply_ceo_json_output_contract",
    "apply_reviewer_json_output_contract",
    "canonical_payload_manifest_entry",
    "build_rework_reducer_events",
    "export_v2_100_rework_audit",
    "load_v2_100e_boardroom_settings",
    "load_v2_100e_openai_settings",
    "merge_payload_resolvers",
    "provider_attempt_manifest_entry",
    "project_snapshot_request",
    "run_v2_100_rework_round",
    "run_v2_100_rework_loop_scenario",
    "validate_agent_authored_plan",
    "validate_agent_authored_review",
    "validate_loop_budget",
    "validate_real_provider_attempt",
    "validate_round_input",
    "validate_scenario_request",
    "validate_v2_100e_provider_json_settings",
]
