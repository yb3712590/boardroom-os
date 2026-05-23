from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator, model_validator

from boardroom_os.agents.skills import _normalize_ref_fields
from boardroom_os.contracts.package import PackageContract
from boardroom_os.contracts.types import (
    AcceptanceRef,
    ContractId,
    NonEmptyTextValue,
    SourceSurfaceRef,
)
from boardroom_os.evidence.verifier import ArtifactSha256, VerifiedEvidenceRef
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.graph.ticket import TicketId
from boardroom_os.workspace.assembler import (
    PackageArtifactKind,
    PackageAssembly,
    PackageAssemblyRef,
)
from boardroom_os.workspace.manifest import WorkspacePath


class SourceInventoryError(ValueError):
    pass


class SourceInventoryRef(NonEmptyTextValue):
    pass


class PackageCommitRef(NonEmptyTextValue):
    pass


_RESERVED_WORKSPACE_SECTION_PREFIXES = {
    "00-boardroom",
    "10-project",
    "20-evidence",
    "30-audit",
}

_RESERVED_FRAMEWORK_LAYOUT_PREFIXES = {
    "doc",
    "scripts",
    "examples",
}


_SOURCE_INVENTORY_TUPLE_REF_FIELDS = (
    "acceptance_refs",
    "evidence_refs",
)


_IMPLEMENTATION_BEARING_ARTIFACT_KINDS = {
    PackageArtifactKind.SOURCE,
    PackageArtifactKind.TEST,
    PackageArtifactKind.DOC,
}


def _reject_malformed_source_inventory_tuple_ref_inputs(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    for field_name in _SOURCE_INVENTORY_TUPLE_REF_FIELDS:
        if field_name in data and not isinstance(data[field_name], list | tuple):
            raise ValueError(f"{field_name} must be a tuple or list")
    return data


class SourceFilePath(NonEmptyTextValue):
    @field_validator("value")
    @classmethod
    def _reject_unsafe_source_path(cls, value: str) -> str:
        normalized = super()._reject_empty_value(value)
        if "\\" in normalized:
            raise ValueError("source file path must use forward slashes")
        if normalized.endswith("/"):
            raise ValueError("source file path must name a file")
        if PurePosixPath(normalized).is_absolute() or PureWindowsPath(normalized).drive:
            raise ValueError("source file path must be relative")

        segments = normalized.split("/")
        if any(segment in {"", ".", ".."} for segment in segments):
            raise ValueError(
                "source file path must not contain empty, current, or parent segments"
            )

        if segments[0] in _RESERVED_WORKSPACE_SECTION_PREFIXES:
            raise ValueError(
                "source file path must be relative to workspace package root 10-project"
            )
        if normalized == "src/boardroom_os" or normalized.startswith("src/boardroom_os/"):
            raise ValueError("source file path must not target framework repository layout")
        if segments[0] in _RESERVED_FRAMEWORK_LAYOUT_PREFIXES:
            raise ValueError("source file path must not target framework repository layout")
        return normalized


class SourceFileRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: SourceFilePath
    sha256: ArtifactSha256

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {
                "path": SourceFilePath,
                "sha256": ArtifactSha256,
            },
        )


class SourceLineageRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: SourceFilePath
    source_surface_ref: SourceSurfaceRef
    producer_ticket_ref: TicketId
    producer_attempt_ref: ProviderAttemptRef
    acceptance_refs: tuple[AcceptanceRef, ...]
    evidence_refs: tuple[VerifiedEvidenceRef, ...]

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        normalized = _reject_malformed_source_inventory_tuple_ref_inputs(data)
        return _normalize_ref_fields(
            normalized,
            {
                "path": SourceFilePath,
                "source_surface_ref": SourceSurfaceRef,
                "producer_ticket_ref": TicketId,
                "producer_attempt_ref": ProviderAttemptRef,
            },
            {
                "acceptance_refs": AcceptanceRef,
                "evidence_refs": VerifiedEvidenceRef,
            },
        )

    @field_validator("acceptance_refs")
    @classmethod
    def _reject_empty_acceptance_refs(
        cls,
        values: tuple[AcceptanceRef, ...],
    ) -> tuple[AcceptanceRef, ...]:
        if not values:
            raise ValueError("acceptance refs must not be empty")
        return values

    @field_validator("evidence_refs")
    @classmethod
    def _reject_empty_evidence_refs(
        cls,
        values: tuple[VerifiedEvidenceRef, ...],
    ) -> tuple[VerifiedEvidenceRef, ...]:
        if not values:
            raise ValueError("evidence refs must not be empty")
        return values


class SourceInventoryEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: SourceFilePath
    sha256: ArtifactSha256
    source_surface_ref: SourceSurfaceRef
    producer_ticket_ref: TicketId
    producer_attempt_ref: ProviderAttemptRef
    acceptance_refs: tuple[AcceptanceRef, ...]
    evidence_refs: tuple[VerifiedEvidenceRef, ...]

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        normalized = _reject_malformed_source_inventory_tuple_ref_inputs(data)
        return _normalize_ref_fields(
            normalized,
            {
                "path": SourceFilePath,
                "sha256": ArtifactSha256,
                "source_surface_ref": SourceSurfaceRef,
                "producer_ticket_ref": TicketId,
                "producer_attempt_ref": ProviderAttemptRef,
            },
            {
                "acceptance_refs": AcceptanceRef,
                "evidence_refs": VerifiedEvidenceRef,
            },
        )

    @field_serializer(
        "path",
        "sha256",
        "source_surface_ref",
        "producer_ticket_ref",
        "producer_attempt_ref",
    )
    def _serialize_refs(
        self,
        value: SourceFilePath | ArtifactSha256 | SourceSurfaceRef | TicketId | ProviderAttemptRef,
    ) -> dict[str, str]:
        return value.model_dump()

    @field_serializer("acceptance_refs")
    def _serialize_acceptance_refs(
        self,
        values: tuple[AcceptanceRef, ...],
    ) -> list[dict[str, str]]:
        return [value.model_dump() for value in values]

    @field_serializer("evidence_refs")
    def _serialize_evidence_refs(
        self,
        values: tuple[VerifiedEvidenceRef, ...],
    ) -> list[dict[str, str]]:
        return [value.model_dump() for value in values]

    @field_validator("acceptance_refs")
    @classmethod
    def _reject_empty_acceptance_refs(
        cls,
        values: tuple[AcceptanceRef, ...],
    ) -> tuple[AcceptanceRef, ...]:
        if not values:
            raise ValueError("acceptance refs must not be empty")
        return values

    @field_validator("evidence_refs")
    @classmethod
    def _reject_empty_evidence_refs(
        cls,
        values: tuple[VerifiedEvidenceRef, ...],
    ) -> tuple[VerifiedEvidenceRef, ...]:
        if not values:
            raise ValueError("evidence refs must not be empty")
        return values


class SourceInventory(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_inventory_id: SourceInventoryRef
    package_assembly_ref: PackageAssemblyRef
    package_contract_ref: ContractId
    package_root: WorkspacePath
    package_commit_ref: PackageCommitRef
    entries: tuple[SourceInventoryEntry, ...]

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {
                "source_inventory_id": SourceInventoryRef,
                "package_assembly_ref": PackageAssemblyRef,
                "package_contract_ref": ContractId,
                "package_root": WorkspacePath,
                "package_commit_ref": PackageCommitRef,
            },
        )

    @field_serializer(
        "source_inventory_id",
        "package_assembly_ref",
        "package_contract_ref",
        "package_root",
        "package_commit_ref",
    )
    def _serialize_refs(
        self,
        value: SourceInventoryRef | PackageAssemblyRef | ContractId | WorkspacePath | PackageCommitRef,
    ) -> dict[str, str]:
        return value.model_dump()

    @field_serializer("entries")
    def _serialize_entries(self, values: tuple[SourceInventoryEntry, ...]) -> list[dict[str, object]]:
        return [value.model_dump() for value in values]

    @field_validator("entries")
    @classmethod
    def _reject_empty_entries(
        cls,
        values: tuple[SourceInventoryEntry, ...],
    ) -> tuple[SourceInventoryEntry, ...]:
        if not values:
            raise ValueError("entries must not be empty")
        return values

    @model_validator(mode="after")
    def _validate_unique_paths(self) -> Self:
        seen: set[str] = set()
        for entry in self.entries:
            if entry.path.value in seen:
                raise ValueError("source inventory entry paths must be unique")
            seen.add(entry.path.value)
        return self


def build_source_inventory(
    *,
    package_assembly: PackageAssembly,
    package_contract: PackageContract,
    package_commit_ref: PackageCommitRef,
    source_files: tuple[SourceFileRecord, ...],
    lineage_records: tuple[SourceLineageRecord, ...],
) -> SourceInventory:
    if package_assembly.package_contract_ref != package_contract.package_contract_id:
        raise SourceInventoryError("package_contract_ref must match package assembly")
    if package_assembly.package_root.value != package_contract.package_root:
        raise SourceInventoryError("package root must match package contract")
    if not source_files:
        raise SourceInventoryError(
            "source inventory rejects ref-only package assembly without source files"
        )
    if not lineage_records:
        raise SourceInventoryError(
            "source inventory rejects ref-only package assembly without lineage records"
        )

    surfaces_by_ref = {
        surface.source_surface_ref.value: surface for surface in package_contract.source_surfaces
    }
    implementation_artifacts_by_path = {
        artifact.relative_path.value: artifact
        for artifact in package_assembly.artifacts
        if artifact.artifact_kind in _IMPLEMENTATION_BEARING_ARTIFACT_KINDS
    }
    source_files_by_path = _source_files_by_path(source_files)
    lineage_by_path = _lineage_records_by_path(lineage_records)
    source_paths = set(source_files_by_path)
    lineage_paths = set(lineage_by_path)
    implementation_paths = set(implementation_artifacts_by_path)

    if source_paths - lineage_paths:
        raise SourceInventoryError("source file is missing lineage")
    if lineage_paths - source_paths:
        raise SourceInventoryError("lineage path is missing source file")
    if source_paths - implementation_paths:
        raise SourceInventoryError("lineage path is not in package assembly")

    entries: list[SourceInventoryEntry] = []
    for path in sorted(source_paths):
        source_file = source_files_by_path[path]
        lineage_record = lineage_by_path[path]
        artifact = implementation_artifacts_by_path[path]
        _validate_lineage_record(
            lineage_record=lineage_record,
            artifact=artifact,
            surfaces_by_ref=surfaces_by_ref,
        )
        entries.append(
            SourceInventoryEntry(
                path=source_file.path,
                sha256=source_file.sha256,
                source_surface_ref=lineage_record.source_surface_ref,
                producer_ticket_ref=lineage_record.producer_ticket_ref,
                producer_attempt_ref=lineage_record.producer_attempt_ref,
                acceptance_refs=lineage_record.acceptance_refs,
                evidence_refs=lineage_record.evidence_refs,
            )
        )

    if implementation_paths - source_paths:
        raise SourceInventoryError("missing source inventory entry for implementation-bearing package artifact")

    return SourceInventory(
        source_inventory_id=SourceInventoryRef(
            value=(
                "source-inventory."
                f"{package_assembly.package_assembly_id.value}."
                f"{package_commit_ref.value}"
            )
        ),
        package_assembly_ref=package_assembly.package_assembly_id,
        package_contract_ref=package_contract.package_contract_id,
        package_root=package_assembly.package_root,
        package_commit_ref=package_commit_ref,
        entries=tuple(entries),
    )


def _source_files_by_path(
    source_files: tuple[SourceFileRecord, ...],
) -> dict[str, SourceFileRecord]:
    source_files_by_path: dict[str, SourceFileRecord] = {}
    for record in source_files:
        path = record.path.value
        if path in source_files_by_path:
            raise SourceInventoryError("source file paths must be unique")
        source_files_by_path[path] = record
    return source_files_by_path


def _lineage_records_by_path(
    lineage_records: tuple[SourceLineageRecord, ...],
) -> dict[str, SourceLineageRecord]:
    lineage_by_path: dict[str, SourceLineageRecord] = {}
    for record in lineage_records:
        path = record.path.value
        if path in lineage_by_path:
            raise SourceInventoryError("lineage paths must be unique")
        lineage_by_path[path] = record
    return lineage_by_path


def _validate_lineage_record(
    *,
    lineage_record: SourceLineageRecord,
    artifact,
    surfaces_by_ref: dict[str, object],
) -> None:
    surface = surfaces_by_ref.get(lineage_record.source_surface_ref.value)
    if surface is None:
        raise SourceInventoryError(
            f"unknown source surface ref: {lineage_record.source_surface_ref.value}"
        )

    artifact_surface_refs = {
        source_surface_ref.value for source_surface_ref in artifact.source_surface_refs
    }
    if lineage_record.source_surface_ref.value not in artifact_surface_refs:
        raise SourceInventoryError("lineage source surface is not compatible with package artifact")

    surface_acceptance_refs = {
        acceptance_ref.value for acceptance_ref in surface.acceptance_refs
    }
    lineage_acceptance_refs = {
        acceptance_ref.value for acceptance_ref in lineage_record.acceptance_refs
    }
    artifact_acceptance_refs = {
        acceptance_ref.value for acceptance_ref in artifact.acceptance_refs
    }

    if not lineage_acceptance_refs.issubset(surface_acceptance_refs):
        raise SourceInventoryError(
            f"lineage acceptance refs outside source surface {lineage_record.source_surface_ref.value}"
        )
    if not artifact_acceptance_refs.issubset(lineage_acceptance_refs):
        raise SourceInventoryError("lineage acceptance refs do not cover package artifact")


__all__ = [
    "PackageCommitRef",
    "SourceFilePath",
    "SourceFileRecord",
    "SourceInventory",
    "SourceInventoryEntry",
    "SourceInventoryError",
    "SourceInventoryRef",
    "SourceLineageRecord",
    "build_source_inventory",
]
