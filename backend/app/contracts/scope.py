from __future__ import annotations

from pydantic import Field, model_validator

from app.contracts.common import StrictModel


class TenantWorkspaceScope(StrictModel):
    tenant_id: str = Field(min_length=1)
    workspace_id: str = Field(min_length=1)


class OptionalTenantWorkspaceScope(StrictModel):
    tenant_id: str | None = None
    workspace_id: str | None = None

    @model_validator(mode="after")
    def validate_scope_pair(self) -> "OptionalTenantWorkspaceScope":
        if (self.tenant_id is None) != (self.workspace_id is None):
            raise ValueError("tenant_id and workspace_id must be provided together.")
        return self
