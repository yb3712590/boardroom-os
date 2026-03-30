from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def db_path(monkeypatch):
    base_dir = Path(__file__).resolve().parents[2] / ".tmp" / "test-db"
    base_dir.mkdir(parents=True, exist_ok=True)
    run_id = uuid4().hex
    path = base_dir / f"boardroom_os_test_{run_id}.db"
    developer_inspector_root = base_dir / f"developer_inspector_{run_id}"
    artifact_store_root = base_dir / f"artifacts_{run_id}"
    monkeypatch.setenv("BOARDROOM_OS_DB_PATH", str(path))
    monkeypatch.setenv("BOARDROOM_OS_DEVELOPER_INSPECTOR_ROOT", str(developer_inspector_root))
    monkeypatch.setenv("BOARDROOM_OS_ARTIFACT_STORE_ROOT", str(artifact_store_root))
    return path


@pytest.fixture
def client(db_path):
    from app.main import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def set_ticket_time(monkeypatch):
    import app.core.ticket_handlers as ticket_handlers
    import app.core.runtime as runtime
    import app.core.projections as projections
    import app.scheduler_runner as scheduler_runner

    state = {"value": datetime.fromisoformat("2026-03-28T10:00:00+08:00")}

    def _set(value: str | datetime) -> datetime:
        if isinstance(value, str):
            state["value"] = datetime.fromisoformat(value)
        else:
            state["value"] = value
        return state["value"]

    monkeypatch.setattr(ticket_handlers, "now_local", lambda: state["value"])
    monkeypatch.setattr(runtime, "now_local", lambda: state["value"])
    monkeypatch.setattr(projections, "now_local", lambda: state["value"])
    monkeypatch.setattr(scheduler_runner, "now_local", lambda: state["value"])
    return _set
