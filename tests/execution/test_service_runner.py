from __future__ import annotations

import hashlib
import socket
import sys
from pathlib import Path

from boardroom_os.adapters.process_runner import ServiceRunner, ServiceRunnerInput
from boardroom_os.contracts.types import ContractId
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
