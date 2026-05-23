from __future__ import annotations

from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath
from typing import Self

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator, model_validator

from boardroom_os.contracts.package import PackageContract, PackageProjectType
from boardroom_os.contracts.types import AcceptanceRef, ContractId, NonEmptyTextValue, SourceSurfaceRef
from boardroom_os.workspace.manifest import WorkspaceManifest, WorkspaceManifestRef, WorkspacePath


class PackageAssemblerError(ValueError):
    pass


class PackageAssemblyRef(NonEmptyTextValue):
    pass


class PackageArtifactPath(NonEmptyTextValue):
    @field_validator("value")
    @classmethod
    def _reject_unsafe_package_path(cls, value: str) -> str:
        normalized = super()._reject_empty_value(value)
        if "\\" in normalized:
            raise ValueError("package artifact path must use forward slashes")
        if normalized.endswith("/"):
            raise ValueError("package artifact path must name a file")
        if PurePosixPath(normalized).is_absolute() or PureWindowsPath(normalized).drive:
            raise ValueError("package artifact path must be relative to package root")

        segments = normalized.split("/")
        if any(segment in {"", ".", ".."} for segment in segments):
            raise ValueError("package artifact path must not contain empty, current, or parent segments")

        workspace_sections = {"00-boardroom", "10-project", "20-evidence", "30-audit"}
        if segments[0] in workspace_sections:
            raise ValueError("package artifact path must be relative to workspace package root 10-project")

        if normalized == "src/boardroom_os" or normalized.startswith("src/boardroom_os/"):
            raise ValueError("package artifact path must not target framework repository layout")
        if segments[0] in {"doc", "scripts", "examples"}:
            raise ValueError("package artifact path must not target framework repository layout")
        return normalized


class PackageArtifactKind(StrEnum):
    README = "readme"
    AGENTS = "agents"
    PACKAGE_CONTRACT = "package_contract"
    RUN_MANIFEST = "run_manifest"
    SOURCE = "source"
    TEST = "test"
    DOC = "doc"


class PackageArtifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    relative_path: PackageArtifactPath
    artifact_kind: PackageArtifactKind
    source_surface_refs: tuple[SourceSurfaceRef, ...] = ()
    acceptance_refs: tuple[AcceptanceRef, ...] = ()

    @model_validator(mode="after")
    def _validate_artifact_metadata(self) -> Self:
        if self.relative_path.value == "README.md" and self.artifact_kind is not PackageArtifactKind.README:
            raise ValueError("README.md must use readme artifact kind")
        if self.relative_path.value == "AGENTS.md" and self.artifact_kind is not PackageArtifactKind.AGENTS:
            raise ValueError("AGENTS.md must use agents artifact kind")
        if self.relative_path.value == "package-contract.json" and self.artifact_kind is not PackageArtifactKind.PACKAGE_CONTRACT:
            raise ValueError("package-contract.json must use package_contract artifact kind")
        if self.relative_path.value == "run-manifest.json" and self.artifact_kind is not PackageArtifactKind.RUN_MANIFEST:
            raise ValueError("run-manifest.json must use run_manifest artifact kind")

        if self.artifact_kind not in {PackageArtifactKind.README, PackageArtifactKind.AGENTS}:
            if not self.source_surface_refs:
                raise ValueError("package artifacts other than README and AGENTS require source_surface_refs")
            if not self.acceptance_refs:
                raise ValueError("package artifacts other than README and AGENTS require acceptance_refs")
        return self

    @field_serializer("relative_path")
    def _serialize_relative_path(self, value: PackageArtifactPath) -> dict[str, str]:
        return value.model_dump()

    @field_serializer("artifact_kind")
    def _serialize_artifact_kind(self, value: PackageArtifactKind) -> str:
        return value.value

    @field_serializer("source_surface_refs")
    def _serialize_source_surface_refs(self, values: tuple[SourceSurfaceRef, ...]) -> list[dict[str, str]]:
        return [value.model_dump() for value in values]

    @field_serializer("acceptance_refs")
    def _serialize_acceptance_refs(self, values: tuple[AcceptanceRef, ...]) -> list[dict[str, str]]:
        return [value.model_dump() for value in values]


class PackageAssembly(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    package_assembly_id: PackageAssemblyRef
    workspace_manifest_ref: WorkspaceManifestRef
    package_contract_ref: ContractId
    package_root: WorkspacePath
    artifacts: tuple[PackageArtifact, ...]

    @field_serializer("package_assembly_id", "workspace_manifest_ref", "package_contract_ref", "package_root")
    def _serialize_refs(
        self,
        value: PackageAssemblyRef | WorkspaceManifestRef | ContractId | WorkspacePath,
    ) -> dict[str, str]:
        return value.model_dump()

    @field_serializer("artifacts")
    def _serialize_artifacts(self, values: tuple[PackageArtifact, ...]) -> list[dict[str, object]]:
        return [value.model_dump() for value in values]


def assemble_package(
    *,
    workspace_manifest: WorkspaceManifest,
    package_contract: PackageContract,
    artifacts: tuple[PackageArtifact, ...],
) -> PackageAssembly:
    if workspace_manifest.package_contract_ref != package_contract.package_contract_id:
        raise PackageAssemblerError("workspace manifest package_contract_ref must match package contract")
    if workspace_manifest.package_root.value != package_contract.package_root:
        raise PackageAssemblerError("package root must match workspace manifest package root")
    if package_contract.package_root != "10-project":
        raise PackageAssemblerError("package root must be 10-project")
    if not artifacts:
        raise PackageAssemblerError("package artifacts must not be empty")

    sorted_artifacts = tuple(sorted(artifacts, key=lambda artifact: artifact.relative_path.value))
    paths = tuple(artifact.relative_path.value for artifact in sorted_artifacts)
    if len(paths) != len(set(paths)):
        raise PackageAssemblerError("package artifact paths must be unique")

    artifacts_by_path = {artifact.relative_path.value: artifact for artifact in sorted_artifacts}
    _require_artifact(artifacts_by_path, "README.md", PackageArtifactKind.README)
    _require_artifact(artifacts_by_path, "AGENTS.md", PackageArtifactKind.AGENTS)
    _require_artifact(artifacts_by_path, "package-contract.json", PackageArtifactKind.PACKAGE_CONTRACT)
    _require_artifact(artifacts_by_path, "run-manifest.json", PackageArtifactKind.RUN_MANIFEST)

    if package_contract.project_type in {PackageProjectType.SOFTWARE, PackageProjectType.MIXED}:
        if not any(artifact.artifact_kind is PackageArtifactKind.SOURCE for artifact in sorted_artifacts):
            raise PackageAssemblerError("software and mixed packages require source artifacts")
        if not any(artifact.artifact_kind is PackageArtifactKind.TEST for artifact in sorted_artifacts):
            raise PackageAssemblerError("software and mixed packages require test artifacts")

    if package_contract.docs_required and not any(
        artifact.artifact_kind is PackageArtifactKind.DOC for artifact in sorted_artifacts
    ):
        raise PackageAssemblerError("docs_required package contracts require doc artifacts")

    _validate_surface_refs(package_contract=package_contract, artifacts=sorted_artifacts)
    _validate_surface_acceptance_ref_coverage(package_contract=package_contract, artifacts=sorted_artifacts)
    _validate_surface_path_coverage(package_contract=package_contract, artifacts=sorted_artifacts)

    return PackageAssembly(
        package_assembly_id=PackageAssemblyRef(
            value=(
                "package-assembly."
                f"{workspace_manifest.workspace_manifest_id.value}."
                f"{package_contract.package_contract_id.value}"
            )
        ),
        workspace_manifest_ref=workspace_manifest.workspace_manifest_id,
        package_contract_ref=package_contract.package_contract_id,
        package_root=workspace_manifest.package_root,
        artifacts=sorted_artifacts,
    )


def _require_artifact(
    artifacts_by_path: dict[str, PackageArtifact],
    path: str,
    expected_kind: PackageArtifactKind,
) -> None:
    artifact = artifacts_by_path.get(path)
    if artifact is None:
        raise PackageAssemblerError(f"{path} is required")
    if artifact.artifact_kind is not expected_kind:
        raise PackageAssemblerError(f"{path} must use {expected_kind.value} artifact kind")


def _validate_surface_refs(*, package_contract: PackageContract, artifacts: tuple[PackageArtifact, ...]) -> None:
    surfaces_by_ref = {
        surface.source_surface_ref.value: surface for surface in package_contract.source_surfaces
    }
    for artifact in artifacts:
        for source_surface_ref in artifact.source_surface_refs:
            surface = surfaces_by_ref.get(source_surface_ref.value)
            if surface is None:
                raise PackageAssemblerError(f"unknown source surface ref: {source_surface_ref.value}")

            declared_acceptance_refs = {acceptance_ref.value for acceptance_ref in surface.acceptance_refs}
            artifact_acceptance_refs = {acceptance_ref.value for acceptance_ref in artifact.acceptance_refs}
            if not artifact_acceptance_refs.issubset(declared_acceptance_refs):
                raise PackageAssemblerError(
                    f"artifact {artifact.relative_path.value} references acceptance refs outside source surface {source_surface_ref.value}"
                )


def _validate_surface_acceptance_ref_coverage(
    *, package_contract: PackageContract, artifacts: tuple[PackageArtifact, ...]
) -> None:
    artifacts_by_surface: dict[str, list[PackageArtifact]] = {}
    for artifact in artifacts:
        for source_surface_ref in artifact.source_surface_refs:
            artifacts_by_surface.setdefault(source_surface_ref.value, []).append(artifact)

    for surface in package_contract.source_surfaces:
        declared_acceptance_refs = {acceptance_ref.value for acceptance_ref in surface.acceptance_refs}
        covered_acceptance_refs = {
            acceptance_ref.value
            for artifact in artifacts_by_surface.get(surface.source_surface_ref.value, [])
            for acceptance_ref in artifact.acceptance_refs
        }
        if not declared_acceptance_refs.issubset(covered_acceptance_refs):
            raise PackageAssemblerError(
                f"source surface {surface.source_surface_ref.value} acceptance refs are not fully covered"
            )



def _validate_surface_path_coverage(*, package_contract: PackageContract, artifacts: tuple[PackageArtifact, ...]) -> None:
    artifacts_by_surface: dict[str, list[PackageArtifact]] = {}
    for artifact in artifacts:
        for source_surface_ref in artifact.source_surface_refs:
            artifacts_by_surface.setdefault(source_surface_ref.value, []).append(artifact)

    for surface in package_contract.source_surfaces:
        surface_artifacts = artifacts_by_surface.get(surface.source_surface_ref.value, [])
        if not surface_artifacts:
            raise PackageAssemblerError(f"source surface {surface.source_surface_ref.value} is not covered")

        for declared_path in surface.paths:
            if not any(
                _artifact_matches_declared_path(
                    artifact_path=artifact.relative_path.value,
                    declared_path=declared_path,
                )
                for artifact in surface_artifacts
            ):
                raise PackageAssemblerError(
                    f"source surface {surface.source_surface_ref.value} path {declared_path} is not covered"
                )


def _artifact_matches_declared_path(*, artifact_path: str, declared_path: str) -> bool:
    if declared_path.endswith("/"):
        return artifact_path.startswith(declared_path)
    return artifact_path == declared_path
