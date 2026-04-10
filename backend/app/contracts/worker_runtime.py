from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from app.contracts.commands import (
    TicketArtifactImportUploadCommand,
    TicketBoardReviewRequest,
    TicketGitCommitRecord,
    TicketResultStatus,
    TicketWrittenArtifact,
)
from app.contracts.common import StrictModel
from app.contracts.runtime import RenderedExecutionPayload
from app.contracts.scope import TenantWorkspaceScope


class WorkerAssignmentItem(StrictModel):
    workflow_id: str = Field(min_length=1)
    ticket_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    lease_expires_at: datetime | None = None
    execution_package_url: str = Field(min_length=1)
    delivery_expires_at: datetime


class WorkerAssignmentsData(TenantWorkspaceScope):
    worker_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    session_token: str = Field(min_length=1)
    session_expires_at: datetime
    assignments: list[WorkerAssignmentItem] = Field(default_factory=list)


class WorkerAssignmentsEnvelope(StrictModel):
    data: WorkerAssignmentsData


class WorkerCommandEndpoints(StrictModel):
    ticket_start_url: str = Field(min_length=1)
    ticket_heartbeat_url: str = Field(min_length=1)
    ticket_result_submit_url: str = Field(min_length=1)
    ticket_artifact_import_upload_url: str = Field(min_length=1)


class WorkerExecutionPackageData(TenantWorkspaceScope):
    worker_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    ticket_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    bundle_id: str = Field(min_length=1)
    compile_id: str = Field(min_length=1)
    compile_request_id: str = Field(min_length=1)
    output_schema_body: dict[str, Any] = Field(default_factory=dict)
    compiled_execution_package: dict[str, Any] = Field(default_factory=dict)
    rendered_execution_payload: RenderedExecutionPayload
    command_endpoints: WorkerCommandEndpoints
    delivery_expires_at: datetime


class WorkerExecutionPackageEnvelope(StrictModel):
    data: WorkerExecutionPackageData


class WorkerTicketStartCommand(StrictModel):
    workflow_id: str = Field(min_length=1)
    ticket_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)


class WorkerTicketHeartbeatCommand(StrictModel):
    workflow_id: str = Field(min_length=1)
    ticket_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)


class WorkerTicketResultSubmitCommand(StrictModel):
    workflow_id: str = Field(min_length=1)
    ticket_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    result_status: TicketResultStatus
    schema_version: str = Field(min_length=1)
    payload: dict[str, Any]
    artifact_refs: list[str] = Field(default_factory=list)
    written_artifacts: list[TicketWrittenArtifact] = Field(default_factory=list)
    verification_evidence_refs: list[str] = Field(default_factory=list)
    git_commit_record: TicketGitCommitRecord | None = None
    assumptions: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    needs_escalation: bool = False
    summary: str = Field(min_length=1)
    review_request: TicketBoardReviewRequest | None = None
    failure_kind: str | None = None
    failure_message: str | None = None
    failure_detail: dict[str, Any] | None = None
    idempotency_key: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_status_specific_fields(self) -> "WorkerTicketResultSubmitCommand":
        if self.result_status == TicketResultStatus.COMPLETED:
            if self.review_request is not None and self.needs_escalation:
                raise ValueError("review_request and needs_escalation cannot conflict.")
            return self
        if not self.failure_kind or not self.failure_message:
            raise ValueError("failed result submissions require failure_kind and failure_message.")
        return self


class WorkerTicketArtifactImportUploadCommand(TicketArtifactImportUploadCommand):
    pass
