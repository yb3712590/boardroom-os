from __future__ import annotations

import argparse
import time
from collections.abc import Callable
from datetime import datetime

from app.config import Settings, get_settings
from app.contracts.commands import ArtifactCleanupCommand
from app.core.artifact_store import ArtifactStore
from app.core.artifact_handlers import handle_artifact_cleanup
from app.core.runtime import run_leased_ticket_runtime
from app.core.ticket_handlers import run_scheduler_tick
from app.core.time import now_local
from app.db.repository import ControlPlaneRepository


def _build_runner_idempotency_key(tick_index: int) -> str:
    return f"scheduler-runner:{now_local().isoformat()}:{tick_index}"


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


def run_scheduler_once(
    repository: ControlPlaneRepository,
    *,
    idempotency_key: str | None = None,
    max_dispatches: int | None = None,
    tick_index: int = 0,
):
    settings = get_settings()
    scheduler_ack = run_scheduler_tick(
        repository,
        idempotency_key=idempotency_key or _build_runner_idempotency_key(tick_index),
        max_dispatches=max_dispatches or settings.scheduler_max_dispatches,
    )
    if settings.runtime_execution_mode == "INPROCESS":
        run_leased_ticket_runtime(repository)
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
