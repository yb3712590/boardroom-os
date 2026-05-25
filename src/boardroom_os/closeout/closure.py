from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from boardroom_os.evidence.verifier import VerifiedEvidence
from boardroom_os.execution.verification_run import VerificationRun
from boardroom_os.workspace.evidence_export import WorkspaceEvidenceBundle
from boardroom_os.workspace.source_inventory import SourceInventory


class CloseoutClosureError(ValueError):
    pass


def _ref_value(ref: object, *, field_name: str) -> str:
    raw_value: object
    if isinstance(ref, str):
        raw_value = ref
    elif hasattr(ref, "value"):
        raw_value = getattr(ref, "value")
    else:
        raise CloseoutClosureError(f"{field_name} must contain refs with .value or strings")

    if not isinstance(raw_value, str):
        raise CloseoutClosureError(f"{field_name} refs must resolve to strings")

    normalized = raw_value.strip()
    if normalized != raw_value:
        raise CloseoutClosureError(f"{field_name} must not contain surrounding whitespace")
    if not raw_value:
        raise CloseoutClosureError(f"{field_name} must not contain empty refs")
    return raw_value


def normalize_ref_tuple(*, field_name: str, refs: Iterable[object]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        value = _ref_value(ref, field_name=field_name)
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return tuple(normalized)


def _sorted_ref_tuple(refs: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(refs))


def _missing_refs_message(
    *,
    domain_object_id: str,
    required_refs: set[str],
    observed_refs: set[str],
) -> str:
    missing_refs = required_refs - observed_refs
    return (
        "closeout closure refs are missing: "
        f"domain_object_id={domain_object_id}; "
        f"missing_refs={_sorted_ref_tuple(missing_refs)}; "
        f"required_refs={_sorted_ref_tuple(required_refs)}; "
        f"observed_refs={_sorted_ref_tuple(observed_refs)}"
    )


def _set_mismatch_message(
    *,
    domain_object_id: str,
    expected_refs: set[str],
    actual_refs: set[str],
) -> str:
    return (
        "closeout closure ref sets differ: "
        f"domain_object_id={domain_object_id}; "
        f"missing_refs={_sorted_ref_tuple(expected_refs - actual_refs)}; "
        f"extra_refs={_sorted_ref_tuple(actual_refs - expected_refs)}; "
        f"expected_refs={_sorted_ref_tuple(expected_refs)}; "
        f"actual_refs={_sorted_ref_tuple(actual_refs)}"
    )


def _require_domain_object_id(domain_object_id: str) -> str:
    normalized = domain_object_id.strip()
    if not normalized:
        raise CloseoutClosureError("domain_object_id must not be empty")
    return normalized


def _require_instance(value: Any, expected_type: type[Any], field_name: str) -> None:
    if not isinstance(value, expected_type):
        raise CloseoutClosureError(f"{field_name} must be {expected_type.__name__}")


def assert_checked_refs_cover(
    domain_object_id: str,
    required_refs: Iterable[object],
    observed_refs: Iterable[object],
) -> None:
    normalized_domain_object_id = _require_domain_object_id(domain_object_id)
    required = set(normalize_ref_tuple(field_name="required_refs", refs=required_refs))
    observed = set(normalize_ref_tuple(field_name="observed_refs", refs=observed_refs))
    if not required.issubset(observed):
        raise CloseoutClosureError(
            _missing_refs_message(
                domain_object_id=normalized_domain_object_id,
                required_refs=required,
                observed_refs=observed,
            )
        )


def assert_source_inventory_evidence_refs_resolve(
    domain_object_id: str,
    source_inventory: SourceInventory,
    verified_evidence: tuple[VerifiedEvidence, ...],
) -> None:
    normalized_domain_object_id = _require_domain_object_id(domain_object_id)
    _require_instance(source_inventory, SourceInventory, "source_inventory")
    required_refs = set(
        normalize_ref_tuple(
            field_name="source_inventory.evidence_refs",
            refs=(
                evidence_ref
                for entry in source_inventory.entries
                for evidence_ref in entry.evidence_refs
            ),
        )
    )
    observed_refs = set(
        normalize_ref_tuple(
            field_name="verified_evidence.verified_evidence_id",
            refs=(evidence.verified_evidence_id for evidence in verified_evidence),
        )
    )
    if not required_refs.issubset(observed_refs):
        raise CloseoutClosureError(
            _missing_refs_message(
                domain_object_id=normalized_domain_object_id,
                required_refs=required_refs,
                observed_refs=observed_refs,
            )
        )


def assert_workspace_evidence_bundle_matches_runs(
    domain_object_id: str,
    workspace_evidence_bundle: WorkspaceEvidenceBundle,
    verification_runs: tuple[VerificationRun, ...],
) -> None:
    normalized_domain_object_id = _require_domain_object_id(domain_object_id)
    _require_instance(
        workspace_evidence_bundle,
        WorkspaceEvidenceBundle,
        "workspace_evidence_bundle",
    )
    expected_refs = set(
        normalize_ref_tuple(
            field_name="verification_runs.verification_run_id",
            refs=(run.verification_run_id for run in verification_runs),
        )
    )
    actual_refs = set(
        normalize_ref_tuple(
            field_name="workspace_evidence_bundle.verification_run_refs",
            refs=workspace_evidence_bundle.verification_run_refs,
        )
    )
    if expected_refs != actual_refs:
        raise CloseoutClosureError(
            _set_mismatch_message(
                domain_object_id=normalized_domain_object_id,
                expected_refs=expected_refs,
                actual_refs=actual_refs,
            )
        )


__all__ = [
    "CloseoutClosureError",
    "assert_checked_refs_cover",
    "assert_source_inventory_evidence_refs_resolve",
    "assert_workspace_evidence_bundle_matches_runs",
    "normalize_ref_tuple",
]
