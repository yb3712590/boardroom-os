from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from app.contracts.advisory import (
    BoardAdvisoryDecision,
    BoardAdvisorySession,
    BoardAdvisoryTurn,
    GraphPatch,
    GraphPatchProposal,
    GovernancePatch,
)
from app.contracts.governance import GovernanceProfile
from app.core.ids import new_prefixed_id
from app.core.review_subjects import ReviewSubjectResolutionError, resolve_execution_graph_target
from app.core.versioning import build_process_asset_canonical_ref

BOARD_ADVISORY_TRIGGER_CONSTRAINT_CHANGE = "CONSTRAINT_CHANGE"
BOARD_ADVISORY_STATUS_OPEN = "OPEN"
BOARD_ADVISORY_STATUS_DRAFTING = "DRAFTING"
BOARD_ADVISORY_STATUS_PENDING_ANALYSIS = "PENDING_ANALYSIS"
BOARD_ADVISORY_STATUS_PENDING_BOARD_CONFIRMATION = "PENDING_BOARD_CONFIRMATION"
BOARD_ADVISORY_STATUS_APPLIED = "APPLIED"
BOARD_ADVISORY_STATUS_ANALYSIS_REJECTED = "ANALYSIS_REJECTED"
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
    source_graph_node_id = str(subject.get("source_graph_node_id") or "").strip()
    if not source_graph_node_id:
        raise ReviewSubjectResolutionError("board advisory review subject is missing source_graph_node_id.")
    execution_graph_node_id, _execution_node_id = resolve_execution_graph_target(
        source_graph_node_id=source_graph_node_id,
        source_node_id=str(subject.get("source_node_id") or "").strip() or None,
    )
    return [execution_graph_node_id]


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
        working_turns=[],
        decision_pack_refs=[],
        board_decision=None,
        latest_patch_proposal_ref=None,
        latest_patch_proposal=None,
        approved_patch_ref=None,
        approved_patch=None,
        patched_graph_version=None,
        latest_timeline_index_ref=None,
        latest_transcript_archive_artifact_ref=None,
        timeline_archive_version_int=None,
        focus_node_ids=[],
        latest_analysis_run_id=None,
        latest_analysis_status=None,
        latest_analysis_incident_id=None,
        latest_analysis_error=None,
        latest_analysis_trace_artifact_ref=None,
        status=BOARD_ADVISORY_STATUS_OPEN,
    )


def governance_modes_from_profile(profile: GovernanceProfile | Mapping[str, Any]) -> dict[str, str]:
    normalized = GovernanceProfile.model_validate(profile)
    return {
        "approval_mode": normalized.approval_mode,
        "audit_mode": normalized.audit_mode,
    }


def effective_governance_modes_for_board_advisory(
    session: Mapping[str, Any] | None,
    *,
    current_profile: GovernanceProfile | Mapping[str, Any],
) -> dict[str, str]:
    modes = governance_modes_from_profile(current_profile)
    if not isinstance(session, Mapping):
        return modes
    board_decision = session.get("board_decision")
    if not isinstance(board_decision, Mapping):
        return modes
    governance_patch = board_decision.get("governance_patch")
    if not isinstance(governance_patch, Mapping):
        return modes
    approval_mode = str(governance_patch.get("approval_mode") or "").strip()
    audit_mode = str(governance_patch.get("audit_mode") or "").strip()
    if approval_mode:
        modes["approval_mode"] = approval_mode
    if audit_mode:
        modes["audit_mode"] = audit_mode
    return modes


def effective_audit_mode_for_board_advisory(
    session: Mapping[str, Any] | None,
    *,
    current_profile: GovernanceProfile | Mapping[str, Any],
) -> str:
    return effective_governance_modes_for_board_advisory(
        session,
        current_profile=current_profile,
    )["audit_mode"]


def board_advisory_requires_full_timeline_archive(
    session: Mapping[str, Any] | None,
    *,
    current_profile: GovernanceProfile | Mapping[str, Any],
) -> bool:
    return (
        effective_audit_mode_for_board_advisory(
            session,
            current_profile=current_profile,
        )
        == "FULL_TIMELINE"
    )


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
    latest_patch_proposal = session.get("latest_patch_proposal")
    context = {
        "session_id": str(session.get("session_id") or ""),
        "approval_id": str(session.get("approval_id") or ""),
        "review_pack_id": str(session.get("review_pack_id") or ""),
        "trigger_type": str(session.get("trigger_type") or ""),
        "status": str(session.get("status") or ""),
        "change_flow_status": str(session.get("status") or ""),
        "source_version": str(session.get("source_version") or ""),
        "governance_profile_ref": str(session.get("governance_profile_ref") or ""),
        "affected_nodes": list(session.get("affected_nodes") or []),
        "working_turns": list(session.get("working_turns") or []),
        "decision_pack_refs": list(session.get("decision_pack_refs") or []),
        "latest_patch_proposal_ref": session.get("latest_patch_proposal_ref"),
        "approved_patch_ref": session.get("approved_patch_ref"),
        "patched_graph_version": session.get("patched_graph_version"),
        "latest_timeline_index_ref": session.get("latest_timeline_index_ref"),
        "latest_transcript_archive_artifact_ref": session.get("latest_transcript_archive_artifact_ref"),
        "timeline_archive_version_int": session.get("timeline_archive_version_int"),
        "focus_node_ids": list(session.get("focus_node_ids") or []),
        "latest_analysis_run_id": session.get("latest_analysis_run_id"),
        "latest_analysis_status": session.get("latest_analysis_status"),
        "latest_analysis_incident_id": session.get("latest_analysis_incident_id"),
        "latest_analysis_error": session.get("latest_analysis_error"),
        "latest_analysis_trace_artifact_ref": session.get("latest_analysis_trace_artifact_ref"),
        "current_governance_modes": governance_modes_from_profile(current_profile),
        "supports_governance_patch": True,
    }
    board_decision = session.get("board_decision")
    if isinstance(board_decision, Mapping):
        context["board_decision"] = dict(board_decision)
    if isinstance(latest_patch_proposal, Mapping):
        context["proposal_summary"] = str(latest_patch_proposal.get("proposal_summary") or "")
        context["pros"] = list(latest_patch_proposal.get("pros") or [])
        context["cons"] = list(latest_patch_proposal.get("cons") or [])
        context["risk_alerts"] = list(latest_patch_proposal.get("risk_alerts") or [])
        context["impact_summary"] = str(latest_patch_proposal.get("impact_summary") or "")
    return context


def build_board_advisory_snapshot_entry(session: Mapping[str, Any]) -> dict[str, Any]:
    entry = {
        "session_id": str(session.get("session_id") or ""),
        "approval_id": str(session.get("approval_id") or ""),
        "review_pack_id": str(session.get("review_pack_id") or ""),
        "trigger_type": str(session.get("trigger_type") or ""),
        "status": str(session.get("status") or ""),
        "change_flow_status": str(session.get("status") or ""),
        "source_version": str(session.get("source_version") or ""),
        "governance_profile_ref": str(session.get("governance_profile_ref") or ""),
        "affected_nodes": list(session.get("affected_nodes") or []),
        "focus_node_ids": list(session.get("focus_node_ids") or []),
        "decision_pack_refs": list(session.get("decision_pack_refs") or []),
        "latest_patch_proposal_ref": session.get("latest_patch_proposal_ref"),
        "approved_patch_ref": session.get("approved_patch_ref"),
        "patched_graph_version": session.get("patched_graph_version"),
        "latest_timeline_index_ref": session.get("latest_timeline_index_ref"),
        "latest_transcript_archive_artifact_ref": session.get("latest_transcript_archive_artifact_ref"),
        "timeline_archive_version_int": session.get("timeline_archive_version_int"),
        "latest_analysis_run_id": session.get("latest_analysis_run_id"),
        "latest_analysis_status": session.get("latest_analysis_status"),
        "latest_analysis_incident_id": session.get("latest_analysis_incident_id"),
        "latest_analysis_error": session.get("latest_analysis_error"),
        "latest_analysis_trace_artifact_ref": session.get("latest_analysis_trace_artifact_ref"),
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
    if str(session.get("status") or "") != BOARD_ADVISORY_STATUS_APPLIED:
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
        "latest_patch_proposal_ref": session.get("latest_patch_proposal_ref"),
        "patched_graph_version": session.get("patched_graph_version"),
        "latest_timeline_index_ref": session.get("latest_timeline_index_ref"),
        "latest_transcript_archive_artifact_ref": session.get("latest_transcript_archive_artifact_ref"),
        "timeline_archive_version_int": session.get("timeline_archive_version_int"),
        "focus_node_ids": list(session.get("focus_node_ids") or []),
        "decision_action": str(board_decision.get("decision_action") or ""),
        "board_comment": str(board_decision.get("board_comment") or ""),
        "constraint_patch": dict(board_decision.get("constraint_patch") or {}),
        "current_governance_modes": effective_governance_modes_for_board_advisory(
            session,
            current_profile=current_profile,
        ),
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


def advisory_patch_proposal_artifact_ref(*, workflow_id: str, session_id: str) -> str:
    return f"art://board-advisory/{workflow_id}/{session_id}/graph-patch-proposal.json"


def advisory_patch_proposal_logical_path(*, session_id: str) -> str:
    return f"20-evidence/board-advisory/{session_id}/graph-patch-proposal.json"


def advisory_patch_proposal_process_asset_ref(session_id: str) -> str:
    return build_process_asset_canonical_ref(f"pa://graph-patch-proposal/{session_id}", 1)


def advisory_graph_patch_artifact_ref(*, workflow_id: str, session_id: str) -> str:
    return f"art://board-advisory/{workflow_id}/{session_id}/graph-patch.json"


def advisory_graph_patch_logical_path(*, session_id: str) -> str:
    return f"20-evidence/board-advisory/{session_id}/graph-patch.json"


def advisory_graph_patch_process_asset_ref(session_id: str) -> str:
    return build_process_asset_canonical_ref(f"pa://graph-patch/{session_id}", 1)


def advisory_timeline_index_artifact_ref(
    *,
    workflow_id: str,
    session_id: str,
    version_int: int,
) -> str:
    return f"art://board-advisory/{workflow_id}/{session_id}/timeline-index-v{version_int}.json"


def advisory_timeline_index_logical_path(*, session_id: str, version_int: int) -> str:
    return f"20-evidence/board-advisory/{session_id}/timeline-index-v{version_int}.json"


def advisory_timeline_index_process_asset_ref(session_id: str, *, version_int: int) -> str:
    return build_process_asset_canonical_ref(f"pa://timeline-index/{session_id}", version_int)


def advisory_transcript_archive_artifact_ref(
    *,
    workflow_id: str,
    session_id: str,
    version_int: int,
) -> str:
    return f"art://board-advisory/{workflow_id}/{session_id}/transcript-v{version_int}.json"


def advisory_transcript_archive_logical_path(*, session_id: str, version_int: int) -> str:
    return f"90-archive/transcripts/board-advisory/{session_id}/v{version_int}.json"


def build_board_advisory_turn(*, actor_type: str, content: str, created_at) -> BoardAdvisoryTurn:
    return BoardAdvisoryTurn(
        turn_id=new_prefixed_id("advturn"),
        actor_type=actor_type,
        content=content,
        created_at=created_at,
    )


def advisory_change_flow_can_append_turn(status: str) -> bool:
    return status in {
        BOARD_ADVISORY_STATUS_DRAFTING,
        BOARD_ADVISORY_STATUS_ANALYSIS_REJECTED,
    }


def advisory_change_flow_can_request_analysis(status: str) -> bool:
    return status in {
        BOARD_ADVISORY_STATUS_DRAFTING,
        BOARD_ADVISORY_STATUS_ANALYSIS_REJECTED,
    }


def advisory_change_flow_can_apply(status: str) -> bool:
    return status == BOARD_ADVISORY_STATUS_PENDING_BOARD_CONFIRMATION


def build_graph_patch_proposal(
    *,
    session: Mapping[str, Any],
    board_decision: BoardAdvisoryDecision,
    current_profile: GovernanceProfile | Mapping[str, Any],
    base_graph_version: str,
) -> GraphPatchProposal:
    affected_nodes = [
        str(node_id).strip()
        for node_id in list(session.get("affected_nodes") or [])
        if str(node_id).strip()
    ]
    if not affected_nodes:
        raise ValueError("Advisory patch proposal needs at least one affected node.")
    pros = ["Keeps runtime changes gated until the board explicitly approves the patch."]
    if board_decision.governance_patch is not None:
        next_modes = build_governance_profile_from_patch(
            current_profile,
            board_decision.governance_patch,
            source_ref="pending-graph-patch",
            effective_from_event="pending-graph-patch",
        )
        if next_modes is not None:
            pros.append("Raises governance rigor before the next autonomous execution pass.")
    cons = ["The affected delivery branch stays blocked until the board confirms the replan."]
    risk_alerts = ["The current proposal freezes the affected nodes before the next runtime import."]
    impact_summary = (
        f"Freeze {len(affected_nodes)} affected node(s) and focus the next CEO pass on the same branch."
    )
    proposal_hash = hashlib.sha256(
        json.dumps(
            {
                "session_id": str(session.get("session_id") or ""),
                "base_graph_version": base_graph_version,
                "constraint_patch": board_decision.constraint_patch,
                "governance_patch": (
                    board_decision.governance_patch.model_dump(mode="json", exclude_none=True)
                    if board_decision.governance_patch is not None
                    else None
                ),
                "affected_nodes": affected_nodes,
                "board_comment": board_decision.board_comment,
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return GraphPatchProposal(
        proposal_ref=advisory_patch_proposal_process_asset_ref(str(session.get("session_id") or "")),
        workflow_id=str(session.get("workflow_id") or ""),
        session_id=str(session.get("session_id") or ""),
        base_graph_version=base_graph_version,
        proposal_summary=(
            "Freeze the affected branch, raise governance if requested, and rerun CEO only after board confirmation."
        ),
        pros=pros,
        cons=cons,
        risk_alerts=risk_alerts,
        impact_summary=impact_summary,
        freeze_node_ids=affected_nodes,
        unfreeze_node_ids=[],
        focus_node_ids=affected_nodes,
        source_decision_pack_ref=advisory_decision_process_asset_ref(str(session.get("session_id") or "")),
        proposal_hash=proposal_hash,
    )


def build_graph_patch_from_proposal(
    proposal: GraphPatchProposal | Mapping[str, Any],
    *,
    session_id: str,
) -> GraphPatch:
    normalized = GraphPatchProposal.model_validate(proposal)
    return GraphPatch(
        patch_ref=advisory_graph_patch_process_asset_ref(session_id),
        workflow_id=normalized.workflow_id,
        session_id=session_id,
        proposal_ref=normalized.proposal_ref,
        base_graph_version=normalized.base_graph_version,
        freeze_node_ids=list(normalized.freeze_node_ids),
        unfreeze_node_ids=list(normalized.unfreeze_node_ids),
        focus_node_ids=list(normalized.focus_node_ids),
        replacements=[item.model_copy() for item in normalized.replacements],
        remove_node_ids=list(normalized.remove_node_ids),
        add_nodes=[item.model_copy() for item in normalized.add_nodes],
        edge_additions=[item.model_copy() for item in normalized.edge_additions],
        edge_removals=[item.model_copy() for item in normalized.edge_removals],
        reason_summary=normalized.proposal_summary,
        patch_hash=normalized.proposal_hash,
    )


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


def build_board_advisory_transcript_payload(
    *,
    session: Mapping[str, Any],
    current_profile: GovernanceProfile | Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "session_id": str(session.get("session_id") or ""),
        "workflow_id": str(session.get("workflow_id") or ""),
        "approval_id": str(session.get("approval_id") or ""),
        "review_pack_id": str(session.get("review_pack_id") or ""),
        "change_flow_status": str(session.get("status") or ""),
        "source_version": str(session.get("source_version") or ""),
        "governance_profile_ref": str(session.get("governance_profile_ref") or ""),
        "current_governance_modes": effective_governance_modes_for_board_advisory(
            session,
            current_profile=current_profile,
        ),
        "working_turns": list(session.get("working_turns") or []),
        "board_decision": (
            dict(session.get("board_decision") or {})
            if isinstance(session.get("board_decision"), Mapping)
            else None
        ),
        "latest_patch_proposal": (
            dict(session.get("latest_patch_proposal") or {})
            if isinstance(session.get("latest_patch_proposal"), Mapping)
            else None
        ),
        "approved_patch": (
            dict(session.get("approved_patch") or {})
            if isinstance(session.get("approved_patch"), Mapping)
            else None
        ),
        "decision_pack_refs": list(session.get("decision_pack_refs") or []),
        "patched_graph_version": session.get("patched_graph_version"),
        "latest_analysis_run_id": session.get("latest_analysis_run_id"),
        "latest_analysis_status": session.get("latest_analysis_status"),
        "latest_analysis_incident_id": session.get("latest_analysis_incident_id"),
        "latest_analysis_error": session.get("latest_analysis_error"),
        "latest_analysis_trace_artifact_ref": session.get("latest_analysis_trace_artifact_ref"),
    }


def build_board_advisory_timeline_index_payload(
    *,
    session: Mapping[str, Any],
    current_profile: GovernanceProfile | Mapping[str, Any],
    timeline_archive_version_int: int,
    transcript_archive_artifact_ref: str,
    latest_analysis_archive_artifact_ref: str | None = None,
) -> dict[str, Any]:
    payload = {
        "session_id": str(session.get("session_id") or ""),
        "workflow_id": str(session.get("workflow_id") or ""),
        "approval_id": str(session.get("approval_id") or ""),
        "review_pack_id": str(session.get("review_pack_id") or ""),
        "timeline_archive_version_int": timeline_archive_version_int,
        "transcript_archive_artifact_ref": transcript_archive_artifact_ref,
        "change_flow_status": str(session.get("status") or ""),
        "current_governance_modes": effective_governance_modes_for_board_advisory(
            session,
            current_profile=current_profile,
        ),
        "decision_pack_refs": list(session.get("decision_pack_refs") or []),
        "latest_patch_proposal_ref": session.get("latest_patch_proposal_ref"),
        "approved_patch_ref": session.get("approved_patch_ref"),
        "patched_graph_version": session.get("patched_graph_version"),
        "latest_analysis_run_id": session.get("latest_analysis_run_id"),
        "latest_analysis_status": session.get("latest_analysis_status"),
        "latest_analysis_incident_id": session.get("latest_analysis_incident_id"),
        "latest_analysis_error": session.get("latest_analysis_error"),
        "latest_analysis_trace_artifact_ref": session.get("latest_analysis_trace_artifact_ref"),
        "turn_ids": [
            str(item.get("turn_id") or "").strip()
            for item in list(session.get("working_turns") or [])
            if isinstance(item, Mapping) and str(item.get("turn_id") or "").strip()
        ],
    }
    if latest_analysis_archive_artifact_ref is not None:
        payload["latest_analysis_archive_artifact_ref"] = latest_analysis_archive_artifact_ref
    return payload
