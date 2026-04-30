from types import SimpleNamespace

from app.core.runtime import (
    _build_runtime_default_artifacts,
    _build_runtime_success_payload,
    _normalize_provider_payload_for_execution,
    _normalize_source_code_delivery_payload,
)


def _fake_execution_package(
    *,
    ticket_id: str,
    output_schema_ref: str,
    process_asset_refs: list[str],
    input_artifact_refs: list[str] | None = None,
    context_blocks: list[SimpleNamespace] | None = None,
):
    return SimpleNamespace(
        meta=SimpleNamespace(ticket_id=ticket_id, attempt_no=1),
        compiled_role=SimpleNamespace(
            employee_role_type="frontend_engineer",
            role_profile_ref="frontend_engineer_primary",
        ),
        execution=SimpleNamespace(
            output_schema_ref=output_schema_ref,
            output_schema_version=1,
            doc_update_requirements=[],
            allowed_write_set=["10-project/src/*", "20-evidence/tests/*", "20-evidence/git/*"],
            input_artifact_refs=list(input_artifact_refs or []),
            input_process_asset_refs=list(process_asset_refs),
        ),
        atomic_context_bundle=SimpleNamespace(
            context_blocks=list(context_blocks)
            if context_blocks is not None
            else [
                SimpleNamespace(source_kind="PROCESS_ASSET", source_ref=ref)
                for ref in process_asset_refs
            ],
        ),
    )


def test_backlog_recommendation_fallback_payload_includes_structured_ticket_split():
    execution_package = _fake_execution_package(
        ticket_id="tkt_backlog_runtime_fallback",
        output_schema_ref="backlog_recommendation",
        process_asset_refs=[
            "pa://governance-document/tkt_architecture",
            "pa://governance-document/tkt_detailed_design",
        ],
    )

    payload = _build_runtime_success_payload(
        execution_package,
        ["art://runtime/tkt_backlog_runtime_fallback/backlog_recommendation.json"],
    )

    handoff = payload["implementation_handoff"]
    tickets = handoff["tickets"]
    dependency_graph = handoff["dependency_graph"]
    recommended_sequence = handoff["recommended_sequence"]

    assert payload["source_process_asset_refs"] == [
        "pa://governance-document/tkt_architecture",
        "pa://governance-document/tkt_detailed_design",
    ]

    assert len(tickets) == 6
    assert [ticket["ticket_id"] for ticket in tickets] == [
        "BR-T01",
        "BR-T02",
        "BR-T03",
        "BR-T04",
        "BR-T05",
        "BR-T06",
    ]
    assert recommended_sequence == ["BR-T01", "BR-T02", "BR-T03", "BR-T04", "BR-T05", "BR-T06"]
    assert dependency_graph

    ticket_blob = " ".join(
        " ".join(
            [
                str(ticket.get("name") or ""),
                *(str(item) for item in list(ticket.get("scope") or [])),
                str(ticket.get("summary") or ""),
                str(ticket.get("target_role") or ""),
            ]
        )
        for ticket in tickets
    )
    assert "books" in ticket_blob
    assert "IN_LIBRARY" in ticket_blob
    assert "CHECKED_OUT" in ticket_blob
    assert "terminal" in ticket_blob.lower()
    for banned_scope in ["RBAC", "预约", "罚金", "报表", "运维", "监控", "用户档案", "借阅历史"]:
        assert banned_scope not in ticket_blob


def test_source_code_delivery_runtime_payload_includes_source_files_and_verification_runs():
    execution_package = _fake_execution_package(
        ticket_id="tkt_source_delivery_runtime_fallback",
        output_schema_ref="source_code_delivery",
        process_asset_refs=[],
    )

    payload = _build_runtime_success_payload(
        execution_package,
        ["art://workspace/tkt_source_delivery_runtime_fallback/source.tsx"],
    )

    assert payload["source_file_refs"] == [
        "art://workspace/tkt_source_delivery_runtime_fallback/source.tsx"
    ]
    assert payload["source_files"] == [
        {
            "artifact_ref": "art://workspace/tkt_source_delivery_runtime_fallback/source.tsx",
            "path": "10-project/src/tkt_source_delivery_runtime_fallback.tsx",
            "content": "export function RuntimeGeneratedDelivery() {\n  return <main>Runtime delivery ready</main>;\n}\n",
        }
    ]
    assert payload["verification_runs"] == [
        {
            "artifact_ref": "art://workspace/tkt_source_delivery_runtime_fallback/test-report.json",
            "path": "20-evidence/tests/tkt_source_delivery_runtime_fallback/attempt-1/test-report.json",
            "runner": "vitest",
            "command": "npm run test -- --runInBand",
            "status": "passed",
            "exit_code": 0,
            "duration_sec": 1.0,
            "stdout": " RUN  v1.0.0\n  ✓ runtime delivery smoke\n\n Test Files  1 passed\n",
            "stderr": "",
            "discovered_count": 1,
            "passed_count": 1,
            "failed_count": 0,
            "skipped_count": 0,
            "failures": [],
        }
    ]


def test_source_code_delivery_default_evidence_paths_use_current_attempt():
    execution_package = _fake_execution_package(
        ticket_id="tkt_source_delivery_attempt_004",
        output_schema_ref="source_code_delivery",
        process_asset_refs=[],
    )
    execution_package.meta.attempt_no = 4

    payload = _normalize_source_code_delivery_payload(
        execution_package,
        {
            "summary": "Retry delivery.",
            "source_file_refs": ["art://workspace/tkt_source_delivery_attempt_004/source.tsx"],
            "source_files": [
                {
                    "artifact_ref": "art://workspace/tkt_source_delivery_attempt_004/source.tsx",
                    "path": "10-project/src/tkt_source_delivery_attempt_004.tsx",
                    "content": "export const attemptFourReady = true;\n",
                }
            ],
        },
    )

    assert payload["verification_runs"][0]["path"] == (
        "20-evidence/tests/tkt_source_delivery_attempt_004/attempt-4/test-report.json"
    )

    _, written_artifacts = _build_runtime_default_artifacts(execution_package, payload)
    written_paths = {item["path"] for item in written_artifacts}
    assert (
        "20-evidence/tests/tkt_source_delivery_attempt_004/attempt-4/test-report.json"
        in written_paths
    )
    assert (
        "20-evidence/git/tkt_source_delivery_attempt_004/attempt-4/git-closeout.json"
        in written_paths
    )
    assert all("/attempt-1/" not in path for path in written_paths)


def test_source_code_delivery_normalization_versions_verification_paths_by_attempt():
    execution_package = _fake_execution_package(
        ticket_id="tkt_source_delivery_retry",
        output_schema_ref="source_code_delivery",
        process_asset_refs=[],
    )
    execution_package.meta.attempt_no = 4

    payload = _normalize_source_code_delivery_payload(
        execution_package,
        {
            "summary": "Retry delivery.",
            "source_file_refs": ["art://workspace/tkt_source_delivery_retry/source.js"],
            "source_files": [
                {
                    "artifact_ref": "art://workspace/tkt_source_delivery_retry/source.js",
                    "path": "10-project/src/actions.js",
                    "content": "export const actionsReady = true;\n",
                }
            ],
            "verification_runs": [
                {
                    "artifact_ref": "art://workspace/tkt_source_delivery_retry/report.json",
                    "path": "20-evidence/tests/report.json",
                    "runner": "node",
                    "command": "node test.js",
                    "status": "passed",
                    "exit_code": 0,
                    "duration_sec": 0.4,
                    "stdout": "1 passed\n",
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

    assert payload["verification_runs"][0]["path"] == (
        "20-evidence/tests/tkt_source_delivery_retry/attempt-4/report.json"
    )


def test_source_code_delivery_normalization_rewrites_wrong_attempt_path_to_current_attempt():
    execution_package = _fake_execution_package(
        ticket_id="tkt_source_delivery_retry_wrong_attempt",
        output_schema_ref="source_code_delivery",
        process_asset_refs=[],
    )
    execution_package.meta.attempt_no = 4

    payload = _normalize_source_code_delivery_payload(
        execution_package,
        {
            "summary": "Retry delivery.",
            "source_file_refs": ["art://workspace/tkt_source_delivery_retry_wrong_attempt/source.js"],
            "source_files": [
                {
                    "artifact_ref": "art://workspace/tkt_source_delivery_retry_wrong_attempt/source.js",
                    "path": "10-project/src/actions.js",
                    "content": "export const actionsReady = true;\n",
                }
            ],
            "verification_runs": [
                {
                    "artifact_ref": "art://workspace/tkt_source_delivery_retry_wrong_attempt/report.json",
                    "path": "20-evidence/tests/tkt_source_delivery_retry_wrong_attempt/attempt-1/report.json",
                    "runner": "node",
                    "command": "node test.js",
                    "status": "passed",
                    "exit_code": 0,
                    "duration_sec": 0.4,
                    "stdout": "1 passed\n",
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

    assert payload["verification_runs"][0]["path"] == (
        "20-evidence/tests/tkt_source_delivery_retry_wrong_attempt/attempt-4/report.json"
    )


def test_delivery_closeout_runtime_payload_filters_non_delivery_input_artifact_refs():
    source_file_ref = "art://workspace/tkt_runtime_source_delivery/source.ts"
    verification_ref = "art://workspace/tkt_runtime_source_delivery/test-report.json"
    project_document_ref = "art://workspace/wf_runtime_closeout/10-project/ARCHITECTURE.md"
    source_delivery_ref = "pa://source-code-delivery/tkt_runtime_source_delivery@1"
    execution_package = _fake_execution_package(
        ticket_id="tkt_runtime_closeout_filters",
        output_schema_ref="delivery_closeout_package",
        process_asset_refs=[source_delivery_ref],
        input_artifact_refs=[
            project_document_ref,
            source_file_ref,
            verification_ref,
        ],
        context_blocks=[
            SimpleNamespace(
                source_kind="PROCESS_ASSET",
                source_ref=source_delivery_ref,
                content_payload={
                    "process_asset_kind": "SOURCE_CODE_DELIVERY",
                    "content_json": {
                        "source_file_refs": [source_file_ref],
                        "verification_evidence_refs": [verification_ref],
                    },
                },
            )
        ],
    )

    payload = _build_runtime_success_payload(
        execution_package,
        ["art://runtime/tkt_runtime_closeout_filters/delivery-closeout-package.json"],
    )

    assert payload["final_artifact_refs"] == [source_file_ref, verification_ref]


def test_delivery_closeout_provider_payload_filters_non_delivery_final_artifact_refs():
    delivery_check_ref = "art://runtime/tkt_runtime_check/delivery-check-report.json"
    project_document_ref = "art://project-workspace/wf_runtime_closeout/10-project/ARCHITECTURE.md"
    backlog_ref = "art://runtime/tkt_runtime_backlog/backlog_recommendation.json"
    execution_package = _fake_execution_package(
        ticket_id="tkt_runtime_closeout_provider_filters",
        output_schema_ref="delivery_closeout_package",
        process_asset_refs=[],
        input_artifact_refs=[delivery_check_ref],
    )

    payload = _normalize_provider_payload_for_execution(
        execution_package,
        {
            "summary": "Closeout package prepared from approved delivery evidence.",
            "final_artifact_refs": [project_document_ref, backlog_ref],
            "handoff_notes": ["Keep the accepted delivery check report linked for audit."],
            "documentation_updates": [],
        },
    )

    assert payload["final_artifact_refs"] == [delivery_check_ref]
