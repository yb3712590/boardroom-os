from __future__ import annotations

import re
import subprocess
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, StrictInt

from boardroom_os.contracts.refs import hash_namespaced_payload, namespaced_ref

from boardroom_os.audit.git_version_audit import (
    GitChangedFile,
    GitChangedFileStatus,
    GitDiffSummary,
    GitDirtyStatus,
    GitVersionAuditFactSet,
)

_GIT_REV_PARSE_HEAD = ("git", "rev-parse", "HEAD")
_GIT_REV_PARSE_BRANCH = ("git", "rev-parse", "--abbrev-ref", "HEAD")
_GIT_STATUS_PORCELAIN = ("git", "status", "--porcelain=v1", "-z")
_GIT_DIFF_STAT = ("git", "diff", "--shortstat")
_GIT_TAG_POINTS_AT_HEAD = ("git", "tag", "--points-at", "HEAD")
_GIT_COMMAND_TEMPLATES = frozenset(
    {
        _GIT_REV_PARSE_HEAD,
        _GIT_REV_PARSE_BRANCH,
        _GIT_STATUS_PORCELAIN,
        _GIT_DIFF_STAT,
        _GIT_TAG_POINTS_AT_HEAD,
    }
)


class GitAuditAdapterError(ValueError):
    pass


class GitCommandResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command: tuple[str, ...]
    cwd: str
    exit_code: StrictInt
    stdout: str
    stderr: str


class GitCommandTransport(Protocol):
    def run(self, command: tuple[str, ...], *, cwd: str) -> GitCommandResult: ...


class SubprocessGitCommandTransport:
    def run(self, command: tuple[str, ...], *, cwd: str) -> GitCommandResult:
        try:
            completed_process = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as error:
            raise GitAuditAdapterError("failed to execute git command") from error
        return GitCommandResult(
            command=command,
            cwd=cwd,
            exit_code=completed_process.returncode,
            stdout=completed_process.stdout,
            stderr=completed_process.stderr,
        )


class GitAuditAdapter:
    def __init__(self, *, transport: GitCommandTransport | None = None) -> None:
        self._transport = transport or SubprocessGitCommandTransport()

    def collect(
        self,
        *,
        package_root: str,
        project_ref: str,
        cwd: str,
        source_inventory_hash: str | None = None,
        base_commit_sha: str | None = None,
        worktree_ref: str | None = None,
        generated_at: datetime | None = None,
    ) -> GitVersionAuditFactSet:
        if source_inventory_hash is None:
            raise GitAuditAdapterError("source_inventory_hash is required")
        if base_commit_sha is None:
            raise GitAuditAdapterError("base_commit_sha is required")
        if worktree_ref is None:
            raise GitAuditAdapterError("worktree_ref is required")

        final_commit_sha = self._rev_parse_head(cwd=cwd).stdout.strip()
        branch_name = self._rev_parse_branch(cwd=cwd).stdout.strip()
        status_output = self._status_porcelain(cwd=cwd).stdout
        diff_stat_output = self._diff_stat(cwd=cwd).stdout
        tag_output = self._tags_pointing_at_head(cwd=cwd).stdout

        changed_files = self._parse_status_z(status_output)
        dirty_status = GitDirtyStatus.DIRTY if changed_files else GitDirtyStatus.CLEAN
        git_clean = dirty_status is GitDirtyStatus.CLEAN
        summary_text = diff_stat_output.strip() if diff_stat_output.strip() else "clean working tree"
        diff_summary = self._build_diff_summary(
            changed_files=changed_files,
            summary_text=summary_text,
        )
        optional_tag_ref = self._first_tag_ref(tag_output)
        now = generated_at or datetime.now(UTC)
        fact_payload_hash = hash_namespaced_payload(
            {
                "project_ref": project_ref,
                "base_commit_sha": base_commit_sha,
                "final_commit_sha": final_commit_sha,
                "worktree_ref": worktree_ref,
                "source_inventory_hash": source_inventory_hash,
            }
        )

        return GitVersionAuditFactSet(
            fact_set_id=namespaced_ref(
                kind="git-version-audit-facts",
                project_ref=project_ref,
                content_hash=fact_payload_hash,
            ),
            project_ref=project_ref,
            package_root=package_root,
            branch_ref=f"branch.{branch_name}",
            worktree_ref=worktree_ref,
            base_commit_sha=base_commit_sha,
            final_commit_sha=final_commit_sha,
            optional_tag_ref=optional_tag_ref,
            dirty_status=dirty_status,
            git_clean=git_clean,
            changed_files=changed_files,
            diff_summary=diff_summary,
            source_inventory_hash=source_inventory_hash,
            generated_at=now,
        )

    def _run_template(self, command: tuple[str, ...], *, cwd: str) -> GitCommandResult:
        if command not in _GIT_COMMAND_TEMPLATES:
            raise GitAuditAdapterError("arbitrary git command execution is not supported")
        result = self._transport.run(command, cwd=cwd)
        if result.exit_code != 0:
            raise GitAuditAdapterError("git command failed")
        return result

    def _rev_parse_head(self, *, cwd: str) -> GitCommandResult:
        return self._run_template(_GIT_REV_PARSE_HEAD, cwd=cwd)

    def _rev_parse_branch(self, *, cwd: str) -> GitCommandResult:
        return self._run_template(_GIT_REV_PARSE_BRANCH, cwd=cwd)

    def _status_porcelain(self, *, cwd: str) -> GitCommandResult:
        return self._run_template(_GIT_STATUS_PORCELAIN, cwd=cwd)

    def _diff_stat(self, *, cwd: str) -> GitCommandResult:
        return self._run_template(_GIT_DIFF_STAT, cwd=cwd)

    def _tags_pointing_at_head(self, *, cwd: str) -> GitCommandResult:
        return self._run_template(_GIT_TAG_POINTS_AT_HEAD, cwd=cwd)

    def _parse_status_z(self, status_output: str) -> tuple[GitChangedFile, ...]:
        changed_files: list[GitChangedFile] = []
        entries = [entry for entry in status_output.split("\0") if entry]
        index = 0
        while index < len(entries):
            entry = entries[index]
            if len(entry) < 4 or entry[2] != " ":
                raise GitAuditAdapterError("invalid git status porcelain entry")
            status_code = entry[:2]
            path = entry[3:]
            status = self._changed_file_status(status_code)
            if status is GitChangedFileStatus.RENAMED:
                index += 1
                if index >= len(entries):
                    raise GitAuditAdapterError("renamed git status entry missing previous path")
                previous_path = entries[index]
                changed_files.append(
                    GitChangedFile(path=path, status=status, previous_path=previous_path)
                )
            else:
                changed_files.append(GitChangedFile(path=path, status=status))
            index += 1
        return tuple(changed_files)

    def _changed_file_status(self, status_code: str) -> GitChangedFileStatus:
        if status_code == "??":
            return GitChangedFileStatus.UNTRACKED
        if "R" in status_code:
            return GitChangedFileStatus.RENAMED
        if "D" in status_code:
            return GitChangedFileStatus.DELETED
        if "A" in status_code:
            return GitChangedFileStatus.ADDED
        return GitChangedFileStatus.MODIFIED

    def _build_diff_summary(
        self,
        *,
        changed_files: tuple[GitChangedFile, ...],
        summary_text: str,
    ) -> GitDiffSummary:
        return GitDiffSummary(
            diff_summary_id="git-diff-summary.clean" if not changed_files else "git-diff-summary.dirty",
            changed_file_count=len(changed_files),
            insertions=self._count_stat(summary_text, "insertion"),
            deletions=self._count_stat(summary_text, "deletion"),
            summary_text=summary_text,
        )

    def _count_stat(self, summary_text: str, label: str) -> int:
        match = re.search(rf"(\d+) {label}s?", summary_text)
        if match is None:
            return 0
        return int(match.group(1))

    def _first_tag_ref(self, tag_output: str) -> str | None:
        tags = tuple(line.strip() for line in tag_output.splitlines() if line.strip())
        if not tags:
            return None
        return f"tag.{tags[0]}"


__all__ = [
    "GitAuditAdapter",
    "GitAuditAdapterError",
    "GitCommandResult",
    "GitCommandTransport",
    "SubprocessGitCommandTransport",
]
