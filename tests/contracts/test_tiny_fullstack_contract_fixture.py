from boardroom_os.contracts.package import PackageProjectType

from tests.fixtures.contracts.tiny_fullstack_contract import (
    TINY_FULLSTACK_AC_V2_BINDINGS,
    build_tiny_fullstack_contract_fixture,
    validate_tiny_fullstack_ac_v2_bindings,
)


def test_tiny_fullstack_fixture_builds_active_contract_chain_and_gate() -> None:
    fixture = build_tiny_fullstack_contract_fixture()

    assert fixture.board_directive.source_type == "natural_language"
    assert fixture.project_charter.delivery_type == "generated_project_package"
    assert fixture.methodology_profile.template_kind == "hybrid"
    assert fixture.acceptance_contract.status.value == "active"
    assert fixture.package_contract.project_type == PackageProjectType.SOFTWARE
    assert fixture.contract_gate.acceptance_contract_ref == fixture.acceptance_contract.acceptance_contract_id
    assert fixture.contract_gate.package_contract_ref == fixture.package_contract.package_contract_id


def test_tiny_fullstack_fixture_declares_package_surfaces_commands_and_obligations() -> None:
    fixture = build_tiny_fullstack_contract_fixture()

    assert [surface.source_surface_ref.value for surface in fixture.package_contract.source_surfaces] == [
        "backend-api",
        "frontend-ui",
        "persistence",
        "tests",
        "docs",
        "run-manifest",
    ]
    assert [command.command_id.value for command in fixture.package_contract.run_commands] == [
        "run-backend",
        "run-frontend",
    ]
    assert [command.command_id.value for command in fixture.package_contract.test_commands] == [
        "test-backend",
        "test-integration",
    ]
    assert [obligation.evidence_obligation_id.value for obligation in fixture.contract_gate.evidence_obligations] == [
        "obl-AC-TINY-API-BOOK-CREATE-backend_http_api_evidence",
        "obl-AC-TINY-API-BOOK-CREATE-backend_source_inventory",
        "obl-AC-TINY-API-BOOK-LIST-backend_http_api_evidence",
        "obl-AC-TINY-API-BOOK-LIST-backend_source_inventory",
        "obl-AC-TINY-API-CHECKOUT-RETURN-backend_http_api_evidence",
        "obl-AC-TINY-API-CHECKOUT-RETURN-backend_source_inventory",
        "obl-AC-TINY-API-BOOK-DELETE-backend_http_api_evidence",
        "obl-AC-TINY-API-BOOK-DELETE-backend_source_inventory",
        "obl-AC-TINY-PERSISTENCE-SQLITE-sqlite_persistence_evidence",
        "obl-AC-TINY-PERSISTENCE-SQLITE-backend_source_inventory",
        "obl-AC-TINY-BACKEND-STARTUP-backend_service_run",
        "obl-AC-TINY-BACKEND-STARTUP-backend_source_inventory",
        "obl-AC-TINY-BACKEND-HTTP-CRUD-backend_http_crud_evidence",
        "obl-AC-TINY-BACKEND-HTTP-CRUD-backend_source_inventory",
        "obl-AC-TINY-SQLITE-PERSISTENCE-VIA-HTTP-sqlite_persistence_http_evidence",
        "obl-AC-TINY-SQLITE-PERSISTENCE-VIA-HTTP-backend_source_inventory",
        "obl-AC-TINY-FRONTEND-STARTUP-frontend_service_run",
        "obl-AC-TINY-FRONTEND-STARTUP-frontend_source_inventory",
        "obl-AC-TINY-FRONTEND-LIVE-BACKEND-INTEGRATION-live_frontend_backend_integration_evidence",
        "obl-AC-TINY-FRONTEND-LIVE-BACKEND-INTEGRATION-frontend_source_inventory",
        "obl-AC-TINY-ALL-RUN-AND-TEST-COMMANDS-VERIFIED-run_manifest",
        "obl-AC-TINY-ALL-RUN-AND-TEST-COMMANDS-VERIFIED-backend_service_run",
        "obl-AC-TINY-ALL-RUN-AND-TEST-COMMANDS-VERIFIED-frontend_service_run",
        "obl-AC-TINY-ALL-RUN-AND-TEST-COMMANDS-VERIFIED-test_command_evidence",
        "obl-AC-TINY-ALL-RUN-AND-TEST-COMMANDS-VERIFIED-final_command_evidence",
    ]


def test_tiny_fullstack_fixture_binds_every_acceptance_ref_to_ac_v2() -> None:
    fixture = build_tiny_fullstack_contract_fixture()

    validate_tiny_fullstack_ac_v2_bindings(
        acceptance_contract=fixture.acceptance_contract,
        ac_v2_bindings=TINY_FULLSTACK_AC_V2_BINDINGS,
    )

    assert TINY_FULLSTACK_AC_V2_BINDINGS == {
        "AC-TINY-API-BOOK-CREATE": ("AC-V2-CONTRACT-001", "AC-V2-PACKAGE-002"),
        "AC-TINY-API-BOOK-LIST": ("AC-V2-CONTRACT-001", "AC-V2-PACKAGE-002"),
        "AC-TINY-API-CHECKOUT-RETURN": ("AC-V2-CONTRACT-001", "AC-V2-PACKAGE-002"),
        "AC-TINY-API-BOOK-DELETE": ("AC-V2-CONTRACT-001", "AC-V2-PACKAGE-002"),
        "AC-TINY-PERSISTENCE-SQLITE": ("AC-V2-CONTRACT-001", "AC-V2-EVIDENCE-003"),
        "AC-TINY-BACKEND-STARTUP": (
            "AC-V2-CONTRACT-002",
            "AC-V2-EVIDENCE-004",
            "AC-V2-PACKAGE-002",
        ),
        "AC-TINY-BACKEND-HTTP-CRUD": (
            "AC-V2-CONTRACT-001",
            "AC-V2-EVIDENCE-004",
            "AC-V2-PACKAGE-002",
        ),
        "AC-TINY-SQLITE-PERSISTENCE-VIA-HTTP": (
            "AC-V2-CONTRACT-001",
            "AC-V2-EVIDENCE-004",
        ),
        "AC-TINY-FRONTEND-STARTUP": (
            "AC-V2-CONTRACT-002",
            "AC-V2-EVIDENCE-004",
            "AC-V2-PACKAGE-002",
        ),
        "AC-TINY-FRONTEND-LIVE-BACKEND-INTEGRATION": (
            "AC-V2-CONTRACT-001",
            "AC-V2-EVIDENCE-004",
            "AC-V2-PACKAGE-001",
        ),
        "AC-TINY-ALL-RUN-AND-TEST-COMMANDS-VERIFIED": (
            "AC-V2-EVIDENCE-001",
            "AC-V2-PACKAGE-002",
            "AC-V2-PACKAGE-003",
        ),
    }
