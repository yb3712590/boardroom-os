from __future__ import annotations

import hashlib
import http.client
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from boardroom_os.adapters.process_runner import (
    CommandRunnerError,
    HttpReadinessProbe,
    ServiceRunner,
    ServiceRunnerError,
    ServiceRunnerInput,
)
from boardroom_os.contracts.types import ContractId
from boardroom_os.evidence.service_run import ServiceReadinessUrl
from boardroom_os.execution.verification_run import EnvironmentProfileRef, RunnerRef, WorkspaceSnapshotRef
from tests.execution.test_command_runner import _execution_package, _package_contract, _python_command


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _write_health_server(package_root: Path) -> Path:
    script = package_root / "service_app.py"
    script.write_text(
        "\n".join(
            [
                "from http.server import BaseHTTPRequestHandler, HTTPServer",
                "import sys",
                "",
                "class Handler(BaseHTTPRequestHandler):",
                "    def do_GET(self):",
                "        if self.path != '/health':",
                "            self.send_response(404)",
                "            self.end_headers()",
                "            return",
                "        body = b'ready'",
                "        self.send_response(200)",
                "        self.send_header('Content-Length', str(len(body)))",
                "        self.end_headers()",
                "        self.wfile.write(body)",
                "    def log_message(self, format, *args):",
                "        return",
                "",
                "HTTPServer(('127.0.0.1', int(sys.argv[1])), Handler).serve_forever()",
            ]
        ),
        encoding="utf-8",
    )
    return script


def test_service_runner_records_http_readiness_evidence(tmp_path: Path) -> None:
    port = _free_port()
    _write_health_server(tmp_path)
    command = _python_command(
        command_id="run-app",
        label="Run app",
        cwd=".",
    ).model_copy(update={"command": (sys.executable, "service_app.py", str(port))})

    result = ServiceRunner().run(
        ServiceRunnerInput(
            execution_package=_execution_package(command),
            package_contract=_package_contract(command),
            command_id=ContractId(value="run-app"),
            package_root=tmp_path,
            readiness_url=f"http://127.0.0.1:{port}/health",
            runner_ref=RunnerRef(value="runner.local-service"),
            environment_profile_ref=EnvironmentProfileRef(value="environment.local"),
            workspace_snapshot_ref=WorkspaceSnapshotRef(value="workspace-snapshot.service"),
            timeout_seconds=5,
            poll_interval_seconds=0.05,
        )
    )

    evidence = result.service_run_evidence
    assert evidence.command_id == ContractId(value="run-app")
    assert evidence.readiness_url.value == f"http://127.0.0.1:{port}/health"
    assert evidence.probe_status_code == 200
    assert evidence.probe_body_sha256.value == hashlib.sha256(b"ready").hexdigest()
    assert evidence.process_id > 0
    assert evidence.ready_at >= evidence.started_at
    assert evidence.stopped_at is not None
    assert evidence.stdout_ref.value.endswith(".stdout")
    assert evidence.stderr_ref.value.endswith(".stderr")


def test_service_runner_runs_after_ready_probe_before_stopping_service(tmp_path: Path) -> None:
    port = _free_port()
    _write_health_server(tmp_path)
    command = _python_command(
        command_id="run-app",
        label="Run app",
        cwd=".",
    ).model_copy(update={"command": (sys.executable, "service_app.py", str(port))})

    def after_ready(evidence) -> int:
        assert evidence.stopped_at is None
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return evidence.process_id

    result = ServiceRunner().run(
        ServiceRunnerInput(
            execution_package=_execution_package(command),
            package_contract=_package_contract(command),
            command_id=ContractId(value="run-app"),
            package_root=tmp_path,
            readiness_url=f"http://127.0.0.1:{port}/health",
            runner_ref=RunnerRef(value="runner.local-service"),
            environment_profile_ref=EnvironmentProfileRef(value="environment.local"),
            workspace_snapshot_ref=WorkspaceSnapshotRef(value="workspace-snapshot.service"),
            timeout_seconds=5,
            poll_interval_seconds=0.05,
        ),
        after_ready_probe=after_ready,
    )

    assert result.after_ready_result == result.service_run_evidence.process_id
    assert result.service_run_evidence.stopped_at is not None


def test_service_runner_rejects_readiness_from_unrelated_running_service(tmp_path: Path) -> None:
    external_port = _free_port()
    _write_health_server(tmp_path)
    external = subprocess.Popen(
        (sys.executable, "service_app.py", str(external_port)),
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        with socket.create_connection(("127.0.0.1", external_port), timeout=5):
            pass
        dead_command = _python_command(
            command_id="run-app",
            label="Run app",
            cwd=".",
        ).model_copy(
            update={
                "command": (
                    sys.executable,
                    "-c",
                    "print('started then exited')",
                )
            }
        )

        with pytest.raises(ServiceRunnerError, match="already ready before service start"):
            ServiceRunner().run(
                ServiceRunnerInput(
                    execution_package=_execution_package(dead_command),
                    package_contract=_package_contract(dead_command),
                    command_id=ContractId(value="run-app"),
                    package_root=tmp_path,
                    readiness_url=f"http://127.0.0.1:{external_port}/health",
                    runner_ref=RunnerRef(value="runner.local-service"),
                    environment_profile_ref=EnvironmentProfileRef(value="environment.local"),
                    workspace_snapshot_ref=WorkspaceSnapshotRef(value="workspace-snapshot.service"),
                    timeout_seconds=5,
                    poll_interval_seconds=0.05,
                )
            )
    finally:
        if external.poll() is None:
            external.terminate()
        external.communicate(timeout=2)


def test_service_runner_rejects_preexisting_readiness_url_before_start(tmp_path: Path) -> None:
    external_port = _free_port()
    _write_health_server(tmp_path)
    external = subprocess.Popen(
        (sys.executable, "service_app.py", str(external_port)),
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        with socket.create_connection(("127.0.0.1", external_port), timeout=5):
            pass
        sleeping_command = _python_command(
            command_id="run-app",
            label="Run app",
            cwd=".",
        ).model_copy(
            update={
                "command": (
                    sys.executable,
                    "-c",
                    "import time; time.sleep(10)",
                )
            }
        )

        with pytest.raises(ServiceRunnerError, match="already ready before service start"):
            ServiceRunner().run(
                ServiceRunnerInput(
                    execution_package=_execution_package(sleeping_command),
                    package_contract=_package_contract(sleeping_command),
                    command_id=ContractId(value="run-app"),
                    package_root=tmp_path,
                    readiness_url=f"http://127.0.0.1:{external_port}/health",
                    runner_ref=RunnerRef(value="runner.local-service"),
                    environment_profile_ref=EnvironmentProfileRef(value="environment.local"),
                    workspace_snapshot_ref=WorkspaceSnapshotRef(value="workspace-snapshot.service"),
                    timeout_seconds=5,
                    poll_interval_seconds=0.05,
                )
            )
    finally:
        if external.poll() is None:
            external.terminate()
        external.communicate(timeout=2)


def test_http_readiness_probe_wraps_connection_disconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    def disconnecting_urlopen(*args: object, **kwargs: object) -> object:
        raise http.client.RemoteDisconnected("closed")

    monkeypatch.setattr(
        "boardroom_os.adapters.process_runner.urlopen",
        disconnecting_urlopen,
    )

    with pytest.raises(CommandRunnerError, match="readiness probe failed"):
        HttpReadinessProbe().probe(
            ServiceReadinessUrl(value="http://127.0.0.1:8000/health")
        )
