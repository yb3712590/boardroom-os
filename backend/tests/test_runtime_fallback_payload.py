from types import SimpleNamespace

from app.core.runtime import _build_runtime_success_payload, _normalize_source_code_delivery_payload


def _fake_execution_package(*, ticket_id: str, output_schema_ref: str, process_asset_refs: list[str]):
    return SimpleNamespace(
        meta=SimpleNamespace(ticket_id=ticket_id, attempt_no=1),
        compiled_role=SimpleNamespace(
            employee_role_type="frontend_engineer",
            role_profile_ref="frontend_engineer_primary",
        ),
        execution=SimpleNamespace(
            output_schema_ref=output_schema_ref,
            doc_update_requirements=[],
            allowed_write_set=["10-project/src/*", "20-evidence/tests/*", "20-evidence/git/*"],
        ),
        atomic_context_bundle=SimpleNamespace(
            context_blocks=[
                SimpleNamespace(source_kind="PROCESS_ASSET", source_ref=ref)
                for ref in process_asset_refs
            ]
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
