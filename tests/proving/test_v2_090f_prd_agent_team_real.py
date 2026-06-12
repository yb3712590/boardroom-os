from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.mark.skipif(
    os.environ.get("BOARDROOM_RUN_REAL_PROVIDER_PROVING") != "1"
    or not os.environ.get("OPENAI_API_KEY"),
    reason="V2-090F real provider proving requires explicit opt-in and provider secret",
)
def test_v2_090f_prd_agent_team_real_provider(tmp_path: Path) -> None:
    from scripts.run_v2_090f_prd_agent_team import main

    prd = tmp_path / "prd.md"
    prd.write_text(
        "Build a tiny library checkout web app with a standard-library Python backend, "
        "static frontend, SQLite persistence, tests, and run instructions. "
        "Users can add books, list books, checkout and return a book, delete a book, "
        "and see the UI update from a real backend.",
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    output = tmp_path / "tiny-fullstack"

    assert (
        main(
            [
                "--prd",
                str(prd),
                "--reset",
                "--workspace-root",
                str(workspace),
                "--output-root",
                str(output),
                "--stage",
                "full",
            ]
        )
        == 0
    )
    assert (output / "00-boardroom/v2-090f-baseline.json").is_file()
    assert (output / "00-boardroom/generated-contracts.json").is_file()
    assert (output / "00-boardroom/generated-ticket-graph.json").is_file()
    assert (output / "closeout-package.json").is_file()
    assert (output / "sample-manifest.json").is_file()


@pytest.mark.skipif(
    os.environ.get("BOARDROOM_RUN_REAL_PROVIDER_PROVING") != "1"
    or not os.environ.get("OPENAI_API_KEY"),
    reason="V2-090F real provider planning gate requires explicit opt-in and provider secret",
)
def test_v2_090f_prd_agent_team_real_provider_planning_gate(tmp_path: Path) -> None:
    from scripts.run_v2_090f_prd_agent_team import main

    prd = tmp_path / "prd.md"
    prd.write_text(
        "Build a tiny library checkout web app with a standard-library Python backend, "
        "static frontend, SQLite persistence, tests, and run instructions. "
        "Users can add books, list books, checkout and return a book, delete a book, "
        "and see the UI update from a real backend.",
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    output = tmp_path / "tiny-fullstack"

    assert (
        main(
            [
                "--prd",
                str(prd),
                "--reset",
                "--workspace-root",
                str(workspace),
                "--output-root",
                str(output),
                "--stage",
                "planning",
            ]
        )
        == 3
    )
    assert (output / "00-boardroom/v2-090f-baseline.json").is_file()
    assert (output / "00-boardroom/generated-board-directive.json").is_file()
    assert (output / "00-boardroom/generated-contracts.json").is_file()
    assert (output / "00-boardroom/generated-ticket-graph.json").is_file()
    assert (output / "00-boardroom/generated-verification-plan.json").is_file()
    assert not (output / "closeout-package.json").exists()
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        extract_v2_090f_planning_artifact,
        validate_v2_090f_generated_ticket_graph_for_worker_execution,
    )
    import json

    ticket_payload = json.loads(
        (output / "00-boardroom/generated-ticket-graph.json").read_text(
            encoding="utf-8"
        )
    )
    ticket_artifact = extract_v2_090f_planning_artifact(
        ticket_payload["provider_output"],
        expected_artifact_name="ticket-graph",
    )
    assert validate_v2_090f_generated_ticket_graph_for_worker_execution(ticket_artifact)


def test_v2_090f_real_opt_in_records_preflight_before_blocking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import UTC, datetime

    from boardroom_os.providers.adapter import FakeProviderTransport, ProviderResponse
    from boardroom_os.providers.attempt import ProviderArtifactRef
    from scripts.run_v2_090f_prd_agent_team import main
    import scripts.run_v2_090f_prd_agent_team as runner

    prd = tmp_path / "prd.md"
    prd.write_text("Build a tiny checkout app.", encoding="utf-8")
    workspace = tmp_path / "workspace"
    output = tmp_path / "tiny-fullstack"
    artifact_root = output / "20-evidence/provider-artifacts"
    artifact_root.mkdir(parents=True)
    for output_name in (
        "board-directive",
        "contracts",
        "ticket-graph",
        "verification-plan",
    ):
        (artifact_root / f"{output_name}.json").write_text(
            '{"status":"planned"}',
            encoding="utf-8",
        )

    def fake_real_provider_factory(*, settings, seat_ref, output_root):
        class FactoryBackedTransport:
            def invoke(self, request):
                output_name = request.execution_package_ref.value.rsplit(".", 1)[-1]
                return FakeProviderTransport(
                    response=ProviderResponse(
                        raw_output_ref=ProviderArtifactRef(value=f"artifact.raw.{output_name}"),
                        parsed_output_ref=ProviderArtifactRef(
                            value=(artifact_root / f"{output_name}.json").as_posix()
                        ),
                        summary=f"{seat_ref} {output_name}",
                    ),
                    attempt_id=f"provider-attempt.v2-090f.{output_name}",
                    started_at=datetime(2026, 6, 12, tzinfo=UTC),
                    finished_at=datetime(2026, 6, 12, 0, 1, tzinfo=UTC),
                ).invoke(request)

        return FactoryBackedTransport()

    monkeypatch.setattr(
        runner,
        "build_v2_090f_planning_provider_adapter",
        fake_real_provider_factory,
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    monkeypatch.setenv("BOARDROOM_RUN_REAL_PROVIDER_PROVING", "1")
    monkeypatch.setenv("BOARDROOM_RUNTIME_CONFIG", "config/boardroom-runtime.v2-090f.yaml")
    monkeypatch.setenv("BOARDROOM_PROVIDERS_CONFIG", "config/boardroom-providers.v2-090f.yaml")
    monkeypatch.setenv("BOARDROOM_ROLES_CONFIG", "config/boardroom-roles.v2-090f.yaml")

    assert (
        main(
            [
                "--prd",
                str(prd),
                "--reset",
                "--workspace-root",
                str(workspace),
                "--output-root",
                str(output),
            ]
        )
        == 3
    )
    assert (workspace / ".boardroom-v2-090f-workspace.json").is_file()
    assert (output / "00-boardroom/v2-090f-baseline.json").is_file()
    assert (output / "00-boardroom/agent-team-role-context.json").is_file()
    assert (output / "00-boardroom/generated-board-directive.json").is_file()
    assert (output / "00-boardroom/generated-contracts.json").is_file()
    assert (output / "00-boardroom/generated-ticket-graph.json").is_file()
    assert (output / "00-boardroom/generated-verification-plan.json").is_file()


def test_v2_090f_runner_worker_stage_records_worker_evidence_with_injected_executor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json
    from dataclasses import dataclass
    from datetime import UTC, datetime

    import scripts.run_v2_090f_prd_agent_team as runner
    from boardroom_os.providers.adapter import FakeProviderTransport, ProviderResponse
    from boardroom_os.providers.attempt import ProviderArtifactRef
    from scripts.run_v2_090f_prd_agent_team import main

    @dataclass(frozen=True)
    class FakeProviderAttempt:
        provider_attempt_id: object

    @dataclass(frozen=True)
    class FakeProjection:
        source_lineage_inputs: tuple[dict[str, object], ...]
        event_stream_ref: str
        events_hash: str

    @dataclass(frozen=True)
    class FakeExecutionResult:
        atomic_run_id: str
        provider_attempt: object
        projection: object

    class ProviderAttemptId:
        def __init__(self, value: str) -> None:
            self.value = value

    class FakeAtomicExecutor:
        def execute(self, request, *, provider_transport_kind: str = "real"):
            ticket = request.execution_package.ticket_ref.value
            return FakeExecutionResult(
                atomic_run_id=f"atomic-run.{ticket}",
                provider_attempt=FakeProviderAttempt(
                    provider_attempt_id=ProviderAttemptId(
                        f"provider-attempt.atomic.{ticket}"
                    )
                ),
                projection=FakeProjection(
                    source_lineage_inputs=(
                        {"path": "app/server.py", "producer_ticket_ref": ticket},
                    ),
                    event_stream_ref=f"{ticket}.jsonl",
                    events_hash="sha256:" + "b" * 64,
                ),
            )

    prd = tmp_path / "prd.md"
    prd.write_text("Build a tiny checkout app.", encoding="utf-8")
    workspace = tmp_path / "workspace"
    output = tmp_path / "tiny-fullstack"
    artifact_root = output / "20-evidence/provider-artifacts"
    artifact_root.mkdir(parents=True)
    planning_payloads = {
        "board-directive": {"artifact_type": "board_directive"},
        "contracts": {"artifact_type": "contracts"},
        "ticket-graph": {
            "ticket_graph": {
                "nodes": [
                    {
                        "node_ref": "ticket.impl.backend_api",
                        "node_type": "implementation",
                        "title": "Implement backend API",
                        "depends_on": [],
                        "owner_seat_ref": "seat.worker.implementation",
                        "acceptance_refs": ["AC-V2-090F-BACKEND-CRUD"],
                        "source_surface_refs": ["surface.backend-api"],
                        "evidence_obligations": [
                            "Backend HTTP API supports add, list, checkout, return, and delete.",
                            (
                                "Backend starts with python -m app.server and reads "
                                "LIBRARY_API_HOST, LIBRARY_API_PORT, and LIBRARY_DB_PATH."
                            ),
                        ],
                        "allowed_write_set": ["app/", "tests/"],
                        "required_outputs": ["app/server.py", "tests/test_api.py"],
                        "commands": [
                            {
                                "command_id": "cmd.backend.tests",
                                "label": "Run backend tests",
                                "command": ["python", "-m", "pytest", "tests/test_api.py"],
                                "cwd": ".",
                            }
                        ],
                    }
                ]
            }
        },
        "verification-plan": {"artifact_type": "verification_plan"},
    }
    for output_name, payload in planning_payloads.items():
        (artifact_root / f"{output_name}.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    def fake_real_provider_factory(*, settings, seat_ref, output_root):
        class FactoryBackedTransport:
            def invoke(self, request):
                output_name = request.execution_package_ref.value.rsplit(".", 1)[-1]
                return FakeProviderTransport(
                    response=ProviderResponse(
                        raw_output_ref=ProviderArtifactRef(value=f"artifact.raw.{output_name}"),
                        parsed_output_ref=ProviderArtifactRef(
                            value=(artifact_root / f"{output_name}.json").as_posix()
                        ),
                        summary=f"{seat_ref} {output_name}",
                    ),
                    attempt_id=f"provider-attempt.v2-090f.{output_name}",
                    started_at=datetime(2026, 6, 12, tzinfo=UTC),
                    finished_at=datetime(2026, 6, 12, 0, 1, tzinfo=UTC),
                ).invoke(request)

        return FactoryBackedTransport()

    monkeypatch.setattr(
        runner,
        "build_v2_090f_planning_provider_adapter",
        fake_real_provider_factory,
    )
    monkeypatch.setattr(
        runner,
        "run_v2_090f_worker_execution_stage",
        lambda *, output_root, workspace_root, settings: __import__(
            "boardroom_os.proving.v2_090f_prd_agent_team",
            fromlist=["run_v2_090f_worker_execution_stage"],
        ).run_v2_090f_worker_execution_stage(
            output_root=output_root,
            workspace_root=workspace_root,
            settings=settings,
            atomic_executor=FakeAtomicExecutor(),
        ),
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    monkeypatch.setenv("BOARDROOM_RUN_REAL_PROVIDER_PROVING", "1")
    monkeypatch.setenv("BOARDROOM_RUNTIME_CONFIG", "config/boardroom-runtime.v2-090f.yaml")
    monkeypatch.setenv("BOARDROOM_PROVIDERS_CONFIG", "config/boardroom-providers.v2-090f.yaml")
    monkeypatch.setenv("BOARDROOM_ROLES_CONFIG", "config/boardroom-roles.v2-090f.yaml")

    assert (
        main(
            [
                "--prd",
                str(prd),
                "--reset",
                "--workspace-root",
                str(workspace),
                "--output-root",
                str(output),
                "--stage",
                "worker",
            ]
        )
        == 3
    )
    assert (output / "20-evidence/worker-execution.json").is_file()
    assert not (output / "closeout-package.json").exists()


def test_v2_090f_runner_full_stage_writes_closeout_with_injected_executor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json
    import scripts.run_v2_090f_prd_agent_team as runner
    from scripts.run_v2_090f_prd_agent_team import main

    prd = tmp_path / "prd.md"
    prd.write_text("Build a tiny checkout app.", encoding="utf-8")
    workspace = tmp_path / "workspace"
    output = tmp_path / "tiny-fullstack"

    def fake_planning_stage(*, prd, output_root, settings, provider_adapter_factory):
        boardroom = output_root / "00-boardroom"
        boardroom.mkdir(parents=True, exist_ok=True)
        for name in ("board-directive", "contracts", "ticket-graph", "verification-plan"):
            (boardroom / f"generated-{name}.json").write_text(
                json.dumps({"provider_output": {"artifact_type": name}}),
                encoding="utf-8",
            )
        role_context_path = boardroom / "agent-team-role-context.json"
        role_context = json.loads(role_context_path.read_text(encoding="utf-8"))
        for seat in ("seat.ceo.delivery", "seat.architect.delivery", "seat.tester.integration"):
            role_context["entries"][seat]["invocation_status"] = "planning_provider_succeeded"
            role_context["entries"][seat]["provider_attempt_refs"] = [f"provider-attempt.v2-090f.{seat}"]
        role_context["entries"]["seat.worker.implementation"]["invocation_status"] = "pending_worker_implementation"
        role_context["entries"]["seat.checker.acceptance"]["invocation_status"] = "pending_checker_review"
        role_context["entries"]["seat.closeout.package"]["invocation_status"] = "pending_closeout"
        role_context["status"] = "planning_stage_succeeded"
        role_context_path.write_text(json.dumps(role_context), encoding="utf-8")
        return {"status": "planning_stage_succeeded", "blocker": "worker pending"}

    def fake_worker_stage(*, output_root, workspace_root, settings):
        workspace_root.mkdir(parents=True, exist_ok=True)
        (workspace_root / "README.md").write_text(
            "Run tests with python -m pytest tests\n",
            encoding="utf-8",
        )
        (workspace_root / "app").mkdir()
        (workspace_root / "app/__init__.py").write_text("", encoding="utf-8")
        (workspace_root / "app/server.py").write_text(
            "from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer\n"
            "import json, os\n"
            "class H(BaseHTTPRequestHandler):\n"
            "    def _send(self, code, data):\n"
            "        body=json.dumps(data).encode(); self.send_response(code); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)\n"
            "    def do_GET(self): self._send(200, {'books': []})\n"
            "    def do_POST(self): self._send(201 if self.path == '/books' else 200, {'book': {'id': 1, 'checked_out': self.path.endswith('checkout')}})\n"
            "    def do_DELETE(self): self._send(200, {'deleted': True, 'id': 1})\n"
            "    def log_message(self, *args): pass\n"
            "def run():\n"
            "    open(os.environ['LIBRARY_DB_PATH'], 'a').close()\n"
            "    ThreadingHTTPServer(('127.0.0.1', int(os.environ['LIBRARY_API_PORT'])), H).serve_forever()\n"
            "if __name__ == '__main__': run()\n",
            encoding="utf-8",
        )
        (workspace_root / "static").mkdir()
        (workspace_root / "static/index.html").write_text("<script src='app.js'></script>", encoding="utf-8")
        (workspace_root / "static/app.js").write_text("fetch('/books')", encoding="utf-8")
        (workspace_root / "tests").mkdir()
        (workspace_root / "tests/test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
        evidence = output_root / "20-evidence"
        evidence.mkdir(parents=True)
        (evidence / "worker-execution.json").write_text(
            json.dumps(
                {
                    "status": "worker_execution_succeeded",
                    "tickets": [
                        {
                            "ticket_ref": "ticket.impl.backend",
                            "provider_attempt_ref": "provider-attempt.real.backend",
                            "declared_command_ids": ["cmd.tests"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return {"status": "worker_execution_succeeded", "blocker": "closeout pending"}

    monkeypatch.setattr(runner, "run_v2_090f_provider_planning_stage", fake_planning_stage)
    monkeypatch.setattr(runner, "run_v2_090f_worker_execution_stage", fake_worker_stage)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    monkeypatch.setenv("BOARDROOM_RUN_REAL_PROVIDER_PROVING", "1")
    monkeypatch.setenv("BOARDROOM_RUNTIME_CONFIG", "config/boardroom-runtime.v2-090f.yaml")
    monkeypatch.setenv("BOARDROOM_PROVIDERS_CONFIG", "config/boardroom-providers.v2-090f.yaml")
    monkeypatch.setenv("BOARDROOM_ROLES_CONFIG", "config/boardroom-roles.v2-090f.yaml")

    assert (
        main(
            [
                "--prd",
                str(prd),
                "--reset",
                "--workspace-root",
                str(workspace),
                "--output-root",
                str(output),
                "--stage",
                "full",
            ]
        )
        == 0
    )
    assert (output / "closeout-package.json").is_file()
    assert (output / "sample-manifest.json").is_file()
