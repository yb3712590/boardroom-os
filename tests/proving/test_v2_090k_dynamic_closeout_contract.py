from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest


def test_dynamic_env_binding_does_not_require_library_api_names(tmp_path: Path) -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import resolve_v2_090k_service_environment
    from boardroom_os.workspace.run_manifest import (
        RunManifestEnvironmentBinding,
        RunManifestEnvironmentValueSource,
    )

    env = resolve_v2_090k_service_environment(
        bindings=(
            RunManifestEnvironmentBinding(
                name="BOOK_APP_HOST",
                value_source=RunManifestEnvironmentValueSource.RUNTIME_HOST,
            ),
            RunManifestEnvironmentBinding(
                name="BOOK_APP_PORT",
                value_source=RunManifestEnvironmentValueSource.RUNTIME_PORT,
            ),
            RunManifestEnvironmentBinding(
                name="BOOK_DB_FILE",
                value_source=RunManifestEnvironmentValueSource.TEMP_SQLITE_PATH,
            ),
        ),
        host="127.0.0.1",
        port=8123,
        temp_sqlite_path=tmp_path / "library.sqlite3",
    )

    assert env == {
        "BOOK_APP_HOST": "127.0.0.1",
        "BOOK_APP_PORT": "8123",
        "BOOK_DB_FILE": str(tmp_path / "library.sqlite3"),
    }


def test_run_manifest_normalizer_accepts_agent_declared_dsl() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import _load_v2_090k_run_manifest_artifact

    manifest = _load_v2_090k_run_manifest_artifact(
        {
            "run_manifest_id": "runmanifest.agent",
            "workspace_manifest_ref": "workspace_manifest.agent",
            "package_contract_ref": "package_contract.agent",
            "package_root": ".",
            "commands": [
                {
                    "command_id": "cmd.backend.run",
                    "kind": "run",
                    "label": "Run backend",
                    "command": ["python", "-m", "agent.server", "--port", "${PORT}"],
                    "cwd": ".",
                    "expected_lifecycle": "long_running_service",
                },
                {
                    "command_id": "cmd.tests",
                    "kind": "test",
                    "label": "Run tests",
                    "command": ["python", "-m", "pytest", "tests"],
                    "cwd": ".",
                },
            ],
            "service_contracts": [
                {
                    "service_ref": "service.backend",
                    "run_command_id": "cmd.backend.run",
                    "role": "backend",
                    "env_bindings": {
                        "HOST": {"default": "127.0.0.1", "required": True},
                        "PORT": {"default": "8765", "required": True},
                        "SQLITE_DB_PATH": {"default": "data/app.sqlite3", "required": True},
                        "STATIC_ROOT": {"default": "frontend", "required": True},
                    },
                    "readiness_probe": {
                        "probe_id": "probe.ready",
                        "method": "GET",
                        "path": "/health",
                        "expect_status": 200,
                    },
                }
            ],
            "frontend_topology": {
                "kind": "static",
                "served_by_service_ref": "service.backend",
            },
            "behavioral_probes": [
                {
                    "probe_id": "probe.crud",
                    "service_ref": "service.backend",
                    "acceptance_refs": ["ACCEPT_ADD_BOOK"],
                    "http_steps": [
                        {
                            "step_id": "step.create",
                            "method": "POST",
                            "path": "/api/books",
                            "json_body": {"title": "Probe Book"},
                            "expect_status": 201,
                            "capture": {"book_id": "$.id"},
                            "assertions": [
                                {"type": "json_equals", "path": "$.title", "value": "Probe Book"}
                            ],
                        }
                    ],
                }
            ],
        }
    )

    assert manifest.package_root.value == "10-project"
    assert manifest.service_contracts[0].command_id.value == "cmd.backend.run"
    assert manifest.service_contracts[0].env_bindings[1].name == "PORT"
    assert manifest.behavioral_probes[0].steps[0].path == "/api/books"


def test_run_manifest_normalizer_accepts_real_provider_dsl_shape() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import _load_v2_090k_run_manifest_artifact
    from boardroom_os.workspace.run_manifest import (
        RunManifestBehaviorAssertionKind,
        RunManifestEnvironmentValueSource,
    )

    manifest = _load_v2_090k_run_manifest_artifact(
        {
            "run_manifest_id": "runmanifest.real-provider",
            "workspace_manifest_ref": "workspacemanifest.real-provider",
            "package_contract_ref": "packagecontract.real-provider",
            "package_root": ".",
            "commands": [
                {
                    "command_id": "cmd.run.backend",
                    "command_type": "long_running_service",
                    "label": "Run backend",
                    "command": ["python", "-m", "library_app.server"],
                    "cwd": ".",
                },
                {
                    "command_id": "cmd.test.unit",
                    "command_type": "finite_test",
                    "label": "Run tests",
                    "command": ["python", "-m", "unittest", "discover", "-s", "tests"],
                    "cwd": ".",
                },
            ],
            "service_contracts": [
                {
                    "service_ref": "svc.backend",
                    "role": "backend",
                    "run_command_id": "cmd.run.backend",
                    "env_bindings": [
                        {"name": "LIBRARY_HOST", "default": "127.0.0.1"},
                        {"name": "LIBRARY_PORT", "default": "8080"},
                        {"name": "LIBRARY_DB_PATH", "default": "data/library.sqlite3"},
                        {"name": "DATABASE_URL", "default": "sqlite:///data/library.sqlite3"},
                        {"name": "LIBRARY_STATIC_DIR", "default": "static"},
                    ],
                    "readiness_probe": {
                        "method": "GET",
                        "path": "/api/health",
                        "expect_status": 200,
                    },
                }
            ],
            "frontend_topology": {
                "kind": "static_frontend_served_by_backend",
                "static_root": "static/",
                "api_base": "same-origin",
            },
            "behavioral_probes": [
                {
                    "probe_id": "probe.lifecycle",
                    "service_ref": "svc.backend",
                    "acceptance_refs": ["AC-BOOK-LIFECYCLE"],
                    "steps": [
                        {
                            "step_id": "step.create",
                            "method": "POST",
                            "path": "/api/books",
                            "json_body": {"title": "Probe"},
                            "expect_status": 201,
                            "capture": {"book_id": "$.id"},
                            "assertions": [
                                {"type": "json_field_equals", "path": "$.title", "value": "Probe"},
                                {"type": "json_field_exists", "field": "id"},
                                {"type": "json_field_type", "path": "$.id", "value": "integer"},
                            ],
                        },
                        {
                            "step_id": "step.contains",
                            "method": "GET",
                            "path": "/api/books",
                            "json_body": None,
                            "expect_status": 200,
                            "capture": {},
                            "assertions": [
                                {
                                    "type": "array_contains",
                                    "path": "$",
                                    "where": {"id": "$capture.book_id", "title": "Probe"},
                                }
                            ],
                        },
                        {
                            "step_id": "step.delete",
                            "method": "DELETE",
                            "path": "/api/books/$capture.book_id",
                            "json_body": None,
                            "expect_status": 204,
                            "capture": {},
                            "assertions": [{"type": "response_body_empty"}],
                        },
                        {
                            "step_id": "step.not-contains",
                            "method": "GET",
                            "path": "/api/books",
                            "json_body": None,
                            "expect_status": 200,
                            "capture": {},
                            "assertions": [
                                {
                                    "type": "json_array_excludes_object",
                                    "field": "$",
                                    "where": {"id": "$capture.book_id"},
                                }
                            ],
                        },
                        {
                            "step_id": "step.frontend",
                            "method": "GET",
                            "path": "/",
                            "json_body": None,
                            "expect_status": 200,
                            "capture": {},
                            "assertions": [
                                {"type": "response_body_contains", "expected": "Tiny Library"},
                                {"type": "response_body_contains_any", "values": ["/api/books", "fetch("]},
                            ],
                        },
                    ],
                }
            ],
        }
    )

    command_kinds = [command.kind.value for command in manifest.commands]
    assert command_kinds == ["run", "test"]
    env_sources = {
        binding.name: binding.value_source
        for binding in manifest.service_contracts[0].env_bindings
    }
    assert env_sources["LIBRARY_HOST"] is RunManifestEnvironmentValueSource.RUNTIME_HOST
    assert env_sources["LIBRARY_PORT"] is RunManifestEnvironmentValueSource.RUNTIME_PORT
    assert env_sources["LIBRARY_DB_PATH"] is RunManifestEnvironmentValueSource.TEMP_SQLITE_PATH
    assert env_sources["DATABASE_URL"] is RunManifestEnvironmentValueSource.TEMP_SQLITE_PATH
    assert env_sources["LIBRARY_STATIC_DIR"] is RunManifestEnvironmentValueSource.LITERAL
    assert manifest.behavioral_probes[0].steps[2].path == "/api/books/${book_id}"
    assertion_kinds = [
        assertion.kind
        for step in manifest.behavioral_probes[0].steps
        for assertion in step.assertions
    ]
    assert RunManifestBehaviorAssertionKind.FIELD_PRESENT in assertion_kinds
    assert RunManifestBehaviorAssertionKind.EMPTY_BODY in assertion_kinds
    assert RunManifestBehaviorAssertionKind.JSON_NOT_CONTAINS in assertion_kinds
    assert RunManifestBehaviorAssertionKind.BODY_CONTAINS in assertion_kinds


def test_run_manifest_normalizer_accepts_binding_type_env_sources() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import _load_v2_090k_run_manifest_artifact
    from boardroom_os.workspace.run_manifest import RunManifestEnvironmentValueSource

    manifest = _load_v2_090k_run_manifest_artifact(
        {
            "run_manifest_id": "runmanifest.binding-types",
            "workspace_manifest_ref": "workspacemanifest.binding-types",
            "package_contract_ref": "packagecontract.binding-types",
            "package_root": ".",
            "commands": [
                {
                    "command_id": "cmd.backend.run",
                    "kind": "run",
                    "command": ["python", "-m", "tiny_library_app.server", "--port", "${PORT}", "--db", "${TINY_LIBRARY_DB}"],
                    "cwd": ".",
                },
            ],
            "service_contracts": [
                {
                    "service_contract_id": "svc.backend",
                    "run_command_id": "cmd.backend.run",
                    "env_bindings": [
                        {"name": "HOST", "value": "127.0.0.1"},
                        {"name": "PORT", "binding_type": "runner_allocated_tcp_port", "required": True},
                        {
                            "name": "TINY_LIBRARY_DB",
                            "binding_type": "runner_temp_file",
                            "default_suffix": ".sqlite3",
                            "required": True,
                        },
                        {"name": "STATIC_ROOT", "value": "frontend"},
                    ],
                    "readiness_probe": {
                        "method": "GET",
                        "path": "/api/health",
                        "expect_status": 200,
                    },
                }
            ],
            "frontend_topology": {
                "type": "static_frontend_served_by_backend",
                "service_contract_id": "svc.backend",
            },
            "behavioral_probes": [
                {
                    "probe_id": "probe.health",
                    "service_contract_id": "svc.backend",
                    "acceptance_refs": ["AC.RUN.READINESS"],
                    "steps": [
                        {
                            "step_id": "health",
                            "method": "GET",
                            "path": "/api/health",
                            "expect_status": 200,
                            "assertions": [{"type": "json_equals", "path": "$.ok", "value": True}],
                        }
                    ],
                }
            ],
        }
    )

    env_sources = {
        binding.name: binding.value_source
        for binding in manifest.service_contracts[0].env_bindings
    }
    assert env_sources["HOST"] is RunManifestEnvironmentValueSource.RUNTIME_HOST
    assert env_sources["PORT"] is RunManifestEnvironmentValueSource.RUNTIME_PORT
    assert env_sources["TINY_LIBRARY_DB"] is RunManifestEnvironmentValueSource.TEMP_SQLITE_PATH
    assert env_sources["STATIC_ROOT"] is RunManifestEnvironmentValueSource.LITERAL
    static_root = next(
        binding
        for binding in manifest.service_contracts[0].env_bindings
        if binding.name == "STATIC_ROOT"
    )
    assert static_root.literal_value == "frontend"


def test_run_manifest_normalizer_accepts_observed_provider_dsl_aliases() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import _load_v2_090k_run_manifest_artifact
    from boardroom_os.workspace.run_manifest import RunManifestBehaviorAssertionKind

    manifest = _load_v2_090k_run_manifest_artifact(
        {
            "run_manifest_id": "runmanifest.provider-aliases",
            "workspace_manifest_ref": "workspacemanifest.provider-aliases",
            "package_contract_ref": "packagecontract.provider-aliases",
            "package_root": ".",
            "commands": [
                {
                    "command_id": "cmd.run.api",
                    "command_type": "service_run",
                    "label": "Start API",
                    "command": ["python", "-m", "api"],
                    "cwd": ".",
                    "env": {"STATIC_ROOT": "frontend"},
                },
                {
                    "command_id": "verify.behavior",
                    "kind": "verification",
                    "label": "Verify behavior",
                    "command": ["python", "-m", "pytest"],
                    "cwd": ".",
                },
            ],
            "service_contracts": [
                {
                    "service_contract_id": "api-service",
                    "run_command_id": "cmd.run.api",
                    "role": "backend",
                    "env_bindings": [
                        {"name": "HOST", "default": "127.0.0.1", "required": False},
                        {"name": "PORT", "default": "8000", "required": False},
                        {
                            "name": "APP_SQLITE_DB_PATH",
                            "default": "data/app.sqlite3",
                            "required": False,
                        },
                        {"name": "STATIC_ROOT", "default": "frontend", "required": False},
                    ],
                    "readiness_probe": {
                        "method": "GET",
                        "path": "/health",
                        "expect_status": 200,
                    },
                }
            ],
            "frontend_topology": {"type": "static_frontend_served_by_backend", "service_ref": "api-service"},
            "behavioral_probes": [
                {
                    "probe_id": "probe.provider-aliases",
                    "acceptance_refs": ["AC-PROVIDER-ALIASES"],
                    "steps": [
                        {
                            "step_id": "create",
                            "method": "POST",
                            "path": "/books",
                            "json_body": {"title": "Alias"},
                            "expect_status": 201,
                            "capture": {"book_id": "$.book.id", "created_status": "$status"},
                            "assertions": [
                                {"type": "status_equals", "value": 201},
                                {"type": "json_path_exists", "path": "$.book.id"},
                                {"type": "equals", "actual": "$.book.title", "expected": "Alias"},
                                {"type": "exists", "actual": "$.book.id"},
                                {"operator": "exists", "path": "$.book.id"},
                                {"operator": "equals", "path": "$.book.title", "value": "Alias"},
                            ],
                        },
                        {
                            "step_id": "list-object",
                            "method": "GET",
                            "path": "/books",
                            "json_body": None,
                            "expect_status": 200,
                            "capture": {},
                            "assertions": [
                                {"operator": "is_array", "path": "$"},
                                {"operator": "contains", "path": "$[*].title", "value": "Alias"},
                                {"operator": "not_contains", "path": "$[*].id", "value": "{missing_book_id}"},
                                {
                                    "type": "json_array_excludes",
                                    "path": "$",
                                    "where": {"id": "{missing_book_id}"},
                                },
                                {"type": "json_is_array", "path": "$"},
                                {
                                    "type": "json_array_contains_field_value",
                                    "path": "$",
                                    "field": "title",
                                    "expected": "Alias",
                                },
                                {
                                    "type": "json_array_not_contains_field_value",
                                    "path": "$",
                                    "field": "id",
                                    "expected_from_capture": "missing_book_id",
                                },
                            ],
                        },
                        {
                            "step_id": "frontend",
                            "method": "GET",
                            "path": "/",
                            "json_body": None,
                            "expect_status": 200,
                            "capture": {"html": "$body"},
                            "assertions": [{"type": "body_contains", "value": "script"}],
                        },
                        {
                            "step_id": "list",
                            "method": "GET",
                            "path": "/books",
                            "json_body": None,
                            "expect_status": 200,
                            "capture": {},
                            "assertions": [
                                {
                                    "type": "array_contains_object",
                                    "actual": "$.books",
                                    "match": {"id": "${capture.book_id}", "title": "Alias"},
                                }
                            ],
                        },
                        {
                            "step_id": "frontend-text",
                            "method": "GET",
                            "path": "/",
                            "json_body": None,
                            "expect_status": 200,
                            "capture": {},
                            "assertions": [
                                {"type": "body_contains", "actual": "$body", "expected": "Checkout"}
                            ],
                        },
                    ],
                }
            ],
        }
    )

    assert [command.kind.value for command in manifest.commands] == ["run", "test"]
    assert manifest.behavioral_probes[0].service_command_id.value == "cmd.run.api"
    first_step_assertions = manifest.behavioral_probes[0].steps[0].assertions
    assert [assertion.kind for assertion in first_step_assertions] == [
        RunManifestBehaviorAssertionKind.FIELD_PRESENT,
        RunManifestBehaviorAssertionKind.JSON_EQUALS,
        RunManifestBehaviorAssertionKind.FIELD_PRESENT,
        RunManifestBehaviorAssertionKind.FIELD_PRESENT,
        RunManifestBehaviorAssertionKind.JSON_EQUALS,
    ]
    operator_assertions = manifest.behavioral_probes[0].steps[1].assertions
    assert [assertion.kind for assertion in operator_assertions] == [
        RunManifestBehaviorAssertionKind.JSON_TYPE,
        RunManifestBehaviorAssertionKind.JSON_CONTAINS,
        RunManifestBehaviorAssertionKind.JSON_NOT_CONTAINS,
        RunManifestBehaviorAssertionKind.JSON_NOT_CONTAINS,
        RunManifestBehaviorAssertionKind.JSON_TYPE,
        RunManifestBehaviorAssertionKind.JSON_CONTAINS,
        RunManifestBehaviorAssertionKind.JSON_NOT_CONTAINS,
    ]
    assert operator_assertions[0].expected == "array"
    assert operator_assertions[1].expected == "Alias"
    assert operator_assertions[2].expected == "${missing_book_id}"
    assert operator_assertions[3].expected == {"id": "${missing_book_id}"}
    assert operator_assertions[4].expected == "array"
    assert operator_assertions[5].expected == {"title": "Alias"}
    assert operator_assertions[6].expected == {"id": "${missing_book_id}"}
    contains_assertion = manifest.behavioral_probes[0].steps[3].assertions[0]
    assert contains_assertion.kind is RunManifestBehaviorAssertionKind.JSON_CONTAINS
    assert contains_assertion.expected == {"id": "${book_id}", "title": "Alias"}
    text_assertion = manifest.behavioral_probes[0].steps[4].assertions[0]
    assert text_assertion.kind is RunManifestBehaviorAssertionKind.BODY_CONTAINS
    assert text_assertion.expected == "Checkout"
    static_binding = manifest.service_contracts[0].env_bindings[3]
    assert static_binding.name == "STATIC_ROOT"
    assert static_binding.literal_value == "frontend"


def test_run_manifest_normalizer_fails_closed_on_conflicting_status_assertion() -> None:
    from boardroom_os.proving.v2_090f_prd_agent_team import _load_v2_090k_run_manifest_artifact

    payload = {
        "run_manifest_id": "runmanifest.bad-status",
        "workspace_manifest_ref": "workspacemanifest.bad-status",
        "package_contract_ref": "packagecontract.bad-status",
        "package_root": ".",
        "commands": [
            {
                "command_id": "svc.api",
                "command_type": "service",
                "label": "Start API",
                "command": ["python", "-m", "api"],
                "cwd": ".",
            }
        ],
        "service_contracts": [
            {
                "service_contract_id": "api-service",
                "run_command_id": "svc.api",
                "role": "backend",
                "env_bindings": {
                    "HOST": {"default": "127.0.0.1"},
                    "PORT": {"default": "8000"},
                },
                "readiness_probe": {
                    "method": "GET",
                    "path": "/health",
                    "expect_status": 200,
                },
            }
        ],
        "frontend_topology": {"kind": "static", "served_by_service_ref": "api-service"},
        "behavioral_probes": [
            {
                "probe_id": "probe.bad-status",
                "service_contract_id": "api-service",
                "acceptance_refs": ["AC-BAD-STATUS"],
                "steps": [
                    {
                        "step_id": "create",
                        "method": "POST",
                        "path": "/books",
                        "json_body": {},
                        "expect_status": 201,
                        "capture": {},
                        "assertions": [{"type": "status_equals", "value": 200}],
                    }
                ],
            }
        ],
    }

    with pytest.raises(ValueError, match="status_equals"):
        _load_v2_090k_run_manifest_artifact(payload)


@dataclass(frozen=True)
class _FakeResponse:
    status_code: int
    payload: object

    def json(self) -> object:
        if isinstance(self.payload, BaseException):
            raise self.payload
        return self.payload

    @property
    def text(self) -> str:
        if isinstance(self.payload, str):
            return self.payload
        return ""


class _FakeHttpClient:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = responses
        self.requests: list[dict[str, object]] = []

    def request(self, method: str, url: str, *, json: object | None = None, timeout: float = 10.0):
        self.requests.append({"method": method, "url": url, "json": json, "timeout": timeout})
        if not self._responses:
            raise AssertionError("unexpected extra HTTP request")
        return self._responses.pop(0)


def test_behavior_probe_executor_captures_and_interpolates_values() -> None:
    from boardroom_os.contracts.types import AcceptanceRef, ContractId
    from boardroom_os.proving.v2_090f_prd_agent_team import execute_v2_090k_behavior_probe
    from boardroom_os.workspace.run_manifest import (
        RunManifestBehaviorAssertion,
        RunManifestBehaviorAssertionKind,
        RunManifestBehaviorProbe,
        RunManifestBehaviorStep,
    )

    client = _FakeHttpClient(
        [
            _FakeResponse(201, {"item": {"id": "agent-123", "name": "Agent Item"}}),
            _FakeResponse(200, {"items": [{"id": "agent-123", "name": "Agent Item"}]}),
        ]
    )
    probe = RunManifestBehaviorProbe(
        probe_id=ContractId(value="probe.agent-custom"),
        service_command_id=ContractId(value="serve-agent-api"),
        acceptance_refs=(AcceptanceRef(value="AC-AGENT-CUSTOM"),),
        steps=(
            RunManifestBehaviorStep(
                step_id="create",
                method="POST",
                path="/custom-items",
                json_body={"name": "Agent Item"},
                expect_status=201,
                capture={"item_id": "$.item.id"},
                assertions=(),
            ),
            RunManifestBehaviorStep(
                step_id="list",
                method="GET",
                path="/custom-items/${item_id}",
                json_body=None,
                expect_status=200,
                capture={},
                assertions=(
                    RunManifestBehaviorAssertion(
                        kind=RunManifestBehaviorAssertionKind.JSON_CONTAINS,
                        target="$.items[*].id",
                        expected="${item_id}",
                    ),
                ),
            ),
        ),
    )

    result = execute_v2_090k_behavior_probe(
        probe=probe,
        base_url="http://127.0.0.1:8123",
        http_client=client,
    )

    assert result["probe_id"] == "probe.agent-custom"
    assert result["passed"] is True
    assert result["captures"] == {"item_id": "agent-123"}
    assert client.requests[1]["url"] == "http://127.0.0.1:8123/custom-items/agent-123"


def test_behavior_probe_executor_supports_all_declared_assertions() -> None:
    from boardroom_os.contracts.types import AcceptanceRef, ContractId
    from boardroom_os.proving.v2_090f_prd_agent_team import execute_v2_090k_behavior_probe
    from boardroom_os.workspace.run_manifest import (
        RunManifestBehaviorAssertion,
        RunManifestBehaviorAssertionKind,
        RunManifestBehaviorProbe,
        RunManifestBehaviorStep,
    )

    client = _FakeHttpClient(
        [
            _FakeResponse(
                200,
                {
                    "status": "ok",
                    "item": {"id": "agent-123", "state": "active"},
                    "items": [{"id": "agent-123"}, {"id": "agent-456"}],
                },
            )
        ]
    )
    probe = RunManifestBehaviorProbe(
        probe_id=ContractId(value="probe.assertions"),
        service_command_id=ContractId(value="serve-agent-api"),
        acceptance_refs=(AcceptanceRef(value="AC-AGENT-CUSTOM"),),
        steps=(
            RunManifestBehaviorStep(
                step_id="assert",
                method="GET",
                path="/custom-items",
                json_body=None,
                expect_status=200,
                capture={},
                assertions=(
                    RunManifestBehaviorAssertion(
                        kind=RunManifestBehaviorAssertionKind.JSON_EQUALS,
                        target="$.status",
                        expected="ok",
                    ),
                    RunManifestBehaviorAssertion(
                        kind=RunManifestBehaviorAssertionKind.JSON_CONTAINS,
                        target="$.items[*].id",
                        expected="agent-123",
                    ),
                    RunManifestBehaviorAssertion(
                        kind=RunManifestBehaviorAssertionKind.FIELD_EQUALS,
                        target="$.item.state",
                        expected="active",
                    ),
                    RunManifestBehaviorAssertion(
                        kind=RunManifestBehaviorAssertionKind.FIELD_ABSENT,
                        target="$.item.deleted_at",
                    ),
                ),
            ),
        ),
    )

    result = execute_v2_090k_behavior_probe(
        probe=probe,
        base_url="http://127.0.0.1:8123",
        http_client=client,
    )

    assert result["passed"] is True


def test_behavior_probe_executor_supports_presence_empty_body_negative_and_body_contains() -> None:
    from boardroom_os.contracts.types import AcceptanceRef, ContractId
    from boardroom_os.proving.v2_090f_prd_agent_team import execute_v2_090k_behavior_probe
    from boardroom_os.workspace.run_manifest import (
        RunManifestBehaviorAssertion,
        RunManifestBehaviorAssertionKind,
        RunManifestBehaviorProbe,
        RunManifestBehaviorStep,
    )

    client = _FakeHttpClient(
        [
            _FakeResponse(201, {"id": "agent-123", "title": "Agent Item"}),
            _FakeResponse(204, ValueError("empty response has no JSON body")),
            _FakeResponse(200, [{"id": "agent-456"}]),
            _FakeResponse(200, "<html><title>Tiny Library</title><script>fetch('/api/books')</script></html>"),
        ]
    )
    probe = RunManifestBehaviorProbe(
        probe_id=ContractId(value="probe.negative-assertions"),
        service_command_id=ContractId(value="serve-agent-api"),
        acceptance_refs=(AcceptanceRef(value="AC-AGENT-CUSTOM"),),
        steps=(
            RunManifestBehaviorStep(
                step_id="create",
                method="POST",
                path="/custom-items",
                json_body={"title": "Agent Item"},
                expect_status=201,
                capture={"item_id": "$.id"},
                assertions=(
                    RunManifestBehaviorAssertion(
                        kind=RunManifestBehaviorAssertionKind.FIELD_PRESENT,
                        target="$.id",
                    ),
                    RunManifestBehaviorAssertion(
                        kind=RunManifestBehaviorAssertionKind.JSON_TYPE,
                        target="$.id",
                        expected="string",
                    ),
                ),
            ),
            RunManifestBehaviorStep(
                step_id="delete",
                method="DELETE",
                path="/custom-items/${item_id}",
                json_body=None,
                expect_status=204,
                capture={},
                assertions=(
                    RunManifestBehaviorAssertion(
                        kind=RunManifestBehaviorAssertionKind.EMPTY_BODY,
                        target="$",
                    ),
                ),
            ),
            RunManifestBehaviorStep(
                step_id="list",
                method="GET",
                path="/custom-items",
                json_body=None,
                expect_status=200,
                capture={},
                assertions=(
                    RunManifestBehaviorAssertion(
                        kind=RunManifestBehaviorAssertionKind.JSON_NOT_CONTAINS,
                        target="$",
                        expected={"id": "${item_id}"},
                    ),
                ),
            ),
            RunManifestBehaviorStep(
                step_id="frontend",
                method="GET",
                path="/",
                json_body=None,
                expect_status=200,
                capture={},
                assertions=(
                    RunManifestBehaviorAssertion(
                        kind=RunManifestBehaviorAssertionKind.BODY_CONTAINS,
                        target="$",
                        expected="Tiny Library",
                    ),
                    RunManifestBehaviorAssertion(
                        kind=RunManifestBehaviorAssertionKind.BODY_CONTAINS_ANY,
                        target="$",
                        expected=["/api/books", "missing-api"],
                    ),
                ),
            ),
        ),
    )

    result = execute_v2_090k_behavior_probe(
        probe=probe,
        base_url="http://127.0.0.1:8123",
        http_client=client,
    )

    assert result["passed"] is True
    assert client.requests[1]["url"] == "http://127.0.0.1:8123/custom-items/agent-123"


def test_behavior_probe_executor_captures_status_and_body_text() -> None:
    from boardroom_os.contracts.types import AcceptanceRef, ContractId
    from boardroom_os.proving.v2_090f_prd_agent_team import execute_v2_090k_behavior_probe
    from boardroom_os.workspace.run_manifest import (
        RunManifestBehaviorAssertion,
        RunManifestBehaviorAssertionKind,
        RunManifestBehaviorProbe,
        RunManifestBehaviorStep,
    )

    client = _FakeHttpClient([_FakeResponse(200, "<html><script src='/app.js'></script></html>")])
    probe = RunManifestBehaviorProbe(
        probe_id=ContractId(value="probe.status-body"),
        service_command_id=ContractId(value="serve-agent-api"),
        acceptance_refs=(AcceptanceRef(value="AC-AGENT-CUSTOM"),),
        steps=(
            RunManifestBehaviorStep(
                step_id="frontend",
                method="GET",
                path="/",
                json_body=None,
                expect_status=200,
                capture={"html": "$body", "status": "$status"},
                assertions=(
                    RunManifestBehaviorAssertion(
                        kind=RunManifestBehaviorAssertionKind.BODY_CONTAINS,
                        target="$",
                        expected="script",
                    ),
                ),
            ),
        ),
    )

    result = execute_v2_090k_behavior_probe(
        probe=probe,
        base_url="http://127.0.0.1:8123",
        http_client=client,
    )

    assert result["passed"] is True
    assert result["captures"] == {
        "html": "<html><script src='/app.js'></script></html>",
        "status": 200,
    }


def test_behavior_probe_executor_fails_closed_on_missing_capture() -> None:
    from boardroom_os.contracts.types import AcceptanceRef, ContractId
    from boardroom_os.proving.v2_090f_prd_agent_team import execute_v2_090k_behavior_probe
    from boardroom_os.workspace.run_manifest import RunManifestBehaviorProbe, RunManifestBehaviorStep

    client = _FakeHttpClient([_FakeResponse(201, {"item": {}})])
    probe = RunManifestBehaviorProbe(
        probe_id=ContractId(value="probe.missing-capture"),
        service_command_id=ContractId(value="serve-agent-api"),
        acceptance_refs=(AcceptanceRef(value="AC-AGENT-CUSTOM"),),
        steps=(
            RunManifestBehaviorStep(
                step_id="create",
                method="POST",
                path="/custom-items",
                json_body={},
                expect_status=201,
                capture={"item_id": "$.item.id"},
                assertions=(),
            ),
        ),
    )

    with pytest.raises(ValueError, match="capture item_id"):
        execute_v2_090k_behavior_probe(
            probe=probe,
            base_url="http://127.0.0.1:8123",
            http_client=client,
        )


def test_behavior_probe_executor_fails_closed_on_bad_status_or_assertion() -> None:
    from boardroom_os.contracts.types import AcceptanceRef, ContractId
    from boardroom_os.proving.v2_090f_prd_agent_team import execute_v2_090k_behavior_probe
    from boardroom_os.workspace.run_manifest import (
        RunManifestBehaviorAssertion,
        RunManifestBehaviorAssertionKind,
        RunManifestBehaviorProbe,
        RunManifestBehaviorStep,
    )

    status_probe = RunManifestBehaviorProbe(
        probe_id=ContractId(value="probe.bad-status"),
        service_command_id=ContractId(value="serve-agent-api"),
        acceptance_refs=(AcceptanceRef(value="AC-AGENT-CUSTOM"),),
        steps=(
            RunManifestBehaviorStep(
                step_id="list",
                method="GET",
                path="/custom-items",
                json_body=None,
                expect_status=200,
                capture={},
                assertions=(),
            ),
        ),
    )
    with pytest.raises(ValueError, match="expected status 200"):
        execute_v2_090k_behavior_probe(
            probe=status_probe,
            base_url="http://127.0.0.1:8123",
            http_client=_FakeHttpClient([_FakeResponse(500, {"error": "boom"})]),
        )

    assertion_probe = status_probe.model_copy(
        update={
            "probe_id": ContractId(value="probe.bad-assertion"),
            "steps": (
                status_probe.steps[0].model_copy(
                    update={
                        "assertions": (
                            RunManifestBehaviorAssertion(
                                kind=RunManifestBehaviorAssertionKind.FIELD_EQUALS,
                                target="$.status",
                                expected="ok",
                            ),
                        )
                    }
                ),
            ),
        }
    )
    with pytest.raises(ValueError, match="assertion failed"):
        execute_v2_090k_behavior_probe(
            probe=assertion_probe,
            base_url="http://127.0.0.1:8123",
            http_client=_FakeHttpClient([_FakeResponse(200, {"status": "wrong"})]),
        )
