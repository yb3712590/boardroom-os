from app.core.governance_templates import (
    ROLE_TEMPLATE_STATUS_LIVE,
    ROLE_TEMPLATE_STATUS_NOT_ENABLED,
    list_role_template_catalog_entries,
    list_role_template_document_kinds,
    list_role_template_fragments,
)


def test_role_template_catalog_exposes_live_reserved_and_governance_templates():
    templates = list_role_template_catalog_entries()

    assert [template["template_id"] for template in templates] == [
        "scope_consensus_primary",
        "frontend_delivery_primary",
        "quality_checker_primary",
        "backend_execution_reserved",
        "database_execution_reserved",
        "platform_sre_reserved",
        "architect_governance",
        "cto_governance",
    ]
    assert [template["template_kind"] for template in templates] == [
        "live_execution",
        "live_execution",
        "live_execution",
        "reserved_execution",
        "reserved_execution",
        "reserved_execution",
        "governance",
        "governance",
    ]
    assert [template["status"] for template in templates] == [
        ROLE_TEMPLATE_STATUS_LIVE,
        ROLE_TEMPLATE_STATUS_LIVE,
        ROLE_TEMPLATE_STATUS_LIVE,
        ROLE_TEMPLATE_STATUS_LIVE,
        ROLE_TEMPLATE_STATUS_LIVE,
        ROLE_TEMPLATE_STATUS_LIVE,
        ROLE_TEMPLATE_STATUS_LIVE,
        ROLE_TEMPLATE_STATUS_LIVE,
    ]
    assert templates[0]["canonical_role_ref"] == "ui_designer_primary"
    assert templates[1]["canonical_role_ref"] == "frontend_engineer_primary"
    assert templates[2]["canonical_role_ref"] == "checker_primary"
    assert templates[3]["provider_target_ref"] == "role_profile:backend_engineer_primary"
    assert templates[6]["provider_target_ref"] == "role_profile:architect_primary"
    assert templates[7]["provider_target_ref"] == "role_profile:cto_primary"
    assert templates[0]["responsibility_summary"]
    assert templates[3]["execution_boundary"]
    assert templates[6]["default_document_kind_refs"] == [
        "architecture_brief",
        "technology_decision",
        "detailed_design",
    ]
    assert templates[7]["default_document_kind_refs"] == [
        "architecture_brief",
        "technology_decision",
        "milestone_plan",
        "backlog_recommendation",
    ]
    assert templates[1]["composition"]["fragment_refs"] == [
        "skill_frontend_ui",
        "delivery_execution_loop",
    ]
    assert templates[2]["composition"]["fragment_refs"] == [
        "skill_quality_validation",
        "review_internal_gate",
    ]
    assert templates[0]["mainline_boundary"] == {
        "boundary_status": "LIVE_ON_MAINLINE",
        "active_path_refs": [
            "catalog_readonly",
            "scope_consensus",
            "governance_document_live",
        ],
        "blocked_path_refs": [],
    }
    assert templates[1]["mainline_boundary"] == {
        "boundary_status": "LIVE_ON_MAINLINE",
        "active_path_refs": [
            "catalog_readonly",
            "governance_document_live",
            "implementation_delivery",
            "final_review",
            "closeout",
        ],
        "blocked_path_refs": [],
    }
    assert templates[2]["mainline_boundary"] == {
        "boundary_status": "LIVE_ON_MAINLINE",
        "active_path_refs": [
            "catalog_readonly",
            "checker_gate",
        ],
        "blocked_path_refs": [],
    }
    assert templates[3]["mainline_boundary"] == {
        "boundary_status": "LIVE_ON_MAINLINE",
        "active_path_refs": [
            "catalog_readonly",
            "staffing",
            "workforce_lane",
            "implementation_delivery",
        ],
        "blocked_path_refs": [
            "ceo_create_ticket",
        ],
    }
    assert templates[4]["mainline_boundary"] == templates[3]["mainline_boundary"]
    assert templates[5]["mainline_boundary"] == templates[3]["mainline_boundary"]
    assert templates[6]["mainline_boundary"] == {
        "boundary_status": "LIVE_ON_MAINLINE",
        "active_path_refs": [
            "catalog_readonly",
            "staffing",
            "workforce_lane",
            "ceo_create_ticket",
            "governance_document_live",
        ],
        "blocked_path_refs": [],
    }
    assert templates[7]["mainline_boundary"] == templates[6]["mainline_boundary"]


def test_role_template_document_kinds_expose_expected_metadata_refs():
    document_kinds = list_role_template_document_kinds()

    assert [kind["kind_ref"] for kind in document_kinds] == [
        "architecture_brief",
        "technology_decision",
        "milestone_plan",
        "detailed_design",
        "backlog_recommendation",
    ]
    assert all(kind["label"] for kind in document_kinds)
    assert all(kind["summary"] for kind in document_kinds)


def test_role_template_fragments_expose_composition_metadata():
    fragments = list_role_template_fragments()

    assert [fragment["fragment_id"] for fragment in fragments] == [
        "skill_frontend_ui",
        "skill_backend_services",
        "skill_database_reliability",
        "skill_platform_operations",
        "skill_architecture_governance",
        "skill_quality_validation",
        "delivery_execution_loop",
        "delivery_document_first",
        "review_internal_gate",
    ]
    assert fragments[0]["fragment_kind"] == "skill_domain"
    assert fragments[6]["fragment_kind"] == "delivery_mode"
    assert fragments[8]["fragment_kind"] == "review_mode"
    assert fragments[0]["payload"]["primary_domain"] == "frontend"
    assert fragments[4]["payload"]["decision_scope"] == "architecture"
