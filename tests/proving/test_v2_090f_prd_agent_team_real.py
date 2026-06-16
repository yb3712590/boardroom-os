from __future__ import annotations

import os
from pathlib import Path

import pytest


def _agent_declared_run_manifest_payload() -> dict[str, object]:
    return {
        "run_manifest_id": {"value": "run-manifest.agent"},
        "workspace_manifest_ref": {"value": "workspace-manifest.agent"},
        "package_contract_ref": {"value": "package-contract.agent"},
        "package_root": {"value": "10-project"},
        "commands": [
            {
                "command_id": {"value": "serve-agent-api"},
                "kind": "run",
                "label": "Serve agent API",
                "command": [os.sys.executable, "-m", "service.main"],
                "cwd": ".",
            },
            {
                "command_id": {"value": "test-agent-api"},
                "kind": "test",
                "label": "Run tests",
                "command": [os.sys.executable, "-m", "pytest", "tests"],
                "cwd": ".",
            },
        ],
        "service_contracts": [
            {
                "command_id": {"value": "serve-agent-api"},
                "role": "backend",
                "env_bindings": [
                    {"name": "AGENT_HOST", "value_source": "runtime_host"},
                    {"name": "AGENT_PORT", "value_source": "runtime_port"},
                    {"name": "AGENT_DB_FILE", "value_source": "temp_sqlite_path"},
                ],
                "readiness_probe": {"method": "GET", "path": "/ready", "expect_status": 200},
            }
        ],
        "frontend_topology": {"mode": "served-by-backend"},
        "behavioral_probes": [
            {
                "probe_id": {"value": "probe.agent-items"},
                "service_command_id": {"value": "serve-agent-api"},
                "acceptance_refs": [{"value": "AC-AGENT-DECLARED-LIBRARY"}],
                "steps": [
                    {
                        "step_id": "create",
                        "method": "POST",
                        "path": "/items",
                        "json_body": {"name": "Agent Item"},
                        "expect_status": 201,
                        "capture": {"item_id": "$.item.id"},
                        "assertions": [],
                    },
                    {
                        "step_id": "list",
                        "method": "GET",
                        "path": "/items",
                        "json_body": None,
                        "expect_status": 200,
                        "capture": {},
                        "assertions": [
                            {
                                "kind": "json_contains",
                                "target": "$.items[*].id",
                                "expected": "${item_id}",
                            }
                        ],
                    },
                ],
            }
        ],
    }


def _agent_declared_ticket_graph_payload() -> dict[str, object]:
    return {
        "ticket_graph": {
            "nodes": [
                {
                    "node_ref": "ticket.impl.agent_service",
                    "node_type": "implementation",
                    "title": "Implement agent-declared service API",
                    "depends_on": [],
                    "owner_seat_ref": "seat.worker.implementation",
                    "acceptance_refs": ["AC-AGENT-DECLARED-LIBRARY"],
                    "source_surface_refs": ["surface.agent-service"],
                    "evidence_obligations": [
                        "Service supports add, list, checkout, return, and delete operations.",
                        "RunManifest declares service startup, readiness, and behavioral probes.",
                    ],
                    "allowed_write_set": ["service/", "tests/"],
                    "required_outputs": ["service/main.py", "tests/test_agent_api.py"],
                    "commands": [
                        {
                            "command_id": "test-agent-api",
                            "label": "Run agent service tests",
                            "command": [
                                os.sys.executable,
                                "-m",
                                "pytest",
                                "tests/test_agent_api.py",
                            ],
                            "cwd": ".",
                        }
                    ],
                }
            ]
        }
    }


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


@pytest.mark.skipif(
    os.environ.get("BOARDROOM_RUN_REAL_PROVIDER_PROVING") != "1"
    or not os.environ.get("OPENAI_API_KEY"),
    reason="V2-090F rework-entry validation requires explicit opt-in and provider secret",
)
def test_v2_090f_prd_agent_team_rework_entry_validation_real_provider(
    tmp_path: Path,
) -> None:
    from scripts.run_v2_090f_prd_agent_team import main

    prd = tmp_path / "prd.md"
    prd.write_text(
        "Build a tiny library checkout web app with a standard-library Python backend, "
        "static frontend, SQLite persistence, tests, and run instructions. "
        "Users can add books, list books, checkout and return a book, delete a book, "
        "and see the UI update from a real backend.",
        encoding="utf-8",
    )
    output = tmp_path / "tiny-fullstack"

    exit_code = main(
        [
            "--prd",
            str(prd),
            "--reset",
            "--workspace-root",
            str(tmp_path / "workspace"),
            "--output-root",
            str(output),
            "--stage",
            "rework-entry",
        ]
    )

    assert exit_code in {0, 4, 5}
    assert (output / "00-boardroom/ticket-graph.before-rework.json").is_file()
    assert (output / "00-boardroom/ticket-graph.before-rework.md").is_file()
    assert (output / "20-evidence/rework-entry/rework-terminal.json").is_file()
    assert (output / "30-audit/rework-entry-validation.md").is_file()


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
        "run-manifest",
    ):
        payload = {"status": "planned"}
        if output_name == "run-manifest":
            payload = _agent_declared_run_manifest_payload()
        elif output_name == "ticket-graph":
            payload = _agent_declared_ticket_graph_payload()
        (artifact_root / f"{output_name}.json").write_text(
            __import__("json").dumps(payload),
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
                        {"path": "service/main.py", "producer_ticket_ref": ticket},
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
        "ticket-graph": _agent_declared_ticket_graph_payload(),
        "verification-plan": {"artifact_type": "verification_plan"},
        "run-manifest": _agent_declared_run_manifest_payload(),
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
        for name in ("board-directive", "contracts", "ticket-graph", "verification-plan", "run-manifest"):
            (boardroom / f"generated-{name}.json").write_text(
                json.dumps({"provider_output": {"artifact_type": name}}),
                encoding="utf-8",
            )
        role_context_path = boardroom / "agent-team-role-context.json"
        role_context = json.loads(role_context_path.read_text(encoding="utf-8"))
        for seat in (
            "seat.ceo.delivery",
            "seat.architect.delivery",
            "seat.tester.integration",
            "seat.release.devops",
        ):
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
        (workspace_root / "service").mkdir()
        (workspace_root / "service/__init__.py").write_text("", encoding="utf-8")
        (workspace_root / "service/main.py").write_text(
            "from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer\n"
            "import json, os\n"
            "class H(BaseHTTPRequestHandler):\n"
            "    def _send(self, code, data):\n"
            "        body=json.dumps(data).encode(); self.send_response(code); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)\n"
            "    def do_GET(self): self._send(200, {'ready': True} if self.path == '/ready' else {'items': [{'id': 'agent-1'}]})\n"
            "    def do_POST(self): self._send(201, {'item': {'id': 'agent-1'}})\n"
            "    def do_DELETE(self): self._send(200, {'deleted': True, 'id': 1})\n"
            "    def log_message(self, *args): pass\n"
            "def run():\n"
            "    open(os.environ['AGENT_DB_FILE'], 'a').close()\n"
            "    ThreadingHTTPServer((os.environ['AGENT_HOST'], int(os.environ['AGENT_PORT'])), H).serve_forever()\n"
            "if __name__ == '__main__': run()\n",
            encoding="utf-8",
        )
        (workspace_root / "tests").mkdir()
        (workspace_root / "tests/test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
        evidence = output_root / "20-evidence"
        (evidence / "tests").mkdir(parents=True)
        source_lineage_inputs = [
            {
                "path": "README.md",
                "sha256": "sha256:" + __import__("hashlib").sha256((workspace_root / "README.md").read_bytes()).hexdigest(),
                "producer_ticket_ref": "ticket.impl.docs",
                "producer_attempt_ref": "provider-attempt.real.backend",
                "acceptance_refs": ["AC-AGENT-DECLARED-LIBRARY"],
                "source_surface_refs": ["surface.agent.package"],
                "evidence_refs": ["verified-evidence.agent.package"],
            },
            {
                "path": "service/__init__.py",
                "sha256": "sha256:" + __import__("hashlib").sha256((workspace_root / "service/__init__.py").read_bytes()).hexdigest(),
                "producer_ticket_ref": "ticket.impl.backend",
                "producer_attempt_ref": "provider-attempt.real.backend",
                "acceptance_refs": ["AC-AGENT-DECLARED-LIBRARY"],
                "source_surface_refs": ["surface.agent.package"],
                "evidence_refs": ["verified-evidence.agent.package"],
            },
            {
                "path": "service/main.py",
                "sha256": "sha256:" + __import__("hashlib").sha256((workspace_root / "service/main.py").read_bytes()).hexdigest(),
                "producer_ticket_ref": "ticket.impl.backend",
                "producer_attempt_ref": "provider-attempt.real.backend",
                "acceptance_refs": ["AC-AGENT-DECLARED-LIBRARY"],
                "source_surface_refs": ["surface.agent.package"],
                "evidence_refs": ["verified-evidence.agent.package"],
            },
            {
                "path": "tests/test_ok.py",
                "sha256": "sha256:" + __import__("hashlib").sha256((workspace_root / "tests/test_ok.py").read_bytes()).hexdigest(),
                "producer_ticket_ref": "ticket.impl.tests",
                "producer_attempt_ref": "provider-attempt.real.backend",
                "acceptance_refs": ["AC-AGENT-DECLARED-LIBRARY"],
                "source_surface_refs": ["surface.agent.package"],
                "evidence_refs": ["verified-evidence.agent.package"],
            },
        ]
        (evidence / "worker-execution.json").write_text(
            json.dumps(
                {
                    "status": "worker_execution_succeeded",
                    "tickets": [
                        {
                            "ticket_ref": "ticket.impl.backend",
                            "provider_attempt_ref": "provider-attempt.real.backend",
                            "declared_command_ids": ["cmd.tests"],
                            "source_lineage_inputs": source_lineage_inputs,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (evidence / "tests/run-manifest.json").write_text(
            json.dumps(_agent_declared_run_manifest_payload()),
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
