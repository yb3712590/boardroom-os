from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    db_path: Path
    busy_timeout_ms: int = 5000
    recent_event_limit: int = 10


def get_settings() -> Settings:
    repo_root = Path(__file__).resolve().parents[2]
    db_path = Path(
        os.environ.get(
            "BOARDROOM_OS_DB_PATH",
            repo_root / "backend" / "data" / "boardroom_os.db",
        )
    )
    return Settings(db_path=db_path)
