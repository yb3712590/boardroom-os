from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json

from atomic_agent.models import AgentRunResult, AgentRunStatus

from boardroom_os.execution.atomic_agent import AtomicAgentResultValidator
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.providers.attempt import (
    ProviderArtifactRef,
    ProviderAttempt,
    ProviderAttemptOutcome,
    ProviderAttemptStatus,
)
from tests.execution.test_atomic_agent_invocation_compiler import _execution_package


def _write_event_stream(path, *, command_id=None, include_provider_turn=False):
    artifact = {
        "artifact_ref": "artifact://run.atomic.1/results/step-0002.json",
        "sha256": "sha256:" + "0" * 64,
        "size_bytes": 42,
        "truncated_in_observation": False,
    }
    diff_artifact = {
        "artifact_ref": "artifact://run.atomic.1/diffs/backend-app.diff",
        "sha256": "sha256:" + "1" * 64,
        "size_bytes": 12,
        "truncated_in_observation": False,
    }
    observation_artifact = {
        "artifact_ref": "artifact://run.atomic.1/observations/tool.1.json",
        "sha256": "sha256:" + "2" * 64,
        "size_bytes": 10,
        "truncated_in_observation": False,
    }
    sequence = 1
    events_without_hash = [
        {
            "event_id": "evt-1",
            "run_id": "run.atomic.1",
            "sequence": sequence,
            "type": "run.started",
            "timestamp": "2026-06-10T00:00:00Z",
            "payload": {"event_protocol_version": 1, "invocation_id": "inv.atomic.1"},
            "previous_event_hash": None,
        },
    ]
    sequence += 1
    if include_provider_turn:
        events_without_hash.extend(
            [
                {
                    "event_id": "evt-provider-start",
                    "run_id": "run.atomic.1",
                    "sequence": sequence,
                    "type": "provider.turn.started",
                    "timestamp": "2026-06-10T00:00:00Z",
                    "payload": {"provider_turn_id": "provider_turn_000001"},
                    "previous_event_hash": None,
                },
                {
                    "event_id": "evt-provider-completed",
                    "run_id": "run.atomic.1",
                    "sequence": sequence + 1,
                    "type": "provider.turn.completed",
                    "timestamp": "2026-06-10T00:00:01Z",
                    "payload": {
                        "provider_turn_id": "provider_turn_000001",
                        "output": {
                            "artifact_ref": "artifact://run.atomic.1/provider/turn_000001.txt",
                            "sha256": "sha256:" + "5" * 64,
                            "size_bytes": 80,
                            "truncated_in_observation": False,
                        },
                    },
                    "previous_event_hash": None,
                },
            ]
        )
        sequence += 2
    events_without_hash.extend(
        [
            {
            "event_id": "evt-2",
            "run_id": "run.atomic.1",
            "sequence": sequence,
            "type": "tool.attempt.started",
            "timestamp": "2026-06-10T00:00:01Z",
            "payload": {
                "tool_attempt_id": "tool.1",
                "action_id": "action.1",
                "tool": "write_file",
            },
            "previous_event_hash": None,
        },
        {
            "event_id": "evt-3",
            "run_id": "run.atomic.1",
            "sequence": sequence + 1,
            "type": "tool.attempt.completed",
            "timestamp": "2026-06-10T00:00:02Z",
            "payload": {
                "tool_attempt_id": "tool.1",
                "action_id": "action.1",
                "tool": "write_file",
                "observation": observation_artifact,
            },
            "previous_event_hash": None,
        },
        {
            "event_id": "evt-4",
            "run_id": "run.atomic.1",
            "sequence": sequence + 2,
            "type": "workspace.mutation.recorded",
            "timestamp": "2026-06-10T00:00:03Z",
            "payload": {
                "tool_attempt_id": "tool.1",
                "path": "backend/app.py",
                "before_hash": None,
                "after_hash": "sha256:" + "0" * 64,
                "diff": diff_artifact,
            },
            "previous_event_hash": None,
        },
        *(
            [
                {
                    "event_id": "evt-4-command",
                    "run_id": "run.atomic.1",
                    "sequence": sequence + 3,
                    "type": "command.completed",
                    "timestamp": "2026-06-10T00:00:03Z",
                    "payload": {
                        "tool_attempt_id": "tool.1",
                        "command_id": command_id,
                        "exit_code": 0,
                        "stdout": {
                            "artifact_ref": "artifact://run.atomic.1/commands/stdout.txt",
                            "sha256": "sha256:" + "3" * 64,
                            "size_bytes": 8,
                            "truncated_in_observation": False,
                        },
                        "stderr": {
                            "artifact_ref": "artifact://run.atomic.1/commands/stderr.txt",
                            "sha256": "sha256:" + "4" * 64,
                            "size_bytes": 0,
                            "truncated_in_observation": False,
                        },
                    },
                    "previous_event_hash": None,
                }
            ]
            if command_id is not None
            else []
        ),
        {
            "event_id": "evt-5",
            "run_id": "run.atomic.1",
            "sequence": sequence + 4 if command_id is not None else sequence + 3,
            "type": "result.submitted",
            "timestamp": "2026-06-10T00:00:04Z",
            "payload": {
                "summary": "Updated backend/app.py",
                "produced_paths": ["backend/app.py"],
                "artifact_refs": [artifact],
            },
            "previous_event_hash": None,
        },
        {
            "event_id": "evt-6",
            "run_id": "run.atomic.1",
            "sequence": sequence + 5 if command_id is not None else sequence + 4,
            "type": "run.completed",
            "timestamp": "2026-06-10T00:00:05Z",
            "payload": {"summary": "Updated backend/app.py"},
            "previous_event_hash": None,
        },
    ])
    events = []
    previous_hash = None
    for event in events_without_hash:
        resolved_event = dict(event)
        resolved_event["previous_event_hash"] = previous_hash
        resolved_event["event_hash"] = _event_hash(resolved_event)
        events.append(resolved_event)
        previous_hash = resolved_event["event_hash"]
    content = "".join(
        json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
        for event in events
    ).encode("utf-8")
    path.write_bytes(content)
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _event_hash(event_without_hash):
    canonical = json.dumps(
        event_without_hash,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _completed_result(event_stream, events_hash, *, run_id="run.atomic.1"):
    return AgentRunResult(
        run_id=run_id,
        status=AgentRunStatus.COMPLETED,
        event_stream_ref=str(event_stream),
        events_hash=events_hash,
        tool_attempts=[{"tool_attempt_id": "tool.1", "action": "write_file"}],
        workspace_mutations=[
            {"path": "backend/app.py", "tool_attempt_id": "tool.1", "sha256": "sha256:" + "0" * 64}
        ],
        artifacts=[
            {
                "artifact_ref": f"artifact://{run_id}/results/step-0002.json",
                "path": "backend/app.py",
                "sha256": "sha256:" + "0" * 64,
            }
        ],
        summary="Updated backend/app.py",
    )


def test_atomic_result_validator_recomputes_event_stream_hash(tmp_path):
    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream)
    result = _completed_result(event_stream, events_hash)
    validator = AtomicAgentResultValidator(
        allowed_write_set=("backend",),
        declared_command_ids=("test-backend",),
        event_stream_root=tmp_path,
    )

    validated = validator.validate(result)

    assert validated.events_hash == events_hash
    assert len(validated.events) == 6


def test_atomic_result_validator_allows_directory_write_policy_with_trailing_slash(tmp_path):
    event_stream = tmp_path / "events.jsonl"
    _write_event_stream(event_stream, command_id="cmd.test", include_provider_turn=True)
    events = [json.loads(line) for line in event_stream.read_text(encoding="utf-8").splitlines()]
    previous_hash = None
    for event in events:
        payload = event.get("payload", {})
        if payload.get("path") == "backend/app.py":
            payload["path"] = "work/real-provider-output.txt"
        if payload.get("produced_paths") == ["backend/app.py"]:
            payload["produced_paths"] = ["work/real-provider-output.txt"]
        event["previous_event_hash"] = previous_hash
        event.pop("event_hash", None)
        event["event_hash"] = _event_hash(event)
        previous_hash = event["event_hash"]
    content = "".join(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n" for event in events).encode("utf-8")
    event_stream.write_bytes(content)
    events_hash = "sha256:" + hashlib.sha256(content).hexdigest()
    result = _completed_result(event_stream, events_hash).model_copy(
        update={
            "workspace_mutations": [
                {"path": "work/real-provider-output.txt", "tool_attempt_id": "tool.1", "sha256": "sha256:" + "0" * 64}
            ],
            "artifacts": [
                {
                    "artifact_ref": "artifact://run.atomic.1/results/step-0002.json",
                    "path": "work/real-provider-output.txt",
                    "sha256": "sha256:" + "0" * 64,
                }
            ],
        }
    )
    validator = AtomicAgentResultValidator(
        allowed_write_set=("work/",),
        declared_command_ids=("cmd.test",),
        event_stream_root=tmp_path,
    )

    validated = validator.validate(result)

    assert validated.evidence_summary["source_inventory_lineage"][0]["path"] == "work/real-provider-output.txt"


def test_atomic_result_validator_accepts_result_mutation_after_hash(tmp_path):
    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream, command_id="cmd.test", include_provider_turn=True)
    result = _completed_result(event_stream, events_hash).model_copy(
        update={
            "workspace_mutations": [
                {"path": "backend/app.py", "tool_attempt_id": "tool.1", "after_hash": "sha256:" + "0" * 64}
            ],
        }
    )
    validator = AtomicAgentResultValidator(
        allowed_write_set=("backend",),
        declared_command_ids=("cmd.test",),
        event_stream_root=tmp_path,
    )

    validated = validator.validate(result)

    assert validated.events_hash == events_hash


def test_atomic_result_validator_allows_extra_audit_artifacts(tmp_path):
    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream, command_id="cmd.test", include_provider_turn=True)
    result = _completed_result(event_stream, events_hash).model_copy(
        update={
            "artifacts": [
                *_completed_result(event_stream, events_hash).artifacts,
                {
                    "artifact_ref": "artifact://run.atomic.1/provider/turn_000001.txt",
                    "sha256": "sha256:" + "5" * 64,
                },
            ],
        }
    )
    validator = AtomicAgentResultValidator(
        allowed_write_set=("backend",),
        declared_command_ids=("cmd.test",),
        event_stream_root=tmp_path,
    )

    validated = validator.validate(result)

    assert len(validated.result.artifacts) == 2


def test_atomic_result_validator_rejects_event_stream_hash_mismatch(tmp_path):
    event_stream = tmp_path / "events.jsonl"
    _write_event_stream(event_stream)
    result = _completed_result(event_stream, "sha256:" + "f" * 64)
    validator = AtomicAgentResultValidator(
        allowed_write_set=("backend",),
        declared_command_ids=("test-backend",),
        event_stream_root=tmp_path,
    )

    try:
        validator.validate(result)
    except ValueError as exc:
        assert "events_hash does not match event stream content" in str(exc)
    else:
        raise AssertionError("expected event stream hash mismatch")


def test_atomic_result_validator_rejects_event_stream_previous_hash_mismatch(tmp_path):
    event_stream = tmp_path / "events.jsonl"
    _write_event_stream(event_stream)
    lines = event_stream.read_text(encoding="utf-8").splitlines()
    event = json.loads(lines[1])
    event["previous_event_hash"] = "sha256:" + "f" * 64
    event["event_hash"] = _event_hash(
        {key: value for key, value in event.items() if key != "event_hash"}
    )
    lines[1] = json.dumps(event, sort_keys=True, separators=(",", ":"))
    event_stream.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = _completed_result(
        event_stream,
        "sha256:" + hashlib.sha256(event_stream.read_bytes()).hexdigest(),
    )
    validator = AtomicAgentResultValidator(
        allowed_write_set=("backend",),
        declared_command_ids=("test-backend",),
        event_stream_root=tmp_path,
    )

    try:
        validator.validate(result)
    except ValueError as exc:
        assert "event_previous_hash_mismatch" in str(exc)
    else:
        raise AssertionError("expected event previous hash mismatch")


def test_atomic_result_validator_rejects_event_stream_outside_root(tmp_path):
    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream)
    result = _completed_result(event_stream, events_hash)
    validator = AtomicAgentResultValidator(
        allowed_write_set=("backend",),
        declared_command_ids=("test-backend",),
        event_stream_root=tmp_path / "other-root",
    )

    try:
        validator.validate(result)
    except ValueError as exc:
        assert "event_stream_ref is outside event_stream_root" in str(exc)
    else:
        raise AssertionError("expected event stream root boundary failure")


def test_atomic_result_validator_rejects_artifact_missing_sha256(tmp_path):
    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream)
    result = _completed_result(event_stream, events_hash).model_copy(
        update={"artifacts": [{"artifact_ref": "artifact://run.atomic.1/backend/app.py"}]}
    )
    validator = AtomicAgentResultValidator(
        allowed_write_set=("backend",),
        declared_command_ids=("test-backend",),
        event_stream_root=tmp_path,
    )

    try:
        validator.validate(result)
    except ValueError as exc:
        assert "artifact sha256 is required" in str(exc)
    else:
        raise AssertionError("expected artifact sha256 failure")


def test_atomic_result_validator_rejects_workspace_mutation_without_known_tool_attempt(tmp_path):
    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream)
    result = _completed_result(event_stream, events_hash).model_copy(
        update={
            "workspace_mutations": [
                {
                    "path": "backend/app.py",
                    "tool_attempt_id": "missing-tool",
                    "sha256": "sha256:" + "0" * 64,
                }
            ]
        }
    )
    validator = AtomicAgentResultValidator(
        allowed_write_set=("backend",),
        declared_command_ids=("test-backend",),
        event_stream_root=tmp_path,
    )

    try:
        validator.validate(result)
    except ValueError as exc:
        assert "workspace mutation tool_attempt_id is not present" in str(exc)
    else:
        raise AssertionError("expected workspace mutation tool attempt failure")


def test_atomic_result_validator_rejects_workspace_mutation_not_bound_to_event_stream(tmp_path):
    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream)
    result = _completed_result(event_stream, events_hash).model_copy(
        update={
            "workspace_mutations": [
                {
                    "path": "backend/other.py",
                    "tool_attempt_id": "tool.1",
                    "sha256": "sha256:" + "0" * 64,
                }
            ]
        }
    )
    validator = AtomicAgentResultValidator(
        allowed_write_set=("backend",),
        declared_command_ids=("test-backend",),
        event_stream_root=tmp_path,
    )

    try:
        validator.validate(result)
    except ValueError as exc:
        assert "workspace mutations must match event stream summary" in str(exc)
    else:
        raise AssertionError("expected workspace mutation event binding failure")


def test_atomic_result_validator_rejects_artifact_not_bound_to_event_stream(tmp_path):
    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream)
    result = _completed_result(event_stream, events_hash).model_copy(
        update={
            "artifacts": [
                {
                    "artifact_ref": "artifact://run.atomic.1/results/other.json",
                    "path": "backend/app.py",
                    "sha256": "sha256:" + "0" * 64,
                }
            ]
        }
    )
    validator = AtomicAgentResultValidator(
        allowed_write_set=("backend",),
        declared_command_ids=("test-backend",),
        event_stream_root=tmp_path,
    )

    try:
        validator.validate(result)
    except ValueError as exc:
        assert "artifacts must match event stream summary" in str(exc)
    else:
        raise AssertionError("expected artifact event binding failure")


def test_atomic_result_validator_rejects_run_id_mismatch_with_event_stream(tmp_path):
    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream)
    result = _completed_result(event_stream, events_hash).model_copy(
        update={"run_id": "run.atomic.other"}
    )
    validator = AtomicAgentResultValidator(
        allowed_write_set=("backend",),
        declared_command_ids=("test-backend",),
        event_stream_root=tmp_path,
    )

    try:
        validator.validate(result)
    except ValueError as exc:
        assert "event stream run_id must match result.run_id" in str(exc)
    else:
        raise AssertionError("expected event stream run_id binding failure")


def test_atomic_result_validator_rejects_undeclared_command_from_event_stream(tmp_path):
    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream, command_id="rm-all")
    result = _completed_result(event_stream, events_hash)
    validator = AtomicAgentResultValidator(
        allowed_write_set=("backend",),
        declared_command_ids=("test-backend",),
        event_stream_root=tmp_path,
    )

    try:
        validator.validate(result)
    except ValueError as exc:
        assert "command_id is not declared" in str(exc)
    else:
        raise AssertionError("expected event stream command policy failure")


def test_atomic_result_projector_builds_work_product_submission(tmp_path):
    from boardroom_os.execution.atomic_agent import AtomicResultProjector

    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream)
    result = _completed_result(event_stream, events_hash)
    execution_package = _execution_package()
    provider_attempt = ProviderAttempt(
        provider_attempt_id=ProviderAttemptRef(value="provider-attempt.atomic.run.atomic.1"),
        provider=execution_package.model_execution_profile.provider,
        model=execution_package.model_execution_profile.model,
        reasoning_effort=execution_package.model_execution_profile.reasoning_effort,
        input_package_ref=execution_package.execution_package_id.value,
        seat_ref=execution_package.seat_ref,
        role_prompt_hook_ref=execution_package.role_prompt_hook.hook_ref,
        role_prompt_hook_version=execution_package.role_prompt_hook.hook_version,
        role_prompt_hook_sha256=execution_package.role_prompt_hook.content_sha256,
        status=ProviderAttemptStatus.SUCCEEDED,
        outcome=ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
        started_at=datetime(2026, 6, 10, 0, 0, tzinfo=UTC),
        finished_at=datetime(2026, 6, 10, 0, 0, 1, tzinfo=UTC),
        raw_output_ref=ProviderArtifactRef(value="artifact://run.atomic.1/provider/raw.json"),
        parsed_output_ref=ProviderArtifactRef(value="artifact://run.atomic.1/provider/parsed.json"),
    )
    validator = AtomicAgentResultValidator(
        allowed_write_set=("backend",),
        declared_command_ids=("test-backend",),
        event_stream_root=tmp_path,
    )
    validated = validator.validate(result)

    projection = AtomicResultProjector().project(
        execution_package=execution_package,
        provider_attempt=provider_attempt,
        validated_result=validated,
    )

    assert projection.atomic_run_id == "run.atomic.1"
    assert projection.work_product_submission.work_product.execution_package_ref.value == (
        execution_package.execution_package_id.value
    )
    assert projection.work_product_submission.work_product.producer_attempt_ref == (
        provider_attempt.provider_attempt_id
    )
    assert "artifact://run.atomic.1/results/step-0002.json" in [
        ref.value for ref in projection.work_product_submission.work_product.artifact_refs
    ]
    assert projection.source_lineage_inputs[0]["path"] == "backend/app.py"
    assert projection.source_lineage_inputs[0]["producer_ticket_ref"] == (
        execution_package.ticket_ref.value
    )
    assert projection.source_lineage_inputs[0]["producer_attempt_ref"] == (
        provider_attempt.provider_attempt_id.value
    )


def test_atomic_result_projector_rejects_provider_attempt_package_mismatch(tmp_path):
    from boardroom_os.execution.atomic_agent import AtomicResultProjector

    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream)
    result = _completed_result(event_stream, events_hash)
    execution_package = _execution_package()
    provider_attempt = ProviderAttempt(
        provider_attempt_id=ProviderAttemptRef(value="provider-attempt.atomic.run.atomic.1"),
        provider=execution_package.model_execution_profile.provider,
        model=execution_package.model_execution_profile.model,
        reasoning_effort=execution_package.model_execution_profile.reasoning_effort,
        input_package_ref="exec.other",
        seat_ref=execution_package.seat_ref,
        role_prompt_hook_ref=execution_package.role_prompt_hook.hook_ref,
        role_prompt_hook_version=execution_package.role_prompt_hook.hook_version,
        role_prompt_hook_sha256=execution_package.role_prompt_hook.content_sha256,
        status=ProviderAttemptStatus.SUCCEEDED,
        outcome=ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
        started_at=datetime(2026, 6, 10, 0, 0, tzinfo=UTC),
        finished_at=datetime(2026, 6, 10, 0, 0, 1, tzinfo=UTC),
        raw_output_ref=ProviderArtifactRef(value="artifact://run.atomic.1/provider/raw.json"),
        parsed_output_ref=ProviderArtifactRef(value="artifact://run.atomic.1/provider/parsed.json"),
    )
    validator = AtomicAgentResultValidator(
        allowed_write_set=("backend",),
        declared_command_ids=("test-backend",),
        event_stream_root=tmp_path,
    )
    validated = validator.validate(result)

    try:
        AtomicResultProjector().project(
            execution_package=execution_package,
            provider_attempt=provider_attempt,
            validated_result=validated,
        )
    except ValueError as exc:
        assert "provider_attempt.input_package_ref must match" in str(exc)
    else:
        raise AssertionError("expected provider attempt package mismatch")


def test_atomic_result_projector_rejects_provider_attempt_model_mismatch(tmp_path):
    from boardroom_os.execution.atomic_agent import AtomicResultProjector

    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream)
    result = _completed_result(event_stream, events_hash)
    execution_package = _execution_package()
    provider_attempt = ProviderAttempt(
        provider_attempt_id=ProviderAttemptRef(value="provider-attempt.atomic.run.atomic.1"),
        provider=execution_package.model_execution_profile.provider,
        model="wrong-model",
        reasoning_effort=execution_package.model_execution_profile.reasoning_effort,
        input_package_ref=execution_package.execution_package_id.value,
        seat_ref=execution_package.seat_ref,
        role_prompt_hook_ref=execution_package.role_prompt_hook.hook_ref,
        role_prompt_hook_version=execution_package.role_prompt_hook.hook_version,
        role_prompt_hook_sha256=execution_package.role_prompt_hook.content_sha256,
        status=ProviderAttemptStatus.SUCCEEDED,
        outcome=ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
        started_at=datetime(2026, 6, 10, 0, 0, tzinfo=UTC),
        finished_at=datetime(2026, 6, 10, 0, 0, 1, tzinfo=UTC),
        raw_output_ref=ProviderArtifactRef(value="artifact://run.atomic.1/provider/raw.json"),
        parsed_output_ref=ProviderArtifactRef(value="artifact://run.atomic.1/provider/parsed.json"),
    )
    validator = AtomicAgentResultValidator(
        allowed_write_set=("backend",),
        declared_command_ids=("test-backend",),
        event_stream_root=tmp_path,
    )
    validated = validator.validate(result)

    try:
        AtomicResultProjector().project(
            execution_package=execution_package,
            provider_attempt=provider_attempt,
            validated_result=validated,
        )
    except ValueError as exc:
        assert "provider_attempt.model must match" in str(exc)
    else:
        raise AssertionError("expected provider attempt model mismatch")


def test_atomic_package_adapter_invokes_runtime_port(tmp_path):
    from boardroom_os.execution.atomic_agent import (
        AtomicAgentDependencyInfo,
        AtomicAgentPackageAdapter,
        AtomicInvocationCompiler,
    )

    event_stream = tmp_path / "events.jsonl"
    events_hash = _write_event_stream(event_stream)

    class FakeRuntimePort:
        def __init__(self):
            self.invocations = []

        def invoke(self, invocation):
            self.invocations.append(invocation)
            return _completed_result(event_stream, events_hash, run_id="run.atomic.fake")

    execution_package = _execution_package()
    runtime_port = FakeRuntimePort()
    adapter = AtomicAgentPackageAdapter(
        runtime_port=runtime_port,
        dependency_info=AtomicAgentDependencyInfo(
            package_name="atomic-agent",
            package_version="0.0.0",
            source_path=str(tmp_path),
            runtime_port_contract_ref="atomic-agent.docs.agent-runtime-port.v1",
        ),
    )
    invocation = AtomicInvocationCompiler(workspace_root=tmp_path).compile(execution_package)

    result = adapter.invoke(invocation)

    assert runtime_port.invocations == [invocation]
    assert result.run_id == "run.atomic.fake"
    assert adapter.dependency_info().package_name == "atomic-agent"
