from __future__ import annotations

import re
import subprocess
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, StrictInt

from boardroom_os.audit.git_version_audit import (
    GitChangedFile,
    GitChangedFileStatus,
    GitDiffSummary,
    GitDirtyStatus,
    GitVersionAuditFactSet,
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

    def run_git(self, command: tuple[str, ...], *, cwd: str) -> GitCommandResult:
        normalized_command = self._normalize_command(command)
        self._require_read_only_command(normalized_command)
        result = self._transport.run(normalized_command, cwd=cwd)
        if result.exit_code != 0:
            raise GitAuditAdapterError("git command failed")
        return result

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
        final_commit_sha = self.run_git(("git", "rev-parse", "HEAD"), cwd=cwd).stdout.strip()
        branch_name = self.run_git(("git", "rev-parse", "--abbrev-ref", "HEAD"), cwd=cwd).stdout.strip()
        status_output = self.run_git(("git", "status", "--porcelain"), cwd=cwd).stdout
        diff_stat_output = self.run_git(("git", "diff", "--stat"), cwd=cwd).stdout
        tag_output = self.run_git(("git", "tag", "--points-at", "HEAD"), cwd=cwd).stdout

        if source_inventory_hash is None:
            raise GitAuditAdapterError("source_inventory_hash is required")

        changed_files = self._parse_status(status_output)
        dirty_status = GitDirtyStatus.DIRTY if changed_files else GitDirtyStatus.CLEAN
        git_clean = dirty_status is GitDirtyStatus.CLEAN
        summary_text = diff_stat_output.strip() if diff_stat_output.strip() else "clean working tree"
        diff_summary = self._build_diff_summary(
            changed_files=changed_files,
            summary_text=summary_text,
        )
        optional_tag_ref = self._first_tag_ref(tag_output)
        now = generated_at or datetime.now(UTC)

        return GitVersionAuditFactSet(
            fact_set_id=f"git-version-audit-facts.{project_ref}",
            project_ref=project_ref,
            package_root=package_root,
            branch_ref=f"branch.{branch_name}",
            worktree_ref=worktree_ref or f"worktree.{package_root}",
            base_commit_sha=base_commit_sha or final_commit_sha,
            final_commit_sha=final_commit_sha,
            optional_tag_ref=optional_tag_ref,
            dirty_status=dirty_status,
            git_clean=git_clean,
            changed_files=changed_files,
            diff_summary=diff_summary,
            source_inventory_hash=source_inventory_hash,
            generated_at=now,
        )

    def _normalize_command(self, command: tuple[str, ...]) -> tuple[str, ...]:
        if not isinstance(command, tuple | list):
            raise GitAuditAdapterError("git command must be a tuple or list")
        normalized = tuple(part.strip() for part in command)
        if not normalized or any(not part for part in normalized):
            raise GitAuditAdapterError("git command must not contain empty items")
        if normalized[0] != "git":
            raise GitAuditAdapterError("git command must start with git")
        return normalized

    def _require_read_only_command(self, command: tuple[str, ...]) -> None:
        if len(command) < 2:
            raise GitAuditAdapterError("git command must include subcommand")
        subcommand = command[1]
        allowed = {
            "branch",
            "diff",
            "log",
            "rev-list",
            "rev-parse",
            "show",
            "status",
            "tag",
        }
        if subcommand not in allowed:
            raise GitAuditAdapterError("git command must be read-only")
        if subcommand == "tag" and command[2:4] != ("--points-at", "HEAD"):
            raise GitAuditAdapterError("git command must be read-only")
        if subcommand == "branch" and any(part in {"-D", "-d", "-m", "-M", "--delete", "--move"} for part in command[2:]):
            raise GitAuditAdapterError("git command must be read-only")
        if subcommand == "diff" and any(part in {"--output", "--quiet", "--exit-code"} for part in command[2:]):
            raise GitAuditAdapterError("git command must be read-only")

    def _parse_status(self, status_output: str) -> tuple[GitChangedFile, ...]:
        changed_files: list[GitChangedFile] = []
        for raw_line in status_output.splitlines():
            line = raw_line.rstrip()
            if not line:
                continue
            status_code = line[:2]
            path_part = line[3:].strip() if len(line) > 3 else ""
            status = self._changed_file_status(status_code)
            if status is GitChangedFileStatus.RENAMED and " -> " in path_part:
                previous_path, path = path_part.split(" -> ", 1)
                changed_files.append(
                    GitChangedFile(path=path, status=status, previous_path=previous_path)
                )
            else:
                changed_files.append(GitChangedFile(path=path_part, status=status))
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
