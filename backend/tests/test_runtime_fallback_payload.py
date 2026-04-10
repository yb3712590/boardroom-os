from types import SimpleNamespace

from app.core.runtime import _build_runtime_success_payload


def _fake_execution_package(*, ticket_id: str, output_schema_ref: str, process_asset_refs: list[str]):
    return SimpleNamespace(
        meta=SimpleNamespace(ticket_id=ticket_id),
        compiled_role=SimpleNamespace(
            employee_role_type="frontend_engineer",
            role_profile_ref="frontend_engineer_primary",
        ),
        execution=SimpleNamespace(output_schema_ref=output_schema_ref),
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
