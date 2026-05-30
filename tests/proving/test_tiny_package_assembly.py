from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from boardroom_os.contracts.types import SourceSurfaceRef
from boardroom_os.workspace.assembler import PackageArtifactKind, PackageArtifactPath

_VERIFY_ERRORS = (ValueError, ValidationError)


def test_tiny_package_assembly_rejects_ref_only_source_inventory(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import (
        build_tiny_package_assembly_fixture,
    )

    fixture = build_tiny_package_assembly_fixture(
        package_root=tmp_path / "physical-package-root",
    )

    with pytest.raises(_VERIFY_ERRORS, match="ref-only|source files|lineage"):
        fixture.build_source_inventory(source_files=(), lineage_records=())


def test_tiny_package_assembly_rejects_missing_run_manifest_artifact(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import (
        build_tiny_package_assembly_fixture,
    )

    fixture = build_tiny_package_assembly_fixture(
        package_root=tmp_path / "physical-package-root",
    )
    artifacts = tuple(
        artifact
        for artifact in fixture.package_artifacts
        if artifact.relative_path.value != "run-manifest.json"
    )

    with pytest.raises(_VERIFY_ERRORS, match="run-manifest.json"):
        fixture.assemble_package(artifacts=artifacts)


@pytest.mark.parametrize(
    "bad_path",
    [
        "/tmp/backend/app.py",
        "../backend/app.py",
        "20-evidence/source-inventory/source-inventory.json",
        "30-audit/process-audit.md",
        "00-boardroom/tickets/ticket.json",
        "10-project/backend/app.py",
    ],
)
def test_tiny_package_assembly_rejects_artifact_outside_package_root(
    bad_path: str,
) -> None:
    with pytest.raises(_VERIFY_ERRORS, match="package artifact path|relative|parent|10-project|workspace"):
        PackageArtifactPath(value=bad_path)


@pytest.mark.parametrize("reserved_root", [Path("10-project"), Path("20-evidence")])
def test_tiny_package_assembly_requires_isolated_tmp_package_root(
    reserved_root: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import (
        build_tiny_package_assembly_fixture,
    )

    with pytest.raises(_VERIFY_ERRORS, match="isolated tmp package root"):
        build_tiny_package_assembly_fixture(package_root=reserved_root)


def test_tiny_generated_package_locates_package_source_and_evidence(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import (
        EXPECTED_TINY_PACKAGE_PATHS,
        build_tiny_package_assembly_fixture,
    )

    fixture = build_tiny_package_assembly_fixture(
        package_root=tmp_path / "physical-package-root",
    )

    assert fixture.workspace_manifest.package_root.value == "10-project"
    assert fixture.package_assembly.package_root.value == "10-project"
    assert {artifact.relative_path.value for artifact in fixture.package_assembly.artifacts} == set(
        EXPECTED_TINY_PACKAGE_PATHS
    )
    assert fixture.command_results_by_id["test-backend"].verification_run.exit_code == 0
    assert fixture.command_results_by_id["test-integration"].verification_run.exit_code == 0
    assert "passed" in fixture.command_results_by_id["test-backend"].stdout
    assert "passed" in fixture.command_results_by_id["test-integration"].stdout
    assert fixture.run_manifest.package_contract_ref == fixture.package_contract.package_contract_id
    assert fixture.source_inventory.package_assembly_ref == fixture.package_assembly.package_assembly_id
    assert fixture.final_evidence_table.complete is True
    assert fixture.workspace_evidence_bundle.closeout_ready is True

    inventory_paths = {entry.path.value for entry in fixture.source_inventory.entries}
    assert inventory_paths == {
        "backend/app.py",
        "backend/db.py",
        "docs/usage.md",
        "frontend/app.js",
        "frontend/index.html",
        "backend/tests/test_api.py",
        "tests/integration/test_frontend_backend.py",
    }
    assert {
        artifact.artifact_kind
        for artifact in fixture.workspace_evidence_bundle.artifacts
    } == fixture.required_evidence_artifact_kinds
    assert all(
        artifact.relative_path.value.startswith("20-evidence/")
        for artifact in fixture.workspace_evidence_bundle.artifacts
    )


def test_tiny_source_inventory_binds_producer_attempts_and_verified_evidence(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import (
        build_tiny_package_assembly_fixture,
    )

    fixture = build_tiny_package_assembly_fixture(
        package_root=tmp_path / "physical-package-root",
    )
    provider_attempt_refs = {
        attempt.provider_attempt_id
        for attempt in fixture.provider_attempts_by_ticket_id.values()
    }
    final_table_evidence_refs = {
        evidence_ref
        for row in fixture.final_evidence_table.rows
        for evidence_ref in row.verified_evidence_refs
    }

    for entry in fixture.source_inventory.entries:
        assert entry.producer_attempt_ref in provider_attempt_refs
        assert entry.evidence_refs
        assert set(entry.evidence_refs).issubset(final_table_evidence_refs)
        assert entry.sha256.value == hashlib.sha256(
            fixture.source_contents[entry.path.value].encode("utf-8")
        ).hexdigest()
        assert (fixture.package_root_path / entry.path.value).read_text(
            encoding="utf-8"
        ) == fixture.source_contents[entry.path.value]

    backend_entries = tuple(
        entry
        for entry in fixture.source_inventory.entries
        if entry.source_surface_ref == SourceSurfaceRef(value="backend-api")
    )
    assert {entry.path.value for entry in backend_entries} == {"backend/app.py"}
    assert all(entry.sha256.value != "0" * 64 for entry in fixture.source_inventory.entries)


def test_tiny_package_assembly_rejects_failed_declared_command(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import (
        TINY_PACKAGE_CONTENTS,
        build_tiny_package_assembly_fixture,
    )

    broken_contents = {
        **TINY_PACKAGE_CONTENTS,
        "backend/tests/test_api.py": (
            "def test_backend_source_inventory_contract():\n"
            "    assert False, 'backend command evidence must fail closed'\n"
        ),
    }

    with pytest.raises(AssertionError, match="tiny evidence verification failed"):
        build_tiny_package_assembly_fixture(
            package_root=tmp_path / "physical-package-root",
            package_contents=broken_contents,
        )


def test_tiny_package_assembly_rejects_run_manifest_content_mismatch(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import (
        TINY_PACKAGE_CONTENTS,
        build_tiny_package_assembly_fixture,
    )

    broken_contents = {
        **TINY_PACKAGE_CONTENTS,
        "run-manifest.json": "not json\n",
    }

    with pytest.raises(_VERIFY_ERRORS, match="run-manifest.json|run manifest"):
        build_tiny_package_assembly_fixture(
            package_root=tmp_path / "physical-package-root",
            package_contents=broken_contents,
        )


def test_tiny_package_assembly_rejects_escape_path_before_writing(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import (
        TINY_PACKAGE_CONTENTS,
        build_tiny_package_assembly_fixture,
    )

    escaped_path = tmp_path / "escape.txt"
    broken_contents = {
        **TINY_PACKAGE_CONTENTS,
        "../escape.txt": "must not be written\n",
    }

    with pytest.raises(_VERIFY_ERRORS, match="package artifact path|package root"):
        build_tiny_package_assembly_fixture(
            package_root=tmp_path / "physical-package-root",
            package_contents=broken_contents,
        )

    assert not escaped_path.exists()


def test_tiny_package_assembly_is_pure_model_proof(tmp_path: Path) -> None:
    from tests.proving.fixtures.tiny_package_assembly import (
        build_tiny_package_assembly_fixture,
    )

    fixture = build_tiny_package_assembly_fixture(
        package_root=tmp_path / "physical-package-root",
    )

    assert fixture.package_root_path == tmp_path / "physical-package-root"
    assert not (tmp_path / "10-project").exists()
    assert not (tmp_path / "20-evidence").exists()
    assert tuple(
        artifact.relative_path.value
        for artifact in fixture.package_assembly.artifacts
    ) == tuple(sorted(fixture.expected_package_paths))
    assert PackageArtifactKind.RUN_MANIFEST in {
        artifact.artifact_kind for artifact in fixture.package_assembly.artifacts
    }
