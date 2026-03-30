from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    db_path: Path
    developer_inspector_root: Path
    artifact_store_root: Path
    busy_timeout_ms: int = 5000
    recent_event_limit: int = 10
    scheduler_poll_interval_sec: float = 5.0
    scheduler_max_dispatches: int = 10
    enable_inprocess_scheduler: bool = False


def _read_bool_env(name: str, default: bool = False) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def get_settings() -> Settings:
    repo_root = Path(__file__).resolve().parents[2]
    db_path = Path(
        os.environ.get(
            "BOARDROOM_OS_DB_PATH",
            repo_root / "backend" / "data" / "boardroom_os.db",
        )
    )
    developer_inspector_root = Path(
        os.environ.get(
            "BOARDROOM_OS_DEVELOPER_INSPECTOR_ROOT",
            repo_root / "backend" / "data" / "developer_inspector",
        )
    )
    artifact_store_root = Path(
        os.environ.get(
            "BOARDROOM_OS_ARTIFACT_STORE_ROOT",
            repo_root / "backend" / "data" / "artifacts",
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
    enable_inprocess_scheduler = _read_bool_env(
        "BOARDROOM_OS_ENABLE_INPROCESS_SCHEDULER",
        default=False,
    )
    return Settings(
        db_path=db_path,
        developer_inspector_root=developer_inspector_root,
        artifact_store_root=artifact_store_root,
        busy_timeout_ms=busy_timeout_ms,
        recent_event_limit=recent_event_limit,
        scheduler_poll_interval_sec=scheduler_poll_interval_sec,
        scheduler_max_dispatches=scheduler_max_dispatches,
        enable_inprocess_scheduler=enable_inprocess_scheduler,
    )
