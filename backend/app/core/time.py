from __future__ import annotations

from datetime import datetime

from app.core.constants import BOARDROOM_TIMEZONE


def now_local() -> datetime:
    return datetime.now(BOARDROOM_TIMEZONE)
