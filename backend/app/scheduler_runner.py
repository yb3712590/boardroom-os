from __future__ import annotations

import argparse
import time
from collections.abc import Callable
from datetime import datetime

from app.config import Settings, get_settings
from app.contracts.commands import ArtifactCleanupCommand
from app.core.artifact_store import ArtifactStore
from app.core.artifact_handlers import handle_artifact_cleanup
from app.core.constants import EVENT_SCHEDULER_ORCHESTRATION_RECORDED
from app.core.ceo_scheduler import run_due_ceo_maintenance
from app.core.runtime import run_leased_ticket_runtime
from app.core.ticket_handlers import run_scheduler_tick
from app.core.time import now_local
from app.core.workflow_auto_advance import (
    auto_advance_workflow_to_next_stop,
    workflow_uses_ceo_board_delegate,
)
from app.db.repository import ControlPlaneRepository

_SCHEDULER_ORCHESTRATION_WORKFLOW_ID = "wf_scheduler_orchestration"


def _build_runner_idempotency_key(tick_index: int) -> str:
    return f"scheduler-runner:{now_local().isoformat()}:{tick_index}"


def _enum_value(value):
    return value.value if hasattr(value, "value") else value


def _serialize_runtime_outcomes(runtime_outcomes) -> dict:
    ticket_ids: list[str] = []
    outcomes: list[dict] = []
    for outcome in runtime_outcomes or []:
        if isinstance(outcome, dict):
            ticket_id = str(outcome.get("ticket_id") or "")
            lease_owner = outcome.get("lease_owner")
            final_ack = outcome.get("final_ack")
            final_ack_status = outcome.get("final_ack_status")
        else:
            ticket_id = str(getattr(outcome, "ticket_id", "") or "")
            lease_owner = getattr(outcome, "lease_owner", None)
            final_ack = getattr(outcome, "final_ack", None)
            final_ack_status = getattr(final_ack, "status", None)
        if ticket_id:
            ticket_ids.append(ticket_id)
        outcomes.append(
            {
                "ticket_id": ticket_id,
                "lease_owner": lease_owner,
                "final_ack_status": _enum_value(final_ack_status),
            }
        )
    return {
        "ticket_ids": ticket_ids,
        "outcomes": outcomes,
        "count": len(outcomes),
    }


def _record_orchestration_trace(
    repository: ControlPlaneRepository,
    *,
    runner_idempotency_key: str,
    tick_index: int,
    ceo_runs: list[dict],
    scheduler_ack,
    runtime_outcomes,
) -> None:
    payload = {
        "runner_idempotency_key": runner_idempotency_key,
        "tick_index": tick_index,
        "stage_order": [
            "collect_due_ceo_maintenance",
            "scheduler_tick",
            "runtime_execution",
            "record_orchestration_trace",
        ],
        "ceo_maintenance": {
            "workflow_ids": [str(run.get("workflow_id") or "") for run in ceo_runs],
            "run_ids": [str(run.get("run_id") or "") for run in ceo_runs],
            "count": len(ceo_runs),
        },
        "scheduler_tick": {
            "status": _enum_value(getattr(scheduler_ack, "status", None)),
            "idempotency_key": getattr(scheduler_ack, "idempotency_key", None),
            "causation_hint": getattr(scheduler_ack, "causation_hint", None),
        },
        "runtime_execution": _serialize_runtime_outcomes(runtime_outcomes),
    }
    with repository.transaction() as connection:
        repository.insert_event(
            connection,
            event_type=EVENT_SCHEDULER_ORCHESTRATION_RECORDED,
            actor_type="system",
            actor_id="scheduler_runner",
            workflow_id=_SCHEDULER_ORCHESTRATION_WORKFLOW_ID,
            idempotency_key=f"{runner_idempotency_key}:orchestration-trace",
            causation_id=getattr(scheduler_ack, "command_id", None),
            correlation_id=runner_idempotency_key,
            payload=payload,
            occurred_at=now_local(),
        )


def _should_run_artifact_cleanup(
    *,
    latest_cleanup_event: dict | None,
    current_time: datetime,
    cleanup_interval_sec: int,
) -> bool:
    if cleanup_interval_sec <= 0:
        return False
    if latest_cleanup_event is None:
        return True
    elapsed_sec = (current_time - latest_cleanup_event["occurred_at"]).total_seconds()
    return elapsed_sec >= cleanup_interval_sec


def _build_artifact_cleanup_idempotency_key(
    *,
    current_time: datetime,
    cleanup_interval_sec: int,
) -> str:
    bucket = int(current_time.timestamp()) // cleanup_interval_sec
    return f"artifact-cleanup:auto:{cleanup_interval_sec}:{bucket}"


def maybe_run_artifact_cleanup(
    repository: ControlPlaneRepository,
    *,
    current_time: datetime | None = None,
) -> None:
    settings = get_settings()
    resolved_current_time = current_time or now_local()
    artifact_cleanup_summary = repository.get_artifact_cleanup_summary(at=resolved_current_time)
    if (
        int(artifact_cleanup_summary["pending_expired_count"]) <= 0
        and int(artifact_cleanup_summary["pending_storage_cleanup_count"]) <= 0
    ):
        return
    if not _should_run_artifact_cleanup(
        latest_cleanup_event=artifact_cleanup_summary["latest_cleanup_event"],
        current_time=resolved_current_time,
        cleanup_interval_sec=settings.artifact_cleanup_interval_sec,
    ):
        return

    handle_artifact_cleanup(
        repository,
        ArtifactCleanupCommand(
            cleaned_by=settings.artifact_cleanup_operator_id,
            idempotency_key=_build_artifact_cleanup_idempotency_key(
                current_time=resolved_current_time,
                cleanup_interval_sec=settings.artifact_cleanup_interval_sec,
            ),
        ),
        trigger="auto_scheduler",
    )


def build_repository(settings: Settings | None = None) -> ControlPlaneRepository:
    resolved_settings = settings or get_settings()
    return ControlPlaneRepository(
        db_path=resolved_settings.db_path,
        busy_timeout_ms=resolved_settings.busy_timeout_ms,
        recent_event_limit=resolved_settings.recent_event_limit,
        artifact_store=ArtifactStore(resolved_settings.artifact_store_root),
    )


def _recover_ceo_delegate_blockers(
    repository: ControlPlaneRepository,
    *,
    runner_idempotency_key: str,
    max_dispatches: int,
) -> None:
    workflow_ids: set[str] = set()
    workflow_ids.update(str(item["workflow_id"]) for item in repository.list_open_incidents())
    workflow_ids.update(str(item["workflow_id"]) for item in repository.list_open_approvals())

    for workflow_id in sorted(workflow_ids):
        workflow = repository.get_workflow_projection(workflow_id)
        if not workflow_uses_ceo_board_delegate(workflow):
            continue
        auto_advance_workflow_to_next_stop(
            repository,
            workflow_id=workflow_id,
            idempotency_key_prefix=f"{runner_idempotency_key}:ceo-delegate-recovery:{workflow_id}",
            max_steps=1,
            max_dispatches=max_dispatches,
        )


def run_scheduler_once(
    repository: ControlPlaneRepository,
    *,
    idempotency_key: str | None = None,
    max_dispatches: int | None = None,
    tick_index: int = 0,
):
    settings = get_settings()
    runner_idempotency_key = idempotency_key or _build_runner_idempotency_key(tick_index)
    effective_max_dispatches = max_dispatches or settings.scheduler_max_dispatches
    _recover_ceo_delegate_blockers(
        repository,
        runner_idempotency_key=runner_idempotency_key,
        max_dispatches=effective_max_dispatches,
    )
    ceo_runs = run_due_ceo_maintenance(
        repository,
        current_time=now_local(),
        trigger_ref=runner_idempotency_key,
        interval_sec=settings.ceo_maintenance_interval_sec,
    )
    scheduler_ack = run_scheduler_tick(
        repository,
        idempotency_key=runner_idempotency_key,
        max_dispatches=effective_max_dispatches,
    )
    runtime_outcomes = []
    if settings.runtime_execution_mode == "INPROCESS":
        runtime_outcomes = run_leased_ticket_runtime(repository)
    _record_orchestration_trace(
        repository,
        runner_idempotency_key=runner_idempotency_key,
        tick_index=tick_index,
        ceo_runs=ceo_runs,
        scheduler_ack=scheduler_ack,
        runtime_outcomes=runtime_outcomes,
    )
    maybe_run_artifact_cleanup(repository, current_time=now_local())
    return scheduler_ack


def run_scheduler_loop(
    repository: ControlPlaneRepository,
    *,
    poll_interval_sec: float,
    max_dispatches: int,
    max_ticks: int | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> list:
    repository.initialize()
    acknowledgements = []
    tick_index = 0

    while max_ticks is None or tick_index < max_ticks:
        acknowledgements.append(
            run_scheduler_once(
                repository,
                max_dispatches=max_dispatches,
                tick_index=tick_index,
            )
        )
        tick_index += 1
        if max_ticks is not None and tick_index >= max_ticks:
            break
        sleep_fn(poll_interval_sec)

    return acknowledgements


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Boardroom OS scheduler runner.")
    parser.add_argument("--once", action="store_true", help="Run a single scheduler tick and exit.")
    parser.add_argument(
        "--max-ticks",
        type=int,
        default=None,
        help="Stop after N ticks. Defaults to infinite loop unless --once is set.",
    )
    parser.add_argument(
        "--poll-interval-sec",
        type=float,
        default=None,
        help="Override scheduler poll interval in seconds.",
    )
    parser.add_argument(
        "--max-dispatches",
        type=int,
        default=None,
        help="Override the number of dispatches per scheduler tick.",
    )
    args = parser.parse_args()

    settings = get_settings()
    repository = build_repository(settings)
    repository.initialize()

    poll_interval_sec = (
        args.poll_interval_sec
        if args.poll_interval_sec is not None
        else settings.scheduler_poll_interval_sec
    )
    max_dispatches = (
        args.max_dispatches
        if args.max_dispatches is not None
        else settings.scheduler_max_dispatches
    )

    if args.once:
        ack = run_scheduler_once(repository, max_dispatches=max_dispatches)
        print(
            f"{ack.received_at.isoformat()} {ack.status.value} {ack.idempotency_key} {ack.causation_hint}"
        )
        return 0

    max_ticks = args.max_ticks
    acks = run_scheduler_loop(
        repository,
        poll_interval_sec=poll_interval_sec,
        max_dispatches=max_dispatches,
        max_ticks=max_ticks,
    )
    for ack in acks:
        print(f"{ack.received_at.isoformat()} {ack.status.value} {ack.idempotency_key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
