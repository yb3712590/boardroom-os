from __future__ import annotations

import pytest
from pydantic import ValidationError

from boardroom_os.audit.process_audit import (
    ProcessAuditArtifactKind,
    ProcessAuditContentRef,
    ProcessAuditError,
    ProcessAuditArtifactRef,
    process_audit_readiness,
)
from boardroom_os.closeout.package import CloseoutPackageError, CloseoutPackageRef, build_closeout_package
from boardroom_os.contracts.hashes import Sha256Hex
from boardroom_os.contracts.refs import namespaced_ref
from tests.closeout.test_closeout_package import _closeout_package_builder_input
from tests.closeout.test_process_audit_artifacts import _artifact_by_kind, _build_bundle


def test_namespaced_ref_binding_helper_accepts_exact_binding() -> None:
    content_hash = Sha256Hex(value="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")
    value = namespaced_ref(
        kind="process-audit-artifact",
        project_ref="project-tiny-fullstack",
        content_hash=content_hash.value,
        run_id="run-v2-071e",
        extra_suffix="timeline",
    )

    from boardroom_os.contracts.refs import assert_namespaced_ref_binding

    assert (
        assert_namespaced_ref_binding(
            value,
            kind="process-audit-artifact",
            project_ref="project-tiny-fullstack",
            content_hash=content_hash,
            run_id="run-v2-071e",
            extra_suffix="timeline",
            field_name="artifact_ref",
        )
        == value
    )


def test_replay_bundle_readiness_verifies_payload_manifest_with_resolver() -> None:
    from tests.negative.test_replay_payload_manifest_tampering_rejected import PayloadResolver, _bundle_with_payload_hashes, _payloads

    payloads = _payloads()
    readiness = process_audit_readiness(_build_bundle()).model_copy()
    replay_readiness = __import__(
        "boardroom_os.audit.replay_bundle",
        fromlist=["replay_bundle_readiness"],
    ).replay_bundle_readiness(_bundle_with_payload_hashes(payloads), payload_resolver=PayloadResolver(payloads))

    assert readiness.all_artifacts_present is True
    assert replay_readiness.payload_sha256_verified is True


def test_closeout_package_accepts_graph_version_equal_to_replay_boundary() -> None:
    builder_input = _closeout_package_builder_input()

    package = build_closeout_package(builder_input)

    assert package.graph_version == builder_input.replay_bundle.attestations[0].event_window.last_graph_version


def test_process_audit_readiness_rejects_legacy_artifact_ref() -> None:
    bundle = _build_bundle()
    timeline = _artifact_by_kind(bundle, ProcessAuditArtifactKind.TIMELINE)
    legacy_timeline = timeline.model_copy(
        update={"artifact_id": ProcessAuditArtifactRef(value="process-audit-artifact.timeline")}
    )
    artifacts = tuple(legacy_timeline if artifact is timeline else artifact for artifact in bundle.artifacts)
    entries = tuple(
        entry.model_copy(update={"artifact_ref": legacy_timeline.artifact_id})
        if entry.path == timeline.path
        else entry
        for entry in bundle.artifact_manifest.entries
    )
    artifact_manifest = bundle.artifact_manifest.model_copy(update={"entries": entries})
    report = bundle.process_audit_report.model_copy(update={"timeline_ref": legacy_timeline.artifact_id})
    hash_manifest = bundle.hash_manifest.model_copy(
        update={
            "artifact_manifest_hash": type(bundle.hash_manifest.artifact_manifest_hash)(
                value=__import__("boardroom_os.audit.process_audit", fromlist=["_hash_model"])._hash_model(artifact_manifest)
            ),
            "process_audit_report_hash": type(bundle.hash_manifest.process_audit_report_hash)(
                value=__import__("boardroom_os.audit.process_audit", fromlist=["_hash_model"])._hash_model(report)
            ),
        }
    )
    broken_bundle = bundle.model_copy(
        update={
            "artifacts": artifacts,
            "artifact_manifest": artifact_manifest,
            "process_audit_report": report,
            "hash_manifest": hash_manifest,
        }
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="process audit artifact ref namespace binding mismatch",
    ):
        process_audit_readiness(broken_bundle)


def test_process_audit_readiness_rejects_legacy_content_ref() -> None:
    bundle = _build_bundle()
    timeline = _artifact_by_kind(bundle, ProcessAuditArtifactKind.TIMELINE)
    legacy_timeline = timeline.model_copy(
        update={"content_ref": ProcessAuditContentRef(value="process-audit-content.timeline")}
    )
    artifacts = tuple(legacy_timeline if artifact is timeline else artifact for artifact in bundle.artifacts)
    entries = tuple(
        entry.model_copy(update={"content_ref": legacy_timeline.content_ref})
        if entry.path == timeline.path
        else entry
        for entry in bundle.artifact_manifest.entries
    )
    artifact_manifest = bundle.artifact_manifest.model_copy(update={"entries": entries})
    hash_manifest = bundle.hash_manifest.model_copy(
        update={
            "artifact_manifest_hash": type(bundle.hash_manifest.artifact_manifest_hash)(
                value=__import__("boardroom_os.audit.process_audit", fromlist=["_hash_model"])._hash_model(artifact_manifest)
            ),
        }
    )
    broken_bundle = bundle.model_copy(
        update={
            "artifacts": artifacts,
            "artifact_manifest": artifact_manifest,
            "hash_manifest": hash_manifest,
        }
    )

    with pytest.raises(
        (ProcessAuditError, ValidationError),
        match="process audit content ref namespace binding mismatch",
    ):
        process_audit_readiness(broken_bundle)


def test_process_audit_artifact_and_content_refs_are_namespaced() -> None:
    bundle = _build_bundle()

    for artifact in bundle.artifacts:
        assert artifact.artifact_id.value.startswith(
            f"process-audit-artifact.{bundle.project_ref.value}.{artifact.sha256.value[:12]}."
        )
        assert artifact.artifact_id.value.endswith(f".{artifact.kind.value}")
        assert artifact.content_ref.value.startswith(
            f"process-audit-content.{bundle.project_ref.value}.{artifact.sha256.value[:12]}."
        )
        assert artifact.content_ref.value.endswith(f".{artifact.kind.value}")


def test_closeout_package_ref_is_namespaced_by_project_hash_and_run() -> None:
    builder_input = _closeout_package_builder_input()
    package = build_closeout_package(builder_input)

    assert package.closeout_package_id.value.startswith(
        f"closeout-package.{package.project_ref.value}."
    )
    assert ".run-v2-071e" in package.closeout_package_id.value


def test_closeout_package_id_changes_when_run_id_changes() -> None:
    first_input = _closeout_package_builder_input(run_id="run-v2-071e-a")
    second_input = _closeout_package_builder_input(run_id="run-v2-071e-b")

    first_package = build_closeout_package(first_input)
    second_package = build_closeout_package(second_input)

    assert first_package.closeout_package_id != second_package.closeout_package_id


def test_closeout_package_rejects_non_namespaced_package_id() -> None:
    package = build_closeout_package(_closeout_package_builder_input())
    payload = package.model_dump(mode="python")
    payload["closeout_package_id"] = CloseoutPackageRef(value="closeout-package.legacy")

    with pytest.raises((CloseoutPackageError, ValidationError), match="closeout_package_id namespace binding mismatch"):
        type(package).model_validate(payload)


def test_closeout_package_checked_refs_cover_payload_manifest_hash() -> None:
    builder_input = _closeout_package_builder_input()
    package = build_closeout_package(builder_input)
    checked_refs = {ref.value for ref in package.checked_refs}

    assert builder_input.replay_readiness.payload_manifest_ref.value in checked_refs
    assert builder_input.replay_readiness.payload_manifest_hash.value in checked_refs


def test_closeout_package_rejects_cross_project_process_audit_artifact_ref() -> None:
    bundle = _build_bundle()
    timeline = _artifact_by_kind(bundle, ProcessAuditArtifactKind.TIMELINE)
    cross_project_ref = ProcessAuditArtifactRef(
        value=namespaced_ref(
            kind="process-audit-artifact",
            project_ref="project-other",
            content_hash=timeline.sha256.value,
            run_id="run-v2-071e",
            extra_suffix=timeline.kind.value,
        )
    )
    legacy_timeline = timeline.model_copy(update={"artifact_id": cross_project_ref})
    artifacts = tuple(legacy_timeline if artifact is timeline else artifact for artifact in bundle.artifacts)
    entries = tuple(
        entry.model_copy(update={"artifact_ref": cross_project_ref}) if entry.path == timeline.path else entry
        for entry in bundle.artifact_manifest.entries
    )
    artifact_manifest = bundle.artifact_manifest.model_copy(update={"entries": entries})
    report = bundle.process_audit_report.model_copy(update={"timeline_ref": cross_project_ref})
    hash_manifest = bundle.hash_manifest.model_copy(
        update={
            "artifact_manifest_hash": type(bundle.hash_manifest.artifact_manifest_hash)(
                value=__import__("boardroom_os.audit.process_audit", fromlist=["_hash_model"])._hash_model(artifact_manifest)
            ),
            "process_audit_report_hash": type(bundle.hash_manifest.process_audit_report_hash)(
                value=__import__("boardroom_os.audit.process_audit", fromlist=["_hash_model"])._hash_model(report)
            ),
        }
    )
    broken_bundle = bundle.model_copy(
        update={
            "artifacts": artifacts,
            "artifact_manifest": artifact_manifest,
            "process_audit_report": report,
            "hash_manifest": hash_manifest,
        }
    )

    with pytest.raises((ProcessAuditError, ValidationError), match="namespace binding mismatch"):
        process_audit_readiness(broken_bundle)


def test_closeout_package_rejects_cross_run_artifact_ref() -> None:
    bundle = _build_bundle()
    timeline = _artifact_by_kind(bundle, ProcessAuditArtifactKind.TIMELINE)
    cross_run_ref = ProcessAuditArtifactRef(
        value=namespaced_ref(
            kind="process-audit-artifact",
            project_ref=bundle.project_ref.value,
            content_hash=timeline.sha256.value,
            run_id="run-other",
            extra_suffix=timeline.kind.value,
        )
    )
    broken_timeline = timeline.model_copy(update={"artifact_id": cross_run_ref})
    artifacts = tuple(broken_timeline if artifact is timeline else artifact for artifact in bundle.artifacts)
    entries = tuple(
        entry.model_copy(update={"artifact_ref": cross_run_ref}) if entry.path == timeline.path else entry
        for entry in bundle.artifact_manifest.entries
    )
    artifact_manifest = bundle.artifact_manifest.model_copy(update={"entries": entries})
    report = bundle.process_audit_report.model_copy(update={"timeline_ref": cross_run_ref})
    hash_manifest = bundle.hash_manifest.model_copy(
        update={
            "artifact_manifest_hash": type(bundle.hash_manifest.artifact_manifest_hash)(
                value=__import__("boardroom_os.audit.process_audit", fromlist=["_hash_model"])._hash_model(artifact_manifest)
            ),
            "process_audit_report_hash": type(bundle.hash_manifest.process_audit_report_hash)(
                value=__import__("boardroom_os.audit.process_audit", fromlist=["_hash_model"])._hash_model(report)
            ),
        }
    )
    broken_bundle = bundle.model_copy(
        update={
            "artifacts": artifacts,
            "artifact_manifest": artifact_manifest,
            "process_audit_report": report,
            "hash_manifest": hash_manifest,
        }
    )

    with pytest.raises((ProcessAuditError, ValidationError), match="namespace binding mismatch"):
        process_audit_readiness(broken_bundle)
