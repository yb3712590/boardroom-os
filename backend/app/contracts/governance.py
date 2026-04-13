from __future__ import annotations

from app.contracts.common import StrictModel


class GovernanceProfile(StrictModel):
    profile_id: str
    workflow_id: str
    approval_mode: str
    audit_mode: str
    source_ref: str
    supersedes_ref: str | None = None
    effective_from_event: str
    version_int: int
