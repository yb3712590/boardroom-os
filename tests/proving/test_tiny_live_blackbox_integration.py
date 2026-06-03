from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from boardroom_os.evidence.claim import EvidenceClaimSourceKind
from boardroom_os.evidence.table import FinalEvidenceStatus


def test_tiny_live_blackbox_allows_fake_fetch_unit_test_when_live_probe_passes(tmp_path: Path) -> None:
    from tests.proving.fixtures.tiny_package_assembly import (
        TINY_PACKAGE_CONTENTS,
        build_tiny_live_blackbox_fixture,
    )
    from tests.proving.fixtures.tiny_provider_attempts import (
        build_tiny_provider_attempt_fixture,
    )

    package_contents = dict(TINY_PACKAGE_CONTENTS)
    package_contents["tests/integration/test_frontend_backend.py"] += (
        "\n\ndef test_fake_fetch_unit_helper_is_not_final_evidence():\n"
        "    fakeFetch = lambda *args, **kwargs: {'books': []}\n"
        "    assert fakeFetch('/books') == {'books': []}\n"
    )

    fixture = build_tiny_live_blackbox_fixture(
        package_root=tmp_path / "tiny-blackbox",
        package_contents=package_contents,
        provider_fixture=build_tiny_provider_attempt_fixture(use_fake_results=True),
        allow_test_provider_transport=True,
    )

    assert fixture.live_blackbox_evidence is not None
    assert all(probe.passed for probe in fixture.live_blackbox_evidence.probes)


def test_tiny_live_blackbox_rejects_schema_valid_but_non_runnable_backend(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import (
        TINY_PACKAGE_CONTENTS,
        build_tiny_live_blackbox_fixture,
    )
    from tests.proving.fixtures.tiny_provider_attempts import (
        build_tiny_provider_attempt_fixture,
    )

    broken_contents = dict(TINY_PACKAGE_CONTENTS)
    broken_contents["backend/app.py"] = (
        "def main():\n"
        "    raise SystemExit('schema-valid source delivery is not enough')\n\n"
        "if __name__ == '__main__':\n"
        "    main()\n"
    )

    with pytest.raises((ValueError, AssertionError), match="service|readiness|verification_run|execute"):
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
    frontend_probe = next(
        probe
        for probe in fixture.live_blackbox_evidence.probes
        if probe.probe_ref.value == "frontend-live-backend"
    )
    assert f":{frontend_port}/" in frontend_probe.observed_facts["frontend_url"]
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


def test_tiny_live_blackbox_service_evidence_hashes_bind_real_process_output(
    tmp_path: Path,
) -> None:
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

    output_by_ref = {
        output.service_run.stdout_ref.value: output.stdout
        for output in fixture.service_run_outputs
    }
    output_by_ref.update(
        {
            output.service_run.stderr_ref.value: output.stderr
            for output in fixture.service_run_outputs
        }
    )
    service_evidence = [
        evidence
        for evidence in fixture.verified_evidence
        if evidence.source_kind is EvidenceClaimSourceKind.SERVICE_RUN
    ]

    assert output_by_ref
    for evidence in service_evidence:
        for artifact in evidence.verified_artifacts:
            assert artifact.artifact_ref.value in output_by_ref
            expected_hash = hashlib.sha256(
                output_by_ref[artifact.artifact_ref.value].encode("utf-8")
            ).hexdigest()
            assert artifact.sha256.value == expected_hash
