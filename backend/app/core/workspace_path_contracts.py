from __future__ import annotations

from dataclasses import dataclass


WORKSPACE_MANAGED_PATH_PREFIXES: tuple[str, ...] = (
    "10-project/",
    "20-evidence/",
    "00-boardroom/",
)


@dataclass(frozen=True)
class WorkspacePathTemplates:
    source: str = "10-project/src/*"
    docs: str = "10-project/docs/*"
    tests: str = "20-evidence/tests/*"
    git: str = "20-evidence/git/*"
    governance: str = "reports/governance/{ticket_id}/*"
    check: str = "reports/check/{ticket_id}/*"
    closeout: str = "20-evidence/closeout/{ticket_id}/*"

    def source_delivery_write_set(self) -> list[str]:
        return [self.source, self.docs, self.tests, self.git]

    def governance_write_set(self, ticket_id: str) -> list[str]:
        return [self.governance.format(ticket_id=ticket_id)]

    def check_write_set(self, ticket_id: str) -> list[str]:
        return [self.check.format(ticket_id=ticket_id)]

    def closeout_write_set(self, ticket_id: str) -> list[str]:
        return [self.closeout.format(ticket_id=ticket_id)]

    def model_dump(self) -> dict[str, str]:
        return {
            "source": self.source,
            "docs": self.docs,
            "tests": self.tests,
            "git": self.git,
            "governance": self.governance,
            "check": self.check,
            "closeout": self.closeout,
        }


DEFAULT_WORKSPACE_PATH_TEMPLATES = WorkspacePathTemplates()


def is_workspace_managed_write_set(allowed_write_set: list[str] | tuple[str, ...]) -> bool:
    return any(
        str(pattern or "").startswith(WORKSPACE_MANAGED_PATH_PREFIXES)
        for pattern in allowed_write_set
    )


def rebind_ticket_id_in_allowed_write_set(
    allowed_write_set: list[str] | tuple[str, ...],
    *,
    previous_ticket_id: str | None,
    next_ticket_id: str | None,
) -> list[str]:
    previous = str(previous_ticket_id or "").strip()
    next_id = str(next_ticket_id or "").strip()
    rebound: list[str] = []
    for pattern in allowed_write_set:
        normalized = str(pattern or "").strip()
        if not normalized:
            continue
        if previous and next_id:
            normalized = normalized.replace(previous, next_id)
        if normalized not in rebound:
            rebound.append(normalized)
    return rebound


def workspace_source_delivery_hard_rules() -> list[str]:
    paths = DEFAULT_WORKSPACE_PATH_TEMPLATES
    return [
        (
            "For workspace-managed source_code_delivery, source_file_refs may only point to "
            f"source artifacts written under {paths.source}; do not put docs, test evidence, "
            "git evidence, or closeout evidence in source_file_refs."
        ),
        (
            "Write documentation updates under "
            f"{paths.docs} and report required documentation surfaces through documentation_updates."
        ),
        (
            "Write verification evidence under "
            f"{paths.tests}, keep each run versioned by attempt, and mirror it through "
            "verification_runs plus verification_evidence_refs."
        ),
        (
            "Write git closeout evidence under "
            f"{paths.git}, keep it versioned by attempt, and include git_commit_record when "
            "source delivery completes."
        ),
    ]
