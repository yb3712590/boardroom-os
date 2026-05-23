from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator, model_validator

from boardroom_os.contracts.package import PackageCommand, PackageContract, PackageProjectType
from boardroom_os.contracts.types import ContractId, NonEmptyTextValue
from boardroom_os.workspace.manifest import WorkspaceManifest, WorkspaceManifestRef, WorkspacePath


class RunManifestError(ValueError):
    pass


class RunManifestRef(NonEmptyTextValue):
    pass


class RunManifestCommandKind(StrEnum):
    RUN = "run"
    TEST = "test"


class RunManifestCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command_id: ContractId
    kind: RunManifestCommandKind
    label: str
    command: tuple[str, ...]
    cwd: str

    @field_validator("label", "cwd")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text fields must not be empty")
        return normalized

    @field_validator("command")
    @classmethod
    def _reject_empty_command(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if not normalized:
            raise ValueError("command must not be empty")
        if any(not value for value in normalized):
            raise ValueError("command must not contain empty items")
        return normalized

    @field_serializer("kind")
    def _serialize_kind(self, value: RunManifestCommandKind) -> str:
        return value.value

    @classmethod
    def from_package_command(cls, *, package_command: PackageCommand, kind: RunManifestCommandKind) -> Self:
        return cls(
            command_id=package_command.command_id,
            kind=kind,
            label=package_command.label,
            command=package_command.command,
            cwd=package_command.cwd,
        )


class RunManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_manifest_id: RunManifestRef
    workspace_manifest_ref: WorkspaceManifestRef
    package_contract_ref: ContractId
    package_root: WorkspacePath
    commands: tuple[RunManifestCommand, ...]

    @field_serializer("run_manifest_id", "workspace_manifest_ref", "package_contract_ref", "package_root")
    def _serialize_refs(
        self,
        value: RunManifestRef | WorkspaceManifestRef | ContractId | WorkspacePath,
    ) -> dict[str, str]:
        return value.model_dump()

    @field_serializer("commands")
    def _serialize_commands(self, values: tuple[RunManifestCommand, ...]) -> list[dict[str, object]]:
        return [value.model_dump() for value in values]

    @model_validator(mode="after")
    def _validate_unique_command_ids(self) -> Self:
        command_ids = [command.command_id.value for command in self.commands]
        if len(command_ids) != len(set(command_ids)):
            raise ValueError("run manifest command ids must be unique")
        return self


class RunManifestBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_manifest_ref: RunManifestRef
    package_contract_ref: ContractId
    command_id: ContractId
    kind: RunManifestCommandKind
    command: tuple[str, ...]
    cwd: str


def build_run_manifest(
    *,
    workspace_manifest: WorkspaceManifest,
    package_contract: PackageContract,
) -> RunManifest:
    _validate_workspace_contract_binding(
        workspace_manifest=workspace_manifest,
        package_contract=package_contract,
    )
    _validate_runnable_package_commands(package_contract)

    commands = _expected_manifest_commands(package_contract)

    return RunManifest(
        run_manifest_id=RunManifestRef(
            value=(
                "run-manifest."
                f"{workspace_manifest.workspace_manifest_id.value}."
                f"{package_contract.package_contract_id.value}"
            )
        ),
        workspace_manifest_ref=workspace_manifest.workspace_manifest_id,
        package_contract_ref=package_contract.package_contract_id,
        package_root=workspace_manifest.package_root,
        commands=commands,
    )


def validate_run_manifest_binding(
    *,
    run_manifest: RunManifest,
    package_contract: PackageContract,
    command_id: ContractId,
) -> RunManifestBinding:
    if run_manifest.package_contract_ref != package_contract.package_contract_id:
        raise RunManifestError("run manifest package_contract_ref must match package contract")
    expected_run_manifest_id = (
        "run-manifest."
        f"{run_manifest.workspace_manifest_ref.value}."
        f"{package_contract.package_contract_id.value}"
    )
    if run_manifest.run_manifest_id.value != expected_run_manifest_id:
        raise RunManifestError("run manifest id must match workspace manifest and package contract")
    if run_manifest.package_root.value != package_contract.package_root:
        raise RunManifestError("run manifest package root must match package contract")
    if run_manifest.package_root.value != "10-project" or package_contract.package_root != "10-project":
        raise RunManifestError("run manifest package root must be 10-project")
    if run_manifest.commands != _expected_manifest_commands(package_contract):
        raise RunManifestError("run manifest commands must match package contract commands")

    manifest_command = _single_manifest_command(run_manifest=run_manifest, command_id=command_id)
    contract_command, expected_kind = _single_contract_command(package_contract=package_contract, command_id=command_id)
    expected_manifest_command = RunManifestCommand.from_package_command(
        package_command=contract_command,
        kind=expected_kind,
    )
    if manifest_command != expected_manifest_command:
        raise RunManifestError("run manifest command must match package contract command")

    return RunManifestBinding(
        run_manifest_ref=run_manifest.run_manifest_id,
        package_contract_ref=package_contract.package_contract_id,
        command_id=manifest_command.command_id,
        kind=manifest_command.kind,
        command=manifest_command.command,
        cwd=manifest_command.cwd,
    )


def _expected_manifest_commands(package_contract: PackageContract) -> tuple[RunManifestCommand, ...]:
    return tuple(
        sorted(
            (
                *(
                    RunManifestCommand.from_package_command(
                        package_command=command,
                        kind=RunManifestCommandKind.RUN,
                    )
                    for command in package_contract.run_commands
                ),
                *(
                    RunManifestCommand.from_package_command(
                        package_command=command,
                        kind=RunManifestCommandKind.TEST,
                    )
                    for command in package_contract.test_commands
                ),
            ),
            key=lambda command: (command.kind.value, command.command_id.value),
        )
    )


def _validate_workspace_contract_binding(*, workspace_manifest: WorkspaceManifest, package_contract: PackageContract) -> None:
    if workspace_manifest.package_contract_ref != package_contract.package_contract_id:
        raise RunManifestError("workspace manifest package_contract_ref must match package contract")
    if workspace_manifest.package_root.value != package_contract.package_root:
        raise RunManifestError("workspace manifest package root must match package contract")
    if package_contract.package_root != "10-project":
        raise RunManifestError("package root must be 10-project")


def _validate_runnable_package_commands(package_contract: PackageContract) -> None:
    if package_contract.project_type not in {PackageProjectType.SOFTWARE, PackageProjectType.MIXED}:
        return
    if not package_contract.run_commands:
        raise RunManifestError("software and mixed packages require run commands")
    if not package_contract.test_commands:
        raise RunManifestError("software and mixed packages require test commands")


def _single_manifest_command(*, run_manifest: RunManifest, command_id: ContractId) -> RunManifestCommand:
    matches = tuple(command for command in run_manifest.commands if command.command_id == command_id)
    if len(matches) != 1:
        raise RunManifestError("command is not declared in run manifest")
    return matches[0]


def _single_contract_command(*, package_contract: PackageContract, command_id: ContractId) -> tuple[PackageCommand, RunManifestCommandKind]:
    matches: list[tuple[PackageCommand, RunManifestCommandKind]] = []
    matches.extend((command, RunManifestCommandKind.RUN) for command in package_contract.run_commands if command.command_id == command_id)
    matches.extend((command, RunManifestCommandKind.TEST) for command in package_contract.test_commands if command.command_id == command_id)
    if len(matches) != 1:
        raise RunManifestError("expected exactly one command in package contract")
    return matches[0]


__all__ = [
    "RunManifest",
    "RunManifestBinding",
    "RunManifestCommand",
    "RunManifestCommandKind",
    "RunManifestError",
    "RunManifestRef",
    "build_run_manifest",
    "validate_run_manifest_binding",
]
