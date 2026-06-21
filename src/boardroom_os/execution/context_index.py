from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any, Literal, Mapping, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from boardroom_os.agents.profiles import ModelExecutionProfile
from boardroom_os.agents.role_prompt_hooks import RolePromptHook
from boardroom_os.agents.seat import AgentSeatRef
from boardroom_os.contracts.evidence_obligation import EvidenceObligation
from boardroom_os.contracts.package import PackageCommand
from boardroom_os.contracts.types import (
    AcceptanceRef,
    NonEmptyTextValue,
    SourceSurfaceRef,
)
from boardroom_os.execution.package import (
    AllowedReadRef,
    AllowedWritePath,
    AuditRequirement,
    ContextRef,
    ExecutionPackage,
    ExecutionPackageRef,
    FallbackPolicyRef,
    RequiredOutput,
    validate_execution_package_write_boundary,
)
from boardroom_os.graph.ticket import TicketId


class AgentContextSnapshotId(NonEmptyTextValue):
    pass


class AgentContextIndexEntryId(NonEmptyTextValue):
    pass


class ProviderAttemptRef(NonEmptyTextValue):
    pass


_SNAPSHOT_FINGERPRINT_FIELDS = (
    "version",
    "execution_package_ref",
    "ticket_ref",
    "graph_version",
    "seat_ref",
    "objective",
    "model_execution_profile",
    "role_prompt_hook",
    "context_refs",
    "constraints",
    "acceptance_refs",
    "source_surface_refs",
    "allowed_read_refs",
    "allowed_write_set",
    "required_outputs",
    "commands",
    "evidence_obligations",
    "fallback_policy_ref",
    "audit_requirements",
)


def _canonicalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        field_names = tuple(type(value).model_fields)
        if field_names == ("value",):
            return _canonicalize(value.value)
        return {
            field_name: _canonicalize(getattr(value, field_name))
            for field_name in field_names
        }
    if isinstance(value, tuple | list):
        return [_canonicalize(item) for item in value]
    if isinstance(value, Mapping):
        return {
            str(key): _canonicalize(item)
            for key, item in value.items()
        }
    if isinstance(value, Enum):
        return value.value
    return value


def _snapshot_fingerprint_from_fields(fields: Mapping[str, Any]) -> str:
    payload = {
        field_name: _canonicalize(fields[field_name])
        for field_name in _SNAPSHOT_FINGERPRINT_FIELDS
    }
    canonical_json = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _snapshot_fingerprint_from_snapshot(snapshot: "AgentContextSnapshot") -> str:
    return _snapshot_fingerprint_from_fields(
        {field_name: getattr(snapshot, field_name) for field_name in _SNAPSHOT_FINGERPRINT_FIELDS}
    )


def _snapshot_id_from_fingerprint(snapshot_fingerprint: str) -> AgentContextSnapshotId:
    return AgentContextSnapshotId(value=f"context-snapshot.{snapshot_fingerprint[:16]}")


class AgentContextSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1]
    context_snapshot_id: AgentContextSnapshotId
    execution_package_ref: ExecutionPackageRef
    ticket_ref: TicketId
    graph_version: int = Field(gt=0)
    seat_ref: AgentSeatRef
    objective: str
    model_execution_profile: ModelExecutionProfile
    role_prompt_hook: RolePromptHook
    context_refs: tuple[ContextRef, ...]
    constraints: tuple[str, ...]
    acceptance_refs: tuple[AcceptanceRef, ...]
    source_surface_refs: tuple[SourceSurfaceRef, ...]
    allowed_read_refs: tuple[AllowedReadRef, ...]
    allowed_write_set: tuple[AllowedWritePath, ...]
    required_outputs: tuple[RequiredOutput, ...]
    commands: tuple[PackageCommand, ...]
    evidence_obligations: tuple[EvidenceObligation, ...]
    fallback_policy_ref: FallbackPolicyRef
    audit_requirements: tuple[AuditRequirement, ...]
    snapshot_fingerprint: str

    @field_validator("objective")
    @classmethod
    def _reject_empty_objective(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("objective must not be empty")
        return normalized

    @field_validator("constraints")
    @classmethod
    def _reject_empty_constraints(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("required tuple must not be empty")
        normalized_values = tuple(value.strip() for value in values)
        if any(not value for value in normalized_values):
            raise ValueError("constraints must not contain empty values")
        return normalized_values

    @field_validator(
        "context_refs",
        "acceptance_refs",
        "source_surface_refs",
        "required_outputs",
        "commands",
        "evidence_obligations",
        "audit_requirements",
    )
    @classmethod
    def _reject_empty_required_tuples(cls, values: tuple[object, ...]) -> tuple[object, ...]:
        if not values:
            raise ValueError("required tuple must not be empty")
        return values

    @field_validator("snapshot_fingerprint")
    @classmethod
    def _validate_snapshot_fingerprint_shape(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) != 64:
            raise ValueError("snapshot_fingerprint must be a SHA-256 hex digest")
        try:
            int(normalized, 16)
        except ValueError as error:
            raise ValueError("snapshot_fingerprint must be a SHA-256 hex digest") from error
        return normalized

    @model_validator(mode="after")
    def _validate_derived_fields(self) -> Self:
        validate_execution_package_write_boundary(
            role_prompt_hook=self.role_prompt_hook,
            context_refs=self.context_refs,
            allowed_read_refs=self.allowed_read_refs,
            allowed_write_set=self.allowed_write_set,
            ticket_ref=self.ticket_ref,
            graph_version=self.graph_version,
        )

        expected_fingerprint = _snapshot_fingerprint_from_snapshot(self)
        if self.snapshot_fingerprint != expected_fingerprint:
            raise ValueError("snapshot_fingerprint does not match input facts")

        expected_snapshot_id = _snapshot_id_from_fingerprint(expected_fingerprint)
        if self.context_snapshot_id != expected_snapshot_id:
            raise ValueError("context_snapshot_id must be derived from snapshot_fingerprint")
        return self


class AgentContextIndexEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    entry_id: AgentContextIndexEntryId
    snapshot: AgentContextSnapshot
    provider_attempt_refs: tuple[ProviderAttemptRef, ...]

    @field_validator("provider_attempt_refs")
    @classmethod
    def _validate_provider_attempt_refs(
        cls,
        values: tuple[ProviderAttemptRef, ...],
    ) -> tuple[ProviderAttemptRef, ...]:
        if not values:
            raise ValueError("provider_attempt_refs must not be empty")
        seen: set[str] = set()
        for value in values:
            if value.value in seen:
                raise ValueError("provider_attempt_refs must be unique")
            seen.add(value.value)
        return values


class AgentContextIndex(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    entries: tuple[AgentContextIndexEntry, ...]

    @model_validator(mode="after")
    def _validate_entries(self) -> Self:
        if not self.entries:
            raise ValueError("entries must not be empty")

        entry_ids: set[str] = set()
        provider_attempt_refs: set[str] = set()
        for entry in self.entries:
            if entry.entry_id.value in entry_ids:
                raise ValueError("entry_id values must be unique")
            entry_ids.add(entry.entry_id.value)

            for provider_attempt_ref in entry.provider_attempt_refs:
                if provider_attempt_ref.value in provider_attempt_refs:
                    raise ValueError("provider_attempt_ref values must belong to one entry")
                provider_attempt_refs.add(provider_attempt_ref.value)

        return self


def build_agent_context_snapshot(execution_package: ExecutionPackage) -> AgentContextSnapshot:
    execution_package_ref = ExecutionPackageRef(
        value=execution_package.execution_package_id.value,
    )
    snapshot_fields: dict[str, Any] = {
        "version": execution_package.version,
        "execution_package_ref": execution_package_ref,
        "ticket_ref": execution_package.ticket_ref,
        "graph_version": execution_package.graph_version,
        "seat_ref": execution_package.seat_ref,
        "objective": execution_package.objective,
        "model_execution_profile": execution_package.model_execution_profile,
        "role_prompt_hook": execution_package.role_prompt_hook,
        "context_refs": execution_package.context_refs,
        "constraints": execution_package.constraints,
        "acceptance_refs": execution_package.acceptance_refs,
        "source_surface_refs": execution_package.source_surface_refs,
        "allowed_read_refs": execution_package.allowed_read_refs,
        "allowed_write_set": execution_package.allowed_write_set,
        "required_outputs": execution_package.required_outputs,
        "commands": execution_package.commands,
        "evidence_obligations": execution_package.evidence_obligations,
        "fallback_policy_ref": execution_package.fallback_policy_ref,
        "audit_requirements": execution_package.audit_requirements,
    }
    snapshot_fingerprint = _snapshot_fingerprint_from_fields(snapshot_fields)
    return AgentContextSnapshot(
        **snapshot_fields,
        context_snapshot_id=_snapshot_id_from_fingerprint(snapshot_fingerprint),
        snapshot_fingerprint=snapshot_fingerprint,
    )


__all__ = [
    "AgentContextSnapshotId",
    "AgentContextIndexEntryId",
    "ProviderAttemptRef",
    "AgentContextSnapshot",
    "AgentContextIndexEntry",
    "AgentContextIndex",
    "build_agent_context_snapshot",
]
