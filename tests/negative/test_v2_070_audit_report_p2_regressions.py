from __future__ import annotations

from boardroom_os.adapters.git_audit import GitAuditAdapter
import pytest

from boardroom_os.audit.git_version_audit import GitVersionAuditError, build_git_version_audit_bundle
from tests.closeout.test_git_audit_hardening import FakeGitTransport, _collect, _second_binding, _second_run
from tests.closeout.test_git_version_audit import _builder_input, _command_binding
from tests.closeout.test_process_audit_fact_chain import _stable_hash_input_with_order
from tests.closeout.test_process_audit_artifacts import _process_audit_builder_input
from tests.closeout.test_replay_bundle_rereplay import _artifact_manifest_entries, _bundle, _events, _payload_manifest_entries
from tests.closeout.test_v2_070_fact_chain_end_to_end import build_v2_070_fact_chain_fixture
from boardroom_os.audit.process_audit import build_process_audit_bundle
from boardroom_os.execution.context_index import ProviderAttemptRef


def test_p2_1_git_version_audit_verification_run_order_is_stable_for_fact_chain_readiness() -> None:
    first_run = __import__("tests.closeout.test_closeout_gate", fromlist=["_ready_input"])._ready_input().verification_runs[0]
    second_run = _second_run()
    first_binding = _command_binding()
    second_binding = _second_binding(second_run)

    first_bundle = build_git_version_audit_bundle(
        _builder_input(verification_runs=(first_run, second_run), command_evidence_bindings=(first_binding, second_binding))
    )
    second_bundle = build_git_version_audit_bundle(
        _builder_input(verification_runs=(second_run, first_run), command_evidence_bindings=(first_binding, second_binding))
    )

    fixture = build_v2_070_fact_chain_fixture()
    assert fixture.git_audit_readiness.git_clean is True
    assert first_bundle.report.command_evidence_refs == second_bundle.report.command_evidence_refs
    assert first_bundle.bundle_hash == second_bundle.bundle_hash


def test_p2_2_replay_manifest_entry_order_is_stable_before_audit_and_closeout() -> None:
    events = _events()
    ordered_payload_bundle = _bundle(events=events, payload_manifest_entries=_payload_manifest_entries(events))
    reversed_payload_bundle = _bundle(events=events, payload_manifest_entries=tuple(reversed(_payload_manifest_entries(events))))
    ordered_artifact_bundle = _bundle(events=events, artifact_manifest_entries=_artifact_manifest_entries(events))
    reversed_artifact_bundle = _bundle(events=events, artifact_manifest_entries=tuple(reversed(_artifact_manifest_entries(events))))

    fixture = build_v2_070_fact_chain_fixture()
    assert fixture.replay_readiness.replay_passed is True
    assert ordered_payload_bundle.payload_manifest.payload_manifest_hash == reversed_payload_bundle.payload_manifest.payload_manifest_hash
    assert ordered_artifact_bundle.artifact_manifest.artifact_manifest_hash == reversed_artifact_bundle.artifact_manifest.artifact_manifest_hash


def test_p2_3_process_audit_checked_refs_order_is_stable_before_closeout() -> None:
    ascending_provider_refs = (ProviderAttemptRef(value="provider-attempt.alpha"), ProviderAttemptRef(value="provider-attempt.beta"))
    first_bundle = build_process_audit_bundle(
        _stable_hash_input_with_order(
            provider_attempt_refs=ascending_provider_refs,
            verification_run_order=(0, 1),
            evidence_order=(0, 1),
            agent_context_entry_order=(0, 1),
        )
    )
    second_bundle = build_process_audit_bundle(
        _stable_hash_input_with_order(
            provider_attempt_refs=tuple(reversed(ascending_provider_refs)),
            verification_run_order=(1, 0),
            evidence_order=(1, 0),
            agent_context_entry_order=(1, 0),
        )
    )

    fixture = build_v2_070_fact_chain_fixture()
    assert fixture.process_audit_readiness.all_artifacts_present is True
    assert first_bundle.checked_refs == second_bundle.checked_refs
    assert first_bundle.bundle_hash == second_bundle.bundle_hash


def test_p2_4_git_status_z_parses_special_filenames_before_git_readiness() -> None:
    facts = _collect(
        FakeGitTransport(
            status_output=(
                " M docs/name with\nnewline.md\0"
                " M docs/quote\"name.md\0"
                " M docs/tab\tname.md\0"
                " M docs/a -> b.md\0"
            ),
            diff_output="4 files changed, 2 insertions(+), 1 deletion(-)\n",
        )
    )

    assert tuple(file.path for file in facts.changed_files) == (
        "docs/name with\nnewline.md",
        "docs/quote\"name.md",
        "docs/tab\tname.md",
        "docs/a -> b.md",
    )
    with pytest.raises(GitVersionAuditError, match="git facts must be clean"):
        build_git_version_audit_bundle(_builder_input(git_facts=facts))


def test_p2_5_git_diff_shortstat_ignores_filename_containing_insertions_before_git_readiness() -> None:
    facts = _collect(
        FakeGitTransport(
            status_output=" M docs/12 insertions.md\0",
            diff_output="1 file changed, 1 deletion(-)\n",
        )
    )

    assert facts.diff_summary.changed_file_count == 1
    assert facts.diff_summary.insertions == 0
    assert facts.diff_summary.deletions == 1
    with pytest.raises(GitVersionAuditError, match="git facts must be clean"):
        build_git_version_audit_bundle(_builder_input(git_facts=facts))
