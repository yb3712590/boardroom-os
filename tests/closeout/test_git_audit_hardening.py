from __future__ import annotations

from datetime import UTC, datetime

from boardroom_os.adapters.git_audit import GitAuditAdapter, GitCommandResult
from boardroom_os.audit.git_version_audit import GitChangedFileStatus, build_git_version_audit_bundle
from tests.closeout.test_closeout_gate import _FINAL_COMMIT_SHA, _ready_input
from tests.closeout.test_git_version_audit import (
    _BASE_COMMIT_SHA,
    _OTHER_COMMIT_SHA,
    _builder_input,
    _command_bindings,
    source_inventory_hash,
)

_NOW = datetime(2026, 5, 27, 12, 0, tzinfo=UTC)
_CWD = "D:/tmp/repo"


class FakeGitTransport:
    def __init__(
        self,
        *,
        head: str = _FINAL_COMMIT_SHA,
        status_output: str = "",
        diff_output: str = "",
    ) -> None:
        self.head = head
        self.status_output = status_output
        self.diff_output = diff_output
        self.commands: list[tuple[str, ...]] = []

    def run(self, command: tuple[str, ...], *, cwd: str) -> GitCommandResult:
        self.commands.append(command)
        outputs = {
            ("git", "rev-parse", "HEAD"): f"{self.head}\n",
            ("git", "rev-parse", "--abbrev-ref", "HEAD"): "main\n",
            ("git", "status", "--porcelain=v1", "-z"): self.status_output,
            ("git", "diff", "--shortstat"): self.diff_output,
            ("git", "tag", "--points-at", "HEAD"): "",
        }
        return GitCommandResult(
            command=command,
            cwd=cwd,
            exit_code=0,
            stdout=outputs[command],
            stderr="",
        )


def _collect(transport: FakeGitTransport):
    return GitAuditAdapter(transport=transport).collect(
        package_root="10-project",
        project_ref="project-tiny-fullstack",
        cwd=_CWD,
        source_inventory_hash=source_inventory_hash(_ready_input().source_inventory),
        base_commit_sha=_BASE_COMMIT_SHA,
        worktree_ref="worktree.final-package",
        generated_at=_NOW,
    )


def _two_verification_runs():
    first_run = _ready_input().verification_runs[0]
    second_run = first_run.model_copy(
        update={
            "verification_run_id": type(first_run.verification_run_id)(
                value="verification-run.test-app.extra"
            ),
            "stdout_ref": type(first_run.stdout_ref)(
                value="command-output.verification-run.test-app.extra.stdout"
            ),
            "stderr_ref": type(first_run.stderr_ref)(
                value="command-output.verification-run.test-app.extra.stderr"
            ),
            "workspace_snapshot_ref": type(first_run.workspace_snapshot_ref)(
                value="workspace-snapshot.app.extra"
            ),
        }
    )
    return first_run, second_run


def _two_command_bindings():
    first_binding = _command_bindings()[0]
    second_binding = first_binding.model_copy(
        update={
            "binding_id": type(first_binding.binding_id)(
                value="git-command-evidence-binding.verification-run.test-app.extra"
            ),
            "verification_run_ref": type(first_binding.verification_run_ref)(
                value="verification-run.test-app.extra"
            ),
            "workspace_snapshot_ref": type(first_binding.workspace_snapshot_ref)(
                value="workspace-snapshot.app.extra"
            ),
        }
    )
    return first_binding, second_binding


def test_status_z_parses_filename_with_newline_quote_tab_and_arrow_text() -> None:
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


def test_status_z_parses_renamed_file_without_arrow_syntax() -> None:
    facts = _collect(
        FakeGitTransport(
            status_output="R  docs/new name.md\0docs/old -> literal name.md\0",
            diff_output="1 file changed, 1 insertion(+)\n",
        )
    )

    assert len(facts.changed_files) == 1
    changed_file = facts.changed_files[0]
    assert changed_file.status is GitChangedFileStatus.RENAMED
    assert changed_file.path == "docs/new name.md"
    assert changed_file.previous_path == "docs/old -> literal name.md"


def test_diff_shortstat_ignores_filename_containing_insertions() -> None:
    facts = _collect(
        FakeGitTransport(
            status_output=" M docs/12 insertions.md\0",
            diff_output="1 file changed, 1 deletion(-)\n",
        )
    )

    assert facts.diff_summary.changed_file_count == 1
    assert facts.diff_summary.insertions == 0
    assert facts.diff_summary.deletions == 1


def test_verification_runs_reordering_keeps_command_evidence_refs_and_bundle_hash_stable() -> None:
    first_run, second_run = _two_verification_runs()
    bindings = _two_command_bindings()

    first_bundle = build_git_version_audit_bundle(
        _builder_input(
            verification_runs=(first_run, second_run),
            command_evidence_bindings=bindings,
        )
    )
    second_bundle = build_git_version_audit_bundle(
        _builder_input(
            verification_runs=(second_run, first_run),
            command_evidence_bindings=bindings,
        )
    )

    assert first_bundle.report.command_evidence_refs == second_bundle.report.command_evidence_refs
    assert first_bundle.bundle_hash == second_bundle.bundle_hash


def test_command_bindings_reordering_keeps_checked_refs_and_bundle_hash_stable() -> None:
    first_run, second_run = _two_verification_runs()
    first_binding, second_binding = _two_command_bindings()

    first_bundle = build_git_version_audit_bundle(
        _builder_input(
            verification_runs=(first_run, second_run),
            command_evidence_bindings=(first_binding, second_binding),
        )
    )
    second_bundle = build_git_version_audit_bundle(
        _builder_input(
            verification_runs=(first_run, second_run),
            command_evidence_bindings=(second_binding, first_binding),
        )
    )

    assert first_bundle.checked_refs == second_bundle.checked_refs
    assert first_bundle.bundle_hash == second_bundle.bundle_hash


def test_fact_set_id_is_namespaced_by_final_commit_payload() -> None:
    first_facts = _collect(FakeGitTransport(head=_FINAL_COMMIT_SHA))
    second_facts = _collect(FakeGitTransport(head=_OTHER_COMMIT_SHA))

    assert first_facts.fact_set_id != second_facts.fact_set_id
    assert first_facts.fact_set_id.value.startswith("git-version-audit-facts.project-tiny-fullstack.")
    assert len(first_facts.fact_set_id.value.rsplit(".", 1)[1]) == 12


def test_git_audit_adapter_collects_explicit_base_and_worktree() -> None:
    facts = _collect(FakeGitTransport())

    assert facts.base_commit_sha.value == _BASE_COMMIT_SHA
    assert facts.worktree_ref.value == "worktree.final-package"
    assert facts.final_commit_sha.value == _FINAL_COMMIT_SHA
