from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from enum import Enum
from urllib.parse import unquote


WORKSPACE_MANAGED_PATH_PREFIXES: tuple[str, ...] = (
    "10-project/",
    "20-evidence/",
    "00-boardroom/",
)


class ArtifactRefKind(str, Enum):
    WORKSPACE_SOURCE = "WORKSPACE_SOURCE"
    TEST_EVIDENCE = "TEST_EVIDENCE"
    GIT_EVIDENCE = "GIT_EVIDENCE"
    DELIVERY_REPORT = "DELIVERY_REPORT"
    DELIVERY_CHECK_REPORT = "DELIVERY_CHECK_REPORT"
    VERIFICATION_EVIDENCE = "VERIFICATION_EVIDENCE"
    CLOSEOUT_PACKAGE = "CLOSEOUT_PACKAGE"
    GOVERNANCE_DOCUMENT = "GOVERNANCE_DOCUMENT"
    UPLOAD_IMPORT = "UPLOAD_IMPORT"
    ARCHIVE = "ARCHIVE"
    UNKNOWN = "UNKNOWN"


class CloseoutFinalRefStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    UNKNOWN_REF = "UNKNOWN_REF"
    ILLEGAL_KIND = "ILLEGAL_KIND"
    SUPERSEDED = "SUPERSEDED"
    PLACEHOLDER = "PLACEHOLDER"


@dataclass(frozen=True)
class ArtifactRefContract:
    artifact_ref: str
    kind: ArtifactRefKind
    ticket_id: str | None
    logical_path: str | None
    is_final_closeout_evidence: bool


@dataclass(frozen=True)
class CloseoutFinalRefCheck:
    artifact_ref: str
    status: CloseoutFinalRefStatus
    kind: ArtifactRefKind
    reason: str | None = None


@dataclass(frozen=True)
class WorkspacePathTemplates:
    source: str = "10-project/src/*"
    docs: str = "10-project/docs/*"
    tests: str = "20-evidence/tests/*"
    git: str = "20-evidence/git/*"
    governance: str = "reports/governance/{ticket_id}/*"
    check: str = "reports/check/{ticket_id}/*"
    closeout: str = "20-evidence/closeout/{ticket_id}/*"

    def source_delivery_write_set(self) -> list[str]:
        return [self.source, self.docs, self.tests, self.git]

    def governance_write_set(self, ticket_id: str) -> list[str]:
        return [self.governance.format(ticket_id=ticket_id)]

    def check_write_set(self, ticket_id: str) -> list[str]:
        return [self.check.format(ticket_id=ticket_id)]

    def closeout_write_set(self, ticket_id: str) -> list[str]:
        return [self.closeout.format(ticket_id=ticket_id)]

    def model_dump(self) -> dict[str, str]:
        return {
            "source": self.source,
            "docs": self.docs,
            "tests": self.tests,
            "git": self.git,
            "governance": self.governance,
            "check": self.check,
            "closeout": self.closeout,
        }


DEFAULT_WORKSPACE_PATH_TEMPLATES = WorkspacePathTemplates()

_FINAL_CLOSEOUT_KINDS = {
    ArtifactRefKind.WORKSPACE_SOURCE,
    ArtifactRefKind.TEST_EVIDENCE,
    ArtifactRefKind.GIT_EVIDENCE,
    ArtifactRefKind.DELIVERY_REPORT,
    ArtifactRefKind.DELIVERY_CHECK_REPORT,
    ArtifactRefKind.VERIFICATION_EVIDENCE,
    ArtifactRefKind.CLOSEOUT_PACKAGE,
}

CAPABILITY_WRITE_SURFACES: dict[str, tuple[str, ...]] = {
    "source.modify.backend": ("10-project/src/backend/**",),
    "source.modify.application": ("10-project/src/app/**",),
    "source.modify.database": (
        "10-project/src/**/migrations/**",
        "10-project/src/**/schema/**",
        "10-project/src/**/seeds/**",
    ),
    "source.modify.platform": ("10-project/src/platform/**", "10-project/scripts/**"),
    "test.run.backend": ("20-evidence/tests/{ticket_id}/**",),
    "test.run.application": ("20-evidence/tests/{ticket_id}/**",),
    "evidence.write.test": ("20-evidence/tests/{ticket_id}/**",),
    "evidence.write.git": ("20-evidence/git/{ticket_id}/**",),
    "evidence.check.delivery": (
        "20-evidence/delivery/{ticket_id}/**",
        "20-evidence/reviews/{ticket_id}/**",
    ),
    "verdict.write.maker_checker": ("20-evidence/reviews/{ticket_id}/**",),
    "docs.update.delivery": ("10-project/docs/**",),
    "runtime.state.write": (".runtime/**",),
    "closeout.write": ("50-closeout/{ticket_id}/**", "20-evidence/closeout/{ticket_id}/**"),
    "archive.write": ("90-archive/**",),
}


def normalize_workspace_contract_path(path: str) -> str:
    normalized = str(path or "").replace("\\", "/").strip("/")
    if not normalized:
        raise ValueError("Workspace contract path cannot be empty.")
    segments = normalized.split("/")
    if any(
        not segment or segment in {".", ".."} or ":" in segment
        for segment in segments
    ):
        raise ValueError("Workspace contract path contains an unsafe segment.")
    return "/".join(segments)


def _safe_normalized_path(path: str | None) -> str | None:
    if not str(path or "").strip():
        return None
    try:
        return normalize_workspace_contract_path(str(path))
    except ValueError:
        return None


def _contract(
    kind: ArtifactRefKind,
    artifact_ref: str,
    ticket_id: str | None,
    logical_path: str | None,
) -> ArtifactRefContract:
    return ArtifactRefContract(
        artifact_ref=artifact_ref,
        kind=kind,
        ticket_id=ticket_id,
        logical_path=_safe_normalized_path(logical_path),
        is_final_closeout_evidence=kind in _FINAL_CLOSEOUT_KINDS,
    )


def _strip_runtime_index_prefix(path: str) -> str:
    head, separator, tail = path.partition("-")
    if separator and head.isdigit() and tail:
        return tail
    return path


def _decode_workspace_tail(encoded_path: str) -> str:
    return normalize_workspace_contract_path(_strip_runtime_index_prefix(unquote(encoded_path)))


def _source_logical_path(decoded_path: str) -> str:
    if decoded_path.startswith("10-project/"):
        return decoded_path
    return normalize_workspace_contract_path(f"10-project/{decoded_path}")


def _tests_logical_path(ticket_id: str, decoded_path: str) -> str:
    if decoded_path.startswith("20-evidence/tests/"):
        return decoded_path
    return normalize_workspace_contract_path(f"20-evidence/tests/{ticket_id}/{decoded_path}")


def _git_logical_path(ticket_id: str, decoded_path: str) -> str:
    if decoded_path.startswith("20-evidence/git/"):
        return decoded_path
    return normalize_workspace_contract_path(f"20-evidence/git/{ticket_id}/{decoded_path}")


def _kind_from_logical_path(path: str) -> ArtifactRefKind:
    if path.startswith("10-project/src/"):
        return ArtifactRefKind.WORKSPACE_SOURCE
    if path.startswith("20-evidence/tests/"):
        return ArtifactRefKind.TEST_EVIDENCE
    if path.startswith("20-evidence/git/"):
        return ArtifactRefKind.GIT_EVIDENCE
    if path.startswith("20-evidence/delivery/"):
        return ArtifactRefKind.DELIVERY_REPORT
    if path.startswith("20-evidence/reviews/"):
        return ArtifactRefKind.DELIVERY_CHECK_REPORT
    if path.startswith("50-closeout/") or path.startswith("20-evidence/closeout/"):
        return ArtifactRefKind.CLOSEOUT_PACKAGE
    if path.startswith("00-boardroom/") or path.startswith("reports/governance/") or path.startswith("10-project/docs/"):
        return ArtifactRefKind.GOVERNANCE_DOCUMENT
    if path.startswith("10-project/"):
        return ArtifactRefKind.GOVERNANCE_DOCUMENT
    if path.startswith("90-archive/"):
        return ArtifactRefKind.ARCHIVE
    return ArtifactRefKind.UNKNOWN


def _legacy_workspace_ref_contract(
    artifact_ref: str,
    *,
    ticket_id: str,
    tail: str,
    logical_path: str | None,
) -> ArtifactRefContract:
    resolved_path = _safe_normalized_path(logical_path)
    if resolved_path is not None:
        return _contract(_kind_from_logical_path(resolved_path), artifact_ref, ticket_id, resolved_path)

    decoded_tail = _safe_normalized_path(unquote(tail))
    if decoded_tail is None:
        return _contract(ArtifactRefKind.UNKNOWN, artifact_ref, ticket_id, logical_path)
    if decoded_tail.startswith("10-project/src/"):
        return _contract(ArtifactRefKind.WORKSPACE_SOURCE, artifact_ref, ticket_id, decoded_tail)
    if decoded_tail.startswith("10-project/"):
        return _contract(ArtifactRefKind.GOVERNANCE_DOCUMENT, artifact_ref, ticket_id, decoded_tail)
    if decoded_tail.startswith("20-evidence/tests/"):
        return _contract(ArtifactRefKind.TEST_EVIDENCE, artifact_ref, ticket_id, decoded_tail)
    if decoded_tail.startswith("20-evidence/git/"):
        return _contract(ArtifactRefKind.GIT_EVIDENCE, artifact_ref, ticket_id, decoded_tail)

    basename = decoded_tail.rsplit("/", 1)[-1].lower()
    if basename.startswith("source.") or basename == "source.py" or "source-code" in basename:
        return _contract(ArtifactRefKind.WORKSPACE_SOURCE, artifact_ref, ticket_id, None)
    if "test" in basename or "verification" in basename:
        return _contract(ArtifactRefKind.TEST_EVIDENCE, artifact_ref, ticket_id, None)
    if "git" in basename or "commit" in basename:
        return _contract(ArtifactRefKind.GIT_EVIDENCE, artifact_ref, ticket_id, None)
    return _contract(ArtifactRefKind.UNKNOWN, artifact_ref, ticket_id, None)


def _runtime_ref_contract(
    artifact_ref: str,
    *,
    ticket_id: str,
    name: str,
    logical_path: str | None,
) -> ArtifactRefContract:
    resolved_path = _safe_normalized_path(logical_path)
    normalized_name = normalize_workspace_contract_path(unquote(name))
    basename = normalized_name.rsplit("/", 1)[-1]
    basename_lower = basename.lower()

    if basename_lower == "delivery-check-report.json" or basename_lower.startswith("delivery-check-report."):
        return _contract(
            ArtifactRefKind.DELIVERY_CHECK_REPORT,
            artifact_ref,
            ticket_id,
            resolved_path or f"20-evidence/delivery/{ticket_id}/{basename}",
        )
    if basename_lower == "delivery-closeout-package.json" or basename_lower.startswith("delivery-closeout-package."):
        return _contract(
            ArtifactRefKind.CLOSEOUT_PACKAGE,
            artifact_ref,
            ticket_id,
            resolved_path or f"50-closeout/{ticket_id}/{basename}",
        )
    if normalized_name.startswith("git/"):
        return _contract(
            ArtifactRefKind.GIT_EVIDENCE,
            artifact_ref,
            ticket_id,
            resolved_path or f"20-evidence/git/{ticket_id}/{normalized_name.removeprefix('git/')}",
        )
    if normalized_name.startswith("tests/") or normalized_name.startswith("verification/"):
        tail = normalized_name.split("/", 1)[1]
        return _contract(
            ArtifactRefKind.VERIFICATION_EVIDENCE,
            artifact_ref,
            ticket_id,
            resolved_path or f"20-evidence/tests/{ticket_id}/{tail}",
        )
    if normalized_name.startswith("delivery/"):
        tail = normalized_name.removeprefix("delivery/")
        return _contract(
            ArtifactRefKind.DELIVERY_REPORT,
            artifact_ref,
            ticket_id,
            resolved_path or f"20-evidence/delivery/{ticket_id}/{tail}",
        )
    if normalized_name.startswith("governance/") or "architecture" in basename_lower or "backlog" in basename_lower:
        return _contract(
            ArtifactRefKind.GOVERNANCE_DOCUMENT,
            artifact_ref,
            ticket_id,
            resolved_path or f"00-boardroom/30-decisions/{ticket_id}/{basename}",
        )
    if "source-code" in basename_lower or basename_lower.startswith("source."):
        return _contract(
            ArtifactRefKind.WORKSPACE_SOURCE,
            artifact_ref,
            ticket_id,
            resolved_path or f"10-project/src/{basename}",
        )
    if "test" in basename_lower or "verification" in basename_lower:
        return _contract(
            ArtifactRefKind.VERIFICATION_EVIDENCE,
            artifact_ref,
            ticket_id,
            resolved_path or f"20-evidence/tests/{ticket_id}/{basename}",
        )
    if "git" in basename_lower or "commit" in basename_lower:
        return _contract(
            ArtifactRefKind.GIT_EVIDENCE,
            artifact_ref,
            ticket_id,
            resolved_path or f"20-evidence/git/{ticket_id}/{basename}",
        )
    if resolved_path is not None:
        return _contract(_kind_from_logical_path(resolved_path), artifact_ref, ticket_id, resolved_path)
    return _contract(ArtifactRefKind.UNKNOWN, artifact_ref, ticket_id, logical_path)


def resolve_artifact_ref_contract(
    artifact_ref: str,
    *,
    logical_path: str | None = None,
) -> ArtifactRefContract:
    normalized_ref = str(artifact_ref or "").strip()
    if not normalized_ref:
        return _contract(ArtifactRefKind.UNKNOWN, normalized_ref, None, None)

    if normalized_ref.startswith("art://archive/"):
        return _contract(ArtifactRefKind.ARCHIVE, normalized_ref, None, logical_path)

    if normalized_ref.startswith("art://upload-import/"):
        return _contract(ArtifactRefKind.UPLOAD_IMPORT, normalized_ref, None, logical_path)

    if normalized_ref.startswith("art://workspace/"):
        remainder = normalized_ref.removeprefix("art://workspace/")
        parts = remainder.split("/", 2)
        if len(parts) == 3:
            ticket_id, section, encoded_path = parts
            decoded_path = _decode_workspace_tail(encoded_path)
            if section == "source":
                return _contract(
                    ArtifactRefKind.WORKSPACE_SOURCE,
                    normalized_ref,
                    ticket_id,
                    _source_logical_path(decoded_path),
                )
            if section in {"tests", "verification"}:
                return _contract(
                    ArtifactRefKind.TEST_EVIDENCE,
                    normalized_ref,
                    ticket_id,
                    _tests_logical_path(ticket_id, decoded_path),
                )
            if section == "git":
                return _contract(
                    ArtifactRefKind.GIT_EVIDENCE,
                    normalized_ref,
                    ticket_id,
                    _git_logical_path(ticket_id, decoded_path),
                )
            return _legacy_workspace_ref_contract(
                normalized_ref,
                ticket_id=ticket_id,
                tail=f"{section}/{encoded_path}",
                logical_path=logical_path,
            )
        if len(parts) >= 2:
            return _legacy_workspace_ref_contract(
                normalized_ref,
                ticket_id=parts[0],
                tail="/".join(parts[1:]),
                logical_path=logical_path,
            )
        return _contract(ArtifactRefKind.UNKNOWN, normalized_ref, None, logical_path)

    if normalized_ref.startswith("art://runtime/"):
        remainder = normalized_ref.removeprefix("art://runtime/")
        parts = remainder.split("/", 1)
        if len(parts) != 2:
            return _contract(ArtifactRefKind.UNKNOWN, normalized_ref, None, logical_path)
        return _runtime_ref_contract(
            normalized_ref,
            ticket_id=parts[0],
            name=parts[1],
            logical_path=logical_path,
        )

    resolved_path = _safe_normalized_path(logical_path)
    if resolved_path is not None:
        return _contract(_kind_from_logical_path(resolved_path), normalized_ref, None, resolved_path)
    return _contract(ArtifactRefKind.UNKNOWN, normalized_ref, None, logical_path)


def validate_artifact_ref_matches_path(artifact_ref: str, path: str) -> ArtifactRefContract:
    normalized_path = normalize_workspace_contract_path(path)
    contract = resolve_artifact_ref_contract(artifact_ref, logical_path=normalized_path)
    if contract.logical_path is not None and normalize_workspace_contract_path(contract.logical_path) != normalized_path:
        raise ValueError(
            f"Artifact ref {artifact_ref} maps to {contract.logical_path}, "
            f"which does not match the directory contract path {normalized_path}."
        )
    return contract


def build_allowed_write_set_for_capabilities(
    capabilities: list[str] | tuple[str, ...],
    *,
    ticket_id: str,
) -> list[str]:
    patterns: list[str] = []
    for capability in capabilities:
        for template in CAPABILITY_WRITE_SURFACES.get(str(capability).strip(), ()):
            pattern = template.format(ticket_id=ticket_id)
            if pattern not in patterns:
                patterns.append(pattern)
    return patterns


def match_contract_write_set(
    path: str,
    allowed_write_set: list[str] | tuple[str, ...],
) -> bool:
    normalized_path = normalize_workspace_contract_path(path)
    return any(
        fnmatch.fnmatchcase(normalized_path, str(pattern or ""))
        for pattern in allowed_write_set
    )


def classify_closeout_final_artifact_ref(
    artifact_ref: str,
    *,
    current_artifact_refs: set[str],
    superseded_artifact_refs: set[str],
    placeholder_artifact_refs: set[str],
) -> CloseoutFinalRefCheck:
    contract = resolve_artifact_ref_contract(artifact_ref)
    normalized_ref = str(artifact_ref or "").strip()
    if normalized_ref not in current_artifact_refs:
        return CloseoutFinalRefCheck(
            normalized_ref,
            CloseoutFinalRefStatus.UNKNOWN_REF,
            contract.kind,
            "not current",
        )
    if normalized_ref in superseded_artifact_refs:
        return CloseoutFinalRefCheck(
            normalized_ref,
            CloseoutFinalRefStatus.SUPERSEDED,
            contract.kind,
            "superseded",
        )
    if normalized_ref in placeholder_artifact_refs:
        return CloseoutFinalRefCheck(
            normalized_ref,
            CloseoutFinalRefStatus.PLACEHOLDER,
            contract.kind,
            "placeholder",
        )
    if not contract.is_final_closeout_evidence:
        return CloseoutFinalRefCheck(
            normalized_ref,
            CloseoutFinalRefStatus.ILLEGAL_KIND,
            contract.kind,
            "illegal final evidence kind",
        )
    return CloseoutFinalRefCheck(
        normalized_ref,
        CloseoutFinalRefStatus.ACCEPTED,
        contract.kind,
    )


def is_workspace_managed_write_set(allowed_write_set: list[str] | tuple[str, ...]) -> bool:
    return any(
        str(pattern or "").startswith(WORKSPACE_MANAGED_PATH_PREFIXES)
        for pattern in allowed_write_set
    )


def rebind_ticket_id_in_allowed_write_set(
    allowed_write_set: list[str] | tuple[str, ...],
    *,
    previous_ticket_id: str | None,
    next_ticket_id: str | None,
) -> list[str]:
    previous = str(previous_ticket_id or "").strip()
    next_id = str(next_ticket_id or "").strip()
    rebound: list[str] = []
    for pattern in allowed_write_set:
        normalized = str(pattern or "").strip()
        if not normalized:
            continue
        if previous and next_id:
            normalized = normalized.replace(previous, next_id)
        if normalized not in rebound:
            rebound.append(normalized)
    return rebound


def workspace_source_delivery_hard_rules() -> list[str]:
    paths = DEFAULT_WORKSPACE_PATH_TEMPLATES
    return [
        (
            "For workspace-managed source_code_delivery, source_file_refs may only point to "
            f"source artifacts written under {paths.source}; do not put docs, test evidence, "
            "git evidence, or closeout evidence in source_file_refs."
        ),
        (
            "Write documentation updates under "
            f"{paths.docs} and report required documentation surfaces through documentation_updates."
        ),
        (
            "Write verification evidence under "
            f"{paths.tests}, keep each run versioned by attempt, and mirror it through "
            "verification_runs plus verification_evidence_refs."
        ),
        (
            "Write git closeout evidence under "
            f"{paths.git}, keep it versioned by attempt, and include git_commit_record when "
            "source delivery completes."
        ),
    ]
