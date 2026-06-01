from __future__ import annotations

from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath
from typing import Self

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator, model_validator

from boardroom_os.contracts.types import ContractId, NonEmptyTextValue
from boardroom_os.evidence.service_run import ServiceRunEvidence, ServiceRunEvidenceRef
from boardroom_os.evidence.table import FinalEvidenceStatus, FinalEvidenceTable, FinalEvidenceTableRef
from boardroom_os.evidence.verifier import VerifiedEvidence, VerifiedEvidenceRef
from boardroom_os.execution.verification_run import VerificationRun, VerificationRunRef, VerificationRunStatus
from boardroom_os.workspace.assembler import PackageArtifactKind, PackageAssembly, PackageAssemblyRef
from boardroom_os.workspace.manifest import WorkspaceManifest, WorkspaceManifestRef
from boardroom_os.workspace.run_manifest import RunManifest, RunManifestRef
from boardroom_os.workspace.source_inventory import SourceInventory, SourceInventoryRef


class WorkspaceEvidenceExportError(ValueError):
    pass


class WorkspaceEvidenceBundleRef(NonEmptyTextValue):
    pass


class EvidenceBundleArtifactPath(NonEmptyTextValue):
    @field_validator("value")
    @classmethod
    def _reject_unsafe_evidence_artifact_path(cls, value: str) -> str:
        normalized = super()._reject_empty_value(value)
        if "\\" in normalized:
            raise ValueError("evidence artifact path must use forward slashes")
        if normalized.endswith("/"):
            raise ValueError("evidence artifact path must name a file")
        if PurePosixPath(normalized).is_absolute() or PureWindowsPath(normalized).drive:
            raise ValueError("evidence artifact path must be relative")

        segments = normalized.split("/")
        if any(segment in {"", ".", ".."} for segment in segments):
            raise ValueError("evidence artifact path must not contain empty, current, or parent segments")
        if segments[0] != "20-evidence":
            raise ValueError("evidence artifact path must be under 20-evidence")
        if normalized == "src/boardroom_os" or normalized.startswith("src/boardroom_os/"):
            raise ValueError("evidence artifact path must not target framework repository layout")
        if segments[0] in {"00-boardroom", "10-project", "30-audit", "doc", "scripts", "examples"}:
            raise ValueError("evidence artifact path must be under 20-evidence")
        return normalized


class EvidenceBundleArtifactKind(StrEnum):
    BUNDLE_MANIFEST = "bundle_manifest"
    SOURCE_INVENTORY = "source_inventory"
    RUN_MANIFEST = "run_manifest"
    VERIFICATION_RUNS = "verification_runs"
    SERVICE_RUNS = "service_runs"
    FINAL_EVIDENCE_TABLE = "final_evidence_table"


_ARTIFACT_PATH_BY_KIND: dict[EvidenceBundleArtifactKind, str] = {
    EvidenceBundleArtifactKind.SOURCE_INVENTORY: "20-evidence/source-inventory/source-inventory.json",
    EvidenceBundleArtifactKind.VERIFICATION_RUNS: "20-evidence/tests/verification-runs.json",
    EvidenceBundleArtifactKind.SERVICE_RUNS: "20-evidence/tests/service-runs.json",
    EvidenceBundleArtifactKind.RUN_MANIFEST: "20-evidence/tests/run-manifest.json",
    EvidenceBundleArtifactKind.FINAL_EVIDENCE_TABLE: "20-evidence/closeout/final-evidence-table.json",
    EvidenceBundleArtifactKind.BUNDLE_MANIFEST: "20-evidence/closeout/evidence-bundle-manifest.json",
}


class EvidenceBundleArtifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    relative_path: EvidenceBundleArtifactPath
    artifact_kind: EvidenceBundleArtifactKind
    source_ref: NonEmptyTextValue
    related_refs: tuple[NonEmptyTextValue, ...]

    @field_validator("related_refs")
    @classmethod
    def _reject_empty_related_refs(cls, values: tuple[NonEmptyTextValue, ...]) -> tuple[NonEmptyTextValue, ...]:
        if not values:
            raise ValueError("related_refs must not be empty")
        return values

    @model_validator(mode="after")
    def _validate_kind_path_match(self) -> Self:
        expected_path = _ARTIFACT_PATH_BY_KIND[self.artifact_kind]
        if self.relative_path.value != expected_path:
            raise ValueError(f"{self.artifact_kind.value} must export to {expected_path}")
        return self

    @field_serializer("relative_path", "source_ref")
    def _serialize_ref(self, value: NonEmptyTextValue) -> dict[str, str]:
        return value.model_dump()

    @field_serializer("artifact_kind")
    def _serialize_artifact_kind(self, value: EvidenceBundleArtifactKind) -> str:
        return value.value

    @field_serializer("related_refs")
    def _serialize_related_refs(self, values: tuple[NonEmptyTextValue, ...]) -> list[dict[str, str]]:
        return [value.model_dump() for value in values]


class WorkspaceEvidenceBundle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    workspace_evidence_bundle_id: WorkspaceEvidenceBundleRef
    workspace_manifest_ref: WorkspaceManifestRef
    package_assembly_ref: PackageAssemblyRef
    package_contract_ref: ContractId
    source_inventory_ref: SourceInventoryRef
    run_manifest_ref: RunManifestRef
    final_evidence_table_ref: FinalEvidenceTableRef
    verification_run_refs: tuple[VerificationRunRef, ...]
    service_run_refs: tuple[ServiceRunEvidenceRef, ...] = ()
    verified_evidence_refs: tuple[VerifiedEvidenceRef, ...]
    artifacts: tuple[EvidenceBundleArtifact, ...]
    closeout_ready: bool

    @model_validator(mode="after")
    def _validate_bundle_shape(self) -> Self:
        if self.closeout_ready is not True:
            raise ValueError("closeout_ready must be true for exported workspace evidence bundle")
        paths = [artifact.relative_path.value for artifact in self.artifacts]
        if len(paths) != len(set(paths)):
            raise ValueError("evidence artifact paths must be unique")
        kinds = [artifact.artifact_kind for artifact in self.artifacts]
        if set(kinds) != set(EvidenceBundleArtifactKind):
            raise ValueError("required evidence bundle artifact kinds are missing")
        if tuple(sorted(self.verification_run_refs, key=lambda ref: ref.value)) != self.verification_run_refs:
            raise ValueError("verification_run_refs must be sorted")
        if tuple(sorted(self.service_run_refs, key=lambda ref: ref.value)) != self.service_run_refs:
            raise ValueError("service_run_refs must be sorted")
        if tuple(sorted(self.verified_evidence_refs, key=lambda ref: ref.value)) != self.verified_evidence_refs:
            raise ValueError("verified_evidence_refs must be sorted")
        return self

    @field_serializer(
        "workspace_evidence_bundle_id",
        "workspace_manifest_ref",
        "package_assembly_ref",
        "package_contract_ref",
        "source_inventory_ref",
        "run_manifest_ref",
        "final_evidence_table_ref",
    )
    def _serialize_ref(self, value: NonEmptyTextValue) -> dict[str, str]:
        return value.model_dump()

    @field_serializer("verification_run_refs", "service_run_refs", "verified_evidence_refs")
    def _serialize_ref_tuple(self, values: tuple[NonEmptyTextValue, ...]) -> list[dict[str, str]]:
        return [value.model_dump() for value in values]

    @field_serializer("artifacts")
    def _serialize_artifacts(self, values: tuple[EvidenceBundleArtifact, ...]) -> list[dict[str, object]]:
        return [value.model_dump() for value in values]


def build_workspace_evidence_bundle(
    *,
    workspace_manifest: WorkspaceManifest,
    package_assembly: PackageAssembly,
    source_inventory: SourceInventory,
    run_manifest: RunManifest,
    verification_runs: tuple[VerificationRun, ...],
    service_runs: tuple[ServiceRunEvidence, ...] = (),
    verified_evidence: tuple[VerifiedEvidence, ...],
    final_evidence_table: FinalEvidenceTable,
) -> WorkspaceEvidenceBundle:
    _validate_workspace_package_source_run_refs(
        workspace_manifest=workspace_manifest,
        package_assembly=package_assembly,
        source_inventory=source_inventory,
        run_manifest=run_manifest,
    )
    _validate_run_manifest_mirror(package_assembly=package_assembly, run_manifest=run_manifest)
    final_table_evidence_refs = _validate_final_evidence_table(final_evidence_table)
    verification_run_refs = _validate_verification_runs(verification_runs)
    service_run_refs = _validate_service_runs(service_runs)
    verified_evidence_refs = _validate_verified_evidence(verified_evidence)
    _validate_evidence_ref_closure(
        source_inventory=source_inventory,
        verification_runs=verification_runs,
        service_runs=service_runs,
        verified_evidence=verified_evidence,
        final_table_evidence_refs=final_table_evidence_refs,
    )

    bundle_id = WorkspaceEvidenceBundleRef(
        value=(
            "workspace-evidence-bundle."
            f"{workspace_manifest.workspace_manifest_id.value}."
            f"{package_assembly.package_assembly_id.value}."
            f"{final_evidence_table.final_evidence_table_id.value}"
        )
    )
    artifacts = _build_artifacts(
        workspace_manifest=workspace_manifest,
        package_assembly=package_assembly,
        source_inventory=source_inventory,
        run_manifest=run_manifest,
        verification_run_refs=verification_run_refs,
        service_run_refs=service_run_refs,
        verified_evidence_refs=verified_evidence_refs,
        final_evidence_table=final_evidence_table,
        bundle_id=bundle_id,
    )
    return WorkspaceEvidenceBundle(
        workspace_evidence_bundle_id=bundle_id,
        workspace_manifest_ref=workspace_manifest.workspace_manifest_id,
        package_assembly_ref=package_assembly.package_assembly_id,
        package_contract_ref=workspace_manifest.package_contract_ref,
        source_inventory_ref=source_inventory.source_inventory_id,
        run_manifest_ref=run_manifest.run_manifest_id,
        final_evidence_table_ref=final_evidence_table.final_evidence_table_id,
        verification_run_refs=verification_run_refs,
        service_run_refs=service_run_refs,
        verified_evidence_refs=verified_evidence_refs,
        artifacts=artifacts,
        closeout_ready=True,
    )


def _build_artifacts(
    *,
    workspace_manifest: WorkspaceManifest,
    package_assembly: PackageAssembly,
    source_inventory: SourceInventory,
    run_manifest: RunManifest,
    verification_run_refs: tuple[VerificationRunRef, ...],
    service_run_refs: tuple[ServiceRunEvidenceRef, ...],
    verified_evidence_refs: tuple[VerifiedEvidenceRef, ...],
    final_evidence_table: FinalEvidenceTable,
    bundle_id: WorkspaceEvidenceBundleRef,
) -> tuple[EvidenceBundleArtifact, ...]:
    evidence_root = workspace_manifest.evidence_root.value
    path_by_kind = {
        kind: EvidenceBundleArtifactPath(value=path.replace("20-evidence", evidence_root, 1))
        for kind, path in _ARTIFACT_PATH_BY_KIND.items()
    }
    related_refs = tuple(
        _as_text_ref(ref)
        for ref in (
            workspace_manifest.workspace_manifest_id,
            package_assembly.package_assembly_id,
            package_assembly.package_contract_ref,
            source_inventory.source_inventory_id,
            run_manifest.run_manifest_id,
            final_evidence_table.final_evidence_table_id,
            *verification_run_refs,
            *service_run_refs,
            *verified_evidence_refs,
        )
    )
    artifacts = (
        EvidenceBundleArtifact(
            relative_path=path_by_kind[EvidenceBundleArtifactKind.SOURCE_INVENTORY],
            artifact_kind=EvidenceBundleArtifactKind.SOURCE_INVENTORY,
            source_ref=source_inventory.source_inventory_id,
            related_refs=related_refs,
        ),
        EvidenceBundleArtifact(
            relative_path=path_by_kind[EvidenceBundleArtifactKind.VERIFICATION_RUNS],
            artifact_kind=EvidenceBundleArtifactKind.VERIFICATION_RUNS,
            source_ref=NonEmptyTextValue(value="verification-runs"),
            related_refs=related_refs,
        ),
        EvidenceBundleArtifact(
            relative_path=path_by_kind[EvidenceBundleArtifactKind.SERVICE_RUNS],
            artifact_kind=EvidenceBundleArtifactKind.SERVICE_RUNS,
            source_ref=NonEmptyTextValue(value="service-runs"),
            related_refs=related_refs,
        ),
        EvidenceBundleArtifact(
            relative_path=path_by_kind[EvidenceBundleArtifactKind.RUN_MANIFEST],
            artifact_kind=EvidenceBundleArtifactKind.RUN_MANIFEST,
            source_ref=run_manifest.run_manifest_id,
            related_refs=related_refs,
        ),
        EvidenceBundleArtifact(
            relative_path=path_by_kind[EvidenceBundleArtifactKind.FINAL_EVIDENCE_TABLE],
            artifact_kind=EvidenceBundleArtifactKind.FINAL_EVIDENCE_TABLE,
            source_ref=final_evidence_table.final_evidence_table_id,
            related_refs=related_refs,
        ),
        EvidenceBundleArtifact(
            relative_path=path_by_kind[EvidenceBundleArtifactKind.BUNDLE_MANIFEST],
            artifact_kind=EvidenceBundleArtifactKind.BUNDLE_MANIFEST,
            source_ref=bundle_id,
            related_refs=related_refs,
        ),
    )
    return tuple(sorted(artifacts, key=lambda artifact: artifact.relative_path.value))


def _as_text_ref(ref: NonEmptyTextValue) -> NonEmptyTextValue:
    return NonEmptyTextValue(value=ref.value)


def _validate_workspace_package_source_run_refs(
    *,
    workspace_manifest: WorkspaceManifest,
    package_assembly: PackageAssembly,
    source_inventory: SourceInventory,
    run_manifest: RunManifest,
) -> None:
    if workspace_manifest.package_contract_ref != package_assembly.package_contract_ref:
        raise WorkspaceEvidenceExportError("workspace/package package_contract_ref must match")
    if workspace_manifest.package_contract_ref != source_inventory.package_contract_ref:
        raise WorkspaceEvidenceExportError("source inventory package_contract_ref must match workspace manifest")
    if workspace_manifest.package_contract_ref != run_manifest.package_contract_ref:
        raise WorkspaceEvidenceExportError("run manifest package_contract_ref must match workspace manifest")
    if package_assembly.workspace_manifest_ref != workspace_manifest.workspace_manifest_id:
        raise WorkspaceEvidenceExportError("package assembly workspace_manifest_ref must match workspace manifest")
    if run_manifest.workspace_manifest_ref != workspace_manifest.workspace_manifest_id:
        raise WorkspaceEvidenceExportError("run manifest workspace_manifest_ref must match workspace manifest")
    if source_inventory.package_assembly_ref != package_assembly.package_assembly_id:
        raise WorkspaceEvidenceExportError("source inventory package_assembly_ref must match package assembly")


def _validate_run_manifest_mirror(*, package_assembly: PackageAssembly, run_manifest: RunManifest) -> None:
    run_manifest_artifacts = tuple(
        artifact for artifact in package_assembly.artifacts if artifact.artifact_kind is PackageArtifactKind.RUN_MANIFEST
    )
    if len(run_manifest_artifacts) != 1:
        raise WorkspaceEvidenceExportError("package assembly must contain exactly one run manifest artifact")
    expected_run_manifest_id = (
        f"run-manifest.{package_assembly.workspace_manifest_ref.value}.{package_assembly.package_contract_ref.value}"
    )
    if run_manifest.run_manifest_id.value != expected_run_manifest_id:
        raise WorkspaceEvidenceExportError("run manifest mirror must reference the same run_manifest_id")


def _validate_final_evidence_table(final_evidence_table: FinalEvidenceTable) -> set[str]:
    if not final_evidence_table.rows:
        raise WorkspaceEvidenceExportError("final evidence table rows must not be empty")
    if final_evidence_table.complete is not True:
        raise WorkspaceEvidenceExportError("final evidence table must be complete")
    final_refs: set[str] = set()
    for row in final_evidence_table.rows:
        if row.status is not FinalEvidenceStatus.SATISFIED:
            raise WorkspaceEvidenceExportError("final evidence table rows must all be satisfied")
        for evidence_ref in row.verified_evidence_refs:
            final_refs.add(evidence_ref.value)
    if not final_refs:
        raise WorkspaceEvidenceExportError("final evidence table must reference verified evidence")
    return final_refs


def _validate_verification_runs(verification_runs: tuple[VerificationRun, ...]) -> tuple[VerificationRunRef, ...]:
    if not verification_runs:
        raise WorkspaceEvidenceExportError("verification runs must not be empty")
    refs = tuple(run.verification_run_id for run in verification_runs)
    ref_values = tuple(ref.value for ref in refs)
    if len(ref_values) != len(set(ref_values)):
        raise WorkspaceEvidenceExportError("verification run refs must be unique")
    for run in verification_runs:
        if run.status is not VerificationRunStatus.PASSED:
            raise WorkspaceEvidenceExportError("verification run status must be passed")
    return tuple(sorted(refs, key=lambda ref: ref.value))


def _validate_verified_evidence(verified_evidence: tuple[VerifiedEvidence, ...]) -> tuple[VerifiedEvidenceRef, ...]:
    if not verified_evidence:
        raise WorkspaceEvidenceExportError("verified evidence must not be empty")
    refs = tuple(evidence.verified_evidence_id for evidence in verified_evidence)
    ref_values = tuple(ref.value for ref in refs)
    if len(ref_values) != len(set(ref_values)):
        raise WorkspaceEvidenceExportError("verified evidence refs must be unique")
    return tuple(sorted(refs, key=lambda ref: ref.value))


def _validate_service_runs(service_runs: tuple[ServiceRunEvidence, ...]) -> tuple[ServiceRunEvidenceRef, ...]:
    refs = tuple(service.service_run_evidence_id for service in service_runs)
    ref_values = tuple(ref.value for ref in refs)
    if len(ref_values) != len(set(ref_values)):
        raise WorkspaceEvidenceExportError("service run refs must be unique")
    for service in service_runs:
        if service.probe_status_code < 200 or service.probe_status_code >= 300:
            raise WorkspaceEvidenceExportError("service run readiness must be passed")
    return tuple(sorted(refs, key=lambda ref: ref.value))


def _validate_evidence_ref_closure(
    *,
    source_inventory: SourceInventory,
    verification_runs: tuple[VerificationRun, ...],
    service_runs: tuple[ServiceRunEvidence, ...],
    verified_evidence: tuple[VerifiedEvidence, ...],
    final_table_evidence_refs: set[str],
) -> None:
    source_inventory_evidence_refs = {
        evidence_ref.value
        for entry in source_inventory.entries
        for evidence_ref in entry.evidence_refs
    }
    if not source_inventory_evidence_refs:
        raise WorkspaceEvidenceExportError("source inventory entries must reference verified evidence")
    if not source_inventory_evidence_refs.issubset(final_table_evidence_refs):
        raise WorkspaceEvidenceExportError("source inventory evidence refs must be acknowledged by final evidence table")

    verified_evidence_by_ref = {evidence.verified_evidence_id.value: evidence for evidence in verified_evidence}
    unresolved_final_refs = final_table_evidence_refs - set(verified_evidence_by_ref)
    if unresolved_final_refs:
        raise WorkspaceEvidenceExportError("final evidence table verified evidence refs must resolve to verified evidence input")

    linked_evidence_refs = final_table_evidence_refs | source_inventory_evidence_refs
    verification_run_refs = {run.verification_run_id.value for run in verification_runs}
    service_run_refs = {service.service_run_evidence_id.value for service in service_runs}
    linked_run_refs: set[str] = set()
    linked_service_refs: set[str] = set()
    for evidence_ref in linked_evidence_refs:
        evidence = verified_evidence_by_ref.get(evidence_ref)
        if evidence is None:
            raise WorkspaceEvidenceExportError("verified evidence refs must resolve")
        linked_run_refs.update(run_ref.value for run_ref in evidence.verification_run_refs)
        linked_service_refs.update(service_ref.value for service_ref in evidence.service_run_refs)

    orphan_runs = verification_run_refs - linked_run_refs
    if orphan_runs:
        raise WorkspaceEvidenceExportError("orphan verification run cannot be exported")
    orphan_services = service_run_refs - linked_service_refs
    if orphan_services:
        raise WorkspaceEvidenceExportError("orphan service run cannot be exported")


__all__ = [
    "EvidenceBundleArtifact",
    "EvidenceBundleArtifactKind",
    "EvidenceBundleArtifactPath",
    "WorkspaceEvidenceBundle",
    "WorkspaceEvidenceBundleRef",
    "WorkspaceEvidenceExportError",
    "build_workspace_evidence_bundle",
]
