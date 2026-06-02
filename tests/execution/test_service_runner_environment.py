from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from boardroom_os.adapters.process_runner import ServiceRunner, ServiceRunnerInput
from boardroom_os.contracts.types import ContractId
from boardroom_os.execution.verification_run import (
    EnvironmentProfileRef,
    RunnerRef,
    WorkspaceSnapshotRef,
)
from tests.execution.test_command_runner import _execution_package, _package_contract, _python_command
from tests.execution.test_service_runner import _free_port


def _write_env_health_server(package_root: Path) -> None:
    (package_root / "env_service_app.py").write_text(
        "\n".join(
            [
                "from http.server import BaseHTTPRequestHandler, HTTPServer",
                "import os",
                "",
                "class Handler(BaseHTTPRequestHandler):",
                "    def do_GET(self):",
                "        expected = os.environ.get('BOARDROOM_TEST_READY_TOKEN')",
                "        if self.path != f'/health/{expected}':",
                "            self.send_response(404)",
                "            self.end_headers()",
                "            return",
                "        body = os.environ['BOARDROOM_TEST_BODY'].encode('utf-8')",
                "        self.send_response(200)",
                "        self.send_header('Content-Length', str(len(body)))",
                "        self.end_headers()",
                "        self.wfile.write(body)",
                "    def log_message(self, format, *args):",
                "        return",
                "",
                "HTTPServer(('127.0.0.1', int(os.environ['PORT'])), Handler).serve_forever()",
            ]
        ),
        encoding="utf-8",
    )


def _service_input(
    tmp_path: Path,
    *,
    environment_overrides: dict[str, str],
    readiness_port: int | None = None,
) -> ServiceRunnerInput:
    port = readiness_port if readiness_port is not None else int(environment_overrides["PORT"])
    command = _python_command(
        command_id="run-app",
        label="Run app",
        cwd=".",
    ).model_copy(update={"command": (sys.executable, "env_service_app.py")})
    return ServiceRunnerInput(
        execution_package=_execution_package(command),
        package_contract=_package_contract(command),
        command_id=ContractId(value="run-app"),
        package_root=tmp_path,
        readiness_url=f"http://127.0.0.1:{port}/health/{environment_overrides['BOARDROOM_TEST_READY_TOKEN']}",
        runner_ref=RunnerRef(value="runner.local-service"),
        environment_profile_ref=EnvironmentProfileRef(value="environment.local"),
        workspace_snapshot_ref=WorkspaceSnapshotRef(value="workspace-snapshot.service"),
        environment_overrides=environment_overrides,
        timeout_seconds=5,
        poll_interval_seconds=0.05,
    )


def test_service_runner_passes_explicit_environment_overrides(tmp_path: Path) -> None:
    _write_env_health_server(tmp_path)
    port = _free_port()

    result = ServiceRunner().run(
        _service_input(
            tmp_path,
            environment_overrides={
                "PORT": str(port),
                "BOARDROOM_TEST_READY_TOKEN": "ready-token",
                "BOARDROOM_TEST_BODY": "ready-from-env",
            },
        )
    )

    assert result.service_run_evidence.probe_status_code == 200
    assert result.service_run_evidence.environment_overrides == {
        "PORT": str(port),
        "BOARDROOM_TEST_READY_TOKEN": "ready-token",
        "BOARDROOM_TEST_BODY": "ready-from-env",
    }
    assert "ready-from-env" not in os.environ.values()


@pytest.mark.parametrize(
    "environment_overrides",
    [
        {"": "8000"},
        {"PORT": ""},
        {"PORT": 8000},
    ],
)
def test_service_runner_rejects_invalid_environment_overrides(
    tmp_path: Path,
    environment_overrides: dict[str, object],
) -> None:
    _write_env_health_server(tmp_path)
    port = _free_port()
    values = {
        "PORT": str(port),
        "BOARDROOM_TEST_READY_TOKEN": "ready-token",
        "BOARDROOM_TEST_BODY": "ready",
    }
    values.update(environment_overrides)

    with pytest.raises(ValidationError, match="environment_overrides"):
        _service_input(
            tmp_path,
            environment_overrides=values,  # type: ignore[arg-type]
            readiness_port=port,
        )
