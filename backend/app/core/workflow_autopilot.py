from __future__ import annotations

from datetime import datetime
from typing import Any

from app.contracts.commands import BoardApproveCommand, ElicitationAnswer
from app.core.ticket_graph import build_ticket_graph_snapshot
from app.core.workflow_completion import resolve_workflow_closeout_completion

STANDARD_WORKFLOW_PROFILE = "STANDARD"
CEO_AUTOPILOT_FINE_GRAINED_WORKFLOW_PROFILE = "CEO_AUTOPILOT_FINE_GRAINED"
WORKFLOW_CHAIN_REPORT_NODE_ID = "node_workflow_chain_report"


def workflow_uses_ceo_board_delegate(workflow: dict[str, object] | None) -> bool:
    if workflow is None:
        return False
    return str(workflow.get("workflow_profile") or STANDARD_WORKFLOW_PROFILE) == (
        CEO_AUTOPILOT_FINE_GRAINED_WORKFLOW_PROFILE
    )


def _approval_selected_option_id(approval: dict[str, Any]) -> str:
    payload = approval.get("payload") or {}
    review_pack = payload.get("review_pack") or {}
    recommendation = review_pack.get("recommendation") or {}
    if str(recommendation.get("recommended_option_id") or "").strip():
        return str(recommendation["recommended_option_id"])
    draft_defaults = payload.get("draft_defaults") or {}
    if str(draft_defaults.get("selected_option_id") or "").strip():
        return str(draft_defaults["selected_option_id"])
    options = review_pack.get("options") or []
    option_id = str((options[0] or {}).get("option_id") or "").strip() if options else ""
    if option_id:
        return option_id
    raise ValueError("Approval is missing an option_id for CEO delegated approval.")


def _default_elicitation_answers() -> list[ElicitationAnswer]:
    return [
        ElicitationAnswer(
            question_id="delivery_scope",
            selected_option_ids=["scope_mvp_slice"],
            text="",
        ),
        ElicitationAnswer(
            question_id="core_roles",
            selected_option_ids=[
                "role_frontend_engineer",
                "role_checker",
            ],
            text="",
        ),
        ElicitationAnswer(
            question_id="quality_bar",
            selected_option_ids=["quality_board_review_ready"],
            text="",
        ),
        ElicitationAnswer(
            question_id="hard_boundaries",
            selected_option_ids=[],
            text="保持审计链路完整，优先交付可演示、可检查、可归档的作品。",
        ),
    ]


def _approval_elicitation_answers(approval: dict[str, Any]) -> list[ElicitationAnswer]:
    payload = approval.get("payload") or {}
    draft_defaults = payload.get("draft_defaults") or {}
    raw_answers = list(draft_defaults.get("elicitation_answers") or [])
    if raw_answers:
        return [ElicitationAnswer.model_validate(item) for item in raw_answers]
    return _default_elicitation_answers()


def build_ceo_delegate_board_approval_command(
    approval: dict[str, Any],
    *,
    idempotency_key_prefix: str,
) -> BoardApproveCommand:
    approval_id = str(approval["approval_id"])
    return BoardApproveCommand(
        review_pack_id=str(approval["review_pack_id"]),
        review_pack_version=int(approval["review_pack_version"]),
        command_target_version=int(approval["command_target_version"]),
        approval_id=approval_id,
        selected_option_id=_approval_selected_option_id(approval),
        board_comment="CEO 代董事会自动批准当前项目，继续主线执行。",
        elicitation_answers=_approval_elicitation_answers(approval)
        if str(approval.get("approval_type") or "") == "REQUIREMENT_ELICITATION"
        else [],
        idempotency_key=f"{idempotency_key_prefix}:{approval_id}",
    )


def workflow_chain_report_artifact_ref(workflow_id: str) -> str:
    return f"art://workflow-chain/{workflow_id}/workflow-chain-report.json"


def workflow_chain_report_logical_path(workflow_id: str) -> str:
    return f"reports/workflow-chain/{workflow_id}/workflow-chain-report.json"


def _extract_atomic_task_title(created_spec: dict[str, Any]) -> str:
    acceptance_criteria = list(created_spec.get("acceptance_criteria") or [])
    prefix = "Must complete this atomic task: "
    if acceptance_criteria and isinstance(acceptance_criteria[0], str) and acceptance_criteria[0].startswith(prefix):
        return acceptance_criteria[0][len(prefix) :].strip()
    return str(created_spec.get("summary") or created_spec.get("ticket_id") or "").strip()


def _serialize_timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def _workflow_closeout_state(
    repository,
    *,
    workflow_id: str,
    connection,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    ticket_rows = connection.execute(
        """
        SELECT * FROM ticket_projection
        WHERE workflow_id = ?
        ORDER BY updated_at ASC, ticket_id ASC
        """,
        (workflow_id,),
    ).fetchall()
    open_approval_count = int(
        connection.execute(
            "SELECT COUNT(*) AS total FROM approval_projection WHERE workflow_id = ? AND status = ?",
            (workflow_id, "OPEN"),
        ).fetchone()["total"]
    )
    open_incident_count = int(
        connection.execute(
            "SELECT COUNT(*) AS total FROM incident_projection WHERE workflow_id = ? AND status = ?",
            (workflow_id, "OPEN"),
        ).fetchone()["total"]
    )
    tickets = [repository._convert_ticket_projection_row(row) for row in ticket_rows]
    graph_snapshot = build_ticket_graph_snapshot(
        repository,
        workflow_id,
        connection=connection,
    )
    nodes = [
        {
            "node_id": str(node.node_id or node.runtime_node_id or ""),
            "status": str(node.node_status or "").strip(),
        }
        for node in graph_snapshot.nodes
    ]
    created_specs_by_ticket = {
        str(ticket["ticket_id"]): repository.get_latest_ticket_created_payload(connection, str(ticket["ticket_id"])) or {}
        for ticket in tickets
    }
    ticket_terminal_events_by_ticket = {
        str(ticket["ticket_id"]): repository.get_latest_ticket_terminal_event(connection, str(ticket["ticket_id"]))
        for ticket in tickets
    }
    completion = resolve_workflow_closeout_completion(
        tickets=tickets,
        nodes=nodes,
        has_open_approval=open_approval_count > 0,
        has_open_incident=open_incident_count > 0,
        created_specs_by_ticket=created_specs_by_ticket,
        ticket_terminal_events_by_ticket=ticket_terminal_events_by_ticket,
    )
    if completion is None:
        return None
    return completion.closeout_ticket, completion.closeout_terminal_event


def build_human_readable_workflow_report(repository, *, workflow_id: str) -> dict[str, Any] | None:
    repository.initialize()
    workflow = repository.get_workflow_projection(workflow_id)
    if workflow is None:
        return None

    with repository.connection() as connection:
        closeout_state = _workflow_closeout_state(
            repository,
            workflow_id=workflow_id,
            connection=connection,
        )
        if closeout_state is None:
            return None
        closeout_ticket, closeout_terminal_event = closeout_state

        ticket_rows = connection.execute(
            """
            SELECT * FROM ticket_projection
            WHERE workflow_id = ?
            ORDER BY updated_at ASC, ticket_id ASC
            """,
            (workflow_id,),
        ).fetchall()
        approval_rows = connection.execute(
            """
            SELECT * FROM approval_projection
            WHERE workflow_id = ?
            ORDER BY created_at ASC, approval_id ASC
            """,
            (workflow_id,),
        ).fetchall()
        tickets = [repository._convert_ticket_projection_row(row) for row in ticket_rows]
        approvals = [repository._convert_approval_row(row) for row in approval_rows]

        governance_chain: list[dict[str, Any]] = []
        atomic_tasks: list[dict[str, Any]] = []
        for ticket in tickets:
            ticket_id = str(ticket["ticket_id"])
            created_spec = repository.get_latest_ticket_created_payload(connection, ticket_id) or {}
            if not created_spec:
                continue

            output_schema_ref = str(created_spec.get("output_schema_ref") or "")
            delivery_stage = str(created_spec.get("delivery_stage") or "")
            dispatch_intent = created_spec.get("dispatch_intent") or {}
            artifact_refs = [
                str(artifact.get("artifact_ref") or "")
                for artifact in repository.list_ticket_artifacts(ticket_id, connection=connection)
                if str(artifact.get("artifact_ref") or "").strip()
            ]
            terminal_event = repository.get_latest_ticket_terminal_event(connection, ticket_id) or {}
            completion_payload = terminal_event.get("payload") or {}

            if output_schema_ref in {
                "architecture_brief",
                "technology_decision",
                "milestone_plan",
                "detailed_design",
                "backlog_recommendation",
                "consensus_document",
            }:
                governance_chain.append(
                    {
                        "ticket_id": ticket_id,
                        "node_id": str(ticket["node_id"]),
                        "document_kind_ref": output_schema_ref,
                        "status": str(ticket["status"]),
                        "summary": str(created_spec.get("summary") or ""),
                    }
                )

            if delivery_stage or dispatch_intent:
                atomic_tasks.append(
                    {
                        "ticket_id": ticket_id,
                        "node_id": str(ticket["node_id"]),
                        "task_title": _extract_atomic_task_title(created_spec),
                        "summary": str(created_spec.get("summary") or ""),
                        "delivery_stage": delivery_stage,
                        "role_profile_ref": str(created_spec.get("role_profile_ref") or ""),
                        "assignee_employee_id": str(dispatch_intent.get("assignee_employee_id") or ""),
                        "dependency_gate_refs": [
                            str(item)
                            for item in list(dispatch_intent.get("dependency_gate_refs") or [])
                            if str(item).strip()
                        ],
                        "status": str(ticket["status"]),
                        "artifact_refs": artifact_refs,
                        "completion_summary": str(completion_payload.get("completion_summary") or ""),
                    }
                )

    closeout_payload = closeout_terminal_event.get("payload") or {}
    closeout_artifact_refs = list(closeout_payload.get("artifact_refs") or [])
    approval_items = [
        {
            "approval_type": str(approval["approval_type"]),
            "status": str(approval["status"]),
            "resolved_by": str(approval.get("resolved_by") or ""),
            "review_pack_id": str(approval.get("review_pack_id") or ""),
        }
        for approval in approvals
    ]
    sections = [
        {
            "section_id": "project_overview",
            "title": "项目概览",
            "summary": "该报告梳理了自动驾驶 workflow 的治理、原子任务执行与最终交付结果。",
            "items": [
                f"项目目标：{workflow['north_star_goal']}",
                f"工作流模式：{workflow.get('workflow_profile') or STANDARD_WORKFLOW_PROFILE}",
                f"总票据数：{len(tickets)}",
                f"总审批数：{len(approvals)}",
                f"Closeout 票据：{closeout_ticket['ticket_id']}",
            ],
        },
        {
            "section_id": "governance_chain",
            "title": "治理链路",
            "summary": "先澄清需求，再进入治理文档与审批链。",
            "items": [
                f"{item['document_kind_ref']} / {item['ticket_id']} / {item['status']} / {item['summary']}"
                for item in governance_chain
            ],
        },
        {
            "section_id": "atomic_execution_chain",
            "title": "原子任务链",
            "summary": "下面列出实际创建的原子任务、指派对象、依赖关系与完成情况。",
            "items": [
                (
                    f"{item['task_title']} / {item['ticket_id']} / 阶段 {item['delivery_stage'] or 'N/A'} / "
                    f"指派给 {item['assignee_employee_id'] or '未固定'} / "
                    f"依赖 {', '.join(item['dependency_gate_refs']) or '无'} / 状态 {item['status']}"
                )
                for item in atomic_tasks
            ],
        },
        {
            "section_id": "delivery_outcome",
            "title": "最终交付",
            "summary": "工作流已完成 closeout，下面是最终交付与审计留痕。",
            "items": [
                f"最终 closeout 工件：{', '.join(closeout_artifact_refs) or '无'}",
                f"Closeout 完成时间：{_serialize_timestamp(closeout_terminal_event.get('occurred_at')) or '未知'}",
            ],
        },
    ]
    return {
        "workflow_id": workflow_id,
        "workflow_profile": workflow.get("workflow_profile") or STANDARD_WORKFLOW_PROFILE,
        "generated_at": _serialize_timestamp(datetime.now(tz=workflow["updated_at"].tzinfo) if workflow.get("updated_at") else None),
        "sections": sections,
        "governance_chain": governance_chain,
        "approvals": approval_items,
        "atomic_tasks": atomic_tasks,
        "final_delivery": {
            "closeout_ticket_id": str(closeout_ticket["ticket_id"]),
            "closeout_artifact_refs": closeout_artifact_refs,
            "closeout_completed_at": _serialize_timestamp(closeout_terminal_event.get("occurred_at")),
        },
    }


def ensure_workflow_atomic_chain_report(repository, *, workflow_id: str) -> str | None:
    repository.initialize()
    workflow = repository.get_workflow_projection(workflow_id)
    if not workflow_uses_ceo_board_delegate(workflow):
        return None

    artifact_ref = workflow_chain_report_artifact_ref(workflow_id)
    if repository.get_artifact_by_ref(artifact_ref) is not None:
        return artifact_ref

    report = build_human_readable_workflow_report(repository, workflow_id=workflow_id)
    if report is None:
        return None

    artifact_store = repository.artifact_store
    if artifact_store is None:
        return None

    logical_path = workflow_chain_report_logical_path(workflow_id)
    materialized = artifact_store.materialize_json(
        logical_path,
        report,
        workflow_id=workflow_id,
        ticket_id=str(report["final_delivery"]["closeout_ticket_id"]),
        artifact_ref=artifact_ref,
    )
    created_at = datetime.fromisoformat(str(report["generated_at"])) if report.get("generated_at") else datetime.now()
    with repository.transaction() as connection:
        repository.save_artifact_record(
            connection,
            artifact_ref=artifact_ref,
            workflow_id=workflow_id,
            ticket_id=str(report["final_delivery"]["closeout_ticket_id"]),
            node_id=WORKFLOW_CHAIN_REPORT_NODE_ID,
            logical_path=logical_path,
            kind="JSON",
            media_type="application/json",
            materialization_status="MATERIALIZED",
            lifecycle_status="ACTIVE",
            storage_backend=materialized.storage_backend,
            storage_relpath=materialized.storage_relpath,
            storage_object_key=materialized.storage_object_key,
            storage_delete_status=materialized.storage_delete_status,
            storage_delete_error=None,
            content_hash=materialized.content_hash,
            size_bytes=materialized.size_bytes,
            retention_class="PERSISTENT",
            retention_class_source="explicit",
            retention_ttl_sec=None,
            retention_policy_source="explicit_class",
            expires_at=None,
            deleted_at=None,
            deleted_by=None,
            delete_reason=None,
            created_at=created_at,
        )
    return artifact_ref
