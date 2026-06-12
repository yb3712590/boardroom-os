from __future__ import annotations

from dataclasses import dataclass
import hashlib
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path, PurePosixPath
import re
from types import ModuleType
from typing import Any, Callable, Protocol

from boardroom_os.execution.package import ExecutionPackage, ExecutionPackageRef
from boardroom_os.execution.work_product import (
    WorkProduct,
    WorkProductArtifactRef,
    WorkProductClaimDraft,
    WorkProductClaimDraftRef,
    WorkProductRef,
    WorkProductSubmission,
)
from boardroom_os.providers.attempt import ProviderAttempt
from boardroom_os.providers.attempt import ProviderAttemptOutcome, ProviderAttemptStatus


class AtomicAgentAdapterError(RuntimeError):
    pass


@dataclass(frozen=True)
class AtomicAgentDependencyInfo:
    package_name: str
    package_version: str
    source_path: str | None
    runtime_port_contract_ref: str


class AtomicAgentPort(Protocol):
    def invoke(self, invocation: Any) -> Any:
        ...


def _default_import_atomic_agent(name: str) -> ModuleType:
    return import_module(name)


class AtomicAgentPackageAdapter:
    def __init__(
        self,
        *,
        runtime_port: AtomicAgentPort | None = None,
        dependency_info: AtomicAgentDependencyInfo | None = None,
        import_atomic_agent: Callable[[str], ModuleType] = _default_import_atomic_agent,
    ) -> None:
        self._runtime_port = runtime_port
        self._dependency_info = dependency_info
        self._import_atomic_agent = import_atomic_agent

    def dependency_info(self) -> AtomicAgentDependencyInfo:
        if self._dependency_info is not None:
            return self._dependency_info
        try:
            module = self._import_atomic_agent("atomic_agent")
        except ImportError as exc:
            raise AtomicAgentAdapterError("atomic-agent package is not importable") from exc
        try:
            package_version = version("atomic-agent")
        except PackageNotFoundError as exc:
            package_version = getattr(module, "__version__", None)
            if (
                not isinstance(package_version, str)
                or not package_version.strip()
                or package_version.strip().lower() == "unknown"
            ):
                raise AtomicAgentAdapterError(
                    "atomic-agent package version is not auditable"
                ) from exc
        module_file = getattr(module, "__file__", None)
        source_path = str(Path(module_file).resolve().parents[1]) if module_file else None
        return AtomicAgentDependencyInfo(
            package_name="atomic-agent",
            package_version=package_version,
            source_path=source_path,
            runtime_port_contract_ref="atomic-agent.docs.agent-runtime-port.v1",
        )

    def invoke(self, invocation: Any) -> Any:
        runtime_port = self._runtime_port
        if runtime_port is None:
            raise AtomicAgentAdapterError("atomic-agent runtime_port is required")
        result = runtime_port.invoke(invocation)
        try:
            agent_models = import_module("atomic_agent.models")
        except ImportError as exc:
            raise AtomicAgentAdapterError("atomic-agent package is not importable") from exc
        AgentRunResult = getattr(agent_models, "AgentRunResult")
        if not isinstance(result, AgentRunResult):
            raise AtomicAgentAdapterError("AgentRuntimePort returned non-AgentRunResult")
        return result


class AtomicInvocationCompiler:
    def __init__(
        self,
        *,
        workspace_root: str | Path,
        enabled_tools: tuple[str, ...] = (
            "list_files",
            "read_file",
            "search_files",
            "write_file",
            "apply_patch",
            "run_command",
            "submit_result",
        ),
        max_steps: int = 20,
        wall_time_seconds: int = 600,
    ) -> None:
        self.workspace_root = Path(workspace_root)
        self.enabled_tools = enabled_tools
        self.max_steps = max_steps
        self.wall_time_seconds = wall_time_seconds

    def compile(self, execution_package: ExecutionPackage) -> Any:
        return self._compile(
            execution_package,
            requires_workspace_mutation=True,
        )

    def _compile(
        self,
        execution_package: ExecutionPackage,
        *,
        requires_workspace_mutation: bool,
    ) -> Any:
        try:
            agent_models = import_module("atomic_agent.models")
        except ImportError as exc:
            raise AtomicAgentAdapterError("atomic-agent package is not importable") from exc
        agent_invocation = getattr(agent_models, "AgentInvocation")
        allowed_write_set = _validate_relative_paths(
            tuple(_ref_value(path) for path in execution_package.allowed_write_set),
            error_message="allowed_write_set must contain relative paths",
            allow_empty=not requires_workspace_mutation,
        )
        evidence_obligations = [
            obligation.model_dump(mode="json")
            for obligation in execution_package.evidence_obligations
        ]
        permission_commands = [
            {
                "command_id": command.command_id.value,
                "label": command.label,
                "argv": list(command.command),
                "cwd": _validate_relative_paths(
                    (command.cwd,),
                    error_message="command cwd must contain relative paths",
                )[0],
            }
            for command in execution_package.commands
        ]
        task = "\n".join(
            (
                execution_package.objective,
                "",
                "Constraints:",
                *[f"- {constraint}" for constraint in execution_package.constraints],
                "",
                "Required outputs:",
                *[f"- {output.value}" for output in execution_package.required_outputs],
                "",
                "Evidence obligations:",
                *[
                    "- "
                    + json.dumps(obligation, sort_keys=True, separators=(",", ":"))
                    for obligation in evidence_obligations
                ],
            )
        )
        hook = execution_package.role_prompt_hook
        role_context = "\n".join(
            (
                f"RolePromptHook ref: {hook.hook_ref.value}",
                f"RolePromptHook version: {hook.hook_version}",
                f"RolePromptHook sha256: {hook.content_sha256.value}",
                "",
                hook.prompt_text,
            )
        )
        return agent_invocation(
            invocation_id=(
                f"atomic-invocation.{execution_package.execution_package_id.value}"
            ),
            task=task,
            workspace_root=str(self.workspace_root),
            allowed_write_set=list(allowed_write_set),
            tools=list(self.enabled_tools),
            permission_policy={
                "commands": permission_commands,
                "network": {"default": "deny"},
                "filesystem": {"allowed_write_set": list(allowed_write_set)},
            },
            provider_profile={
                "provider": execution_package.model_execution_profile.provider,
                "model": execution_package.model_execution_profile.model,
                "reasoning_effort": execution_package.model_execution_profile.reasoning_effort,
                "temperature": execution_package.model_execution_profile.temperature,
                "context_window": execution_package.model_execution_profile.context_window,
            },
            budgets={
                "max_steps": self.max_steps,
                "wall_time_seconds": self.wall_time_seconds,
            },
            output_requirements={
                "require_event_stream": True,
                "require_tool_attempts": True,
                "require_workspace_mutations": requires_workspace_mutation,
                "require_artifacts": True,
                "evidence_obligations": evidence_obligations,
            },
            role_context=role_context,
            skill_context={
                "audit_requirements": [
                    item.value for item in execution_package.audit_requirements
                ]
            },
            initial_files=[ref.value for ref in execution_package.context_refs],
            metadata={
                "execution_package_ref": execution_package.execution_package_id.value,
                "ticket_ref": execution_package.ticket_ref.value,
                "seat_ref": execution_package.seat_ref.value,
                "graph_version": execution_package.graph_version,
                "acceptance_refs": [
                    ref.value for ref in execution_package.acceptance_refs
                ],
                "source_surface_refs": [
                    ref.value for ref in execution_package.source_surface_refs
                ],
            },
        )

    def compile_with_settings(
        self,
        *,
        execution_package: ExecutionPackage,
        settings: Any,
        seat_ref: str,
    ) -> Any:
        role_slot = settings.role_slot_by_seat(seat_ref)
        if role_slot.seat_ref != execution_package.seat_ref.value:
            raise ValueError("role slot seat_ref must match execution_package.seat_ref")
        provider_config = settings.provider_by_id(role_slot.provider_profile_ref)
        profile = execution_package.model_execution_profile
        if (
            profile.provider != "openai-compatible"
            or profile.model != provider_config.model
            or profile.reasoning_effort != (provider_config.reasoning_effort or profile.reasoning_effort)
            or profile.context_window != provider_config.context_window_tokens
        ):
            raise ValueError("provider profile does not match execution package")
        provider_options = settings.openai_compatible_options(provider_config.provider_profile_id)
        role_category = role_slot.role_category
        role_execution_kind = _role_execution_kind(role_category)
        requires_workspace_mutation = role_category == "worker"
        requires_command_evidence = role_category == "worker" or bool(execution_package.commands)
        requires_source_lineage = role_category == "worker"
        allowed_write_set = _validate_relative_paths(
            tuple(_ref_value(path) for path in execution_package.allowed_write_set),
            error_message="allowed_write_set must contain relative paths",
            allow_empty=not requires_workspace_mutation,
        )
        tools = AtomicToolPolicyResolver().resolve_tools(
            runtime_tools=tuple(settings.runtime.atomic_agent.default_tools),
            role_tools=tuple(role_slot.default_tools),
            tool_permissions=tuple(execution_package.model_execution_profile.tool_permissions),
            skill_refs=tuple(role_slot.skill_refs),
            requires_command_evidence=requires_command_evidence,
            requires_workspace_mutation=requires_workspace_mutation,
            allow_apply_patch=settings.runtime.atomic_agent.filesystem.allow_apply_patch,
        )
        resolved_budget = settings.budgets_for_seat(role_slot.seat_ref)
        base_invocation = self._compile(
            execution_package,
            requires_workspace_mutation=requires_workspace_mutation,
        )
        budget_payload = {
            key: resolved_budget[key]
            for key in (
                "max_steps",
                "max_parse_failures",
                "max_observation_chars",
                "max_wall_seconds",
                "max_actions_per_turn",
            )
        }
        checkpoint = None
        checkpoint_policy = "manual-declared-commands-v1"
        if execution_package.required_outputs and len(execution_package.commands) == 1:
            checkpoint = {
                "when_all_paths_exist": [output.value for output in execution_package.required_outputs],
                "run_command_id": execution_package.commands[0].command_id.value,
                "max_auto_runs": settings.runtime.atomic_agent.checkpoints.required_output.max_auto_runs,
            }
            checkpoint_policy = "required-output-single-command-v1"
        output_requirements = {
            **base_invocation.output_requirements,
            "require_command_evidence": requires_command_evidence,
            "require_source_lineage": requires_source_lineage,
            "declared_command_ids": list(declared_command_ids_from_execution_package(execution_package)),
            "required_output_checkpoint": checkpoint,
        }
        metadata = {
            **base_invocation.metadata,
            "action_protocol": "agent-action-batch-v1",
            "action_protocol_version": "agent-action-batch-v1",
            "checkpoint_policy": checkpoint_policy,
            "provider_profile_ref": provider_config.provider_profile_id,
            "role_slot_ref": role_slot.seat_ref,
            "role_profile_ref": role_slot.role_profile_ref,
            "role_category": role_category,
            "role_execution_kind": role_execution_kind,
            "budget_profile_ref": resolved_budget["budget_profile_ref"],
            "resolved_budget_hash": stable_hash(resolved_budget),
            "resolved_tool_policy_hash": stable_hash({"tools": tools}),
            "runtime_config_hash": settings.config_hashes.runtime_config_hash,
            "providers_config_hash": settings.config_hashes.providers_config_hash,
            "roles_config_hash": settings.config_hashes.roles_config_hash,
            "event_stream_format": "jsonl-utf8-lf-canonical-json-v1",
            "execution_policy": settings.runtime.atomic_agent.execution_policy.model_dump(mode="json"),
        }
        return base_invocation.model_copy(
            update={
                "tools": list(tools),
                "permission_policy": {
                    "policy_ref": f"policy://boardroom/atomic-agent/{execution_package.execution_package_id.value}",
                    "commands": [
                        {
                            "command_id": command.command_id.value,
                            "label": command.label,
                            "argv": list(command.command),
                            "cwd": _validate_relative_paths(
                                (command.cwd,),
                                error_message="command cwd must contain relative paths",
                            )[0],
                        }
                        for command in execution_package.commands
                    ],
                    "network": settings.runtime.atomic_agent.network.model_dump(mode="json"),
                    "filesystem": {"allowed_write_set": list(allowed_write_set)},
                },
                "provider_profile": provider_options.to_provider_profile(),
                "budgets": budget_payload,
                "output_requirements": output_requirements,
                "skill_context": {
                    "skill_refs": list(role_slot.skill_refs),
                    "audit_requirements": [item.value for item in execution_package.audit_requirements],
                },
                "metadata": metadata,
            }
        )


class AtomicToolPolicyResolver:
    def resolve_tools(
        self,
        *,
        runtime_tools: tuple[str, ...],
        role_tools: tuple[str, ...],
        tool_permissions: tuple[str, ...],
        skill_refs: tuple[str, ...],
        requires_command_evidence: bool,
        requires_workspace_mutation: bool,
        allow_apply_patch: bool = True,
    ) -> tuple[str, ...]:
        allowed = [tool for tool in role_tools if tool in set(runtime_tools)]
        if requires_command_evidence and "run_command" not in allowed:
            raise ValueError("resolved tools must include run_command for command evidence")
        if requires_workspace_mutation and not {"write_file", "apply_patch"}.intersection(allowed):
            raise ValueError("resolved tools must include write_file or apply_patch for workspace mutation")
        if "submit_result" not in allowed:
            raise ValueError("resolved tools must include submit_result")
        permission_tools: set[str] = {"submit_result"}
        if "filesystem.read" in tool_permissions:
            permission_tools.update({"list_files", "read_file", "search_files"})
        if "filesystem.write" in tool_permissions or any(ref == "skill.filesystem.patch" for ref in skill_refs):
            permission_tools.update({"write_file", "apply_patch"})
        if "command.execute" in tool_permissions or any(ref == "skill.command.test" for ref in skill_refs):
            permission_tools.add("run_command")
        resolved = tuple(tool for tool in allowed if tool in permission_tools)
        if requires_command_evidence and "run_command" not in resolved:
            raise ValueError("resolved tools must include run_command for command evidence")
        if requires_workspace_mutation and not {"write_file", "apply_patch"}.intersection(resolved):
            raise ValueError("resolved tools must include write_file or apply_patch for workspace mutation")
        if "submit_result" not in resolved:
            raise ValueError("resolved tools must include submit_result")
        if "apply_patch" in resolved and not allow_apply_patch:
            raise ValueError("apply_patch tool is visible but not supported by runtime policy")
        return resolved


_GOVERNANCE_FORBIDDEN_KEYS = {
    "ticket_completed",
    "closeout_committed",
    "governance_status",
    "evidence_verified",
    "source_inventory_accepted",
}
_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class AtomicAgentValidatedResult:
    result: Any
    events: tuple[dict[str, Any], ...]
    events_hash: str
    evidence_summary: dict[str, Any]


class AtomicAgentResultValidator:
    def __init__(
        self,
        *,
        allowed_write_set: tuple[str, ...],
        declared_command_ids: tuple[str, ...],
        event_stream_root: str | Path | None = None,
        require_workspace_mutation: bool = True,
    ) -> None:
        self.allowed_write_set = _validate_relative_paths(
            allowed_write_set,
            error_message="allowed_write_set must contain relative paths",
        )
        self.declared_command_ids = set(declared_command_ids)
        if event_stream_root is None:
            raise ValueError("event_stream_root is required")
        self.event_stream_root = Path(event_stream_root).resolve()
        self.require_workspace_mutation = require_workspace_mutation

    def validate(self, result: Any) -> AtomicAgentValidatedResult:
        status = getattr(result, "status", None)
        if getattr(status, "value", status) != "completed":
            raise ValueError("atomic-agent result must be completed")
        self._reject_governance_fields(result)
        if not getattr(result, "event_stream_ref", None):
            raise ValueError("event_stream_ref is required")
        if not getattr(result, "events_hash", None):
            raise ValueError("events_hash is required")
        if not getattr(result, "tool_attempts", None):
            raise ValueError("tool_attempts are required")
        if not getattr(result, "artifacts", None):
            raise ValueError("artifacts are required")
        workspace_mutations = getattr(result, "workspace_mutations", None)
        if self.require_workspace_mutation and not workspace_mutations:
            raise ValueError("workspace mutation is required")
        self._validate_tool_attempt_commands(tuple(getattr(result, "tool_attempts", ())))
        self._validate_workspace_mutations(tuple(workspace_mutations or ()))
        self._validate_artifacts(tuple(getattr(result, "artifacts", ())))
        event_stream_path = self._resolve_event_stream_path(result.event_stream_ref)
        events, evidence_summary = self._read_events_and_summary(
            event_stream_path,
            result,
        )
        self._validate_result_matches_event_summary(result, evidence_summary)
        return AtomicAgentValidatedResult(
            result=result,
            events=events,
            events_hash=result.events_hash,
            evidence_summary=evidence_summary,
        )

    def _reject_governance_fields(self, value: Any) -> None:
        if isinstance(value, dict):
            if _GOVERNANCE_FORBIDDEN_KEYS.intersection(value):
                raise ValueError("atomic-agent result must not contain governance field")
            for nested in value.values():
                self._reject_governance_fields(nested)
            return
        if isinstance(value, (list, tuple)):
            for nested in value:
                self._reject_governance_fields(nested)
            return
        if hasattr(value, "model_dump"):
            self._reject_governance_fields(value.model_dump(mode="json"))

    def _validate_workspace_mutations(
        self,
        mutations: tuple[dict[str, Any], ...],
    ) -> None:
        known_tool_attempt_ids = {
            attempt.get("tool_attempt_id")
            for attempt in getattr(self, "_current_tool_attempts", ())
            if isinstance(attempt, dict)
        }
        for mutation in mutations:
            path = mutation.get("path")
            if not isinstance(path, str) or not path:
                raise ValueError("workspace mutation path is required")
            _validate_relative_paths(
                (path,),
                error_message="workspace mutation path is outside allowed_write_set",
            )
            if not _path_is_in_allowed_write_set(path, self.allowed_write_set):
                raise ValueError("workspace mutation path is outside allowed_write_set")
            mutation_hash = _mutation_after_hash(mutation)
            if not _is_sha256(mutation_hash):
                raise ValueError("workspace mutation sha256 is required")
            tool_attempt_id = mutation.get("tool_attempt_id")
            if not isinstance(tool_attempt_id, str) or not tool_attempt_id:
                raise ValueError("workspace mutation tool_attempt_id is required")
            if known_tool_attempt_ids and tool_attempt_id not in known_tool_attempt_ids:
                raise ValueError("workspace mutation tool_attempt_id is not present in tool_attempts")

    def _validate_tool_attempt_commands(
        self,
        tool_attempts: tuple[dict[str, Any], ...],
    ) -> None:
        self._current_tool_attempts = tool_attempts
        for attempt in tool_attempts:
            if attempt.get("action") != "run_command":
                continue
            if attempt.get("command_id") not in self.declared_command_ids:
                raise ValueError("command_id is not declared")

    def _validate_artifacts(self, artifacts: tuple[dict[str, Any], ...]) -> None:
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                raise ValueError("artifact must be a dict")
            if not artifact.get("artifact_ref"):
                raise ValueError("artifact_ref is required")
            if not _is_sha256(artifact.get("sha256")):
                raise ValueError("artifact sha256 is required")
            path = artifact.get("path")
            if path is None:
                continue
            if not isinstance(path, str) or not path:
                raise ValueError("artifact path must be non-empty when provided")
            _validate_relative_paths(
                (path,),
                error_message="artifact path is outside allowed_write_set",
            )
            if not _path_is_in_allowed_write_set(path, self.allowed_write_set):
                raise ValueError("artifact path is outside allowed_write_set")

    def _resolve_event_stream_path(self, event_stream_ref: str) -> Path:
        path = Path(event_stream_ref)
        resolved = path if path.is_absolute() else self.event_stream_root / path
        resolved = resolved.resolve()
        try:
            resolved.relative_to(self.event_stream_root)
        except ValueError as exc:
            raise ValueError("event_stream_ref is outside event_stream_root") from exc
        return resolved

    def _read_events_and_summary(
        self,
        event_stream_path: Path,
        result: Any,
    ) -> tuple[tuple[dict[str, Any], ...], dict[str, Any]]:
        try:
            atomic_evidence = import_module("atomic_agent.evidence")
        except ImportError as exc:
            raise AtomicAgentAdapterError("atomic-agent package is not importable") from exc
        integrity = atomic_evidence.verify_event_stream(
            event_stream_path,
            expected_events_hash=result.events_hash,
        )
        if not integrity["ok"]:
            failure_kind = integrity.get("failure_kind", "event_stream_invalid")
            message = integrity.get("message", "event stream is invalid")
            if failure_kind == "events_hash_mismatch":
                raise ValueError("events_hash does not match event stream content")
            raise ValueError(f"{failure_kind}: {message}")
        content = event_stream_path.read_bytes()
        events = tuple(
            json.loads(line)
            for line in content.decode("utf-8").splitlines()
            if line.strip()
        )
        if events[0].get("type") != "run.started":
            raise ValueError("event stream must start with run.started")
        if events[-1].get("type") != "run.completed":
            raise ValueError("completed atomic-agent result must end with run.completed")
        if any(event.get("run_id") != result.run_id for event in events):
            raise ValueError("event stream run_id must match result.run_id")
        self._reject_governance_fields(events)
        try:
            evidence_summary = atomic_evidence.build_evidence_summary(result, event_stream_path)
        except Exception as exc:
            raise ValueError(f"event stream evidence summary is invalid: {exc}") from exc
        evidence_summary = dict(evidence_summary)
        evidence_summary["_events"] = list(events)
        self._reject_governance_fields(evidence_summary)
        return events, evidence_summary

    def _validate_result_matches_event_summary(
        self,
        result: Any,
        evidence_summary: dict[str, Any],
    ) -> None:
        event_mutations = {
            (mutation["path"], mutation["tool_attempt_id"], mutation["after_hash"])
            for mutation in evidence_summary.get("workspace_mutations", ())
            if isinstance(mutation, dict)
        }
        result_mutations = {
            (mutation["path"], mutation["tool_attempt_id"], _mutation_after_hash(mutation))
            for mutation in result.workspace_mutations
        }
        if result_mutations != event_mutations:
            raise ValueError("workspace mutations must match event stream summary")

        latest_lineage_mutations = {
            (
                mutation["path"],
                mutation["tool_attempt_id"],
                mutation["latest_after_hash"] if "latest_after_hash" in mutation else mutation.get("after_hash"),
            )
            for mutation in _summary_workspace_mutations(evidence_summary)
        }
        if not latest_lineage_mutations.issubset(result_mutations):
            raise ValueError("workspace mutations must match event stream summary")

        summary_artifact_refs = _submitted_artifact_refs(evidence_summary)
        result_artifact_refs = {
            artifact["artifact_ref"]
            for artifact in result.artifacts
            if isinstance(artifact, dict)
        }
        if not summary_artifact_refs.issubset(result_artifact_refs):
            raise ValueError("artifacts must match event stream summary")

        latest_command_results: dict[str, dict[str, Any]] = {}
        for command_result in evidence_summary.get("command_results", ()):
            command_id = command_result.get("command_id") if isinstance(command_result, dict) else None
            if command_id not in self.declared_command_ids:
                raise ValueError("command_id is not declared")
            latest_command_results[command_id] = command_result
        for command_id, command_result in latest_command_results.items():
            if command_result.get("exit_code") != 0:
                raise ValueError("declared command evidence must have exit_code 0")
        missing_commands = self.declared_command_ids - set(latest_command_results)
        if missing_commands:
            raise ValueError("command evidence is required")


@dataclass(frozen=True)
class AtomicResultProjection:
    atomic_run_id: str
    work_product_submission: WorkProductSubmission
    source_lineage_inputs: tuple[dict[str, Any], ...]
    event_stream_ref: str
    events_hash: str


class AtomicResultProjector:
    def project(
        self,
        *,
        execution_package: ExecutionPackage,
        provider_attempt: ProviderAttempt,
        validated_result: AtomicAgentValidatedResult,
    ) -> AtomicResultProjection:
        _validate_provider_attempt_binding(
            execution_package=execution_package,
            provider_attempt=provider_attempt,
        )
        result = validated_result.result
        artifact_refs = tuple(
            WorkProductArtifactRef(value=artifact["artifact_ref"])
            for artifact in result.artifacts
            if isinstance(artifact, dict) and artifact.get("artifact_ref")
        )
        if not artifact_refs:
            raise ValueError("atomic-agent artifacts are required for work product")

        execution_package_ref = ExecutionPackageRef(
            value=execution_package.execution_package_id.value
        )
        claim_draft_ref = WorkProductClaimDraftRef(
            value=f"claim-draft.atomic.{provider_attempt.provider_attempt_id.value}"
        )
        claim_draft = WorkProductClaimDraft(
            claim_draft_ref=claim_draft_ref,
            producer_attempt_ref=provider_attempt.provider_attempt_id,
            execution_package_ref=execution_package_ref,
            ticket_ref=execution_package.ticket_ref,
            acceptance_refs=execution_package.acceptance_refs,
            source_surface_refs=execution_package.source_surface_refs,
            artifact_refs=artifact_refs,
            summary=result.summary,
        )
        work_product = WorkProduct(
            work_product_id=WorkProductRef(
                value=f"work-product.atomic.{provider_attempt.provider_attempt_id.value}"
            ),
            execution_package_ref=execution_package_ref,
            ticket_ref=execution_package.ticket_ref,
            producer_attempt_ref=provider_attempt.provider_attempt_id,
            artifact_refs=artifact_refs,
            claim_refs=(claim_draft_ref,),
            summary=result.summary,
        )
        source_lineage_inputs = tuple(
            {
                "path": lineage["path"],
                "sha256": lineage["latest_after_hash"],
                "producer_ticket_ref": execution_package.ticket_ref.value,
                "producer_attempt_ref": provider_attempt.provider_attempt_id.value,
                "atomic_run_id": result.run_id,
                "tool_attempt_id": lineage["mutation_refs"][-1]["tool_attempt_id"],
                "acceptance_refs": [
                    ref.value for ref in execution_package.acceptance_refs
                ],
                "source_surface_refs": [
                    ref.value for ref in execution_package.source_surface_refs
                ],
                "evidence_refs": [ref.value for ref in artifact_refs],
            }
            for lineage in validated_result.evidence_summary["source_inventory_lineage"]
            if lineage["lineage_status"] == "traceable"
        )
        if not source_lineage_inputs:
            raise ValueError("source inventory lineage input is required")
        return AtomicResultProjection(
            atomic_run_id=result.run_id,
            work_product_submission=WorkProductSubmission(
                work_product=work_product,
                claim_drafts=(claim_draft,),
            ),
            source_lineage_inputs=source_lineage_inputs,
            event_stream_ref=result.event_stream_ref,
            events_hash=result.events_hash,
        )


def _validate_relative_paths(
    paths: tuple[str, ...],
    *,
    error_message: str,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if not paths:
        if allow_empty:
            return paths
        raise ValueError(error_message)
    for path in paths:
        parsed = PurePosixPath(path)
        if (
            parsed.is_absolute()
            or ".." in parsed.parts
            or _looks_like_windows_absolute_path(path)
        ):
            raise ValueError(error_message)
    return paths


def _looks_like_windows_absolute_path(path: str) -> bool:
    return bool(re.match(r"^[A-Za-z]:[/\\]", path)) or path.startswith(("\\\\", "//"))


def _path_is_in_allowed_write_set(path: str, allowed_write_set: tuple[str, ...]) -> bool:
    for allowed_path in allowed_write_set:
        if allowed_path.endswith("/"):
            prefix = allowed_path.rstrip("/")
            if path == prefix or path.startswith(prefix + "/"):
                return True
        if path == allowed_path:
            return True
        if allowed_path.endswith("/**"):
            prefix = allowed_path.removesuffix("/**").rstrip("/")
            if path.startswith(prefix + "/"):
                return True
            continue
        if "/" not in allowed_path and path.startswith(allowed_path + "/"):
            return True
    return False


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256_PATTERN.fullmatch(value) is not None


def _mutation_after_hash(mutation: dict[str, Any]) -> object:
    return mutation.get("sha256") or mutation.get("after_hash")


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def declared_command_ids_from_execution_package(execution_package: ExecutionPackage) -> tuple[str, ...]:
    return tuple(command.command_id.value for command in execution_package.commands)


def _role_execution_kind(role_category: str) -> str:
    if role_category == "worker":
        return "implementation"
    return role_category


def _ref_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _summary_workspace_mutations(evidence_summary: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    lineage = evidence_summary.get("source_inventory_lineage")
    if not isinstance(lineage, list):
        raise ValueError("event stream summary source_inventory_lineage is required")
    mutations: list[dict[str, Any]] = []
    for item in lineage:
        if not isinstance(item, dict):
            raise ValueError("event stream summary source_inventory_lineage item is invalid")
        if item.get("lineage_status") != "traceable":
            continue
        mutation_refs = item.get("mutation_refs")
        if not isinstance(mutation_refs, list) or not mutation_refs:
            raise ValueError("traceable source lineage requires mutation_refs")
        latest = mutation_refs[-1]
        mutations.append(
            {
                "path": item["path"],
                "tool_attempt_id": latest["tool_attempt_id"],
                "latest_after_hash": item["latest_after_hash"],
            }
        )
    if not mutations:
        raise ValueError("event stream summary must contain traceable workspace mutations")
    return tuple(mutations)


def _submitted_artifact_refs(evidence_summary: dict[str, Any]) -> set[str]:
    events = evidence_summary.get("_events")
    if isinstance(events, list):
        for event in reversed(events):
            if event.get("type") == "result.submitted":
                return {
                    artifact["artifact_ref"]
                    for artifact in event["payload"].get("artifact_refs", ())
                    if isinstance(artifact, dict) and artifact.get("artifact_ref")
                }
    # build_evidence_summary does not expose events; callers attach them after construction.
    return {
        artifact["artifact_ref"]
        for artifact in evidence_summary.get("result_artifacts", ())
        if isinstance(artifact, dict) and artifact.get("artifact_ref")
    }


def _validate_provider_attempt_binding(
    *,
    execution_package: ExecutionPackage,
    provider_attempt: ProviderAttempt,
) -> None:
    if provider_attempt.status is not ProviderAttemptStatus.SUCCEEDED:
        raise ValueError("provider_attempt.status must be succeeded")
    if provider_attempt.outcome is not ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT:
        raise ValueError("provider_attempt.outcome must be primary_provider_output")
    if provider_attempt.input_package_ref != ExecutionPackageRef(
        value=execution_package.execution_package_id.value
    ):
        raise ValueError("provider_attempt.input_package_ref must match execution_package")
    if provider_attempt.provider != execution_package.model_execution_profile.provider:
        raise ValueError("provider_attempt.provider must match execution_package")
    if provider_attempt.model != execution_package.model_execution_profile.model:
        raise ValueError("provider_attempt.model must match execution_package")
    if provider_attempt.reasoning_effort != execution_package.model_execution_profile.reasoning_effort:
        raise ValueError("provider_attempt.reasoning_effort must match execution_package")
    if provider_attempt.seat_ref != execution_package.seat_ref:
        raise ValueError("provider_attempt.seat_ref must match execution_package")
    if provider_attempt.role_prompt_hook_ref != execution_package.role_prompt_hook.hook_ref:
        raise ValueError("provider_attempt.role_prompt_hook_ref must match execution_package")
    if provider_attempt.role_prompt_hook_version != execution_package.role_prompt_hook.hook_version:
        raise ValueError("provider_attempt.role_prompt_hook_version must match execution_package")
    if provider_attempt.role_prompt_hook_sha256 != execution_package.role_prompt_hook.content_sha256:
        raise ValueError("provider_attempt.role_prompt_hook_sha256 must match execution_package")


__all__ = [
    "AtomicAgentAdapterError",
    "AtomicAgentDependencyInfo",
    "AtomicAgentPackageAdapter",
    "AtomicAgentPort",
    "AtomicAgentResultValidator",
    "AtomicAgentValidatedResult",
    "AtomicInvocationCompiler",
    "AtomicResultProjection",
    "AtomicResultProjector",
]
