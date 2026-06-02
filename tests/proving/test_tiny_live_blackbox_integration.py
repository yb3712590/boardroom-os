from __future__ import annotations

from pathlib import Path

import pytest

from boardroom_os.evidence.claim import EvidenceClaimSourceKind
from boardroom_os.evidence.table import FinalEvidenceStatus


def test_tiny_live_blackbox_rejects_fake_fetch_only_package(tmp_path: Path) -> None:
    from tests.proving.fixtures.tiny_package_assembly import (
        TINY_PACKAGE_CONTENTS,
        build_tiny_live_blackbox_fixture,
    )
    from tests.proving.fixtures.tiny_provider_attempts import (
        build_tiny_provider_attempt_fixture,
    )

    broken_contents = dict(TINY_PACKAGE_CONTENTS)
    broken_contents["tests/integration/test_frontend_backend.py"] = (
        "def test_fake_fetch_only():\n"
        "    fakeFetch = lambda *args, **kwargs: {'books': []}\n"
        "    assert fakeFetch('/books') == {'books': []}\n"
    )

    with pytest.raises(ValueError, match="fakeFetch|live|integration behavior"):
        build_tiny_live_blackbox_fixture(
            package_root=tmp_path / "tiny-blackbox",
            package_contents=broken_contents,
            provider_fixture=build_tiny_provider_attempt_fixture(use_fake_results=True),
            allow_test_provider_transport=True,
        )


def test_tiny_live_blackbox_rejects_missing_backend_delete_endpoint(tmp_path: Path) -> None:
    from tests.proving.fixtures.tiny_package_assembly import (
        TINY_PACKAGE_CONTENTS,
        build_tiny_live_blackbox_fixture,
    )
    from tests.proving.fixtures.tiny_provider_attempts import (
        build_tiny_provider_attempt_fixture,
    )

    broken_contents = dict(TINY_PACKAGE_CONTENTS)
    broken_contents["backend/app.py"] = broken_contents["backend/app.py"].replace(
        "def do_DELETE(self):",
        "def do_DELETE_MISSING(self):",
    )

    with pytest.raises((ValueError, AssertionError), match="delete|live blackbox|verification_run"):
        build_tiny_live_blackbox_fixture(
            package_root=tmp_path / "tiny-blackbox",
            package_contents=broken_contents,
            provider_fixture=build_tiny_provider_attempt_fixture(use_fake_results=True),
            allow_test_provider_transport=True,
        )


def test_tiny_live_blackbox_rejects_sqlite_function_unit_test_only(tmp_path: Path) -> None:
    from tests.proving.fixtures.tiny_package_assembly import (
        TINY_PACKAGE_CONTENTS,
        build_tiny_live_blackbox_fixture,
    )
    from tests.proving.fixtures.tiny_provider_attempts import (
        build_tiny_provider_attempt_fixture,
    )

    broken_contents = dict(TINY_PACKAGE_CONTENTS)
    broken_contents["backend/app.py"] = broken_contents["backend/app.py"].replace(
        "os.environ.get('BOOKS_DB_PATH', DEFAULT_DB_PATH)",
        "DEFAULT_DB_PATH",
    )

    with pytest.raises(ValueError, match="SQLite|HTTP workflow"):
        build_tiny_live_blackbox_fixture(
            package_root=tmp_path / "tiny-blackbox",
            package_contents=broken_contents,
            provider_fixture=build_tiny_provider_attempt_fixture(use_fake_results=True),
            allow_test_provider_transport=True,
        )


def test_tiny_live_blackbox_satisfies_phase_9_live_integration_rows(tmp_path: Path) -> None:
    from tests.proving.fixtures.tiny_package_assembly import (
        TINY_PACKAGE_CONTENTS,
        build_tiny_live_blackbox_fixture,
    )
    from tests.proving.fixtures.tiny_provider_attempts import (
        build_tiny_provider_attempt_fixture,
    )

    fixture = build_tiny_live_blackbox_fixture(
        package_root=tmp_path / "tiny-blackbox",
        package_contents=TINY_PACKAGE_CONTENTS,
        provider_fixture=build_tiny_provider_attempt_fixture(use_fake_results=True),
        allow_test_provider_transport=True,
    )

    assert fixture.live_blackbox_evidence is not None
    assert {
        service.command_id.value for service in fixture.service_runs
    } == {"run-backend", "run-frontend"}
    frontend_service = next(
        service
        for service in fixture.service_runs
        if service.command_id.value == "run-frontend"
    )
    frontend_port = frontend_service.environment_overrides["FRONTEND_PORT"]
    assert f":{frontend_port}/" in fixture.live_blackbox_evidence.frontend_probe.frontend_url.value
    satisfied_refs = {
        row.acceptance_ref.value
        for row in fixture.final_evidence_table.rows
        if row.status is FinalEvidenceStatus.SATISFIED
    }
    assert {
        "AC-TINY-BACKEND-STARTUP",
        "AC-TINY-BACKEND-HTTP-CRUD",
        "AC-TINY-SQLITE-PERSISTENCE-VIA-HTTP",
        "AC-TINY-FRONTEND-STARTUP",
        "AC-TINY-FRONTEND-LIVE-BACKEND-INTEGRATION",
        "AC-TINY-ALL-RUN-AND-TEST-COMMANDS-VERIFIED",
    }.issubset(satisfied_refs)
    assert any(
        evidence.source_kind is EvidenceClaimSourceKind.LIVE_BLACKBOX
        for evidence in fixture.verified_evidence
    )
    assert fixture.workspace_evidence_bundle is not None
    assert fixture.workspace_evidence_bundle.live_blackbox_evidence_refs == (
        fixture.live_blackbox_evidence.live_blackbox_evidence_id,
    )
