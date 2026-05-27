from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Mapping, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictBool,
    ValidationInfo,
    computed_field,
    field_serializer,
    field_validator,
    model_validator,
)

from boardroom_os.agents.skills import _normalize_ref_fields
from boardroom_os.closeout.gate import GitAuditReadiness, GitCommitSha, SourceInventoryHash
from boardroom_os.contracts.hashes import Sha256Hex
from boardroom_os.contracts.refs import canonical_sort_for_hash
from boardroom_os.contracts.package import PackageContract
from boardroom_os.contracts.types import ContractId, NonEmptyTextValue
from boardroom_os.events.types import ProjectRef
from boardroom_os.execution.verification_run import VerificationRun, VerificationRunRef, VerificationRunStatus, WorkspaceSnapshotRef
from boardroom_os.workspace.run_manifest import RunManifest, RunManifestRef
from boardroom_os.workspace.source_inventory import PackageCommitRef, SourceInventory, SourceInventoryRef

class GitVersionAuditError(ValueError):
    pass


class GitVersionAuditBundleRef(NonEmptyTextValue):
    pass


class GitVersionAuditReportRef(NonEmptyTextValue):
    pass


class GitVersionAuditFactSetRef(NonEmptyTextValue):
    pass


class GitVersionAuditManifestRef(NonEmptyTextValue):
    pass


class GitVersionAuditContentHash(Sha256Hex):
    pass


class GitVersionAuditCheckedRef(NonEmptyTextValue):
    pass


class GitTagRef(NonEmptyTextValue):
    pass


class GitBranchRef(NonEmptyTextValue):
    pass


class GitWorktreeRef(NonEmptyTextValue):
    pass


class GitDiffSummaryRef(NonEmptyTextValue):
    pass


class GitDirtyStatus(StrEnum):
    CLEAN = "clean"
    DIRTY = "dirty"


class GitChangedFileStatus(StrEnum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"
    UNTRACKED = "untracked"


def _is_valid_sha1(value: str) -> bool:
    try:
        GitCommitSha(value=value)
    except ValueError:
        return False
    return True


def _reject_unsafe_ref(value: str, *, field_name: str, allow_current_dir: bool = False) -> str:
    if allow_current_dir and value == ".":
        return value
    if (
        value.startswith("/")
        or "\\" in value
        or re.match(r"^[A-Za-z]:", value)
        or value in {".", ".."}
        or value.endswith("/")
        or value.endswith("/.")
        or value.endswith("/..")
        or value.startswith("./")
        or value.startswith("../")
        or "/./" in value
        or "/../" in value
    ):
        raise GitVersionAuditError(f"{field_name} must be audit-friendly")
    return value


def _canonical_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        field_names = tuple(type(value).model_fields)
        if field_names == ("value",):
            return value.value
        return value.model_dump(mode="json")
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, tuple | list):
        return [_canonical_jsonable(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _canonical_jsonable(item) for key, item in value.items()}
    return value


def _hash_jsonable(value: Any) -> str:
    encoded = json.dumps(
        _canonical_jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _hash_model(model: BaseModel) -> str:
    return _hash_jsonable(model.model_dump(mode="json"))


def _content_hash(value: Any) -> GitVersionAuditContentHash:
    return GitVersionAuditContentHash(value=_hash_jsonable(value))


def source_inventory_hash(source_inventory: SourceInventory) -> SourceInventoryHash:
    return SourceInventoryHash(value=_hash_jsonable(source_inventory.model_dump(mode="json")))


def _normalize_source_inventory_hash(value: Any) -> SourceInventoryHash:
    if isinstance(value, SourceInventoryHash):
        return value
    if isinstance(value, dict):
        return SourceInventoryHash.model_validate(value)
    return SourceInventoryHash(value=value)


def _normalize_content_hash(value: Any) -> GitVersionAuditContentHash:
    if isinstance(value, GitVersionAuditContentHash):
        return value
    if isinstance(value, dict):
        return GitVersionAuditContentHash.model_validate(value)
    return GitVersionAuditContentHash(value=value)


def _require_timezone(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise GitVersionAuditError("generated_at must include timezone")
    return value


def _ref_value(value: Any) -> str:
    if isinstance(value, BaseModel) and tuple(type(value).model_fields) == ("value",):
        return str(value.value)
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _hash_ref_value(value: Any, field_name: str) -> str:
    if not isinstance(value, GitVersionAuditContentHash):
        raise GitVersionAuditError(f"{field_name} must be GitVersionAuditContentHash")
    return value.value


class GitChangedFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    status: GitChangedFileStatus
    previous_path: str | None = None

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise GitVersionAuditError("changed file path must not be empty")
        return _reject_unsafe_ref(normalized, field_name="changed file path")

    @field_validator("previous_path")
    @classmethod
    def _validate_previous_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise GitVersionAuditError("previous_path must not be empty")
        return _reject_unsafe_ref(normalized, field_name="previous_path")

    @model_validator(mode="after")
    def _validate_rename_shape(self) -> Self:
        if self.status is GitChangedFileStatus.RENAMED and self.previous_path is None:
            raise GitVersionAuditError("renamed changed file requires previous_path")
        if self.status is not GitChangedFileStatus.RENAMED and self.previous_path is not None:
            raise GitVersionAuditError("previous_path is only allowed for renamed files")
        return self

    @field_serializer("status")
    def _serialize_status(self, value: GitChangedFileStatus) -> str:
        return value.value


class GitDiffSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    diff_summary_id: GitDiffSummaryRef
    changed_file_count: int
    insertions: int
    deletions: int
    summary_text: str

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(data, {"diff_summary_id": GitDiffSummaryRef})

    @field_validator("changed_file_count", "insertions", "deletions")
    @classmethod
    def _reject_negative_counts(cls, value: int) -> int:
        if value < 0:
            raise GitVersionAuditError("diff summary counts must be non-negative")
        return value

    @field_validator("summary_text")
    @classmethod
    def _validate_summary_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise GitVersionAuditError("diff summary text must not be empty")
        _reject_unsafe_ref(normalized, field_name="diff summary text")
        return normalized


class GitVersionAuditFactSet(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_set_id: GitVersionAuditFactSetRef
    project_ref: ProjectRef
    package_root: str
    branch_ref: GitBranchRef
    worktree_ref: GitWorktreeRef
    base_commit_sha: GitCommitSha
    final_commit_sha: GitCommitSha
    optional_tag_ref: GitTagRef | None = None
    dirty_status: GitDirtyStatus
    git_clean: StrictBool
    changed_files: tuple[GitChangedFile, ...]
    diff_summary: GitDiffSummary
    source_inventory_hash: SourceInventoryHash
    generated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if isinstance(data, dict) and "changed_files" in data and not isinstance(
            data["changed_files"], list | tuple
        ):
            raise GitVersionAuditError("changed_files must be a tuple or list")
        normalized = _normalize_ref_fields(
            data,
            {
                "fact_set_id": GitVersionAuditFactSetRef,
                "project_ref": ProjectRef,
                "branch_ref": GitBranchRef,
                "worktree_ref": GitWorktreeRef,
                "base_commit_sha": GitCommitSha,
                "final_commit_sha": GitCommitSha,
                "optional_tag_ref": GitTagRef,
            },
        )
        if isinstance(normalized, dict) and "source_inventory_hash" in normalized:
            normalized = dict(normalized)
            normalized["source_inventory_hash"] = _normalize_source_inventory_hash(
                normalized["source_inventory_hash"]
            )
        return normalized

    @field_validator("package_root")
    @classmethod
    def _validate_package_root(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise GitVersionAuditError("package_root must not be empty")
        return _reject_unsafe_ref(normalized, field_name="package_root")

    @field_validator("branch_ref", "worktree_ref", "optional_tag_ref")
    @classmethod
    def _validate_audit_refs(cls, value: GitBranchRef | GitWorktreeRef | GitTagRef | None) -> Any:
        if value is not None:
            _reject_unsafe_ref(value.value, field_name="git audit ref")
        return value

    @field_validator("base_commit_sha", "final_commit_sha")
    @classmethod
    def _validate_commit_sha(cls, value: GitCommitSha) -> GitCommitSha:
        return value

    @field_validator("source_inventory_hash")
    @classmethod
    def _validate_source_inventory_hash(cls, value: SourceInventoryHash) -> SourceInventoryHash:
        return value

    @field_validator("generated_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        return _require_timezone(value)

    @model_validator(mode="after")
    def _validate_cleanliness(self) -> Self:
        if self.dirty_status is GitDirtyStatus.CLEAN:
            if self.git_clean is not True:
                raise GitVersionAuditError("clean dirty_status requires git_clean true")
            if self.changed_files:
                raise GitVersionAuditError("clean git facts must not include changed files")
            if self.diff_summary.changed_file_count != 0 or self.diff_summary.insertions != 0 or self.diff_summary.deletions != 0:
                raise GitVersionAuditError("clean git facts require empty diff summary")
        else:
            if self.git_clean is not False:
                raise GitVersionAuditError("dirty dirty_status requires git_clean false")
            if not self.changed_files:
                raise GitVersionAuditError("dirty git facts require changed files")
        if self.diff_summary.changed_file_count != len(self.changed_files):
            raise GitVersionAuditError("diff summary changed_file_count mismatch")
        return self

    @field_serializer("dirty_status")
    def _serialize_dirty_status(self, value: GitDirtyStatus) -> str:
        return value.value


class GitCommandEvidenceBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    binding_id: GitVersionAuditCheckedRef
    verification_run_ref: VerificationRunRef
    run_manifest_ref: RunManifestRef
    package_contract_ref: ContractId
    command_id: ContractId
    command: tuple[str, ...]
    cwd: str
    workspace_snapshot_ref: WorkspaceSnapshotRef
    commit_sha: GitCommitSha
    source_inventory_hash: SourceInventoryHash

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if isinstance(data, dict) and "command" in data and not isinstance(
            data["command"], list | tuple
        ):
            raise GitVersionAuditError("command must be a tuple or list")
        normalized = _normalize_ref_fields(
            data,
            {
                "binding_id": GitVersionAuditCheckedRef,
                "verification_run_ref": VerificationRunRef,
                "run_manifest_ref": RunManifestRef,
                "package_contract_ref": ContractId,
                "command_id": ContractId,
                "workspace_snapshot_ref": WorkspaceSnapshotRef,
                "commit_sha": GitCommitSha,
            },
        )
        if isinstance(normalized, dict) and "source_inventory_hash" in normalized:
            normalized = dict(normalized)
            normalized["source_inventory_hash"] = _normalize_source_inventory_hash(
                normalized["source_inventory_hash"]
            )
        return normalized

    @field_validator("command")
    @classmethod
    def _validate_command(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if not normalized:
            raise GitVersionAuditError("command must not be empty")
        if any(not value for value in normalized):
            raise GitVersionAuditError("command must not contain empty items")
        return normalized

    @field_validator("cwd")
    @classmethod
    def _validate_cwd(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise GitVersionAuditError("cwd must not be empty")
        return _reject_unsafe_ref(normalized, field_name="cwd", allow_current_dir=True)

    @field_validator("commit_sha")
    @classmethod
    def _validate_commit_sha(cls, value: GitCommitSha) -> GitCommitSha:
        return value

    @field_validator("source_inventory_hash")
    @classmethod
    def _validate_source_inventory_hash(cls, value: SourceInventoryHash) -> SourceInventoryHash:
        return value


class GitVersionAuditReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    git_version_audit_report_id: GitVersionAuditReportRef
    project_ref: ProjectRef
    generated_at: datetime
    fact_set_ref: GitVersionAuditFactSetRef
    final_commit_sha: GitCommitSha
    package_commit_ref: PackageCommitRef
    source_inventory_ref: SourceInventoryRef
    source_inventory_hash: SourceInventoryHash
    source_inventory_hash_matches: StrictBool
    git_clean: StrictBool
    final_command_evidence_at_final_commit: StrictBool
    command_evidence_refs: tuple[str, ...]
    checked_refs: tuple[str, ...]

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for field_name in ("command_evidence_refs", "checked_refs"):
                if field_name in data and not isinstance(data[field_name], list | tuple):
                    raise GitVersionAuditError(f"{field_name} must be a tuple or list")
        normalized = _normalize_ref_fields(
            data,
            {
                "git_version_audit_report_id": GitVersionAuditReportRef,
                "project_ref": ProjectRef,
                "fact_set_ref": GitVersionAuditFactSetRef,
                "final_commit_sha": GitCommitSha,
                "package_commit_ref": PackageCommitRef,
                "source_inventory_ref": SourceInventoryRef,
            },
        )
        if isinstance(normalized, dict) and "source_inventory_hash" in normalized:
            normalized = dict(normalized)
            normalized["source_inventory_hash"] = _normalize_source_inventory_hash(
                normalized["source_inventory_hash"]
            )
        return normalized

    @field_validator("generated_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        return _require_timezone(value)

    @field_validator("final_commit_sha")
    @classmethod
    def _validate_commit_sha(cls, value: GitCommitSha) -> GitCommitSha:
        if not _is_valid_sha1(value.value):
            raise GitVersionAuditError("final_commit_sha must be a 40-character lowercase sha1")
        return value

    @field_validator("package_commit_ref", "source_inventory_ref")
    @classmethod
    def _validate_refs(cls, value: PackageCommitRef | SourceInventoryRef) -> PackageCommitRef | SourceInventoryRef:
        _reject_unsafe_ref(value.value, field_name="report ref")
        return value

    @field_validator("command_evidence_refs", "checked_refs")
    @classmethod
    def _validate_unique_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if not normalized:
            raise GitVersionAuditError("refs must not be empty")
        if any(not value for value in normalized):
            raise GitVersionAuditError("refs must not contain empty values")
        if len(set(normalized)) != len(normalized):
            raise GitVersionAuditError("refs must be unique")
        return normalized


class GitVersionAuditHashManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    hash_manifest_id: GitVersionAuditManifestRef
    project_ref: ProjectRef
    fact_set_hash: GitVersionAuditContentHash
    report_hash: GitVersionAuditContentHash
    command_binding_hashes: dict[str, GitVersionAuditContentHash]
    bundle_payload_hash: GitVersionAuditContentHash

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        normalized = _normalize_ref_fields(
            data,
            {
                "hash_manifest_id": GitVersionAuditManifestRef,
                "project_ref": ProjectRef,
                "fact_set_hash": GitVersionAuditContentHash,
                "report_hash": GitVersionAuditContentHash,
                "bundle_payload_hash": GitVersionAuditContentHash,
            },
        )
        if isinstance(normalized, dict) and "command_binding_hashes" in normalized:
            normalized = dict(normalized)
            normalized["command_binding_hashes"] = {
                key: _normalize_content_hash(value)
                for key, value in normalized["command_binding_hashes"].items()
            }
        return normalized

    @field_validator("command_binding_hashes")
    @classmethod
    def _validate_command_binding_hashes(
        cls, values: dict[str, GitVersionAuditContentHash]
    ) -> dict[str, GitVersionAuditContentHash]:
        if not values:
            raise GitVersionAuditError("command binding hashes must not be empty")
        return dict(values)


class GitVersionAuditBundle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    git_version_audit_bundle_id: GitVersionAuditBundleRef
    project_ref: ProjectRef
    generated_at: datetime
    fact_set: GitVersionAuditFactSet
    command_evidence_bindings: tuple[GitCommandEvidenceBinding, ...]
    report: GitVersionAuditReport
    hash_manifest: GitVersionAuditHashManifest
    checked_refs: tuple[str, ...]

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for field_name in ("command_evidence_bindings", "checked_refs"):
                if field_name in data and not isinstance(data[field_name], list | tuple):
                    raise GitVersionAuditError(f"{field_name} must be a tuple or list")
        return _normalize_ref_fields(
            data,
            {
                "git_version_audit_bundle_id": GitVersionAuditBundleRef,
                "project_ref": ProjectRef,
            },
        )

    @field_validator("generated_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        return _require_timezone(value)

    @field_validator("command_evidence_bindings")
    @classmethod
    def _validate_bindings(
        cls, values: tuple[GitCommandEvidenceBinding, ...]
    ) -> tuple[GitCommandEvidenceBinding, ...]:
        if not values:
            raise GitVersionAuditError("command evidence bindings must not be empty")
        refs = [binding.binding_id.value for binding in values]
        if len(set(refs)) != len(refs):
            raise GitVersionAuditError("command evidence bindings must be unique")
        return values

    @field_validator("checked_refs")
    @classmethod
    def _validate_checked_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if not normalized:
            raise GitVersionAuditError("checked_refs must not be empty")
        if any(not value for value in normalized):
            raise GitVersionAuditError("checked_refs must not contain empty values")
        if len(set(normalized)) != len(normalized):
            raise GitVersionAuditError("checked_refs must be unique")
        return normalized

    @model_validator(mode="after")
    def _validate_bundle_shape(self) -> Self:
        if self.project_ref != self.fact_set.project_ref or self.project_ref != self.report.project_ref:
            raise GitVersionAuditError("bundle project_ref mismatch")
        if self.project_ref != self.hash_manifest.project_ref:
            raise GitVersionAuditError("bundle hash manifest project_ref mismatch")
        if self.generated_at != self.report.generated_at:
            raise GitVersionAuditError("bundle report generated_at mismatch")
        _validate_hash_manifest(self)
        return self

    @computed_field
    @property
    def bundle_hash(self) -> str:
        return self.hash_manifest.bundle_payload_hash.value


class GitVersionAuditBuilderInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    project_ref: ProjectRef
    generated_at: datetime
    package_contract: PackageContract
    source_inventory: SourceInventory
    run_manifest: RunManifest
    verification_runs: tuple[VerificationRun, ...]
    command_evidence_bindings: tuple[GitCommandEvidenceBinding, ...]
    git_facts: GitVersionAuditFactSet

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for field_name in ("verification_runs", "command_evidence_bindings"):
                if field_name in data and not isinstance(data[field_name], list | tuple):
                    raise GitVersionAuditError(f"{field_name} must be a tuple or list")
        return _normalize_ref_fields(data, {"project_ref": ProjectRef})

    @field_validator("generated_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        return _require_timezone(value)

    @field_validator("package_contract", "source_inventory", "run_manifest", mode="wrap")
    @classmethod
    def _require_typed_model_instances(cls, value: Any, handler: Any, info: ValidationInfo) -> Any:
        expected_types = {
            "package_contract": PackageContract,
            "source_inventory": SourceInventory,
            "run_manifest": RunManifest,
        }
        expected_type = expected_types[info.field_name]
        if not isinstance(value, expected_type):
            raise GitVersionAuditError(
                f"{info.field_name} must be {expected_type.__name__}"
            )
        return value

    @field_validator("verification_runs", mode="before")
    @classmethod
    def _require_verification_runs(cls, value: Any) -> Any:
        return _require_instance_tuple(value, VerificationRun, "verification_runs")

    @field_validator("command_evidence_bindings", mode="before")
    @classmethod
    def _require_command_evidence_bindings(cls, value: Any) -> Any:
        return _require_instance_tuple(value, GitCommandEvidenceBinding, "command_evidence_bindings")

    @field_validator("git_facts", mode="wrap")
    @classmethod
    def _require_git_facts(cls, value: Any, handler: Any) -> Any:
        if not isinstance(value, GitVersionAuditFactSet):
            raise GitVersionAuditError("git_facts must be GitVersionAuditFactSet")
        return value


def _require_instance_tuple(value: Any, expected_type: type[Any], field_name: str) -> tuple[Any, ...]:
    if not isinstance(value, list | tuple):
        raise GitVersionAuditError(f"{field_name} must be a tuple or list")
    for item in value:
        if not isinstance(item, expected_type):
            raise GitVersionAuditError(f"{field_name} must contain {expected_type.__name__} values")
    return tuple(value)


def build_git_version_audit_bundle(builder_input: GitVersionAuditBuilderInput) -> GitVersionAuditBundle:
    if not isinstance(builder_input, GitVersionAuditBuilderInput):
        raise GitVersionAuditError("builder_input must be GitVersionAuditBuilderInput")
    _validate_builder_input(builder_input)
    sorted_runs = canonical_sort_for_hash(
        builder_input.verification_runs,
        key=lambda run: run.verification_run_id.value,
    )
    sorted_bindings = canonical_sort_for_hash(
        builder_input.command_evidence_bindings,
        key=lambda binding: binding.binding_id.value,
    )

    report = _build_report(builder_input, sorted_runs, sorted_bindings)
    checked_refs = _checked_refs(builder_input, sorted_runs, sorted_bindings, report)
    bundle_id_placeholder = GitVersionAuditBundleRef(
        value=f"git-version-audit-bundle.{builder_input.project_ref.value}.{builder_input.git_facts.final_commit_sha.value}"
    )
    hash_manifest = _build_hash_manifest(
        project_ref=builder_input.project_ref,
        fact_set=builder_input.git_facts,
        command_evidence_bindings=sorted_bindings,
        report=report,
        bundle_id=bundle_id_placeholder,
        generated_at=builder_input.generated_at,
        checked_refs=checked_refs,
    )
    bundle_id = GitVersionAuditBundleRef(
        value=f"git-version-audit-bundle.{builder_input.project_ref.value}.{hash_manifest.bundle_payload_hash.value[:16]}"
    )
    hash_manifest = _build_hash_manifest(
        project_ref=builder_input.project_ref,
        fact_set=builder_input.git_facts,
        command_evidence_bindings=sorted_bindings,
        report=report,
        bundle_id=bundle_id,
        generated_at=builder_input.generated_at,
        checked_refs=checked_refs,
    )
    return GitVersionAuditBundle(
        git_version_audit_bundle_id=bundle_id,
        project_ref=builder_input.project_ref,
        generated_at=builder_input.generated_at,
        fact_set=builder_input.git_facts,
        command_evidence_bindings=sorted_bindings,
        report=report,
        hash_manifest=hash_manifest,
        checked_refs=checked_refs,
    )


def git_version_audit_readiness(bundle: GitVersionAuditBundle) -> GitAuditReadiness:
    if not isinstance(bundle, GitVersionAuditBundle):
        raise GitVersionAuditError("bundle must be GitVersionAuditBundle")
    _validate_hash_manifest(bundle)
    _validate_report_semantics(bundle)
    git_clean = bundle.fact_set.git_clean is True and bundle.fact_set.dirty_status is GitDirtyStatus.CLEAN
    source_inventory_hash_matches = (
        bundle.report.source_inventory_hash == bundle.fact_set.source_inventory_hash
    )
    final_command_evidence_at_final_commit = all(
        binding.commit_sha == bundle.fact_set.final_commit_sha
        for binding in bundle.command_evidence_bindings
    )
    if git_clean is not True:
        raise GitVersionAuditError("git facts must be clean")
    if source_inventory_hash_matches is not True:
        raise GitVersionAuditError("source inventory hash mismatch")
    if final_command_evidence_at_final_commit is not True:
        raise GitVersionAuditError("final command evidence must be at final commit")
    return GitAuditReadiness(
        git_clean=git_clean,
        final_commit_sha=bundle.fact_set.final_commit_sha,
        source_inventory_hash=bundle.fact_set.source_inventory_hash,
        source_inventory_hash_matches=source_inventory_hash_matches,
        final_command_evidence_at_final_commit=final_command_evidence_at_final_commit,
    )


def _validate_report_semantics(bundle: GitVersionAuditBundle) -> None:
    report = bundle.report
    fact_set = bundle.fact_set
    bindings = bundle.command_evidence_bindings
    if report.fact_set_ref != fact_set.fact_set_id:
        raise GitVersionAuditError("report fact_set_ref mismatch")
    if report.final_commit_sha != fact_set.final_commit_sha:
        raise GitVersionAuditError("report final_commit_sha mismatch")
    _validate_package_commit_ref(report.package_commit_ref.value, fact_set.final_commit_sha.value)
    if report.source_inventory_hash != fact_set.source_inventory_hash:
        raise GitVersionAuditError("report source inventory hash mismatch")

    expected_git_clean = fact_set.git_clean is True and fact_set.dirty_status is GitDirtyStatus.CLEAN
    if report.git_clean is not expected_git_clean:
        raise GitVersionAuditError("report git_clean mismatch")

    expected_command_refs = tuple(binding.verification_run_ref.value for binding in bindings)
    if report.command_evidence_refs != expected_command_refs:
        raise GitVersionAuditError("report command evidence refs mismatch")

    source_inventory_hash_matches = report.source_inventory_hash == fact_set.source_inventory_hash
    if report.source_inventory_hash_matches is not source_inventory_hash_matches:
        raise GitVersionAuditError("report source inventory hash readiness mismatch")

    final_command_evidence_at_final_commit = all(
        binding.commit_sha == fact_set.final_commit_sha for binding in bindings
    )
    if report.final_command_evidence_at_final_commit is not final_command_evidence_at_final_commit:
        raise GitVersionAuditError("report final command evidence readiness mismatch")

    required_checked_refs = {
        fact_set.fact_set_id.value,
        fact_set.final_commit_sha.value,
        fact_set.source_inventory_hash.value,
        *expected_command_refs,
        *(binding.binding_id.value for binding in bindings),
    }
    if not required_checked_refs.issubset(set(report.checked_refs)):
        raise GitVersionAuditError("report checked_refs missing git audit closure refs")
    if not required_checked_refs.issubset(set(bundle.checked_refs)):
        raise GitVersionAuditError("bundle checked_refs missing git audit closure refs")


def _validate_builder_input(builder_input: GitVersionAuditBuilderInput) -> None:
    if builder_input.project_ref != builder_input.git_facts.project_ref:
        raise GitVersionAuditError("project_ref mismatch")
    if builder_input.source_inventory.package_contract_ref != builder_input.package_contract.package_contract_id:
        raise GitVersionAuditError("source_inventory package_contract_ref mismatch")
    if builder_input.run_manifest.package_contract_ref != builder_input.package_contract.package_contract_id:
        raise GitVersionAuditError("run_manifest package_contract_ref mismatch")
    if not builder_input.verification_runs:
        raise GitVersionAuditError("verification runs must not be empty")
    for run in builder_input.verification_runs:
        if run.status is not VerificationRunStatus.PASSED or run.exit_code != 0:
            raise GitVersionAuditError("verification runs must pass")
    if not builder_input.command_evidence_bindings:
        raise GitVersionAuditError("command evidence bindings must not be empty")
    if builder_input.git_facts.git_clean is not True:
        raise GitVersionAuditError("git facts must be clean")

    expected_hash = source_inventory_hash(builder_input.source_inventory)
    if builder_input.git_facts.source_inventory_hash != expected_hash:
        raise GitVersionAuditError("source inventory hash mismatch")
    _validate_package_commit_ref(
        builder_input.source_inventory.package_commit_ref.value,
        builder_input.git_facts.final_commit_sha.value,
    )
    _validate_command_bindings(builder_input, expected_hash)


def _validate_package_commit_ref(package_commit_ref: str, final_commit_sha: str) -> None:
    if package_commit_ref not in {final_commit_sha, f"package-commit.{final_commit_sha}"}:
        raise GitVersionAuditError("package_commit_ref must match final commit")


def _validate_command_bindings(
    builder_input: GitVersionAuditBuilderInput,
    expected_hash: SourceInventoryHash,
) -> None:
    run_by_ref = {run.verification_run_id.value: run for run in builder_input.verification_runs}
    binding_by_ref = {
        binding.verification_run_ref.value: binding
        for binding in builder_input.command_evidence_bindings
    }
    if len(binding_by_ref) != len(builder_input.command_evidence_bindings):
        raise GitVersionAuditError("command evidence bindings must be unique")
    if set(binding_by_ref) != set(run_by_ref):
        raise GitVersionAuditError("command evidence bindings must match verification runs")

    commands_by_id = {command.command_id.value: command for command in builder_input.run_manifest.commands}
    for binding_ref, binding in binding_by_ref.items():
        run = run_by_ref[binding_ref]
        manifest_command = commands_by_id.get(binding.command_id.value)
        if manifest_command is None:
            raise GitVersionAuditError("command binding must reference a declared command")
        if binding.run_manifest_ref != builder_input.run_manifest.run_manifest_id:
            raise GitVersionAuditError("command binding run_manifest_ref mismatch")
        if binding.package_contract_ref != builder_input.package_contract.package_contract_id:
            raise GitVersionAuditError("command binding package_contract_ref mismatch")
        if binding.command_id != run.command_id or binding.command != run.command or binding.cwd != run.cwd:
            raise GitVersionAuditError("command binding must match verification run")
        if manifest_command.command_id != binding.command_id or manifest_command.command != binding.command or manifest_command.cwd != binding.cwd:
            raise GitVersionAuditError("command binding must reference a declared command")
        if binding.workspace_snapshot_ref != run.workspace_snapshot_ref:
            raise GitVersionAuditError("command binding workspace snapshot mismatch")
        if binding.commit_sha != builder_input.git_facts.final_commit_sha:
            raise GitVersionAuditError("command binding must reference final commit")
        if binding.source_inventory_hash != expected_hash or binding.source_inventory_hash != builder_input.git_facts.source_inventory_hash:
            raise GitVersionAuditError("command binding source inventory hash mismatch")


def _build_report(
    builder_input: GitVersionAuditBuilderInput,
    verification_runs: tuple[VerificationRun, ...],
    command_evidence_bindings: tuple[GitCommandEvidenceBinding, ...],
) -> GitVersionAuditReport:
    command_refs = tuple(binding.verification_run_ref.value for binding in command_evidence_bindings)
    checked_refs = _checked_refs(builder_input, verification_runs, command_evidence_bindings, None)
    return GitVersionAuditReport(
        git_version_audit_report_id=GitVersionAuditReportRef(
            value=f"git-version-audit-report.{builder_input.project_ref.value}.{builder_input.git_facts.final_commit_sha.value}"
        ),
        project_ref=builder_input.project_ref,
        generated_at=builder_input.generated_at,
        fact_set_ref=builder_input.git_facts.fact_set_id,
        final_commit_sha=builder_input.git_facts.final_commit_sha,
        package_commit_ref=builder_input.source_inventory.package_commit_ref,
        source_inventory_ref=builder_input.source_inventory.source_inventory_id,
        source_inventory_hash=builder_input.git_facts.source_inventory_hash,
        source_inventory_hash_matches=True,
        git_clean=builder_input.git_facts.git_clean,
        final_command_evidence_at_final_commit=True,
        command_evidence_refs=command_refs,
        checked_refs=checked_refs,
    )


def _checked_refs(
    builder_input: GitVersionAuditBuilderInput,
    verification_runs: tuple[VerificationRun, ...],
    command_evidence_bindings: tuple[GitCommandEvidenceBinding, ...],
    report: GitVersionAuditReport | None,
) -> tuple[str, ...]:
    refs = [
        builder_input.package_contract.package_contract_id.value,
        builder_input.source_inventory.source_inventory_id.value,
        builder_input.run_manifest.run_manifest_id.value,
        builder_input.git_facts.final_commit_sha.value,
        builder_input.git_facts.source_inventory_hash.value,
        builder_input.git_facts.fact_set_id.value,
    ]
    refs.extend(run.verification_run_id.value for run in verification_runs)
    refs.extend(binding.binding_id.value for binding in command_evidence_bindings)
    if report is not None:
        refs.append(report.git_version_audit_report_id.value)
    return tuple(dict.fromkeys(refs))


def _build_hash_manifest(
    *,
    project_ref: ProjectRef,
    fact_set: GitVersionAuditFactSet,
    command_evidence_bindings: tuple[GitCommandEvidenceBinding, ...],
    report: GitVersionAuditReport,
    bundle_id: GitVersionAuditBundleRef,
    generated_at: datetime,
    checked_refs: tuple[str, ...],
) -> GitVersionAuditHashManifest:
    command_binding_hashes = {
        binding.binding_id.value: _content_hash(binding.model_dump(mode="json"))
        for binding in command_evidence_bindings
    }
    bundle_payload = _bundle_payload_for_hash(
        bundle_id=bundle_id,
        project_ref=project_ref,
        generated_at=generated_at,
        fact_set=fact_set,
        command_evidence_bindings=command_evidence_bindings,
        report=report,
        checked_refs=checked_refs,
        hash_manifest_without_bundle_hash={
            "hash_manifest_id": f"git-version-audit-hash-manifest.{project_ref.value}.{fact_set.final_commit_sha.value}",
            "project_ref": project_ref.value,
            "fact_set_hash": _hash_model(fact_set),
            "report_hash": _hash_model(report),
            "command_binding_hashes": {
                key: value.value for key, value in command_binding_hashes.items()
            },
        },
    )
    return GitVersionAuditHashManifest(
        hash_manifest_id=GitVersionAuditManifestRef(
            value=f"git-version-audit-hash-manifest.{project_ref.value}.{fact_set.final_commit_sha.value}"
        ),
        project_ref=project_ref,
        fact_set_hash=_content_hash(fact_set.model_dump(mode="json")),
        report_hash=_content_hash(report.model_dump(mode="json")),
        command_binding_hashes=command_binding_hashes,
        bundle_payload_hash=_content_hash(bundle_payload),
    )


def _bundle_payload_for_hash(
    *,
    bundle_id: GitVersionAuditBundleRef,
    project_ref: ProjectRef,
    generated_at: datetime,
    fact_set: GitVersionAuditFactSet,
    command_evidence_bindings: tuple[GitCommandEvidenceBinding, ...],
    report: GitVersionAuditReport,
    checked_refs: tuple[str, ...],
    hash_manifest_without_bundle_hash: dict[str, Any],
) -> dict[str, Any]:
    return {
        "version": 1,
        "git_version_audit_bundle_id": bundle_id.value,
        "project_ref": project_ref.value,
        "generated_at": generated_at.isoformat(),
        "fact_set": fact_set.model_dump(mode="json"),
        "command_evidence_bindings": [
            binding.model_dump(mode="json") for binding in command_evidence_bindings
        ],
        "report": report.model_dump(mode="json"),
        "hash_manifest": hash_manifest_without_bundle_hash,
        "checked_refs": checked_refs,
    }


def _validate_hash_manifest(bundle: GitVersionAuditBundle) -> None:
    manifest = bundle.hash_manifest
    expected_command_hashes = {
        binding.binding_id.value: _content_hash(binding.model_dump(mode="json"))
        for binding in bundle.command_evidence_bindings
    }
    if _hash_ref_value(manifest.fact_set_hash, "hash manifest fact_set_hash") != _hash_model(bundle.fact_set):
        raise GitVersionAuditError("hash manifest fact_set_hash mismatch")
    if _hash_ref_value(manifest.report_hash, "hash manifest report_hash") != _hash_model(bundle.report):
        raise GitVersionAuditError("hash manifest report_hash mismatch")
    if manifest.command_binding_hashes != expected_command_hashes:
        raise GitVersionAuditError("hash manifest command binding hashes mismatch")
    hash_manifest_without_bundle_hash = {
        "hash_manifest_id": manifest.hash_manifest_id.value,
        "project_ref": manifest.project_ref.value,
        "fact_set_hash": _hash_ref_value(manifest.fact_set_hash, "hash manifest fact_set_hash"),
        "report_hash": _hash_ref_value(manifest.report_hash, "hash manifest report_hash"),
        "command_binding_hashes": {
            key: _hash_ref_value(value, "hash manifest command binding hash")
            for key, value in manifest.command_binding_hashes.items()
        },
    }
    expected_payload = _bundle_payload_for_hash(
        bundle_id=bundle.git_version_audit_bundle_id,
        project_ref=bundle.project_ref,
        generated_at=bundle.generated_at,
        fact_set=bundle.fact_set,
        command_evidence_bindings=bundle.command_evidence_bindings,
        report=bundle.report,
        checked_refs=bundle.checked_refs,
        hash_manifest_without_bundle_hash=hash_manifest_without_bundle_hash,
    )
    if _hash_ref_value(manifest.bundle_payload_hash, "hash manifest bundle_payload_hash") != _hash_jsonable(expected_payload):
        raise GitVersionAuditError("hash manifest bundle_payload_hash mismatch")


__all__ = [
    "GitBranchRef",
    "GitChangedFile",
    "GitChangedFileStatus",
    "GitCommandEvidenceBinding",
    "GitDiffSummary",
    "GitDiffSummaryRef",
    "GitDirtyStatus",
    "GitTagRef",
    "GitVersionAuditBundle",
    "GitVersionAuditBundleRef",
    "GitVersionAuditBuilderInput",
    "GitVersionAuditCheckedRef",
    "GitVersionAuditContentHash",
    "GitVersionAuditError",
    "GitVersionAuditFactSet",
    "GitVersionAuditFactSetRef",
    "GitVersionAuditHashManifest",
    "GitVersionAuditManifestRef",
    "GitVersionAuditReport",
    "GitVersionAuditReportRef",
    "GitWorktreeRef",
    "build_git_version_audit_bundle",
    "git_version_audit_readiness",
    "source_inventory_hash",
]
