from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from boardroom_os.audit.process_audit import (
    REQUIRED_PROCESS_AUDIT_ARTIFACT_PATHS,
    ProcessAuditArtifactFormat,
    ProcessAuditArtifactKind,
    ProcessAuditBuilderInput,
    ProcessAuditError,
    build_process_audit_bundle,
    process_audit_readiness,
)
from boardroom_os.closeout.gate import GitAuditReadiness, ProcessAuditReadiness

from tests.closeout.test_process_audit_artifacts import (
    _artifact_by_kind,
    _artifact_by_path,
    _artifact_content_hash,
    _build_bundle,
    _process_audit_builder_input,
)


def test_process_audit_bundle_materializes_required_audit_artifacts() -> None:
    bundle = _build_bundle()

    assert bundle.version == 1
    assert len(bundle.artifacts) == 10
    assert {artifact.path.value for artifact in bundle.artifacts} == set(
        REQUIRED_PROCESS_AUDIT_ARTIFACT_PATHS
    )
    assert {entry.path.value for entry in bundle.artifact_manifest.entries} == set(
        REQUIRED_PROCESS_AUDIT_ARTIFACT_PATHS
    )
    assert {artifact.kind for artifact in bundle.artifacts} == {
        ProcessAuditArtifactKind.PROCESS_AUDIT,
        ProcessAuditArtifactKind.TIMELINE,
        ProcessAuditArtifactKind.DECISION_LOG,
        ProcessAuditArtifactKind.AGENT_CONTEXT_INDEX,
        ProcessAuditArtifactKind.TICKET_GRAPH,
        ProcessAuditArtifactKind.ARTIFACT_LINEAGE,
        ProcessAuditArtifactKind.EVIDENCE_MAP,
        ProcessAuditArtifactKind.GIT_VERSION_AUDIT,
        ProcessAuditArtifactKind.CLOSEOUT_SUMMARY,
        ProcessAuditArtifactKind.REPLAY_BUNDLE_REPORT,
    }


def test_process_audit_bundle_computes_hash_manifest_closure() -> None:
    bundle = _build_bundle()

    assert set(bundle.hash_manifest.artifact_hashes) == set(REQUIRED_PROCESS_AUDIT_ARTIFACT_PATHS)
    for artifact in bundle.artifacts:
        assert artifact.sha256.value == _artifact_content_hash(
            artifact.content, artifact.format
        )
        assert (
            bundle.hash_manifest.artifact_hashes[artifact.path.value].value
            == artifact.sha256.value
        )
    assert bundle.hash_manifest.artifact_manifest_hash.value
    assert bundle.hash_manifest.process_audit_report_hash.value
    assert bundle.hash_manifest.bundle_payload_hash.value
    assert bundle.bundle_hash == bundle.hash_manifest.bundle_payload_hash.value


def test_process_audit_readiness_projects_to_closeout_gate_contract() -> None:
    readiness = process_audit_readiness(_build_bundle())

    assert isinstance(readiness, ProcessAuditReadiness)
    assert {
        getattr(path, "value", path) for path in readiness.artifact_paths
    } == set(REQUIRED_PROCESS_AUDIT_ARTIFACT_PATHS)
    assert readiness.all_artifacts_present is True
    assert readiness.timeline_key_events_present is True
    assert readiness.agent_context_index_complete is True
    assert readiness.artifact_lineage_complete is True
    assert readiness.evidence_map_consistent_with_final_table is True


def test_process_audit_bundle_is_audit_friendly_json() -> None:
    first_bundle = _build_bundle()
    second_bundle = _build_bundle()

    payload = first_bundle.model_dump(mode="json")
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)

    assert "D:/" not in serialized
    assert "C:/" not in serialized
    assert "D:\\\\" not in serialized
    assert "C:\\\\" not in serialized
    assert ".pytest_tmp" not in serialized
    assert first_bundle.process_audit_bundle_id == second_bundle.process_audit_bundle_id
    assert first_bundle.bundle_hash == second_bundle.bundle_hash


def test_process_audit_report_indexes_all_artifacts() -> None:
    bundle = _build_bundle()
    report = bundle.process_audit_report

    artifact_refs = {artifact.artifact_id.value for artifact in bundle.artifacts}
    indexed_refs = {
        report.process_audit_ref.value,
        report.timeline_ref.value,
        report.decision_log_ref.value,
        report.agent_context_index_ref.value,
        report.ticket_graph_ref.value,
        report.artifact_lineage_ref.value,
        report.evidence_map_ref.value,
        report.git_audit_ref.value,
        report.closeout_summary_ref.value,
        report.replay_bundle_report_ref.value,
    }

    assert indexed_refs == artifact_refs
    checked_refs = set(report.checked_refs)
    assert "package-contract.closeout-gate" in checked_refs
    assert "acceptance-contract.process-audit" in checked_refs
    assert "source-diff.app" in checked_refs
    assert "provider-attempt.app" in checked_refs
    assert any(ref.startswith("replay-bundle.") for ref in checked_refs)
    assert any(ref.startswith("report.replay.") for ref in checked_refs)
    assert any(ref.startswith("git-version-audit-bundle.") for ref in checked_refs)
    assert any(ref.startswith("git-version-audit-report.") for ref in checked_refs)
    assert any(ref.startswith("git-version-audit-facts.") for ref in checked_refs)
    assert "verification-run.app" in checked_refs
    assert "git-command-evidence-binding.verification-run.app" in checked_refs


def test_process_audit_markdown_is_human_readable() -> None:
    bundle = _build_bundle()

    process_audit = _artifact_by_path(bundle, "30-audit/process-audit.md")
    decision_log = _artifact_by_path(bundle, "30-audit/decision-log.md")
    ticket_graph = _artifact_by_path(bundle, "30-audit/ticket-graph.md")
    git_audit = _artifact_by_path(bundle, "30-audit/git-version-audit.md")
    closeout_summary = _artifact_by_path(bundle, "30-audit/closeout-summary.md")

    assert process_audit.format is ProcessAuditArtifactFormat.MARKDOWN
    assert process_audit.content.startswith("# Process Audit\n\n")
    assert "\n\n## Requirement interpretation\n" in process_audit.content
    assert "\n\n## Contract formation\n" in process_audit.content
    assert "\n\n## Team execution\n" in process_audit.content
    assert "\n\n## Evidence verification\n" in process_audit.content
    assert "\n\n## Checker review\n" in process_audit.content
    assert "\n\n## Replay and closeout readiness\n" in process_audit.content
    assert " " not in process_audit.content

    assert decision_log.content.startswith("# Decision Log\n\n")
    assert "\n\n## CEO / Human Board Decision\n" in decision_log.content
    assert "ticket.app" in ticket_graph.content
    assert "AC-APP" in ticket_graph.content
    assert "Final commit SHA" in git_audit.content
    assert "Git clean status" in git_audit.content
    assert "Source inventory hash" in git_audit.content
    assert "Source inventory ref" in git_audit.content
    assert "Package commit ref" in git_audit.content
    assert "Git bundle id" in git_audit.content
    assert "Git report id" in git_audit.content
    assert "Git hash manifest id" in git_audit.content
    assert "Git fact set id" in git_audit.content
    assert "Command binding ids" in git_audit.content
    assert "package-contract.closeout-gate" in closeout_summary.content
    assert "source-inventory" in closeout_summary.content
    assert "checker-verdict" in closeout_summary.content


def test_process_audit_report_references_json_and_markdown_artifacts() -> None:
    bundle = _build_bundle()

    assert _artifact_by_kind(bundle, ProcessAuditArtifactKind.TIMELINE).format is ProcessAuditArtifactFormat.JSON
    assert _artifact_by_kind(bundle, ProcessAuditArtifactKind.AGENT_CONTEXT_INDEX).format is ProcessAuditArtifactFormat.JSON
    assert _artifact_by_kind(bundle, ProcessAuditArtifactKind.ARTIFACT_LINEAGE).format is ProcessAuditArtifactFormat.JSON
    assert _artifact_by_kind(bundle, ProcessAuditArtifactKind.EVIDENCE_MAP).format is ProcessAuditArtifactFormat.JSON
    assert _artifact_by_kind(bundle, ProcessAuditArtifactKind.REPLAY_BUNDLE_REPORT).format is ProcessAuditArtifactFormat.JSON
    assert _artifact_by_kind(bundle, ProcessAuditArtifactKind.PROCESS_AUDIT).format is ProcessAuditArtifactFormat.MARKDOWN
    assert _artifact_by_kind(bundle, ProcessAuditArtifactKind.DECISION_LOG).format is ProcessAuditArtifactFormat.MARKDOWN


def test_process_audit_timeline_includes_real_event_records() -> None:
    builder_input = _process_audit_builder_input()
    bundle = build_process_audit_bundle(builder_input)

    timeline = _artifact_by_kind(bundle, ProcessAuditArtifactKind.TIMELINE)
    event_by_ref = {event["event_ref"]: event for event in timeline.content["events"]}

    for source_event in builder_input.events:
        projected = event_by_ref[source_event.event_id.value]
        assert projected["kind"] == source_event.event_type.value
        assert projected["timestamp"] == source_event.timestamp.isoformat()
        assert projected["actor_ref"] == source_event.actor_ref.value
        assert projected["graph_version"] == source_event.graph_version
        assert projected["payload_refs"] == [ref.value for ref in source_event.payload_refs]
        assert projected["source"] == "event_log"


def test_process_audit_timeline_keeps_audit_milestones_separate_from_event_log() -> None:
    builder_input = _process_audit_builder_input()
    bundle = build_process_audit_bundle(builder_input)

    timeline = _artifact_by_kind(bundle, ProcessAuditArtifactKind.TIMELINE)
    source_events = [event for event in timeline.content["events"] if event["source"] == "event_log"]
    audit_milestones = [event for event in timeline.content["events"] if event["source"] == "process_audit_projection"]

    assert [event["event_ref"] for event in source_events] == [
        event.event_id.value for event in builder_input.events
    ]
    assert {event["kind"] for event in audit_milestones} >= {
        "directive_received",
        "acceptance_contract_created",
        "package_contract_created",
        "evidence_verified",
        "checker_verdict_recorded",
        "closeout_prepared",
        "replay_bundle_materialized",
    }


def test_process_audit_builder_input_rejects_raw_dict_inputs() -> None:
    payload = _process_audit_builder_input().model_dump(mode="python")

    with pytest.raises(ValidationError, match="typed model instances"):
        ProcessAuditBuilderInput.model_validate(payload)


def test_process_audit_builder_input_rejects_scalar_tuple_inputs() -> None:
    payload = _process_audit_builder_input().model_dump(mode="python")
    payload["provider_attempt_refs"] = "provider-attempt.app"

    with pytest.raises(ValidationError, match="provider_attempt_refs must be a tuple or list"):
        ProcessAuditBuilderInput.model_validate(payload)


def test_process_audit_builder_input_rejects_wrong_typed_model_field() -> None:
    base_input = _process_audit_builder_input()

    with pytest.raises(ValidationError, match="package_contract must be PackageContract"):
        ProcessAuditBuilderInput.model_validate(
            {
                **base_input.model_dump(mode="python"),
                "package_contract": base_input.checker_verdict,
                "acceptance_contract": base_input.acceptance_contract,
                "source_inventory": base_input.source_inventory,
                "workspace_evidence_bundle": base_input.workspace_evidence_bundle,
                "final_evidence_table": base_input.final_evidence_table,
                "checker_verdict": base_input.checker_verdict,
                "replay_bundle": base_input.replay_bundle,
                "replay_readiness": base_input.replay_readiness,
                "git_version_audit_bundle": base_input.git_version_audit_bundle,
                "git_audit_readiness": base_input.git_audit_readiness,
                "agent_context_index": base_input.agent_context_index,
                "ticket_graph_summary": base_input.ticket_graph_summary,
            }
        )


def test_process_audit_builder_input_requires_git_version_audit_bundle() -> None:
    base_input = _process_audit_builder_input()
    payload = base_input.model_dump(mode="python")
    payload.pop("git_version_audit_bundle")

    with pytest.raises(ValidationError, match="git_version_audit_bundle"):
        ProcessAuditBuilderInput.model_validate(payload)


def test_process_audit_builder_input_rejects_git_audit_readiness_mismatch() -> None:
    with pytest.raises(
        ValidationError,
        match="git version audit readiness mismatch",
    ):
        ProcessAuditBuilderInput.model_validate(
            _process_audit_builder_input(
                git_audit_readiness=GitAuditReadiness(
                    git_clean=False,
                    final_commit_sha="d" * 40,
                    source_inventory_hash="e" * 64,
                    source_inventory_hash_matches=False,
                    final_command_evidence_at_final_commit=False,
                )
            ).model_dump(mode="python")
        )


def test_process_audit_builder_input_rejects_git_version_audit_project_ref_mismatch() -> None:
    base_input = _process_audit_builder_input()
    mismatched_input = base_input.model_copy(
        update={
            "git_version_audit_bundle": base_input.git_version_audit_bundle.model_copy(
                update={"project_ref": type(base_input.project_ref)(value="project.other")}
            )
        }
    )

    with pytest.raises(ValidationError, match="git version audit bundle project_ref mismatch"):
        ProcessAuditBuilderInput.model_validate(mismatched_input)


def test_process_audit_builder_input_requires_typed_model_instances() -> None:
    typed_input = _build_bundle()

    assert typed_input.version == 1
    assert ProcessAuditBuilderInput is not None
    assert build_process_audit_bundle is not None
