from __future__ import annotations

import logging
from collections.abc import Callable
from threading import Event, Lock, Thread

from app.config import Settings
from app.db.repository import ControlPlaneRepository
from app.scheduler_runner import run_scheduler_once

logger = logging.getLogger(__name__)


class InProcessSchedulerLoop:
    def __init__(
        self,
        *,
        run_once: Callable[[], object],
        poll_interval_sec: float,
        thread_name: str = "boardroom-inprocess-scheduler",
    ) -> None:
        self._run_once = run_once
        self._poll_interval_sec = poll_interval_sec
        self._thread_name = thread_name
        self._lock = Lock()
        self._stop_event = Event()
        self._thread: Thread | None = None

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event = Event()
            self._thread = Thread(
                target=self._run_loop,
                name=self._thread_name,
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout_sec: float = 5.0) -> None:
        with self._lock:
            thread = self._thread
            if thread is None:
                return
            self._stop_event.set()

        thread.join(timeout=timeout_sec)
        if thread.is_alive():
            raise RuntimeError(f"{self._thread_name} did not stop within {timeout_sec} seconds.")

        with self._lock:
            if self._thread is thread:
                self._thread = None

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._run_once()
            except Exception:
                logger.exception("In-process scheduler loop iteration failed.")
            if self._stop_event.wait(self._poll_interval_sec):
                break


def build_inprocess_scheduler(
    repository: ControlPlaneRepository,
    settings: Settings,
) -> InProcessSchedulerLoop:
    return InProcessSchedulerLoop(
        run_once=lambda: run_scheduler_once(
            repository,
            max_dispatches=settings.scheduler_max_dispatches,
        ),
        poll_interval_sec=settings.scheduler_poll_interval_sec,
    )
