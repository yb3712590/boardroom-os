from __future__ import annotations

from datetime import UTC, datetime

import pytest

from boardroom_os.adapters.git_audit import GitAuditAdapter, GitAuditAdapterError, GitCommandResult
from tests.closeout.test_closeout_gate import _FINAL_COMMIT_SHA, _ready_input
from tests.closeout.test_git_version_audit import _BASE_COMMIT_SHA, source_inventory_hash

_NOW = datetime(2026, 5, 27, 12, 0, tzinfo=UTC)
_CWD = "D:/tmp/repo"


class FakeGitTransport:
    def __init__(self) -> None:
        self.commands: list[tuple[str, ...]] = []

    def run(self, command: tuple[str, ...], *, cwd: str) -> GitCommandResult:
        self.commands.append(command)
        outputs = {
            ("git", "rev-parse", "HEAD"): f"{_FINAL_COMMIT_SHA}\n",
            ("git", "rev-parse", "--abbrev-ref", "HEAD"): "main\n",
            ("git", "status", "--porcelain=v1", "-z"): "",
            ("git", "diff", "--shortstat"): "",
            ("git", "tag", "--points-at", "HEAD"): "",
        }
        return GitCommandResult(
            command=command,
            cwd=cwd,
            exit_code=0,
            stdout=outputs[command],
            stderr="",
        )


def _collect_kwargs(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "package_root": "10-project",
        "project_ref": "project-tiny-fullstack",
        "cwd": _CWD,
        "source_inventory_hash": source_inventory_hash(_ready_input().source_inventory),
        "base_commit_sha": _BASE_COMMIT_SHA,
        "worktree_ref": "worktree.final-package",
        "generated_at": _NOW,
    }
    values.update(overrides)
    return values


def test_git_audit_adapter_requires_base_commit_sha() -> None:
    adapter = GitAuditAdapter(transport=FakeGitTransport())

    with pytest.raises(GitAuditAdapterError, match="base_commit_sha is required"):
        adapter.collect(**_collect_kwargs(base_commit_sha=None))


def test_git_audit_adapter_requires_worktree_ref() -> None:
    adapter = GitAuditAdapter(transport=FakeGitTransport())

    with pytest.raises(GitAuditAdapterError, match="worktree_ref is required"):
        adapter.collect(**_collect_kwargs(worktree_ref=None))


def test_git_audit_adapter_rejects_missing_source_inventory_hash() -> None:
    adapter = GitAuditAdapter(transport=FakeGitTransport())

    with pytest.raises(GitAuditAdapterError, match="source_inventory_hash is required"):
        adapter.collect(**_collect_kwargs(source_inventory_hash=None))


def test_git_audit_adapter_uses_status_porcelain_v1_z() -> None:
    transport = FakeGitTransport()
    adapter = GitAuditAdapter(transport=transport)

    adapter.collect(**_collect_kwargs())

    assert ("git", "status", "--porcelain=v1", "-z") in transport.commands
    assert ("git", "status", "--porcelain") not in transport.commands


def test_git_audit_adapter_uses_diff_shortstat() -> None:
    transport = FakeGitTransport()
    adapter = GitAuditAdapter(transport=transport)

    adapter.collect(**_collect_kwargs())

    assert ("git", "diff", "--shortstat") in transport.commands
    assert ("git", "diff", "--stat") not in transport.commands
