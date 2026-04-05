from __future__ import annotations

from datetime import datetime

from app.contracts.runtime import (
    CompileRequestMeta,
    CompileRequestWorkerBinding,
    CompiledExecutionPackageMeta,
)
from app.contracts.scope import OptionalTenantWorkspaceScope, TenantWorkspaceScope
from app.contracts.worker_admin import (
    WorkerAdminBindingItem,
    WorkerAdminIssueBootstrapRequest,
    WorkerAdminRevokeSessionRequest,
)
from app.contracts.worker_runtime import WorkerAssignmentsData, WorkerExecutionPackageData


def test_runtime_and_worker_runtime_contracts_reuse_required_scope_contract() -> None:
    assert issubclass(CompileRequestMeta, TenantWorkspaceScope)
    assert issubclass(CompileRequestWorkerBinding, TenantWorkspaceScope)
    assert issubclass(CompiledExecutionPackageMeta, TenantWorkspaceScope)
    assert issubclass(WorkerAssignmentsData, TenantWorkspaceScope)
    assert issubclass(WorkerExecutionPackageData, TenantWorkspaceScope)


def test_worker_admin_contracts_reuse_shared_scope_contracts_and_keep_field_names() -> None:
    assert issubclass(WorkerAdminBindingItem, TenantWorkspaceScope)
    assert issubclass(WorkerAdminIssueBootstrapRequest, OptionalTenantWorkspaceScope)
    assert issubclass(WorkerAdminRevokeSessionRequest, OptionalTenantWorkspaceScope)

    binding = WorkerAdminBindingItem(
        worker_id="emp_worker_1",
        credential_version=1,
        tenant_id="tenant_default",
        workspace_id="ws_default",
        updated_at=datetime.fromisoformat("2026-04-06T10:00:00+08:00"),
        active_session_count=1,
        active_delivery_grant_count=0,
        active_ticket_count=0,
        bootstrap_issue_count=0,
        cleanup_eligible=False,
    )
    issue_request = WorkerAdminIssueBootstrapRequest(
        worker_id="emp_worker_1",
        tenant_id="tenant_default",
        workspace_id="ws_default",
    )

    assert binding.model_dump()["tenant_id"] == "tenant_default"
    assert binding.model_dump()["workspace_id"] == "ws_default"
    assert issue_request.model_dump()["tenant_id"] == "tenant_default"
    assert issue_request.model_dump()["workspace_id"] == "ws_default"
