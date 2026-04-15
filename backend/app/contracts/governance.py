from __future__ import annotations

from app.contracts.common import StrictModel


class GovernanceProfile(StrictModel):
    profile_id: str
    workflow_id: str
    approval_mode: str
    audit_mode: str
    auto_approval_scope: list[str]
    expert_review_targets: list[str]
    audit_materialization_policy: dict[str, bool]
    source_ref: str
    supersedes_ref: str | None = None
    effective_from_event: str
    version_int: int


class GovernanceModeSlice(StrictModel):
    governance_profile_ref: str
    approval_mode: str
    audit_mode: str
    auto_approval_scope: list[str]
    expert_review_targets: list[str]
    audit_materialization_policy: dict[str, bool]
