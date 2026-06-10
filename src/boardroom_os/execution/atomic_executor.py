from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import time
from typing import Any

from boardroom_os.execution.atomic_agent import (
    AtomicAgentPackageAdapter,
    AtomicAgentResultValidator,
    AtomicInvocationCompiler,
    AtomicResultProjection,
    AtomicResultProjector,
    declared_command_ids_from_execution_package,
)
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.package import ExecutionPackage, ExecutionPackageRef
from boardroom_os.providers.attempt import (
    ProviderArtifactRef,
    ProviderAttempt,
    ProviderAttemptOutcome,
    ProviderAttemptStatus,
)


@dataclass(frozen=True)
class AtomicExecutionRequest:
    execution_package: ExecutionPackage
    settings: Any
    seat_ref: str
    workspace_root: Path
    event_stream_root: Path


@dataclass(frozen=True)
class AtomicExecutionResult:
    atomic_run_id: str
    provider_attempt: ProviderAttempt
    projection: AtomicResultProjection
    raw_result: Any


@dataclass(frozen=True)
class AtomicRetryDecision:
    allowed: bool
    reason: str

    @classmethod
    def can_retry(
        cls,
        *,
        failure_kind: str,
        attempt_index: int,
        max_retries: int,
        workspace_mutations: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    ) -> AtomicRetryDecision:
        if attempt_index >= max_retries:
            return cls(False, "max retries exhausted")
        if workspace_mutations:
            return cls(False, "retry is not allowed after workspace mutation")
        if failure_kind != "runtime_crash":
            return cls(False, f"failure kind is not retryable: {failure_kind}")
        return cls(True, "runtime crash retry allowed before workspace mutation")


class AtomicAgentExecutor:
    def __init__(self, *, runtime_port: Any | None, allow_fake_provider_for_unit_tests: bool = True) -> None:
        self.runtime_port = runtime_port
        self.allow_fake_provider_for_unit_tests = allow_fake_provider_for_unit_tests

    def execute(self, request: AtomicExecutionRequest, *, provider_transport_kind: str = "real") -> AtomicExecutionResult:
        if self.runtime_port is None:
            raise ValueError("AgentRuntimePort is required")
        if provider_transport_kind == "fake" and not self.allow_fake_provider_for_unit_tests:
            raise ValueError("fake provider transport cannot satisfy V2-090H")
        invocation = AtomicInvocationCompiler(workspace_root=request.workspace_root).compile_with_settings(
            execution_package=request.execution_package,
            settings=request.settings,
            seat_ref=request.seat_ref,
        )
        result = AtomicAgentPackageAdapter(runtime_port=self.runtime_port).invoke(invocation)
        _reject_summary_governance_markers(getattr(result, "summary", ""))
        _require_lf_event_stream(result.event_stream_ref, request.event_stream_root)
        validator = AtomicAgentResultValidator(
            allowed_write_set=tuple(path.value for path in request.execution_package.allowed_write_set),
            declared_command_ids=declared_command_ids_from_execution_package(request.execution_package),
            event_stream_root=request.event_stream_root,
        )
        validated = validator.validate(result)
        _require_provider_turn_facts(validated.evidence_summary)
        _require_command_evidence(validated.evidence_summary)
        provider_attempt = _provider_attempt_from_atomic_summary(
            request.execution_package,
            validated.evidence_summary,
        )
        projection = AtomicResultProjector().project(
            execution_package=request.execution_package,
            provider_attempt=provider_attempt,
            validated_result=validated,
        )
        return AtomicExecutionResult(
            atomic_run_id=result.run_id,
            provider_attempt=provider_attempt,
            projection=projection,
            raw_result=result,
        )


class AtomicAgentRuntimeFactory:
    def __init__(self, *, settings: Any) -> None:
        self.settings = settings

    def build_runtime_port(
        self,
        *,
        execution_package: ExecutionPackage,
        seat_ref: str,
        workspace_root: Path,
        run_id: str,
    ) -> Any:
        from atomic_agent.agent_loop import AgentLoop, AgentLoopConfig, AgentLoopDependencies
        from atomic_agent.artifacts import ArtifactWriter, ArtifactWriterConfig
        from atomic_agent.command_tools import CommandPolicy, CommandSpec, CommandToolConfig, CommandTools
        from atomic_agent.event_recorder import EventRecorder, EventRecorderConfig
        from atomic_agent.filesystem_tools import FilesystemToolConfig, FilesystemTools
        from atomic_agent.path_guard import WorkspacePathGuard
        from atomic_agent.providers.openai_compatible import OpenAICompatibleProviderAdapter
        from atomic_agent.runtime_port import BoardroomAgentRuntimePortAdapter
        from atomic_agent.web_fetch_tools import NetworkAllowRule, NetworkPolicy, WebFetchToolConfig, WebFetchTools

        role_slot = self.settings.role_slot_by_seat(seat_ref)
        provider_options = self.settings.openai_compatible_options(role_slot.provider_profile_ref)
        runtime = self.settings.runtime.atomic_agent
        workspace_root = workspace_root.resolve()
        workspace_root.mkdir(parents=True, exist_ok=True)
        self._ensure_command_cwds(workspace_root, execution_package)
        event_root = Path(runtime.event_stream_root).resolve()
        artifact_root = Path(runtime.artifact_root).resolve()
        event_root.mkdir(parents=True, exist_ok=True)
        artifact_root.mkdir(parents=True, exist_ok=True)
        guard = WorkspacePathGuard(
            workspace_root,
            [path.value for path in execution_package.allowed_write_set],
        )
        filesystem_tools = FilesystemTools(
            guard,
            FilesystemToolConfig(**runtime.filesystem.model_dump()),
        )
        command_policy = CommandPolicy(
            {
                command.command_id.value: CommandSpec(
                    argv=tuple(command.command),
                    cwd=None if command.cwd in {"", "."} else command.cwd,
                    timeout_seconds=None,
                    env=None,
                    allow_network=False,
                )
                for command in execution_package.commands
            }
        )
        command_tools = CommandTools(
            guard,
            command_policy,
            CommandToolConfig(**runtime.commands.model_dump()),
        )
        network_policy = NetworkPolicy(
            tuple(
                NetworkAllowRule(
                    rule.rule_id,
                    rule.scheme,
                    rule.host,
                    rule.port,
                    rule.path_prefix,
                )
                for rule in runtime.network.allow_rules
            )
        )
        web_fetch_tools = WebFetchTools(
            network_policy,
            WebFetchToolConfig(timeout_seconds=30, max_response_bytes=200000),
        )
        recorder = EventRecorder(
            run_id=run_id,
            config=EventRecorderConfig(
                event_stream_path=event_root / f"{run_id}.jsonl",
                event_stream_ref=f"{run_id}.jsonl",
            ),
            clock=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )
        artifact_writer = ArtifactWriter(
            ArtifactWriterConfig(
                artifact_root=artifact_root,
                artifact_ref_prefix=f"artifact://{run_id}",
            )
        )
        loop = AgentLoop(
            AgentLoopConfig(run_id=run_id),
            AgentLoopDependencies(
                provider=OpenAICompatibleProviderAdapter(provider_options),
                filesystem_tools=filesystem_tools,
                command_tools=command_tools,
                event_recorder=recorder,
                artifact_writer=artifact_writer,
                runtime_clock=time.monotonic,
                web_fetch_tools=web_fetch_tools,
            ),
        )
        return BoardroomAgentRuntimePortAdapter(loop)

    def _ensure_command_cwds(self, workspace_root: Path, execution_package: ExecutionPackage) -> None:
        for command in execution_package.commands:
            cwd = command.cwd
            if cwd in {"", "."}:
                continue
            target = workspace_root / cwd
            target.mkdir(parents=True, exist_ok=True)


def reject_provider_executor_for_implementation(provider_executor: Any, *, ticket_category: str) -> None:
    if ticket_category == "implementation" and provider_executor is not None:
        raise ValueError("ProviderExecutor cannot satisfy implementation ticket evidence")


def _reject_summary_governance_markers(summary: object) -> None:
    if isinstance(summary, str) and "ticket_completed" in summary.lower():
        raise ValueError("atomic-agent result must not contain governance field")


def _require_lf_event_stream(event_stream_ref: str, event_stream_root: Path) -> None:
    path = Path(event_stream_ref)
    resolved = path if path.is_absolute() else event_stream_root / path
    resolved = resolved.resolve()
    try:
        resolved.relative_to(event_stream_root.resolve())
    except ValueError as exc:
        raise ValueError("event_stream_ref is outside event_stream_root") from exc
    content = resolved.read_bytes()
    if b"\r\n" in content or b"\r" in content:
        raise ValueError("event stream must use LF line endings")


def _require_provider_turn_facts(evidence_summary: dict[str, Any]) -> None:
    if not evidence_summary.get("provider_attempts"):
        raise ValueError("provider turn facts are required")


def _require_command_evidence(evidence_summary: dict[str, Any]) -> None:
    if not evidence_summary.get("command_results"):
        raise ValueError("command evidence is required")


def _provider_attempt_from_atomic_summary(
    execution_package: ExecutionPackage,
    evidence_summary: dict[str, Any],
) -> ProviderAttempt:
    provider_turns = evidence_summary.get("provider_attempts") or []
    provider_turn = provider_turns[0]
    output = provider_turn.get("output", {})
    artifact_ref = output.get("artifact_ref")
    if not isinstance(artifact_ref, str) or not artifact_ref:
        raise ValueError("provider turn output artifact_ref is required")
    now = datetime.now(UTC)
    profile = execution_package.model_execution_profile
    safe_ref = artifact_ref.replace("artifact://", "artifact.atomic.").replace("/", ".")
    return ProviderAttempt(
        provider_attempt_id=ProviderAttemptRef(value=f"provider-attempt.atomic.{evidence_summary['run_id']}.{provider_turn['provider_turn_id']}"),
        provider=profile.provider,
        model=profile.model,
        reasoning_effort=profile.reasoning_effort,
        input_package_ref=ExecutionPackageRef(value=execution_package.execution_package_id.value),
        seat_ref=execution_package.seat_ref,
        role_prompt_hook_ref=execution_package.role_prompt_hook.hook_ref,
        role_prompt_hook_version=execution_package.role_prompt_hook.hook_version,
        role_prompt_hook_sha256=execution_package.role_prompt_hook.content_sha256,
        status=ProviderAttemptStatus.SUCCEEDED,
        outcome=ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
        started_at=now,
        finished_at=now,
        raw_output_ref=ProviderArtifactRef(value=f"provider-artifact.atomic.raw.{safe_ref}"),
        parsed_output_ref=ProviderArtifactRef(value=f"provider-artifact.atomic.parsed.{safe_ref}"),
    )
