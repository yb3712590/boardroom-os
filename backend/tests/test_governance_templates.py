from app.core.governance_templates import (
    GOVERNANCE_TEMPLATE_STATUS_NOT_ENABLED,
    list_governance_document_kinds,
    list_governance_role_templates,
)


def test_governance_role_templates_expose_expected_read_only_catalog():
    templates = list_governance_role_templates()

    assert [template["template_id"] for template in templates] == [
        "cto_governance",
        "architect_governance",
    ]
    assert all(template["status"] == GOVERNANCE_TEMPLATE_STATUS_NOT_ENABLED for template in templates)
    assert templates[0]["provider_target_ref"] == "role_profile:cto_primary"
    assert templates[1]["provider_target_ref"] == "role_profile:architect_primary"
    assert templates[0]["execution_boundary"]
    assert templates[1]["execution_boundary"]
    assert templates[0]["default_document_kind_refs"] == [
        "architecture_brief",
        "technology_decision",
        "milestone_plan",
        "backlog_recommendation",
    ]
    assert templates[1]["default_document_kind_refs"] == [
        "architecture_brief",
        "technology_decision",
        "detailed_design",
    ]


def test_governance_document_kinds_expose_expected_metadata_refs():
    document_kinds = list_governance_document_kinds()

    assert [kind["kind_ref"] for kind in document_kinds] == [
        "architecture_brief",
        "technology_decision",
        "milestone_plan",
        "detailed_design",
        "backlog_recommendation",
    ]
    assert all(kind["label"] for kind in document_kinds)
    assert all(kind["summary"] for kind in document_kinds)
