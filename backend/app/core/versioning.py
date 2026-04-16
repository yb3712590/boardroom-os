from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.constants import (
    EVENT_BOARD_REVIEW_APPROVED,
    EVENT_BOARD_REVIEW_REJECTED,
    EVENT_BOARD_REVIEW_REQUIRED,
    EVENT_GRAPH_PATCH_APPLIED,
    EVENT_MEETING_CONCLUDED,
    EVENT_MEETING_REQUESTED,
    EVENT_MEETING_STARTED,
    EVENT_TICKET_CANCELLED,
    EVENT_TICKET_COMPLETED,
    EVENT_TICKET_CREATED,
    EVENT_WORKFLOW_CREATED,
)

if TYPE_CHECKING:
    import sqlite3

    from app.db.repository import ControlPlaneRepository


_GRAPH_VERSION_PREFIX = "gv_"
_GOVERNANCE_PROFILE_PREFIX = "gp_"

_GRAPH_MUTATION_EVENTS = {
    EVENT_WORKFLOW_CREATED,
    EVENT_TICKET_CREATED,
    EVENT_TICKET_COMPLETED,
    EVENT_TICKET_CANCELLED,
    EVENT_BOARD_REVIEW_REQUIRED,
    EVENT_BOARD_REVIEW_APPROVED,
    EVENT_BOARD_REVIEW_REJECTED,
    EVENT_GRAPH_PATCH_APPLIED,
    EVENT_MEETING_REQUESTED,
    EVENT_MEETING_STARTED,
    EVENT_MEETING_CONCLUDED,
}


def build_graph_version(version_int: int) -> str:
    if int(version_int) < 1:
        raise ValueError("graph version must be >= 1")
    return f"{_GRAPH_VERSION_PREFIX}{int(version_int)}"


def build_governance_profile_id(version_int: int) -> str:
    if int(version_int) < 1:
        raise ValueError("governance profile version must be >= 1")
    return f"{_GOVERNANCE_PROFILE_PREFIX}{int(version_int)}"


def build_process_asset_canonical_ref(process_asset_ref: str, version_int: int) -> str:
    base_ref, _ = split_versioned_ref(process_asset_ref)
    if int(version_int) < 1:
        raise ValueError("process asset version must be >= 1")
    return f"{base_ref}@{int(version_int)}"


def split_versioned_ref(ref: str) -> tuple[str, int | None]:
    normalized = str(ref).strip()
    if "@" not in normalized:
        return normalized, None
    base_ref, _, suffix = normalized.rpartition("@")
    if not base_ref or not suffix.isdigit():
        return normalized, None
    version_int = int(suffix)
    if version_int < 1:
        raise ValueError(f"Invalid version suffix in ref: {ref}")
    return base_ref, version_int


def validate_supersedes_ref(
    *,
    canonical_ref: str,
    version_int: int,
    supersedes_ref: str | None,
) -> None:
    if supersedes_ref is None:
        if int(version_int) != 1:
            raise ValueError("supersedes_ref is required when version_int > 1")
        return
    superseded_base_ref, superseded_version = split_versioned_ref(supersedes_ref)
    current_base_ref, _ = split_versioned_ref(canonical_ref)
    if superseded_version is None:
        if not str(supersedes_ref).strip():
            raise ValueError("supersedes_ref must not be empty.")
        return
    if superseded_base_ref != current_base_ref:
        raise ValueError("supersedes_ref must point to the same canonical object.")
    if superseded_version != int(version_int) - 1:
        raise ValueError("supersedes_ref must point to the immediately previous version.")


def build_compiled_context_bundle_version_ref(
    ticket_id: str,
    attempt_no: int,
    version_int: int,
) -> str:
    return f"cb_{ticket_id}_{int(attempt_no)}_{int(version_int)}"


def build_compile_manifest_version_ref(
    ticket_id: str,
    attempt_no: int,
    version_int: int,
) -> str:
    return f"cm_{ticket_id}_{int(attempt_no)}_{int(version_int)}"


def build_compiled_execution_package_version_ref(
    ticket_id: str,
    attempt_no: int,
    version_int: int,
) -> str:
    return f"pkg_{ticket_id}_{int(attempt_no)}_{int(version_int)}"


def build_skill_binding_id(
    ticket_id: str,
    binding_seq: int,
) -> str:
    if int(binding_seq) < 1:
        raise ValueError("skill binding version must be >= 1")
    return f"sb_{ticket_id}_{int(binding_seq)}"


def resolve_workflow_graph_version(
    repository: "ControlPlaneRepository",
    workflow_id: str,
    *,
    connection: "sqlite3.Connection" | None = None,
) -> str:
    if connection is not None:
        events = repository.list_all_events(connection)
    else:
        repository.initialize()
        with repository.connection() as owned_connection:
            events = repository.list_all_events(owned_connection)

    for event in reversed(events):
        if event.get("workflow_id") != workflow_id:
            continue
        if str(event.get("event_type") or "") not in _GRAPH_MUTATION_EVENTS:
            continue
        return build_graph_version(int(event["sequence_no"]))
    raise ValueError(f"Workflow {workflow_id} has no graph version because no graph events were found.")
