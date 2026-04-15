from __future__ import annotations

from typing import Any

from app.contracts.governance import GovernanceModeSlice, GovernanceProfile
from app.core.ids import new_prefixed_id


DEFAULT_APPROVAL_MODE = "AUTO_CEO"
DEFAULT_AUDIT_MODE = "MINIMAL"
DEFAULT_AUTO_APPROVAL_SCOPE = ["scope:mainline_internal"]
DEFAULT_EXPERT_REVIEW_TARGETS = ["checker", "board"]
DEFAULT_AUDIT_MATERIALIZATION_POLICY = {
    "ticket_context_archive": False,
    "full_timeline": False,
    "closeout_evidence": True,
}


def build_default_governance_profile(
    *,
    workflow_id: str,
    source_ref: str,
    effective_from_event: str,
) -> GovernanceProfile:
    return GovernanceProfile(
        profile_id=new_prefixed_id("gp"),
        workflow_id=workflow_id,
        approval_mode=DEFAULT_APPROVAL_MODE,
        audit_mode=DEFAULT_AUDIT_MODE,
        auto_approval_scope=list(DEFAULT_AUTO_APPROVAL_SCOPE),
        expert_review_targets=list(DEFAULT_EXPERT_REVIEW_TARGETS),
        audit_materialization_policy=dict(DEFAULT_AUDIT_MATERIALIZATION_POLICY),
        source_ref=source_ref,
        supersedes_ref=None,
        effective_from_event=effective_from_event,
        version_int=1,
    )


def governance_profile_to_mode_slice(profile: GovernanceProfile | dict[str, Any]) -> GovernanceModeSlice:
    normalized = GovernanceProfile.model_validate(profile)
    return GovernanceModeSlice(
        governance_profile_ref=normalized.profile_id,
        approval_mode=normalized.approval_mode,
        audit_mode=normalized.audit_mode,
        auto_approval_scope=list(normalized.auto_approval_scope),
        expert_review_targets=list(normalized.expert_review_targets),
        audit_materialization_policy=dict(normalized.audit_materialization_policy),
    )


def require_governance_profile(
    repository,
    *,
    workflow_id: str,
    connection=None,
) -> GovernanceProfile:
    profile = repository.get_latest_governance_profile(workflow_id, connection=connection)
    if profile is None:
        raise ValueError(f"GovernanceProfile is required for workflow {workflow_id}.")
    return GovernanceProfile.model_validate(profile)
