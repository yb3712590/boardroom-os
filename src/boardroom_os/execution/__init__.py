"""Execution package and runtime input snapshot models."""

from boardroom_os.execution.compiler import (
    ExecutionPackageCompiler,
    ExecutionPackageCompilerError,
    ExecutionPackageCompilerInput,
    ExecutionWorkspaceContext,
    VerificationExecutionContext,
)
from boardroom_os.execution.context_index import (
    AgentContextIndex,
    AgentContextIndexEntry,
    AgentContextIndexEntryId,
    AgentContextSnapshot,
    AgentContextSnapshotId,
    ProviderAttemptRef,
    build_agent_context_snapshot,
)
from boardroom_os.execution.fallback import (
    EvidencePurpose,
    FallbackEvidenceDecision,
    FallbackEvidenceRequest,
    FallbackKind,
    FallbackPolicy,
    evaluate_fallback_evidence,
)
from boardroom_os.execution.package import (
    AllowedReadRef,
    AllowedWritePath,
    AuditRequirement,
    ContextRef,
    ExecutionPackage,
    ExecutionPackageId,
    ExecutionPackageRef,
    FallbackPolicyRef,
    RequiredOutput,
)
from boardroom_os.execution.atomic_agent import (
    AtomicAgentAdapterError,
    AtomicAgentDependencyInfo,
    AtomicAgentPackageAdapter,
    AtomicAgentPort,
    AtomicAgentResultValidator,
    AtomicAgentValidatedResult,
    AtomicInvocationCompiler,
    AtomicResultProjection,
    AtomicResultProjector,
)
from boardroom_os.execution.atomic_executor import (
    AtomicAgentExecutor,
    AtomicExecutionRequest,
    AtomicExecutionResult,
    reject_provider_executor_for_implementation,
)
from boardroom_os.execution.verification_run import (
    CommandOutputRef,
    EnvironmentProfileRef,
    RunnerRef,
    VerificationRun,
    VerificationRunRef,
    VerificationRunStatus,
    WorkspaceSnapshotRef,
    status_from_exit_code,
    stderr_ref_for,
    stdout_ref_for,
)

_PROVIDER_EXECUTOR_EXPORTS = {
    "ProviderExecutor",
    "ProviderExecutorError",
    "ProviderExecutorInput",
    "ProviderExecutorResult",
    "render_prompt_from_snapshot",
}

_RUNTIME_EXECUTOR_EXPORTS = {
    "RuntimeEventBoundary",
    "RuntimeEventSequencer",
    "RuntimeExecutionInput",
    "RuntimeExecutionResult",
    "RuntimeExecutor",
    "RuntimeExecutorError",
    "build_command_run_recorded_event",
    "build_execution_started_event",
    "build_provider_attempt_recorded_event",
}


def __getattr__(name: str) -> object:
    if name in _PROVIDER_EXECUTOR_EXPORTS:
        from boardroom_os.execution import provider_executor

        return getattr(provider_executor, name)
    if name in _RUNTIME_EXECUTOR_EXPORTS:
        from boardroom_os.execution import runtime_executor

        return getattr(runtime_executor, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AgentContextIndex",
    "AgentContextIndexEntry",
    "AgentContextIndexEntryId",
    "AgentContextSnapshot",
    "AgentContextSnapshotId",
    "AllowedReadRef",
    "AllowedWritePath",
    "AtomicAgentAdapterError",
    "AtomicAgentDependencyInfo",
    "AtomicAgentExecutor",
    "AtomicAgentPackageAdapter",
    "AtomicAgentPort",
    "AtomicAgentResultValidator",
    "AtomicAgentValidatedResult",
    "AtomicInvocationCompiler",
    "AtomicResultProjection",
    "AtomicResultProjector",
    "AtomicExecutionRequest",
    "AtomicExecutionResult",
    "AuditRequirement",
    "ContextRef",
    "EvidencePurpose",
    "ExecutionPackage",
    "ExecutionPackageCompiler",
    "ExecutionPackageCompilerError",
    "ExecutionPackageCompilerInput",
    "ExecutionPackageId",
    "ExecutionPackageRef",
    "ExecutionWorkspaceContext",
    "VerificationExecutionContext",
    "FallbackEvidenceDecision",
    "FallbackEvidenceRequest",
    "FallbackKind",
    "FallbackPolicy",
    "FallbackPolicyRef",
    "ProviderAttemptRef",
    "ProviderExecutor",
    "ProviderExecutorError",
    "ProviderExecutorInput",
    "ProviderExecutorResult",
    "RequiredOutput",
    "RuntimeEventBoundary",
    "RuntimeEventSequencer",
    "RuntimeExecutionInput",
    "RuntimeExecutionResult",
    "RuntimeExecutor",
    "RuntimeExecutorError",
    "CommandOutputRef",
    "EnvironmentProfileRef",
    "RunnerRef",
    "VerificationRun",
    "VerificationRunRef",
    "VerificationRunStatus",
    "WorkspaceSnapshotRef",
    "status_from_exit_code",
    "stderr_ref_for",
    "stdout_ref_for",
    "build_agent_context_snapshot",
    "build_command_run_recorded_event",
    "build_execution_started_event",
    "build_provider_attempt_recorded_event",
    "evaluate_fallback_evidence",
    "render_prompt_from_snapshot",
    "reject_provider_executor_for_implementation",
]
