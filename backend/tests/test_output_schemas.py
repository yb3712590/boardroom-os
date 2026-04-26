from __future__ import annotations

import pytest

from app.core.output_schemas import (
    ARCHITECTURE_BRIEF_SEGMENT_SCHEMA_REF,
    ARCHITECTURE_BRIEF_SEGMENT_SCHEMA_VERSION,
    DECOMPOSITION_PLAN_SCHEMA_REF,
    DECOMPOSITION_PLAN_SCHEMA_VERSION,
    get_output_schema_body,
    validate_output_payload,
)


def _iter_object_schemas(schema: object, *, path: str = "$"):
    if isinstance(schema, dict):
        schema_type = schema.get("type")
        if schema_type == "object":
            yield path, schema
        for key, value in schema.items():
            child_path = f"{path}.{key}" if path != "$" else f"$.{key}"
            yield from _iter_object_schemas(value, path=child_path)
    elif isinstance(schema, list):
        for index, item in enumerate(schema):
            yield from _iter_object_schemas(item, path=f"{path}[{index}]")


def _backlog_recommendation_implementation_handoff() -> dict[str, object]:
    return {
        "tickets": [
            {
                "ticket_id": "BR-T01",
                "name": "Implement the scoped delivery foundation",
                "summary": "Build the smallest implementation slice that satisfies the approved scope.",
                "scope": ["workspace source update", "direct validation evidence"],
                "target_role": "frontend_engineer",
            },
            {
                "ticket_id": "BR-T02",
                "name": "Close the delivery evidence loop",
                "summary": "Verify the implementation and preserve the evidence chain for closeout.",
                "scope": ["verification report", "handoff evidence"],
                "target_role": "frontend_engineer",
            },
        ],
        "dependency_graph": [
            {"ticket_id": "BR-T01", "depends_on": []},
            {"ticket_id": "BR-T02", "depends_on": ["BR-T01"]},
        ],
        "recommended_sequence": ["BR-T01", "BR-T02"],
    }


def _governance_document_payload(document_kind_ref: str) -> dict[str, object]:
    payload = {
        "title": f"{document_kind_ref} for Boardroom OS",
        "summary": f"{document_kind_ref} keeps the next delivery slice aligned.",
        "document_kind_ref": document_kind_ref,
        "linked_document_refs": ["doc://governance/technology-decision/current"],
        "linked_artifact_refs": ["art://inputs/board-brief.md"],
        "source_process_asset_refs": ["pa://artifact/art%3A%2F%2Finputs%2Fboard-brief.md"],
        "decisions": [
            "Keep the next slice inside the current local MVP boundary.",
            "Preserve explicit governance between board review and worker execution.",
        ],
        "constraints": [
            "Do not widen into remote handoff.",
            "Keep React as a thin governance shell.",
        ],
        "sections": [
            {
                "section_id": "sec_context",
                "label": "Context",
                "summary": "Current boundary and rationale.",
                "content_markdown": "## Context\n\nKeep the scope narrow and auditable.",
            }
        ],
        "followup_recommendations": [
            {
                "recommendation_id": "rec_followup_build",
                "summary": "Prepare the next implementation ticket without widening scope.",
                "target_role": "frontend_engineer",
            }
        ],
    }
    if document_kind_ref == "backlog_recommendation":
        payload["implementation_handoff"] = _backlog_recommendation_implementation_handoff()
    return payload


def test_output_schema_registry_exposes_consensus_document_schema() -> None:
    schema = get_output_schema_body("consensus_document", 1)

    assert schema["type"] == "object"
    assert "topic" in schema["required"]
    assert "participants" in schema["required"]
    assert "followup_tickets" not in schema["required"]
    assert "followup_tickets" not in schema["properties"]


def test_output_schema_registry_marks_structured_objects_as_closed_for_openai_strict_mode() -> None:
    schema_refs = [
        "ui_milestone_review",
        "consensus_document",
        "architecture_brief",
        "technology_decision",
        "milestone_plan",
        "detailed_design",
        "backlog_recommendation",
        "source_code_delivery",
        "delivery_check_report",
        "delivery_closeout_package",
        "maker_checker_verdict",
        "architecture_brief_segment",
    ]

    for schema_ref in schema_refs:
        schema = get_output_schema_body(schema_ref, 1)
        object_paths = list(_iter_object_schemas(schema))
        assert object_paths, f"{schema_ref} should expose at least one structured object schema"
        for path, object_schema in object_paths:
            assert object_schema.get("additionalProperties") is False, (
                f"{schema_ref} schema object {path} must set additionalProperties to false"
            )
            properties = object_schema.get("properties")
            if isinstance(properties, dict):
                required = object_schema.get("required")
                assert isinstance(required, list), (
                    f"{schema_ref} schema object {path} must expose required as a list"
                )
            assert set(required) == set(properties.keys()), (
                f"{schema_ref} schema object {path} must require every declared property for OpenAI strict mode"
            )


def test_output_schema_registry_accepts_valid_architecture_brief_segment_payload() -> None:
    validate_output_payload(
        schema_ref=ARCHITECTURE_BRIEF_SEGMENT_SCHEMA_REF,
        schema_version=ARCHITECTURE_BRIEF_SEGMENT_SCHEMA_VERSION,
        submitted_schema_version="architecture_brief_segment_v1",
        payload={
            "segment_id": "scope_and_goals_brief",
            "summary": "Scope is limited to the first auditable architecture brief slice.",
            "findings": ["The workflow must remain replayable without provider hidden state."],
            "decisions": ["Keep chunk state in tickets and artifacts only."],
            "open_questions": [],
            "artifact_refs": ["art://project-init/wf_demo/board-brief.md"],
        },
    )


def test_output_schema_registry_rejects_architecture_brief_segment_missing_artifact_refs() -> None:
    with pytest.raises(ValueError, match="artifact_refs"):
        validate_output_payload(
            schema_ref=ARCHITECTURE_BRIEF_SEGMENT_SCHEMA_REF,
            schema_version=ARCHITECTURE_BRIEF_SEGMENT_SCHEMA_VERSION,
            submitted_schema_version="architecture_brief_segment_v1",
            payload={
                "segment_id": "scope_and_goals_brief",
                "summary": "Scope is explicit.",
                "findings": ["Replayable ticket state is required."],
                "decisions": ["Persist segment output as an artifact."],
                "open_questions": [],
            },
        )


def test_output_schema_registry_accepts_valid_decomposition_plan_payload() -> None:
    validate_output_payload(
        schema_ref=DECOMPOSITION_PLAN_SCHEMA_REF,
        schema_version=DECOMPOSITION_PLAN_SCHEMA_VERSION,
        submitted_schema_version="decomposition_plan_v1",
        payload={
            "plan_id": "decomp_wf_demo_architecture_brief",
            "decision_kind": "DECOMPOSE_NOW",
            "reason": "CEO determined the request spans independent architecture concerns.",
            "evidence_refs": ["art://project-init/wf_demo/board-brief.md"],
            "target_output_schema_ref": "architecture_brief",
            "target_output_schema_version": 1,
            "uses_provider_hidden_state": False,
            "final_output_schema_ref": "architecture_brief",
            "final_output_schema_version": 1,
            "segment_output_schema_ref": "architecture_brief_segment",
            "segment_output_schema_version": 1,
            "role_profile_ref": "architect_primary",
            "segments": [
                {
                    "segment_id": "scope",
                    "ticket_id": "tkt_wf_demo_ceo_scope",
                    "node_id": "node_ceo_scope",
                    "summary": "Clarify scope and goals.",
                    "input_artifact_refs": ["art://project-init/wf_demo/board-brief.md"],
                    "acceptance_criteria": ["Produce an auditable scope segment artifact."],
                    "artifact_ref": "art://runtime/tkt_wf_demo_ceo_scope/architecture_brief_segment.json",
                    "artifact_path": "reports/governance/tkt_wf_demo_ceo_scope/architecture_brief_segment.json",
                }
            ],
            "aggregator": {
                "ticket_id": "tkt_wf_demo_ceo_architecture_brief",
                "node_id": "node_ceo_architecture_brief",
                "summary": "Synthesize final architecture brief from segment artifacts.",
                "role_profile_ref": "architect_primary",
                "input_artifact_refs": [
                    "art://project-init/wf_demo/board-brief.md",
                    "art://runtime/tkt_wf_demo_ceo_scope/architecture_brief_segment.json",
                ],
                "acceptance_criteria": ["Reduce all segment artifacts into the final architecture_brief."],
                "artifact_path": "reports/governance/tkt_wf_demo_ceo_architecture_brief/architecture_brief.json",
                "dependency_policy": "all_segments_complete",
                "reduce_instructions": "Read every segment artifact and synthesize the final schema without hidden state.",
            },
        },
    )


def test_output_schema_registry_rejects_decomposition_plan_with_provider_hidden_state() -> None:
    with pytest.raises(ValueError, match="provider hidden state"):
        validate_output_payload(
            schema_ref=DECOMPOSITION_PLAN_SCHEMA_REF,
            schema_version=DECOMPOSITION_PLAN_SCHEMA_VERSION,
            submitted_schema_version="decomposition_plan_v1",
            payload={
                "plan_id": "decomp_wf_demo_architecture_brief",
                "decision_kind": "DECOMPOSE_NOW",
                "reason": "CEO determined the request is too large.",
                "evidence_refs": ["art://project-init/wf_demo/board-brief.md"],
                "target_output_schema_ref": "architecture_brief",
                "target_output_schema_version": 1,
                "uses_provider_hidden_state": True,
                "final_output_schema_ref": "architecture_brief",
                "final_output_schema_version": 1,
                "segment_output_schema_ref": "architecture_brief_segment",
                "segment_output_schema_version": 1,
                "role_profile_ref": "architect_primary",
                "segments": [],
                "aggregator": {},
            },
        )


def test_output_schema_registry_accepts_valid_consensus_document_payload() -> None:
    validate_output_payload(
        schema_ref="consensus_document",
        schema_version=1,
        submitted_schema_version="consensus_document_v1",
        payload={
            "topic": "Resolve homepage interaction conflict",
            "participants": ["emp_frontend_2", "emp_checker_1"],
            "input_artifact_refs": ["art://inputs/brief.md"],
            "consensus_summary": "Use the stronger hierarchy with a simplified motion pass.",
            "rejected_options": ["full-motion-hero"],
            "open_questions": [],
            "decision_record": {
                "format": "ADR_V1",
                "context": "Homepage contract choice is blocking the next implementation round.",
                "decision": "Lock the narrower runtime contract for MVP delivery.",
                "rationale": [
                    "It keeps the current board review scope stable.",
                    "It avoids reopening remote handoff in the MVP path.",
                ],
                "consequences": [
                    "Implementation tickets must stay inside the narrowed contract.",
                    "Deferred alternatives can return through a later governance ticket.",
                ],
                "archived_context_refs": ["art://runtime/tkt_meeting_001/meeting-digest.json"],
            },
        },
    )


def test_output_schema_registry_accepts_valid_source_code_delivery_with_documentation_updates() -> None:
    validate_output_payload(
        schema_ref="source_code_delivery",
        schema_version=1,
        submitted_schema_version="source_code_delivery_v1",
        payload={
            "summary": "Prepared one source code delivery package.",
            "source_file_refs": ["art://workspace/tkt_impl_001/source.ts"],
            "source_files": [
                {
                    "artifact_ref": "art://workspace/tkt_impl_001/source.ts",
                    "path": "10-project/src/tkt_impl_001.ts",
                    "content": "export const buildReady = true;\n",
                }
            ],
            "verification_runs": [
                {
                    "artifact_ref": "art://workspace/tkt_impl_001/test-report.json",
                    "path": "20-evidence/tests/tkt_impl_001/attempt-1/test-report.json",
                    "runner": "pytest",
                    "command": "pytest tests/test_project_workspace_hooks.py -q",
                    "status": "passed",
                    "exit_code": 0,
                    "duration_sec": 1.2,
                    "stdout": "collected 1 item\n\n1 passed in 0.12s\n",
                    "stderr": "",
                    "discovered_count": 1,
                    "passed_count": 1,
                    "failed_count": 0,
                    "skipped_count": 0,
                    "failures": [],
                }
            ],
            "implementation_notes": ["Kept the scope inside the approved MVP slice."],
            "documentation_updates": [
                {
                    "doc_ref": "10-project/docs/tracking/active-tasks.md",
                    "status": "UPDATED",
                    "summary": "Recorded the ticket outcome in active tasks.",
                },
                {
                    "doc_ref": "10-project/docs/history/memory-recent.md",
                    "status": "NO_CHANGE_REQUIRED",
                    "summary": "No new cross-ticket memory had to be recorded.",
                },
            ],
        },
    )


def test_output_schema_registry_rejects_invalid_consensus_document_payload() -> None:
    with pytest.raises(ValueError, match="participants must be a non-empty array"):
        validate_output_payload(
            schema_ref="consensus_document",
            schema_version=1,
            submitted_schema_version="consensus_document_v1",
            payload={
                "topic": "Resolve homepage interaction conflict",
                "participants": [],
            },
        )


def test_output_schema_registry_rejects_invalid_consensus_document_decision_record() -> None:
    with pytest.raises(ValueError, match="decision_record"):
        validate_output_payload(
            schema_ref="consensus_document",
            schema_version=1,
            submitted_schema_version="consensus_document_v1",
            payload={
                "topic": "Resolve homepage interaction conflict",
                "participants": ["emp_frontend_2", "emp_checker_1"],
                "decision_record": {
                    "format": "ADR_V1",
                    "context": "",
                    "decision": "Use the narrowed runtime contract.",
                    "rationale": ["Reduce scope drift."],
                    "consequences": ["Implementation follows the locked contract."],
                    "archived_context_refs": ["art://runtime/tkt_meeting_001/meeting-digest.json"],
                },
            },
        )


def test_output_schema_registry_rejects_legacy_consensus_followup_tickets_field() -> None:
    with pytest.raises(ValueError, match="followup_tickets"):
        validate_output_payload(
            schema_ref="consensus_document",
            schema_version=1,
            submitted_schema_version="consensus_document_v1",
            payload={
                "topic": "Resolve homepage interaction conflict",
                "participants": ["emp_frontend_2", "emp_checker_1"],
                "followup_tickets": [
                    {
                        "ticket_id": "tkt_followup_001",
                        "task_title": "实现首页基础版",
                        "summary": "Implement approved homepage direction",
                    }
                ],
            },
        )


def test_output_schema_registry_exposes_maker_checker_verdict_schema() -> None:
    schema = get_output_schema_body("maker_checker_verdict", 1)

    assert schema["type"] == "object"
    assert "summary" in schema["required"]
    assert "review_status" in schema["required"]
    assert "findings" in schema["required"]


def test_output_schema_registry_accepts_valid_maker_checker_verdict_payload() -> None:
    validate_output_payload(
        schema_ref="maker_checker_verdict",
        schema_version=1,
        submitted_schema_version="maker_checker_verdict_v1",
        payload={
            "summary": "Checker approved the visual milestone with one non-blocking note.",
            "review_status": "APPROVED_WITH_NOTES",
            "findings": [
                {
                    "finding_id": "finding_cta_spacing",
                    "severity": "low",
                    "category": "VISUAL_POLISH",
                    "headline": "CTA spacing can be tightened slightly.",
                    "summary": "Current CTA spacing is acceptable but leaves room for polish.",
                    "required_action": "Tighten CTA spacing during downstream implementation.",
                    "blocking": False,
                }
            ],
        },
    )


def test_output_schema_registry_rejects_changes_required_without_blocking_finding() -> None:
    with pytest.raises(ValueError, match="blocking"):
        validate_output_payload(
            schema_ref="maker_checker_verdict",
            schema_version=1,
            submitted_schema_version="maker_checker_verdict_v1",
            payload={
                "summary": "Checker requires changes before the board sees this milestone.",
                "review_status": "CHANGES_REQUIRED",
                "findings": [
                    {
                        "finding_id": "finding_weak_hierarchy",
                        "severity": "high",
                        "category": "VISUAL_HIERARCHY",
                        "headline": "Visual hierarchy is still weak.",
                        "summary": "The hero does not establish clear first-screen priority.",
                        "required_action": "Strengthen the hero hierarchy before resubmitting.",
                        "blocking": False,
                    }
                ],
            },
        )


def test_output_schema_registry_exposes_source_code_delivery_schema() -> None:
    schema = get_output_schema_body("source_code_delivery", 1)

    assert schema["type"] == "object"
    assert "summary" in schema["required"]
    assert "source_file_refs" in schema["required"]


def test_output_schema_registry_accepts_valid_source_code_delivery_payload() -> None:
    validate_output_payload(
        schema_ref="source_code_delivery",
        schema_version=1,
        submitted_schema_version="source_code_delivery_v1",
        payload={
            "summary": "Homepage source code delivery is ready for internal checking.",
            "source_file_refs": [
                "art://workspace/tkt_followup_scope_build/homepage.tsx",
                "art://workspace/tkt_followup_scope_build/header.tsx",
            ],
            "source_files": [
                {
                    "artifact_ref": "art://workspace/tkt_followup_scope_build/homepage.tsx",
                    "path": "10-project/src/homepage.tsx",
                    "content": "export function Homepage() {\n  return <main>Boardroom</main>;\n}\n",
                },
                {
                    "artifact_ref": "art://workspace/tkt_followup_scope_build/header.tsx",
                    "path": "10-project/src/header.tsx",
                    "content": "export function Header() {\n  return <header>Boardroom</header>;\n}\n",
                },
            ],
            "verification_runs": [
                {
                    "artifact_ref": "art://workspace/tkt_followup_scope_build/test-report.json",
                    "path": "20-evidence/tests/tkt_followup_scope_build/attempt-1/test-report.json",
                    "runner": "vitest",
                    "command": "npm run test -- --runInBand",
                    "status": "passed",
                    "exit_code": 0,
                    "duration_sec": 2.4,
                    "stdout": " RUN  v1.0.0\n  ✓ homepage renders\n\n Test Files  1 passed\n",
                    "stderr": "",
                    "discovered_count": 1,
                    "passed_count": 1,
                    "failed_count": 0,
                    "skipped_count": 0,
                    "failures": [],
                }
            ],
            "implementation_notes": ["Hero layout and CTA hierarchy now follow the approved scope lock."],
        },
    )


def test_output_schema_registry_accepts_source_code_delivery_with_stderr_raw_output() -> None:
    validate_output_payload(
        schema_ref="source_code_delivery",
        schema_version=1,
        submitted_schema_version="source_code_delivery_v1",
        payload={
            "summary": "Backend source code delivery captured a failing regression trace.",
            "source_file_refs": ["art://workspace/tkt_impl_001/source.py"],
            "source_files": [
                {
                    "artifact_ref": "art://workspace/tkt_impl_001/source.py",
                    "path": "10-project/src/tkt_impl_001.py",
                    "content": "def build_ready():\n    return True\n",
                }
            ],
            "verification_runs": [
                {
                    "artifact_ref": "art://workspace/tkt_impl_001/test-report.json",
                    "path": "20-evidence/tests/tkt_impl_001/attempt-2/test-report.json",
                    "runner": "pytest",
                    "command": "pytest -q",
                    "status": "failed",
                    "exit_code": 1,
                    "duration_sec": 0.5,
                    "stdout": "",
                    "stderr": "AssertionError: regression failed\n",
                    "discovered_count": 1,
                    "passed_count": 0,
                    "failed_count": 1,
                    "skipped_count": 0,
                    "failures": [],
                }
            ],
        },
    )


def test_output_schema_registry_rejects_source_code_delivery_without_source_files() -> None:
    with pytest.raises(ValueError, match="source_file_refs"):
        validate_output_payload(
            schema_ref="source_code_delivery",
            schema_version=1,
            submitted_schema_version="source_code_delivery_v1",
            payload={
                "summary": "Missing source files should fail schema validation.",
                "source_file_refs": [],
            },
        )


def test_output_schema_registry_rejects_source_code_delivery_without_source_file_bodies() -> None:
    with pytest.raises(ValueError, match="source_files"):
        validate_output_payload(
            schema_ref="source_code_delivery",
            schema_version=1,
            submitted_schema_version="source_code_delivery_v1",
            payload={
                "summary": "Missing source file bodies should fail schema validation.",
                "source_file_refs": ["art://workspace/tkt_impl_001/source.ts"],
                "verification_runs": [
                    {
                        "artifact_ref": "art://workspace/tkt_impl_001/test-report.json",
                        "path": "20-evidence/tests/tkt_impl_001/attempt-1/test-report.json",
                        "runner": "pytest",
                        "command": "pytest tests/test_project_workspace_hooks.py -q",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_sec": 0.5,
                        "stdout": "1 passed in 0.05s\n",
                        "stderr": "",
                        "discovered_count": 1,
                        "passed_count": 1,
                        "failed_count": 0,
                        "skipped_count": 0,
                        "failures": [],
                    }
                ],
            },
        )


def test_output_schema_registry_rejects_source_code_delivery_without_verification_runs() -> None:
    with pytest.raises(ValueError, match="verification_runs"):
        validate_output_payload(
            schema_ref="source_code_delivery",
            schema_version=1,
            submitted_schema_version="source_code_delivery_v1",
            payload={
                "summary": "Missing verification runs should fail schema validation.",
                "source_file_refs": ["art://workspace/tkt_impl_001/source.ts"],
                "source_files": [
                    {
                        "artifact_ref": "art://workspace/tkt_impl_001/source.ts",
                        "path": "10-project/src/tkt_impl_001.ts",
                        "content": "export const buildReady = true;\n",
                    }
                ],
            },
        )


def test_output_schema_registry_rejects_source_code_delivery_with_placeholder_source_content() -> None:
    with pytest.raises(ValueError) as exc_info:
        validate_output_payload(
            schema_ref="source_code_delivery",
            schema_version=1,
            submitted_schema_version="source_code_delivery_v1",
            payload={
                "summary": "Placeholder source content should fail schema validation.",
                "source_file_refs": ["art://workspace/tkt_impl_001/source.ts"],
                "source_files": [
                    {
                        "artifact_ref": "art://workspace/tkt_impl_001/source.ts",
                        "path": "10-project/src/source.ts",
                        "content": "export const runtimeSourceDelivery = true;\n",
                    }
                ],
                "verification_runs": [
                    {
                        "artifact_ref": "art://workspace/tkt_impl_001/test-report.json",
                        "path": "20-evidence/tests/tkt_impl_001/attempt-1/test-report.json",
                        "runner": "pytest",
                        "command": "pytest tests/test_project_workspace_hooks.py -q",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_sec": 0.5,
                        "stdout": "1 passed in 0.05s\n",
                        "stderr": "",
                        "discovered_count": 1,
                        "passed_count": 1,
                        "failed_count": 0,
                        "skipped_count": 0,
                        "failures": [],
                    }
                ],
            },
        )
    assert getattr(exc_info.value, "field_path", None) == "source_files[0].content"


def test_output_schema_registry_rejects_source_code_delivery_with_minimal_verification_stub() -> None:
    with pytest.raises(ValueError) as exc_info:
        validate_output_payload(
            schema_ref="source_code_delivery",
            schema_version=1,
            submitted_schema_version="source_code_delivery_v1",
            payload={
                "summary": "Minimal self-reported verification should fail schema validation.",
                "source_file_refs": ["art://workspace/tkt_impl_001/source.ts"],
                "source_files": [
                    {
                        "artifact_ref": "art://workspace/tkt_impl_001/source.ts",
                        "path": "10-project/src/tkt_impl_001.ts",
                        "content": "export const buildReady = true;\n",
                    }
                ],
                "verification_runs": [
                    {
                        "artifact_ref": "art://workspace/tkt_impl_001/test-report.json",
                        "path": "20-evidence/tests/tkt_impl_001/attempt-1/test-report.json",
                        "runner": "pytest",
                        "command": "pytest -q",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_sec": 0.1,
                        "stdout": "",
                        "stderr": "",
                        "discovered_count": 0,
                        "passed_count": 0,
                        "failed_count": 0,
                        "skipped_count": 0,
                        "failures": [],
                    }
                ],
            },
        )
    assert getattr(exc_info.value, "field_path", None) == "verification_runs[0].raw_output"


def test_output_schema_registry_exposes_delivery_check_report_schema() -> None:
    schema = get_output_schema_body("delivery_check_report", 1)

    assert schema["type"] == "object"
    assert "summary" in schema["required"]
    assert "status" in schema["required"]
    assert "findings" in schema["required"]


def test_output_schema_registry_accepts_valid_delivery_check_report_payload() -> None:
    validate_output_payload(
        schema_ref="delivery_check_report",
        schema_version=1,
        submitted_schema_version="delivery_check_report_v1",
        payload={
            "summary": "Internal check confirmed the implementation still stays inside the approved scope.",
            "status": "PASS_WITH_NOTES",
            "findings": [
                {
                    "finding_id": "finding_scope_copy",
                    "summary": "Keep the launch copy trimmed to the approved scope.",
                    "blocking": False,
                }
            ],
        },
    )


def test_output_schema_registry_accepts_valid_delivery_closeout_package_payload_with_documentation_updates() -> None:
    validate_output_payload(
        schema_ref="delivery_closeout_package",
        schema_version=1,
        submitted_schema_version="delivery_closeout_package_v1",
        payload={
            "summary": "Delivery closeout package is ready for internal review.",
            "final_artifact_refs": ["art://runtime/tkt_closeout_001/delivery-closeout-package.json"],
            "handoff_notes": [
                "Board-approved final option is captured in this closeout package.",
                "Final evidence remains linked back to the board review pack.",
            ],
            "documentation_updates": [
                {
                    "doc_ref": "doc/TODO.md",
                    "status": "UPDATED",
                    "summary": "Marked P2-GOV-007 as completed after closeout evidence sync landed.",
                },
                {
                    "doc_ref": "README.md",
                    "status": "NO_CHANGE_REQUIRED",
                    "summary": "No public capability or runtime flow changed in this round.",
                },
            ],
        },
    )


def test_output_schema_registry_rejects_delivery_closeout_package_invalid_documentation_update_status() -> None:
    with pytest.raises(Exception) as exc_info:
        validate_output_payload(
            schema_ref="delivery_closeout_package",
            schema_version=1,
            submitted_schema_version="delivery_closeout_package_v1",
            payload={
                "summary": "Delivery closeout package is ready for internal review.",
                "final_artifact_refs": ["art://runtime/tkt_closeout_001/delivery-closeout-package.json"],
                "handoff_notes": ["Final evidence remains linked back to the board review pack."],
                "documentation_updates": [
                    {
                        "doc_ref": "doc/TODO.md",
                        "status": "PENDING",
                        "summary": "This should be rejected.",
                    }
                ],
            },
        )
    assert getattr(exc_info.value, "field_path", None) == "documentation_updates[0].status"


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("doc_ref", ""),
        ("summary", ""),
    ],
)
def test_output_schema_registry_rejects_delivery_closeout_package_documentation_update_missing_required_text(
    field_name: str,
    field_value: str,
) -> None:
    documentation_update = {
        "doc_ref": "doc/TODO.md",
        "status": "UPDATED",
        "summary": "Marked P2-GOV-007 as completed after closeout evidence sync landed.",
    }
    documentation_update[field_name] = field_value

    with pytest.raises(Exception) as exc_info:
        validate_output_payload(
            schema_ref="delivery_closeout_package",
            schema_version=1,
            submitted_schema_version="delivery_closeout_package_v1",
            payload={
                "summary": "Delivery closeout package is ready for internal review.",
                "final_artifact_refs": ["art://runtime/tkt_closeout_001/delivery-closeout-package.json"],
                "handoff_notes": ["Final evidence remains linked back to the board review pack."],
                "documentation_updates": [documentation_update],
            },
        )
    assert getattr(exc_info.value, "field_path", None) == f"documentation_updates[0].{field_name}"


def test_output_schema_registry_exposes_structured_failure_detail_for_missing_required_field() -> None:
    with pytest.raises(Exception) as exc_info:
        validate_output_payload(
            schema_ref="ui_milestone_review",
            schema_version=1,
            submitted_schema_version="ui_milestone_review_v1",
            payload={
                "summary": "Provider left out the options array.",
                "recommended_option_id": "option_a",
            },
        )

    assert getattr(exc_info.value, "field_path", None) == "options"
    assert getattr(exc_info.value, "expected", None) == "non-empty array"
    assert getattr(exc_info.value, "actual", None) == "missing"


@pytest.mark.parametrize(
    "schema_ref",
    [
        "architecture_brief",
        "technology_decision",
        "milestone_plan",
        "detailed_design",
        "backlog_recommendation",
    ],
)
def test_output_schema_registry_exposes_governance_document_schemas(schema_ref: str) -> None:
    schema = get_output_schema_body(schema_ref, 1)

    assert schema["type"] == "object"
    assert "title" in schema["required"]
    assert "summary" in schema["required"]
    assert "document_kind_ref" in schema["required"]
    assert "decisions" in schema["required"]
    assert "constraints" in schema["required"]
    assert "sections" in schema["required"]


@pytest.mark.parametrize(
    "schema_ref",
    [
        "architecture_brief",
        "technology_decision",
        "milestone_plan",
        "detailed_design",
        "backlog_recommendation",
    ],
)
def test_output_schema_registry_accepts_valid_governance_document_payloads(schema_ref: str) -> None:
    payload = _governance_document_payload(schema_ref)
    payload["sections"] = []

    validate_output_payload(
        schema_ref=schema_ref,
        schema_version=1,
        submitted_schema_version=f"{schema_ref}_v1",
        payload=payload,
    )


def test_output_schema_registry_rejects_governance_document_kind_mismatch() -> None:
    with pytest.raises(ValueError, match="document_kind_ref"):
        validate_output_payload(
            schema_ref="architecture_brief",
            schema_version=1,
            submitted_schema_version="architecture_brief_v1",
            payload=_governance_document_payload("detailed_design"),
        )
