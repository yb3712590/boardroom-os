from __future__ import annotations

from typing import Any, Mapping

from app.contracts.advisory import (
    BoardAdvisoryDecision,
    BoardAdvisorySession,
    GovernancePatch,
)
from app.contracts.governance import GovernanceProfile
from app.core.ids import new_prefixed_id
from app.core.versioning import build_process_asset_canonical_ref

BOARD_ADVISORY_TRIGGER_CONSTRAINT_CHANGE = "CONSTRAINT_CHANGE"
BOARD_ADVISORY_STATUS_OPEN = "OPEN"
BOARD_ADVISORY_STATUS_DECIDED = "DECIDED"
BOARD_ADVISORY_STATUS_DISMISSED = "DISMISSED"

AUDIT_MATERIALIZATION_POLICY_BY_MODE = {
    "MINIMAL": {
        "ticket_context_archive": False,
        "full_timeline": False,
        "closeout_evidence": True,
    },
    "TICKET_TRACE": {
        "ticket_context_archive": True,
        "full_timeline": False,
        "closeout_evidence": True,
    },
    "FULL_TIMELINE": {
        "ticket_context_archive": True,
        "full_timeline": True,
        "closeout_evidence": True,
    },
}


def review_pack_requires_board_advisory(review_pack: Mapping[str, Any] | None) -> bool:
    if not isinstance(review_pack, Mapping):
        return False
    decision_form = review_pack.get("decision_form")
    if not isinstance(decision_form, Mapping):
        return False
    return bool(decision_form.get("requires_constraint_patch_on_modify"))


def advisory_supports_governance_patch(review_pack: Mapping[str, Any] | None) -> bool:
    return review_pack_requires_board_advisory(review_pack)


def advisory_affected_nodes(review_pack: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(review_pack, Mapping):
        return []
    subject = review_pack.get("subject")
    if not isinstance(subject, Mapping):
        return []
    source_node_id = str(subject.get("source_node_id") or "").strip()
    return [source_node_id] if source_node_id else []


def build_board_advisory_session(
    *,
    workflow_id: str,
    approval_id: str,
    review_pack_id: str,
    review_pack: Mapping[str, Any] | None,
    source_version: str,
    governance_profile_ref: str,
) -> BoardAdvisorySession:
    return BoardAdvisorySession(
        session_id=new_prefixed_id("adv"),
        workflow_id=workflow_id,
        approval_id=approval_id,
        review_pack_id=review_pack_id,
        trigger_type=BOARD_ADVISORY_TRIGGER_CONSTRAINT_CHANGE,
        source_version=source_version,
        governance_profile_ref=governance_profile_ref,
        affected_nodes=advisory_affected_nodes(review_pack),
        decision_pack_refs=[],
        board_decision=None,
        approved_patch_ref=None,
        status=BOARD_ADVISORY_STATUS_OPEN,
    )


def governance_modes_from_profile(profile: GovernanceProfile | Mapping[str, Any]) -> dict[str, str]:
    normalized = GovernanceProfile.model_validate(profile)
    return {
        "approval_mode": normalized.approval_mode,
        "audit_mode": normalized.audit_mode,
    }


def build_governance_profile_from_patch(
    current_profile: GovernanceProfile | Mapping[str, Any],
    governance_patch: GovernancePatch,
    *,
    source_ref: str,
    effective_from_event: str,
) -> GovernanceProfile | None:
    normalized = GovernanceProfile.model_validate(current_profile)
    next_approval_mode = governance_patch.approval_mode or normalized.approval_mode
    next_audit_mode = governance_patch.audit_mode or normalized.audit_mode
    if next_approval_mode == normalized.approval_mode and next_audit_mode == normalized.audit_mode:
        return None
    return GovernanceProfile(
        profile_id=new_prefixed_id("gp"),
        workflow_id=normalized.workflow_id,
        approval_mode=next_approval_mode,
        audit_mode=next_audit_mode,
        auto_approval_scope=list(normalized.auto_approval_scope),
        expert_review_targets=list(normalized.expert_review_targets),
        audit_materialization_policy=dict(AUDIT_MATERIALIZATION_POLICY_BY_MODE[next_audit_mode]),
        source_ref=source_ref,
        supersedes_ref=normalized.profile_id,
        effective_from_event=effective_from_event,
        version_int=int(normalized.version_int) + 1,
    )


def build_board_advisory_context(
    session: Mapping[str, Any],
    *,
    current_profile: GovernanceProfile | Mapping[str, Any],
) -> dict[str, Any]:
    context = {
        "session_id": str(session.get("session_id") or ""),
        "approval_id": str(session.get("approval_id") or ""),
        "review_pack_id": str(session.get("review_pack_id") or ""),
        "trigger_type": str(session.get("trigger_type") or ""),
        "status": str(session.get("status") or ""),
        "source_version": str(session.get("source_version") or ""),
        "governance_profile_ref": str(session.get("governance_profile_ref") or ""),
        "affected_nodes": list(session.get("affected_nodes") or []),
        "decision_pack_refs": list(session.get("decision_pack_refs") or []),
        "approved_patch_ref": session.get("approved_patch_ref"),
        "current_governance_modes": governance_modes_from_profile(current_profile),
        "supports_governance_patch": True,
    }
    board_decision = session.get("board_decision")
    if isinstance(board_decision, Mapping):
        context["board_decision"] = dict(board_decision)
    return context


def build_board_advisory_snapshot_entry(session: Mapping[str, Any]) -> dict[str, Any]:
    entry = {
        "session_id": str(session.get("session_id") or ""),
        "approval_id": str(session.get("approval_id") or ""),
        "review_pack_id": str(session.get("review_pack_id") or ""),
        "trigger_type": str(session.get("trigger_type") or ""),
        "status": str(session.get("status") or ""),
        "source_version": str(session.get("source_version") or ""),
        "governance_profile_ref": str(session.get("governance_profile_ref") or ""),
        "affected_nodes": list(session.get("affected_nodes") or []),
        "decision_pack_refs": list(session.get("decision_pack_refs") or []),
        "approved_patch_ref": session.get("approved_patch_ref"),
    }
    board_decision = session.get("board_decision")
    if isinstance(board_decision, Mapping):
        entry["decision_action"] = str(board_decision.get("decision_action") or "")
        entry["board_comment"] = str(board_decision.get("board_comment") or "")
    return entry


def build_latest_advisory_decision(
    session: Mapping[str, Any] | None,
    *,
    current_profile: GovernanceProfile | Mapping[str, Any],
) -> dict[str, Any] | None:
    if not isinstance(session, Mapping):
        return None
    if str(session.get("status") or "") != BOARD_ADVISORY_STATUS_DECIDED:
        return None
    board_decision = session.get("board_decision")
    if not isinstance(board_decision, Mapping):
        return None
    payload = {
        "session_id": str(session.get("session_id") or ""),
        "approval_id": str(session.get("approval_id") or ""),
        "review_pack_id": str(session.get("review_pack_id") or ""),
        "trigger_type": str(session.get("trigger_type") or ""),
        "source_version": str(session.get("source_version") or ""),
        "governance_profile_ref": str(session.get("governance_profile_ref") or ""),
        "affected_nodes": list(session.get("affected_nodes") or []),
        "decision_pack_refs": list(session.get("decision_pack_refs") or []),
        "approved_patch_ref": session.get("approved_patch_ref"),
        "decision_action": str(board_decision.get("decision_action") or ""),
        "board_comment": str(board_decision.get("board_comment") or ""),
        "constraint_patch": dict(board_decision.get("constraint_patch") or {}),
        "current_governance_modes": governance_modes_from_profile(current_profile),
    }
    governance_patch = board_decision.get("governance_patch")
    if isinstance(governance_patch, Mapping):
        payload["governance_patch"] = dict(governance_patch)
    return payload


def advisory_decision_artifact_ref(*, workflow_id: str, session_id: str) -> str:
    return f"art://board-advisory/{workflow_id}/{session_id}/decision-summary.json"


def advisory_decision_logical_path(*, session_id: str) -> str:
    return f"20-evidence/board-advisory/{session_id}/decision-summary.json"


def advisory_decision_process_asset_ref(session_id: str) -> str:
    return build_process_asset_canonical_ref(f"pa://decision-summary/{session_id}", 1)


def build_board_advisory_decision(
    *,
    board_comment: str,
    constraint_patch: dict[str, list[str]],
    governance_patch: GovernancePatch | None,
    source_artifact_ref: str,
) -> BoardAdvisoryDecision:
    return BoardAdvisoryDecision(
        decision_action="MODIFY_CONSTRAINTS",
        board_comment=board_comment,
        constraint_patch=constraint_patch,
        governance_patch=governance_patch,
        source_artifact_ref=source_artifact_ref,
    )


def build_board_advisory_decision_artifact_payload(
    *,
    session: Mapping[str, Any],
    board_decision: BoardAdvisoryDecision,
    current_profile: GovernanceProfile | Mapping[str, Any],
    next_profile: GovernanceProfile | Mapping[str, Any] | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "session_id": str(session.get("session_id") or ""),
        "approval_id": str(session.get("approval_id") or ""),
        "review_pack_id": str(session.get("review_pack_id") or ""),
        "trigger_type": str(session.get("trigger_type") or ""),
        "source_version": str(session.get("source_version") or ""),
        "governance_profile_ref": str(session.get("governance_profile_ref") or ""),
        "affected_nodes": list(session.get("affected_nodes") or []),
        "decision_action": board_decision.decision_action,
        "board_comment": board_decision.board_comment,
        "constraint_patch": board_decision.constraint_patch,
        "current_governance_modes": governance_modes_from_profile(current_profile),
    }
    if board_decision.governance_patch is not None:
        payload["governance_patch"] = board_decision.governance_patch.model_dump(mode="json", exclude_none=True)
    if next_profile is not None:
        payload["next_governance_modes"] = governance_modes_from_profile(next_profile)
        payload["next_governance_profile_ref"] = GovernanceProfile.model_validate(next_profile).profile_id
    return payload
