from __future__ import annotations

from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath
from typing import Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from boardroom_os.contracts.package import PackageContract
from boardroom_os.contracts.types import ContractId, NonEmptyTextValue


class WorkspaceManifestError(ValueError):
    pass


class WorkspaceManifestRef(NonEmptyTextValue):
    pass


class WorkflowRef(NonEmptyTextValue):
    pass


class WorkspacePath(NonEmptyTextValue):
    @field_validator("value")
    @classmethod
    def _reject_unsafe_relative_path(cls, value: str) -> str:
        normalized = super()._reject_empty_value(value)
        if "\\" in normalized:
            raise ValueError("workspace path must use forward slashes")
        if normalized.endswith("/"):
            raise ValueError("workspace path must not end with a slash")
        if PurePosixPath(normalized).is_absolute() or PureWindowsPath(normalized).drive:
            raise ValueError("workspace path must be relative")

        segments = normalized.split("/")
        if any(segment in {"", ".", ".."} for segment in segments):
            raise ValueError("workspace path must not contain empty, current, or parent segments")
        return normalized


class WorkspaceSection(StrEnum):
    BOARDROOM = "boardroom"
    PROJECT = "project"
    EVIDENCE = "evidence"
    AUDIT = "audit"


_CANONICAL_SECTION_PATHS: dict[WorkspaceSection, str] = {
    WorkspaceSection.BOARDROOM: "00-boardroom",
    WorkspaceSection.PROJECT: "10-project",
    WorkspaceSection.EVIDENCE: "20-evidence",
    WorkspaceSection.AUDIT: "30-audit",
}

_SECTION_ORDER: tuple[WorkspaceSection, ...] = (
    WorkspaceSection.BOARDROOM,
    WorkspaceSection.PROJECT,
    WorkspaceSection.EVIDENCE,
    WorkspaceSection.AUDIT,
)

_RESERVED_WORKSPACE_ROOT_PREFIXES: tuple[str, ...] = (
    "src",
    "src/boardroom_os",
    "tests",
    "doc",
    "scripts",
    "examples",
    "backend",
)


class WorkspaceSectionPath(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    section: WorkspaceSection
    relative_path: WorkspacePath

    @model_validator(mode="after")
    def _validate_canonical_path(self) -> Self:
        expected_path = _CANONICAL_SECTION_PATHS[self.section]
        if self.relative_path.value != expected_path:
            raise ValueError(f"{self.section.value} section must use {expected_path}")
        return self


class WorkspaceManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    workspace_manifest_id: WorkspaceManifestRef
    workflow_ref: WorkflowRef
    workspace_root: WorkspacePath
    package_contract_ref: ContractId
    sections: tuple[WorkspaceSectionPath, ...]

    @model_validator(mode="after")
    def _validate_manifest_identity(self) -> Self:
        expected_manifest_id = f"workspace-manifest.{self.workflow_ref.value}"
        if self.workspace_manifest_id.value != expected_manifest_id:
            raise ValueError(f"workspace_manifest_id must match workflow_ref as {expected_manifest_id}")

        workspace_root = self.workspace_root.value
        if any(
            workspace_root == reserved_prefix or workspace_root.startswith(f"{reserved_prefix}/")
            for reserved_prefix in _RESERVED_WORKSPACE_ROOT_PREFIXES
        ):
            raise ValueError("workspace_root must not use framework reserved prefixes")
        return self

    @model_validator(mode="after")
    def _validate_sections(self) -> Self:
        by_section: dict[WorkspaceSection, WorkspaceSectionPath] = {}
        for section_path in self.sections:
            if section_path.section in by_section:
                expected_path = _CANONICAL_SECTION_PATHS[section_path.section]
                raise ValueError(f"{section_path.section.value} section must be unique at {expected_path}")
            by_section[section_path.section] = section_path

        for section in _SECTION_ORDER:
            expected_path = _CANONICAL_SECTION_PATHS[section]
            actual = by_section.get(section)
            if actual is None:
                raise ValueError(f"{section.value} section is required at {expected_path}")
            if actual.relative_path.value != expected_path:
                raise ValueError(f"{section.value} section must use {expected_path}")

        if len(by_section) != len(_SECTION_ORDER):
            raise ValueError("workspace manifest sections must contain only canonical sections")
        return self

    def section_path(self, section: WorkspaceSection) -> WorkspacePath:
        for section_path in self.sections:
            if section_path.section == section:
                return section_path.relative_path
        expected_path = _CANONICAL_SECTION_PATHS[section]
        raise WorkspaceManifestError(f"{section.value} section is required at {expected_path}")

    @property
    def boardroom_root(self) -> WorkspacePath:
        return self.section_path(WorkspaceSection.BOARDROOM)

    @property
    def package_root(self) -> WorkspacePath:
        return self.section_path(WorkspaceSection.PROJECT)

    @property
    def evidence_root(self) -> WorkspacePath:
        return self.section_path(WorkspaceSection.EVIDENCE)

    @property
    def audit_root(self) -> WorkspacePath:
        return self.section_path(WorkspaceSection.AUDIT)

    def full_section_path(self, section: WorkspaceSection) -> WorkspacePath:
        return WorkspacePath(value=f"{self.workspace_root.value}/{self.section_path(section).value}")


def build_workspace_manifest(
    *,
    workflow_ref: WorkflowRef,
    workspace_root: WorkspacePath,
    package_contract: PackageContract,
) -> WorkspaceManifest:
    if package_contract.package_root != _CANONICAL_SECTION_PATHS[WorkspaceSection.PROJECT]:
        raise WorkspaceManifestError("package root must be exactly 10-project")

    return WorkspaceManifest(
        workspace_manifest_id=WorkspaceManifestRef(value=f"workspace-manifest.{workflow_ref.value}"),
        workflow_ref=workflow_ref,
        workspace_root=workspace_root,
        package_contract_ref=package_contract.package_contract_id,
        sections=tuple(
            WorkspaceSectionPath(
                section=section,
                relative_path=WorkspacePath(value=_CANONICAL_SECTION_PATHS[section]),
            )
            for section in _SECTION_ORDER
        ),
    )
