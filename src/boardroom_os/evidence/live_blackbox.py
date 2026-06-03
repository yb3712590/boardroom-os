from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt, field_validator, model_validator

from boardroom_os.agents.skills import _normalize_ref_fields
from boardroom_os.contracts.hashes import Sha256Hex
from boardroom_os.contracts.package import PackageCommand, PackageContract
from boardroom_os.contracts.types import AcceptanceRef, ContractId, NonEmptyTextValue
from boardroom_os.evidence.service_run import (
    ServiceReadinessUrl,
    ServiceRunEvidence,
    ServiceRunEvidenceRef,
)


class LiveBlackboxIntegrationEvidenceRef(NonEmptyTextValue):
    pass


class LiveBlackboxBlockerCode(StrEnum):
    PROBE_FAILED = "probe_failed"
    PROBE_EVIDENCE_MISSING = "probe_evidence_missing"
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


class LiveBlackboxProbeResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    probe_ref: NonEmptyTextValue
    acceptance_refs: tuple[AcceptanceRef, ...]
    service_run_refs: tuple[ServiceRunEvidenceRef, ...]
    command_ids: tuple[ContractId, ...]
    probe_url: ServiceReadinessUrl | None = None
    status_code: StrictInt | None = None
    passed: StrictBool
    observed_facts: dict[str, Any]
    body_sha256: Sha256Hex | None = None
    probed_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: object) -> object:
        return _normalize_ref_fields(
            data,
            {
                "probe_ref": NonEmptyTextValue,
                "probe_url": ServiceReadinessUrl,
                "body_sha256": Sha256Hex,
            },
            {
                "acceptance_refs": AcceptanceRef,
                "service_run_refs": ServiceRunEvidenceRef,
                "command_ids": ContractId,
            },
        )

    @field_validator("acceptance_refs", "service_run_refs", "command_ids")
    @classmethod
    def _reject_empty_ref_tuple(cls, values: tuple[object, ...]) -> tuple[object, ...]:
        if not values:
            raise ValueError("probe ref tuples must not be empty")
        return values

    @field_validator("status_code")
    @classmethod
    def _require_positive_status_code(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value <= 0:
            raise ValueError("status_code must be positive")
        return value

    @field_validator("observed_facts")
    @classmethod
    def _reject_empty_observed_facts(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not value:
            raise ValueError("observed_facts must not be empty")
        for key in value:
            if not isinstance(key, str) or not key.strip():
                raise ValueError("observed_facts keys must be non-empty strings")
        return dict(value)

    @model_validator(mode="after")
    def _validate_probe_shape(self) -> Self:
        if len({ref.value for ref in self.acceptance_refs}) != len(self.acceptance_refs):
            raise ValueError("acceptance_refs must be unique")
        if len({ref.value for ref in self.service_run_refs}) != len(self.service_run_refs):
            raise ValueError("service_run_refs must be unique")
        if len({command_id.value for command_id in self.command_ids}) != len(self.command_ids):
            raise ValueError("command_ids must be unique")
        if self.status_code is not None and self.passed and not (200 <= self.status_code < 300):
            raise ValueError("passed HTTP probe status_code must be 2xx")
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
    probes: tuple[LiveBlackboxProbeResult, ...]
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
        if not self.probes:
            raise ValueError("live blackbox probes are required")
        probe_refs = tuple(probe.probe_ref.value for probe in self.probes)
        if len(set(probe_refs)) != len(probe_refs):
            raise ValueError("live blackbox probe refs must be unique")
        required_service_refs = {
            self.backend_service_run_ref.value,
            self.frontend_service_run_ref.value,
        }
        linked_service_refs = {
            service_ref.value
            for probe in self.probes
            for service_ref in probe.service_run_refs
        }
        if not required_service_refs.issubset(linked_service_refs):
            raise ValueError("live blackbox probes must bind backend and frontend services")
        required_command_ids = {
            self.backend_command_id.value,
            self.frontend_command_id.value,
        }
        linked_command_ids = {
            command_id.value
            for probe in self.probes
            for command_id in probe.command_ids
        }
        if not required_command_ids.issubset(linked_command_ids):
            raise ValueError("live blackbox probes must bind backend and frontend commands")
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
        blockers.extend(_probe_blockers(evidence))
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
    service_urls = {
        backend_service.service_run_evidence_id.value: backend_service.readiness_url.value,
        frontend_service.service_run_evidence_id.value: frontend_service.readiness_url.value,
    }
    for probe in evidence.probes:
        if probe.probe_url is None:
            continue
        bound_origins = {
            _url_origin(service_urls[service_ref.value])
            for service_ref in probe.service_run_refs
            if service_ref.value in service_urls
        }
        if _url_origin(probe.probe_url.value) in bound_origins:
            continue
        blockers.append(
            _blocker(
                LiveBlackboxBlockerCode.PROBE_EVIDENCE_MISSING,
                "live blackbox probe_url must match a bound service origin",
                probe.probe_ref.value,
            )
        )
    return tuple(blockers)


def _url_origin(value: str) -> str:
    parsed = urlparse(value)
    return f"{parsed.scheme}://{parsed.netloc}"


def _probe_blockers(evidence: LiveBlackboxIntegrationEvidence) -> tuple[LiveBlackboxBlocker, ...]:
    blockers: list[LiveBlackboxBlocker] = []
    expected_service_refs = {
        evidence.backend_service_run_ref.value,
        evidence.frontend_service_run_ref.value,
    }
    expected_command_ids = {
        evidence.backend_command_id.value,
        evidence.frontend_command_id.value,
    }
    for probe in evidence.probes:
        if not probe.passed:
            blockers.append(
                _blocker(
                    LiveBlackboxBlockerCode.PROBE_FAILED,
                    "live blackbox probe did not pass",
                    probe.probe_ref.value,
                )
            )
        probe_service_refs = {ref.value for ref in probe.service_run_refs}
        if not probe_service_refs.issubset(expected_service_refs):
            blockers.append(
                _blocker(
                    LiveBlackboxBlockerCode.PROBE_EVIDENCE_MISSING,
                    "live blackbox probe references unknown service_run_refs",
                    probe.probe_ref.value,
                )
            )
        probe_command_ids = {command_id.value for command_id in probe.command_ids}
        if not probe_command_ids.issubset(expected_command_ids):
            blockers.append(
                _blocker(
                    LiveBlackboxBlockerCode.PROBE_EVIDENCE_MISSING,
                    "live blackbox probe references unknown command_ids",
                    probe.probe_ref.value,
                )
            )
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
    return tuple(
        f"{evidence_id}.{probe.probe_ref.value}"
        for probe in sorted(evidence.probes, key=lambda item: item.probe_ref.value)
    )


__all__ = [
    "LiveBlackboxBlocker",
    "LiveBlackboxBlockerCode",
    "LiveBlackboxIntegrationEvidence",
    "LiveBlackboxIntegrationEvidenceRef",
    "LiveBlackboxIntegrationVerifier",
    "LiveBlackboxProbeResult",
    "LiveBlackboxVerificationResult",
    "LiveBlackboxVerifierInput",
    "artifact_refs_for_live_blackbox",
]
