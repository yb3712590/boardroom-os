from __future__ import annotations

import pytest
from pydantic import ValidationError

from boardroom_os.adapters.git_audit import GitAuditAdapterError
from boardroom_os.audit.process_audit import ProcessAuditArtifactKind, ProcessAuditError, process_audit_readiness
from boardroom_os.audit.replay_bundle import ReplayBundleBuilderInput
from boardroom_os.closeout.package import CloseoutPackageError
from boardroom_os.events.types import EventType
from boardroom_os.reducers.closeout_reducer import CloseoutTerminalStatus
from tests.closeout.test_process_audit_artifacts import _artifact_by_kind, _replace_artifact
from tests.closeout.test_replay_bundle import _builder_input as _replay_builder_input
from tests.closeout.test_v2_070_fact_chain_end_to_end import build_v2_070_fact_chain_fixture
from tests.negative.test_git_audit_fallback_rejected import FakeGitTransport, _collect_kwargs


def test_p0_1_fact_chain_commits_closeout_only_after_process_audit_and_package() -> None:
    fixture = build_v2_070_fact_chain_fixture()

    assert all(event.event_type is not EventType.CLOSEOUT_COMMITTED for event in fixture.replay_bundle.events)
    assert fixture.closeout_committed_event.event_type is EventType.CLOSEOUT_COMMITTED
    assert fixture.events_after_closeout == (*fixture.replay_bundle.events, fixture.closeout_committed_event)
    assert fixture.closeout_projection.terminal_status is CloseoutTerminalStatus.SUCCEEDED
    assert fixture.closeout_projection.closeout_package_ref == fixture.closeout_package.closeout_package_id


def test_p0_2_external_projection_summary_cannot_enter_fact_chain() -> None:
    fixture = build_v2_070_fact_chain_fixture()
    payload = {
        **_replay_builder_input(events=fixture.events_before_closeout).model_dump(mode="python"),
        "projection_summary": {"graph_version": 999},
    }

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ReplayBundleBuilderInput.model_validate(payload)


def test_p0_3_tampered_process_audit_timeline_is_rejected_in_shared_fixture_context() -> None:
    fixture = build_v2_070_fact_chain_fixture()
    timeline = _artifact_by_kind(fixture.process_audit_bundle, ProcessAuditArtifactKind.TIMELINE)
    content = dict(timeline.content)
    content["events"] = [event for event in content["events"] if event["event_ref"] != fixture.events_before_closeout[2].event_id.value]
    broken_bundle = _replace_artifact(
        fixture.process_audit_bundle,
        kind=ProcessAuditArtifactKind.TIMELINE,
        content=content,
    )

    with pytest.raises((ProcessAuditError, ValidationError), match="timeline|key event|hash manifest"):
        process_audit_readiness(broken_bundle)


def test_p0_4a_missing_base_commit_sha_stops_git_boundary_before_closeout() -> None:
    with pytest.raises(GitAuditAdapterError, match="base_commit_sha is required"):
        __import__("boardroom_os.adapters.git_audit", fromlist=["GitAuditAdapter"]).GitAuditAdapter(
            transport=FakeGitTransport()
        ).collect(**_collect_kwargs(base_commit_sha=None))


def test_p0_4b_missing_worktree_ref_stops_git_boundary_before_closeout() -> None:
    with pytest.raises(GitAuditAdapterError, match="worktree_ref is required"):
        __import__("boardroom_os.adapters.git_audit", fromlist=["GitAuditAdapter"]).GitAuditAdapter(
            transport=FakeGitTransport()
        ).collect(**_collect_kwargs(worktree_ref=None))


def test_p0_5_closeout_package_cannot_extend_beyond_replay_boundary_in_full_context() -> None:
    fixture = build_v2_070_fact_chain_fixture()

    with pytest.raises((CloseoutPackageError, ValidationError), match="graph_version must equal replay bundle proof boundary"):
        __import__("tests.closeout.test_closeout_package", fromlist=["_closeout_package_builder_input"])._closeout_package_builder_input(
            closeout_gate_result=fixture.closeout_gate_result,
            source_inventory=fixture.source_inventory,
            final_evidence_table=fixture.final_evidence_table,
            replay_bundle=fixture.replay_bundle,
            replay_readiness=fixture.replay_readiness,
            process_audit_bundle=fixture.process_audit_bundle,
            process_audit_readiness=fixture.process_audit_readiness,
            git_version_audit_bundle=fixture.git_version_audit_bundle,
            git_audit_readiness=fixture.git_audit_readiness,
            graph_version=fixture.closeout_package.graph_version + 1,
        )
