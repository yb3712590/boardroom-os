from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    db_path: Path
    busy_timeout_ms: int = 5000
    recent_event_limit: int = 10
    scheduler_poll_interval_sec: float = 5.0
    scheduler_max_dispatches: int = 10


def get_settings() -> Settings:
    repo_root = Path(__file__).resolve().parents[2]
    db_path = Path(
        os.environ.get(
            "BOARDROOM_OS_DB_PATH",
            repo_root / "backend" / "data" / "boardroom_os.db",
        )
    )
    busy_timeout_ms = int(os.environ.get("BOARDROOM_OS_BUSY_TIMEOUT_MS", "5000"))
    recent_event_limit = int(os.environ.get("BOARDROOM_OS_RECENT_EVENT_LIMIT", "10"))
    scheduler_poll_interval_sec = float(
        os.environ.get("BOARDROOM_OS_SCHEDULER_POLL_INTERVAL_SEC", "5.0")
    )
    scheduler_max_dispatches = int(
        os.environ.get("BOARDROOM_OS_SCHEDULER_MAX_DISPATCHES", "10")
    )
    return Settings(
        db_path=db_path,
        busy_timeout_ms=busy_timeout_ms,
        recent_event_limit=recent_event_limit,
        scheduler_poll_interval_sec=scheduler_poll_interval_sec,
        scheduler_max_dispatches=scheduler_max_dispatches,
    )
