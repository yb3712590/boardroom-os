from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt, field_validator, model_validator

from boardroom_os.agents.skills import _normalize_ref_fields
from boardroom_os.contracts.hashes import Sha256Hex
from boardroom_os.contracts.package import PackageCommand, PackageContract
from boardroom_os.contracts.types import ContractId, NonEmptyTextValue
from boardroom_os.evidence.service_run import (
    ServiceReadinessUrl,
    ServiceRunEvidence,
    ServiceRunEvidenceRef,
)


class LiveBlackboxIntegrationEvidenceRef(NonEmptyTextValue):
    pass


class LiveBlackboxBlockerCode(StrEnum):
    BACKEND_CRUD_INCOMPLETE = "backend_crud_incomplete"
    SQLITE_NOT_PROVEN_VIA_HTTP = "sqlite_not_proven_via_http"
    FRONTEND_NOT_LIVE = "frontend_not_live"
    COMMAND_EVIDENCE_MISSING = "command_evidence_missing"


class LiveBlackboxBlocker(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: LiveBlackboxBlockerCode
    message: str
    related_ref: str

    @field_validator("message", "related_ref")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text fields must not be empty")
        return normalized


class BackendCrudProbeResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    backend_url: ServiceReadinessUrl
    created_book_id: StrictInt
    create_status: StrictInt
    list_status: StrictInt
    checkout_status: StrictInt
    checkout_state: str
    return_status: StrictInt
    return_state: str
    delete_status: StrictInt
    delete_confirmed: StrictBool
    probed_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: object) -> object:
        return _normalize_ref_fields(
            data,
            {"backend_url": ServiceReadinessUrl},
        )

    @field_validator("created_book_id")
    @classmethod
    def _require_positive_book_id(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("created_book_id must be positive")
        return value

    @field_validator("checkout_state", "return_state")
    @classmethod
    def _reject_empty_state(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("state fields must not be empty")
        return normalized

    @field_validator("probed_at")
    @classmethod
    def _require_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("probed_at must be timezone-aware")
        return value


class SQLitePersistenceProbeResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    db_path: Path
    table_names: tuple[str, ...]
    observed_states: tuple[str, ...]
    deleted_book_absent: StrictBool
    source: str
    probed_at: datetime

    @field_validator("table_names", "observed_states")
    @classmethod
    def _reject_empty_text_tuple(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if not normalized or any(not value for value in normalized):
            raise ValueError("tuple fields must contain non-empty text")
        return normalized

    @field_validator("source")
    @classmethod
    def _reject_empty_source(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("source must not be empty")
        return normalized

    @field_validator("probed_at")
    @classmethod
    def _require_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("probed_at must be timezone-aware")
        return value


class FrontendLiveProbeResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    frontend_url: ServiceReadinessUrl
    backend_url: ServiceReadinessUrl
    fetched_paths: tuple[str, ...]
    fetched_methods: tuple[str, ...]
    used_fake_fetch: StrictBool
    response_body_sha256: Sha256Hex
    probed_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: object) -> object:
        return _normalize_ref_fields(
            data,
            {
                "frontend_url": ServiceReadinessUrl,
                "backend_url": ServiceReadinessUrl,
                "response_body_sha256": Sha256Hex,
            },
        )

    @field_validator("fetched_paths")
    @classmethod
    def _reject_empty_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if not normalized or any(not value or not value.startswith("/") for value in normalized):
            raise ValueError("fetched_paths must contain HTTP paths")
        return normalized

    @field_validator("fetched_methods")
    @classmethod
    def _reject_empty_methods(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip().upper() for value in values)
        if not normalized or any(not value for value in normalized):
            raise ValueError("fetched_methods must contain HTTP methods")
        return normalized

    @model_validator(mode="after")
    def _validate_trace_shape(self) -> Self:
        if len(self.fetched_methods) != len(self.fetched_paths):
            raise ValueError("fetched_methods must align with fetched_paths")
        return self

    @field_validator("probed_at")
    @classmethod
    def _require_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("probed_at must be timezone-aware")
        return value


class LiveBlackboxIntegrationEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    live_blackbox_evidence_id: LiveBlackboxIntegrationEvidenceRef
    package_contract_ref: ContractId
    backend_command_id: ContractId
    frontend_command_id: ContractId
    backend_service_run_ref: ServiceRunEvidenceRef
    frontend_service_run_ref: ServiceRunEvidenceRef
    backend_probe: BackendCrudProbeResult
    sqlite_probe: SQLitePersistenceProbeResult
    frontend_probe: FrontendLiveProbeResult
    generated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: object) -> object:
        return _normalize_ref_fields(
            data,
            {
                "live_blackbox_evidence_id": LiveBlackboxIntegrationEvidenceRef,
                "package_contract_ref": ContractId,
                "backend_command_id": ContractId,
                "frontend_command_id": ContractId,
                "backend_service_run_ref": ServiceRunEvidenceRef,
                "frontend_service_run_ref": ServiceRunEvidenceRef,
            },
        )

    @field_validator("generated_at")
    @classmethod
    def _require_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _validate_distinct_services(self) -> Self:
        if self.backend_service_run_ref == self.frontend_service_run_ref:
            raise ValueError("backend and frontend service run refs must be distinct")
        return self


class LiveBlackboxVerifierInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    evidence: LiveBlackboxIntegrationEvidence
    package_contract: PackageContract
    service_runs: tuple[ServiceRunEvidence, ...]

    @field_validator("package_contract", mode="wrap")
    @classmethod
    def _require_package_contract_instance(cls, value: object, handler: object) -> PackageContract:
        if not isinstance(value, PackageContract):
            raise ValueError("package_contract must be a PackageContract")
        return value


class LiveBlackboxVerificationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence: LiveBlackboxIntegrationEvidence | None = None
    blockers: tuple[LiveBlackboxBlocker, ...] = ()

    @property
    def success(self) -> bool:
        return self.evidence is not None

    @model_validator(mode="after")
    def _validate_result_shape(self) -> Self:
        if self.evidence is not None and self.blockers:
            raise ValueError("successful result must not include blockers")
        if self.evidence is None and not self.blockers:
            raise ValueError("failed result must include blockers")
        return self


class LiveBlackboxIntegrationVerifier:
    def verify(self, verifier_input: LiveBlackboxVerifierInput) -> LiveBlackboxVerificationResult:
        evidence = verifier_input.evidence
        blockers: list[LiveBlackboxBlocker] = []
        blockers.extend(_package_contract_blockers(evidence, verifier_input.package_contract))
        service_binding = _service_run_binding(
            evidence,
            verifier_input.package_contract,
            verifier_input.service_runs,
        )
        blockers.extend(service_binding.blockers)
        if service_binding.backend_service is not None and service_binding.frontend_service is not None:
            blockers.extend(
                _probe_binding_blockers(
                    evidence,
                    backend_service=service_binding.backend_service,
                    frontend_service=service_binding.frontend_service,
                )
            )
        blockers.extend(_backend_crud_blockers(evidence.backend_probe))
        blockers.extend(_sqlite_blockers(evidence.sqlite_probe))
        blockers.extend(_frontend_blockers(evidence.frontend_probe))
        if blockers:
            return LiveBlackboxVerificationResult(blockers=tuple(blockers))
        return LiveBlackboxVerificationResult(evidence=evidence)


def _package_contract_blockers(
    evidence: LiveBlackboxIntegrationEvidence,
    package_contract: PackageContract,
) -> tuple[LiveBlackboxBlocker, ...]:
    blockers: list[LiveBlackboxBlocker] = []
    if evidence.package_contract_ref != package_contract.package_contract_id:
        blockers.append(
            _blocker(
                LiveBlackboxBlockerCode.COMMAND_EVIDENCE_MISSING,
                "live blackbox package_contract_ref must match package contract",
                evidence.package_contract_ref.value,
            )
        )
        return tuple(blockers)

    run_command_ids = {command.command_id.value for command in package_contract.run_commands}
    for command_id, label in (
        (evidence.backend_command_id, "backend"),
        (evidence.frontend_command_id, "frontend"),
    ):
        if command_id.value not in run_command_ids:
            blockers.append(
                _blocker(
                    LiveBlackboxBlockerCode.COMMAND_EVIDENCE_MISSING,
                    f"{label} command must be declared as a package run command",
                    command_id.value,
                )
            )
    return tuple(blockers)


class _ServiceRunBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    backend_service: ServiceRunEvidence | None = None
    frontend_service: ServiceRunEvidence | None = None
    blockers: tuple[LiveBlackboxBlocker, ...]


def _service_run_binding(
    evidence: LiveBlackboxIntegrationEvidence,
    package_contract: PackageContract,
    service_runs: tuple[ServiceRunEvidence, ...],
) -> _ServiceRunBinding:
    blockers: list[LiveBlackboxBlocker] = []
    service_by_ref: dict[str, ServiceRunEvidence] = {}
    for service_run in service_runs:
        service_ref = service_run.service_run_evidence_id.value
        if service_ref in service_by_ref:
            blockers.append(
                _blocker(
                    LiveBlackboxBlockerCode.COMMAND_EVIDENCE_MISSING,
                    "service run refs must be unique",
                    service_ref,
                )
            )
        service_by_ref[service_ref] = service_run

    command_by_id = {
        command.command_id.value: command
        for command in package_contract.run_commands
    }
    bound_services: dict[str, ServiceRunEvidence] = {}
    for service_ref, command_id, label in (
        (evidence.backend_service_run_ref, evidence.backend_command_id, "backend"),
        (evidence.frontend_service_run_ref, evidence.frontend_command_id, "frontend"),
    ):
        service_run = service_by_ref.get(service_ref.value)
        if service_run is None:
            blockers.append(
                _blocker(
                    LiveBlackboxBlockerCode.COMMAND_EVIDENCE_MISSING,
                    f"{label} service run evidence must be present",
                    service_ref.value,
                )
            )
            continue
        bound_services[label] = service_run
        expected_command = command_by_id.get(command_id.value)
        blockers.extend(_bound_service_run_blockers(service_run, expected_command, command_id, label))
    return _ServiceRunBinding(
        backend_service=bound_services.get("backend"),
        frontend_service=bound_services.get("frontend"),
        blockers=tuple(blockers),
    )


def _bound_service_run_blockers(
    service_run: ServiceRunEvidence,
    expected_command: PackageCommand | None,
    command_id: ContractId,
    label: str,
) -> tuple[LiveBlackboxBlocker, ...]:
    blockers: list[LiveBlackboxBlocker] = []
    if service_run.command_id != command_id:
        blockers.append(
            _blocker(
                LiveBlackboxBlockerCode.COMMAND_EVIDENCE_MISSING,
                f"{label} service run command_id must match live blackbox command id",
                service_run.service_run_evidence_id.value,
            )
        )
    if expected_command is None:
        return tuple(blockers)
    if service_run.command != expected_command.command or service_run.cwd != expected_command.cwd:
        blockers.append(
            _blocker(
                LiveBlackboxBlockerCode.COMMAND_EVIDENCE_MISSING,
                f"{label} service run command must match package contract run command",
                service_run.service_run_evidence_id.value,
            )
        )
    if service_run.probe_status_code < 200 or service_run.probe_status_code >= 300:
        blockers.append(
            _blocker(
                LiveBlackboxBlockerCode.COMMAND_EVIDENCE_MISSING,
                f"{label} service run must include successful readiness evidence",
                service_run.service_run_evidence_id.value,
            )
        )
    return tuple(blockers)


def _probe_binding_blockers(
    evidence: LiveBlackboxIntegrationEvidence,
    *,
    backend_service: ServiceRunEvidence,
    frontend_service: ServiceRunEvidence,
) -> tuple[LiveBlackboxBlocker, ...]:
    blockers: list[LiveBlackboxBlocker] = []
    if evidence.frontend_probe.frontend_url != frontend_service.readiness_url:
        blockers.append(
            _blocker(
                LiveBlackboxBlockerCode.FRONTEND_NOT_LIVE,
                "frontend_probe.frontend_url must match frontend service readiness_url",
                evidence.frontend_probe.frontend_url.value,
            )
        )
    if evidence.frontend_probe.backend_url != backend_service.readiness_url:
        blockers.append(
            _blocker(
                LiveBlackboxBlockerCode.FRONTEND_NOT_LIVE,
                "frontend_probe.backend_url must match backend service readiness_url",
                evidence.frontend_probe.backend_url.value,
            )
        )
    if evidence.backend_probe.backend_url != backend_service.readiness_url:
        blockers.append(
            _blocker(
                LiveBlackboxBlockerCode.BACKEND_CRUD_INCOMPLETE,
                "backend_probe.backend_url must match backend service readiness_url",
                evidence.backend_probe.backend_url.value,
            )
        )
    backend_db_path = backend_service.environment_overrides.get("BOOKS_DB_PATH")
    if backend_db_path is None:
        blockers.append(
            _blocker(
                LiveBlackboxBlockerCode.SQLITE_NOT_PROVEN_VIA_HTTP,
                "backend service run must include BOOKS_DB_PATH environment override",
                backend_service.service_run_evidence_id.value,
            )
        )
    elif _normalized_path(evidence.sqlite_probe.db_path) != _normalized_path(Path(backend_db_path)):
        blockers.append(
            _blocker(
                LiveBlackboxBlockerCode.SQLITE_NOT_PROVEN_VIA_HTTP,
                "sqlite_probe.db_path must match backend service BOOKS_DB_PATH",
                str(evidence.sqlite_probe.db_path),
            )
        )
    return tuple(blockers)


def _normalized_path(path: Path) -> str:
    return str(path.expanduser().resolve(strict=False))


def _backend_crud_blockers(probe: BackendCrudProbeResult) -> tuple[LiveBlackboxBlocker, ...]:
    blockers: list[LiveBlackboxBlocker] = []
    if probe.create_status != 201:
        blockers.append(_blocker(LiveBlackboxBlockerCode.BACKEND_CRUD_INCOMPLETE, "create HTTP operation failed", "create"))
    if probe.list_status != 200:
        blockers.append(_blocker(LiveBlackboxBlockerCode.BACKEND_CRUD_INCOMPLETE, "list HTTP operation failed", "list"))
    if probe.checkout_status != 200 or probe.checkout_state != "CHECKED_OUT":
        blockers.append(_blocker(LiveBlackboxBlockerCode.BACKEND_CRUD_INCOMPLETE, "checkout HTTP operation failed", "checkout"))
    if probe.return_status != 200 or probe.return_state != "IN_LIBRARY":
        blockers.append(_blocker(LiveBlackboxBlockerCode.BACKEND_CRUD_INCOMPLETE, "return HTTP operation failed", "return"))
    if probe.delete_status != 200 or probe.delete_confirmed is not True:
        blockers.append(_blocker(LiveBlackboxBlockerCode.BACKEND_CRUD_INCOMPLETE, "delete HTTP operation failed", "delete"))
    return tuple(blockers)


def _sqlite_blockers(probe: SQLitePersistenceProbeResult) -> tuple[LiveBlackboxBlocker, ...]:
    blockers: list[LiveBlackboxBlocker] = []
    if probe.source != "http_workflow":
        blockers.append(
            _blocker(
                LiveBlackboxBlockerCode.SQLITE_NOT_PROVEN_VIA_HTTP,
                "SQLite persistence must be proven through HTTP workflow",
                probe.source,
            )
        )
    if "books" not in probe.table_names:
        blockers.append(_blocker(LiveBlackboxBlockerCode.SQLITE_NOT_PROVEN_VIA_HTTP, "SQLite books table missing", "books"))
    if not {"CHECKED_OUT", "IN_LIBRARY"}.issubset(set(probe.observed_states)):
        blockers.append(_blocker(LiveBlackboxBlockerCode.SQLITE_NOT_PROVEN_VIA_HTTP, "SQLite HTTP workflow states missing", "states"))
    if probe.deleted_book_absent is not True:
        blockers.append(_blocker(LiveBlackboxBlockerCode.SQLITE_NOT_PROVEN_VIA_HTTP, "deleted book remained in SQLite", "delete"))
    return tuple(blockers)


def _frontend_blockers(probe: FrontendLiveProbeResult) -> tuple[LiveBlackboxBlocker, ...]:
    blockers: list[LiveBlackboxBlocker] = []
    if probe.used_fake_fetch:
        blockers.append(_blocker(LiveBlackboxBlockerCode.FRONTEND_NOT_LIVE, "fakeFetch cannot satisfy live frontend/backend integration", "fakeFetch"))
    required_paths = {"/health", "/books"}
    if not required_paths.issubset(set(probe.fetched_paths)):
        blockers.append(_blocker(LiveBlackboxBlockerCode.FRONTEND_NOT_LIVE, "frontend live probe did not fetch backend health and books", "frontend"))
    if not any(
        method == "DELETE" and path.startswith("/books/")
        for method, path in zip(probe.fetched_methods, probe.fetched_paths, strict=True)
    ):
        blockers.append(_blocker(LiveBlackboxBlockerCode.FRONTEND_NOT_LIVE, "frontend live probe must execute DELETE /books/{id}", "frontend-delete"))
    return tuple(blockers)


def _blocker(
    code: LiveBlackboxBlockerCode,
    message: str,
    related_ref: str,
) -> LiveBlackboxBlocker:
    return LiveBlackboxBlocker(code=code, message=message, related_ref=related_ref)


def artifact_refs_for_live_blackbox(
    evidence: LiveBlackboxIntegrationEvidence,
) -> tuple[str, ...]:
    evidence_id = evidence.live_blackbox_evidence_id.value
    return (
        f"{evidence_id}.backend-crud",
        f"{evidence_id}.sqlite-http",
        f"{evidence_id}.frontend-live",
    )


__all__ = [
    "BackendCrudProbeResult",
    "FrontendLiveProbeResult",
    "LiveBlackboxBlocker",
    "LiveBlackboxBlockerCode",
    "LiveBlackboxIntegrationEvidence",
    "LiveBlackboxIntegrationEvidenceRef",
    "LiveBlackboxIntegrationVerifier",
    "LiveBlackboxVerificationResult",
    "LiveBlackboxVerifierInput",
    "SQLitePersistenceProbeResult",
    "artifact_refs_for_live_blackbox",
]
