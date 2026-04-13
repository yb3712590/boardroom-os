from types import SimpleNamespace

from app.core.runtime import _build_runtime_success_payload


def _fake_execution_package(*, ticket_id: str, output_schema_ref: str, process_asset_refs: list[str]):
    return SimpleNamespace(
        meta=SimpleNamespace(ticket_id=ticket_id),
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

    sections = payload["sections"]
    structured_section = next(
        section
        for section in sections
        if isinstance(section.get("content_json"), dict) and section["content_json"].get("tickets")
    )
    dependency_section = next(
        section
        for section in sections
        if isinstance(section.get("content_json"), dict)
        and (
            section["content_json"].get("dependency_graph")
            or section["content_json"].get("recommended_sequence")
        )
    )

    assert payload["source_process_asset_refs"] == [
        "pa://governance-document/tkt_architecture",
        "pa://governance-document/tkt_detailed_design",
    ]
    assert len(structured_section["content_json"]["tickets"]) >= 30
    assert dependency_section["content_json"]["dependency_graph"]
    assert dependency_section["content_json"]["recommended_sequence"]


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
