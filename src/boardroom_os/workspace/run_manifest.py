from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator, model_validator

from boardroom_os.contracts.package import PackageCommand, PackageContract, PackageProjectType
from boardroom_os.contracts.types import AcceptanceRef, ContractId, NonEmptyTextValue
from boardroom_os.workspace.manifest import WorkspaceManifest, WorkspaceManifestRef, WorkspacePath
from boardroom_os.workspace.run_manifest_ingestion import (
    RunManifestIngestionContext,
    RunManifestRawAssertion,
    RunManifestSkeletonSummary,
    ingest_run_manifest_artifact,
)


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


class RunManifestEnvironmentValueSource(StrEnum):
    RUNTIME_HOST = "runtime_host"
    RUNTIME_PORT = "runtime_port"
    TEMP_SQLITE_PATH = "temp_sqlite_path"
    LITERAL = "literal"


class RunManifestEnvironmentBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    value_source: RunManifestEnvironmentValueSource
    literal_value: str | None = None

    @field_validator("name")
    @classmethod
    def _validate_environment_name(cls, value: str) -> str:
        normalized = value.strip()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", normalized):
            raise ValueError("environment name must be uppercase")
        return normalized

    @field_validator("literal_value")
    @classmethod
    def _reject_empty_literal_value(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("literal_value must not be empty")
        return normalized

    @field_serializer("value_source")
    def _serialize_value_source(self, value: RunManifestEnvironmentValueSource) -> str:
        return value.value

    @model_validator(mode="after")
    def _validate_literal_value_source(self) -> Self:
        if self.value_source is RunManifestEnvironmentValueSource.LITERAL:
            if self.literal_value is None:
                raise ValueError("literal source requires literal_value")
            return self
        if self.literal_value is not None:
            raise ValueError("literal_value is only allowed for literal source")
        return self


class RunManifestReadinessProbe(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    method: Literal["GET"]
    path: str
    expect_status: int

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.startswith("/"):
            raise ValueError("readiness probe path must start with /")
        return normalized

    @field_validator("expect_status")
    @classmethod
    def _validate_status(cls, value: int) -> int:
        if not 100 <= value <= 599:
            raise ValueError("expect_status must be a valid HTTP status")
        return value


class RunManifestServiceContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command_id: ContractId
    role: str
    env_bindings: tuple[RunManifestEnvironmentBinding, ...]
    readiness_probe: RunManifestReadinessProbe

    @field_validator("role")
    @classmethod
    def _reject_empty_role(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("role must not be empty")
        return normalized

    @model_validator(mode="after")
    def _validate_unique_environment_names(self) -> Self:
        names = [binding.name for binding in self.env_bindings]
        if len(names) != len(set(names)):
            raise ValueError("service contract environment names must be unique")
        return self


class RunManifestFrontendMode(StrEnum):
    SERVED_BY_BACKEND = "served-by-backend"
    STATIC_SERVER = "static-server"
    PROXY_REQUIRED = "proxy-required"
    CONFIGURABLE_API_BASE = "configurable-api-base"


class RunManifestFrontendTopology(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: RunManifestFrontendMode
    service_command_id: ContractId | None = None
    api_base_binding: str | None = None

    @field_serializer("mode")
    def _serialize_mode(self, value: RunManifestFrontendMode) -> str:
        return value.value

    @field_validator("api_base_binding")
    @classmethod
    def _reject_empty_api_base_binding(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("api_base_binding must not be empty")
        return normalized

    @model_validator(mode="after")
    def _validate_topology_bindings(self) -> Self:
        if self.mode in {RunManifestFrontendMode.STATIC_SERVER, RunManifestFrontendMode.PROXY_REQUIRED}:
            if self.service_command_id is None:
                raise ValueError("service_command_id is required for frontend service modes")
        if self.mode is RunManifestFrontendMode.CONFIGURABLE_API_BASE and self.api_base_binding is None:
            raise ValueError("api_base_binding is required for configurable-api-base")
        return self


class RunManifestBehaviorAssertionKind(StrEnum):
    JSON_EQUALS = "json_equals"
    JSON_CONTAINS = "json_contains"
    JSON_NOT_CONTAINS = "json_not_contains"
    FIELD_EQUALS = "field_equals"
    FIELD_PRESENT = "field_present"
    FIELD_ABSENT = "field_absent"
    EMPTY_BODY = "empty_body"
    BODY_CONTAINS = "body_contains"
    BODY_CONTAINS_ANY = "body_contains_any"
    JSON_TYPE = "json_type"


class RunManifestBehaviorAssertion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: RunManifestBehaviorAssertionKind
    target: str
    expected: Any = None

    @field_validator("target")
    @classmethod
    def _reject_empty_target(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("behavior assertion target must not be empty")
        return normalized

    @field_serializer("kind")
    def _serialize_kind(self, value: RunManifestBehaviorAssertionKind) -> str:
        return value.value


class RunManifestBehaviorStep(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    step_id: str
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str
    json_body: Any = None
    expect_status: int
    capture: dict[str, str] = {}
    assertions: tuple[RunManifestBehaviorAssertion, ...] = ()

    @field_validator("step_id")
    @classmethod
    def _reject_empty_step_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("step_id must not be empty")
        return normalized

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.startswith("/"):
            raise ValueError("behavior step path must start with /")
        return normalized

    @field_validator("expect_status")
    @classmethod
    def _validate_status(cls, value: int) -> int:
        if not 100 <= value <= 599:
            raise ValueError("expect_status must be a valid HTTP status")
        return value

    @field_validator("capture")
    @classmethod
    def _validate_capture(cls, values: dict[str, str]) -> dict[str, str]:
        for key, value in values.items():
            if not key.strip() or not value.strip():
                raise ValueError("capture keys and values must not be empty")
        return dict(values)

    @model_validator(mode="after")
    def _validate_field_absent_shape(self) -> Self:
        for assertion in self.assertions:
            if assertion.kind in {
                RunManifestBehaviorAssertionKind.FIELD_ABSENT,
                RunManifestBehaviorAssertionKind.FIELD_PRESENT,
                RunManifestBehaviorAssertionKind.EMPTY_BODY,
            } and assertion.expected is not None:
                raise ValueError(f"{assertion.kind.value} assertion must not include expected")
        return self


class RunManifestBehaviorProbe(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    probe_id: ContractId
    service_command_id: ContractId
    acceptance_refs: tuple[AcceptanceRef, ...]
    steps: tuple[RunManifestBehaviorStep, ...]

    @field_serializer("acceptance_refs")
    def _serialize_acceptance_refs(self, values: tuple[AcceptanceRef, ...]) -> list[dict[str, str]]:
        return [value.model_dump() for value in values]

    @field_validator("acceptance_refs")
    @classmethod
    def _reject_empty_acceptance_refs(
        cls,
        values: tuple[AcceptanceRef, ...],
    ) -> tuple[AcceptanceRef, ...]:
        if not values:
            raise ValueError("acceptance_refs must not be empty")
        if len({value.value for value in values}) != len(values):
            raise ValueError("acceptance_refs must be unique")
        return values

    @field_validator("steps")
    @classmethod
    def _reject_empty_steps(
        cls,
        values: tuple[RunManifestBehaviorStep, ...],
    ) -> tuple[RunManifestBehaviorStep, ...]:
        if not values:
            raise ValueError("behavioral probe requires steps")
        return values

    @model_validator(mode="after")
    def _validate_unique_step_ids(self) -> Self:
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("behavioral probe step ids must be unique")
        return self


class RunManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_manifest_id: RunManifestRef
    workspace_manifest_ref: WorkspaceManifestRef
    package_contract_ref: ContractId
    package_root: WorkspacePath
    commands: tuple[RunManifestCommand, ...]
    service_contracts: tuple[RunManifestServiceContract, ...] | None = None
    frontend_topology: RunManifestFrontendTopology | None = None
    behavioral_probes: tuple[RunManifestBehaviorProbe, ...] | None = None

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
    def _validate_run_manifest(self) -> Self:
        command_ids = [command.command_id.value for command in self.commands]
        if len(command_ids) != len(set(command_ids)):
            raise ValueError("run manifest command ids must be unique")
        self._validate_service_contracts(command_ids)
        self._validate_frontend_topology()
        self._validate_behavioral_probes()
        return self

    def _validate_service_contracts(self, command_ids: list[str]) -> None:
        if self.service_contracts == () and any(command.kind is RunManifestCommandKind.RUN for command in self.commands):
            raise ValueError("run manifest with run commands requires service contracts")
        if self.service_contracts is None:
            return
        service_command_ids = [service.command_id.value for service in self.service_contracts]
        if len(service_command_ids) != len(set(service_command_ids)):
            raise ValueError("duplicate service contract command_id")
        run_command_ids = _run_command_ids(self.commands)
        for service_contract in self.service_contracts:
            if service_contract.command_id.value not in command_ids:
                raise ValueError("service contract command_id must exist in run manifest")
            if service_contract.command_id.value not in run_command_ids:
                raise ValueError("service contract command_id must reference RUN command")

    def _validate_frontend_topology(self) -> None:
        if self.frontend_topology is None:
            return
        if (
            self.frontend_topology.service_command_id is not None
            and self.frontend_topology.service_command_id.value not in _run_command_ids(self.commands)
        ):
            raise ValueError("frontend topology service_command_id must reference RUN command")

    def _validate_behavioral_probes(self) -> None:
        if self.behavioral_probes == () and self.service_contracts:
            raise ValueError("run manifest with service contracts requires behavioral probes")
        if self.behavioral_probes is None:
            return
        probe_ids = [probe.probe_id.value for probe in self.behavioral_probes]
        if len(probe_ids) != len(set(probe_ids)):
            raise ValueError("duplicate behavioral probe id")
        service_command_ids = {
            service_contract.command_id.value
            for service_contract in self.service_contracts or ()
        }
        for probe in self.behavioral_probes:
            if probe.service_command_id.value not in service_command_ids:
                raise ValueError("behavioral probe service_command_id must exist in service contracts")


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
    service_contracts: tuple[RunManifestServiceContract, ...] | None = None,
    frontend_topology: RunManifestFrontendTopology | None = None,
    behavioral_probes: tuple[RunManifestBehaviorProbe, ...] | None = None,
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
        service_contracts=service_contracts,
        frontend_topology=frontend_topology,
        behavioral_probes=behavioral_probes,
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


def _run_command_ids(commands: tuple[RunManifestCommand, ...]) -> set[str]:
    return {
        command.command_id.value
        for command in commands
        if command.kind is RunManifestCommandKind.RUN
    }


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
    "RunManifestBehaviorAssertion",
    "RunManifestBehaviorAssertionKind",
    "RunManifestBehaviorProbe",
    "RunManifestBehaviorStep",
    "RunManifestBinding",
    "RunManifestCommand",
    "RunManifestCommandKind",
    "RunManifestEnvironmentBinding",
    "RunManifestEnvironmentValueSource",
    "RunManifestError",
    "RunManifestFrontendMode",
    "RunManifestFrontendTopology",
    "RunManifestIngestionContext",
    "RunManifestReadinessProbe",
    "RunManifestRef",
    "RunManifestRawAssertion",
    "RunManifestServiceContract",
    "RunManifestSkeletonSummary",
    "build_run_manifest",
    "ingest_run_manifest_artifact",
    "validate_run_manifest_binding",
]
