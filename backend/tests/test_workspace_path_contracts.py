from __future__ import annotations

import pytest

from app.core.workspace_path_contracts import (
    ArtifactRefKind,
    CloseoutFinalRefStatus,
    build_allowed_write_set_for_capabilities,
    classify_closeout_final_artifact_ref,
    match_contract_write_set,
    resolve_artifact_ref_contract,
    validate_artifact_ref_matches_path,
)


def test_workspace_source_ref_maps_to_project_source_path() -> None:
    contract = resolve_artifact_ref_contract(
        "art://workspace/tkt_1/source/src/app/main.py"
    )

    assert contract.kind == ArtifactRefKind.WORKSPACE_SOURCE
    assert contract.ticket_id == "tkt_1"
    assert contract.logical_path == "10-project/src/app/main.py"
    assert contract.is_final_closeout_evidence is True


def test_workspace_source_ref_accepts_runtime_encoded_project_path() -> None:
    contract = resolve_artifact_ref_contract(
        "art://workspace/tkt_1/source/1-10-project%2Fsrc%2Fapp%2Fmain.py"
    )

    assert contract.kind == ArtifactRefKind.WORKSPACE_SOURCE
    assert contract.logical_path == "10-project/src/app/main.py"


def test_legacy_workspace_source_ref_uses_submitted_path() -> None:
    contract = validate_artifact_ref_matches_path(
        "art://workspace/tkt_1/source.ts",
        "10-project/src/tkt_1.ts",
    )

    assert contract.kind == ArtifactRefKind.WORKSPACE_SOURCE
    assert contract.logical_path == "10-project/src/tkt_1.ts"


def test_workspace_tests_ref_maps_to_ticket_evidence_path() -> None:
    contract = resolve_artifact_ref_contract(
        "art://workspace/tkt_1/tests/attempt-1/pytest.json"
    )

    assert contract.kind == ArtifactRefKind.TEST_EVIDENCE
    assert contract.logical_path == "20-evidence/tests/tkt_1/attempt-1/pytest.json"
    assert contract.is_final_closeout_evidence is True


@pytest.mark.parametrize(
    ("artifact_ref", "expected_path", "expected_kind"),
    [
        (
            "art://runtime/tkt_1/delivery-check-report.json",
            "20-evidence/delivery/tkt_1/delivery-check-report.json",
            ArtifactRefKind.DELIVERY_CHECK_REPORT,
        ),
        (
            "art://runtime/tkt_1/delivery-closeout-package.json",
            "50-closeout/tkt_1/delivery-closeout-package.json",
            ArtifactRefKind.CLOSEOUT_PACKAGE,
        ),
        (
            "art://runtime/tkt_1/git/attempt-1/commit.json",
            "20-evidence/git/tkt_1/attempt-1/commit.json",
            ArtifactRefKind.GIT_EVIDENCE,
        ),
    ],
)
def test_runtime_refs_map_to_contract_paths(
    artifact_ref: str,
    expected_path: str,
    expected_kind: ArtifactRefKind,
) -> None:
    contract = resolve_artifact_ref_contract(artifact_ref)

    assert contract.kind == expected_kind
    assert contract.logical_path == expected_path


def test_governance_ref_is_document_not_final_evidence() -> None:
    contract = resolve_artifact_ref_contract(
        "art://runtime/tkt_1/governance/architecture-brief.json"
    )

    assert contract.kind == ArtifactRefKind.GOVERNANCE_DOCUMENT
    assert contract.is_final_closeout_evidence is False


def test_validate_artifact_ref_matches_path_rejects_mismatch() -> None:
    with pytest.raises(ValueError, match="does not match the directory contract"):
        validate_artifact_ref_matches_path(
            "art://workspace/tkt_1/tests/attempt-1/pytest.json",
            "10-project/src/pytest.json",
        )


def test_upload_import_ref_uses_submitted_path_contract() -> None:
    contract = resolve_artifact_ref_contract(
        "art://upload-import/tkt_1/spec.pdf",
        logical_path="20-evidence/delivery/tkt_1/spec.pdf",
    )

    assert contract.kind == ArtifactRefKind.UPLOAD_IMPORT
    assert contract.logical_path == "20-evidence/delivery/tkt_1/spec.pdf"
    assert contract.is_final_closeout_evidence is False


def test_capability_write_set_does_not_need_role_name() -> None:
    assert build_allowed_write_set_for_capabilities(
        [
            "source.modify.application",
            "test.run.application",
            "evidence.write.git",
            "docs.update.delivery",
        ],
        ticket_id="tkt_1",
    ) == [
        "10-project/src/app/**",
        "20-evidence/tests/tkt_1/**",
        "20-evidence/git/tkt_1/**",
        "10-project/docs/**",
    ]


def test_contract_write_set_matches_nested_paths() -> None:
    allowed = build_allowed_write_set_for_capabilities(
        ["test.run.application"],
        ticket_id="tkt_1",
    )

    assert match_contract_write_set("20-evidence/tests/tkt_1/attempt-1/pytest.json", allowed)
    assert not match_contract_write_set("20-evidence/tests/tkt_2/attempt-1/pytest.json", allowed)
    assert not match_contract_write_set("10-project/src/app/main.py", allowed)


@pytest.mark.parametrize(
    "artifact_ref",
    [
        "art://workspace/tkt_1/source/src/app/main.py",
        "art://workspace/tkt_1/source.ts",
        "art://workspace/tkt_1/tests/attempt-1/pytest.json",
        "art://workspace/tkt_1/test-report.json",
        "art://runtime/tkt_1/delivery-check-report.json",
        "art://runtime/tkt_1/git/attempt-1/commit.json",
        "art://runtime/tkt_1/delivery-closeout-package.json",
    ],
)
def test_closeout_final_ref_accepts_current_delivery_evidence(artifact_ref: str) -> None:
    result = classify_closeout_final_artifact_ref(
        artifact_ref,
        current_artifact_refs={artifact_ref},
        superseded_artifact_refs=set(),
        placeholder_artifact_refs=set(),
    )

    assert result.status == CloseoutFinalRefStatus.ACCEPTED


@pytest.mark.parametrize(
    "artifact_ref",
    [
        "art://runtime/tkt_1/governance/architecture-brief.json",
        "art://archive/tkt_1/old-source.json",
        "art://workspace/tkt_1/source/source.py",
        "art://runtime/tkt_1/placeholder/source-code-delivery.json",
    ],
)
def test_closeout_final_ref_rejects_docs_archive_and_placeholder(artifact_ref: str) -> None:
    result = classify_closeout_final_artifact_ref(
        artifact_ref,
        current_artifact_refs={artifact_ref},
        superseded_artifact_refs=set(),
        placeholder_artifact_refs=(
            {artifact_ref}
            if "placeholder" in artifact_ref or artifact_ref.endswith("/source.py")
            else set()
        ),
    )

    assert result.status != CloseoutFinalRefStatus.ACCEPTED


def test_closeout_final_ref_rejects_superseded_current_ref() -> None:
    artifact_ref = "art://workspace/tkt_1/source/src/app/main.py"

    result = classify_closeout_final_artifact_ref(
        artifact_ref,
        current_artifact_refs={artifact_ref},
        superseded_artifact_refs={artifact_ref},
        placeholder_artifact_refs=set(),
    )

    assert result.status == CloseoutFinalRefStatus.SUPERSEDED
