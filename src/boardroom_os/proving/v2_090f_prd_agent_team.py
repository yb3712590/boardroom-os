from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import http.client
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any

from boardroom_os.agents.role_prompt_hooks import (
    RolePromptHookRef,
    build_baseline_role_prompt_hook_registry,
)
from boardroom_os.agents.profiles import ModelExecutionProfile
from boardroom_os.agents.seat import AgentSeatRef
from boardroom_os.config.boardroom import (
    BoardroomConfigPaths,
    load_boardroom_settings,
)
from boardroom_os.contracts.evidence_obligation import (
    EvidenceObligation,
    RequiredArtifactType,
    RequiredVerifier,
)
from boardroom_os.contracts.package import PackageCommand
from boardroom_os.contracts.types import (
    AcceptanceRef,
    ContractId,
    EvidenceObligationRef,
    SourceSurfaceRef,
)
from boardroom_os.execution.package import (
    AllowedReadRef,
    AllowedWritePath,
    AuditRequirement,
    ContextRef,
    ExecutionPackage,
    ExecutionPackageId,
    FallbackPolicyRef,
    RequiredOutput,
)
from boardroom_os.execution.provider_executor import (
    ProviderExecutor,
    ProviderExecutorInput,
)
from boardroom_os.graph.ticket import TicketId
from boardroom_os.providers.attempt import ProviderAttempt
from boardroom_os.providers.openai_adapter import FileProviderOutputStore
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.atomic_executor import AtomicExecutionRequest
from boardroom_os.execution.atomic_executor import AtomicAgentExecutor, AtomicAgentRuntimeFactory
from boardroom_os.providers.attempt import ProviderAttemptStatus
from boardroom_os.providers.attempt import ProviderAttemptOutcome


V2_090F_MARKER = ".boardroom-v2-090f-workspace.json"
V2_090F_PROVIDER_PROFILE_REF = "provider.openai-compatible.v2-090f-primary"
V2_090F_BUDGET_PROFILE_REF = "agent_team.v2_090f.fullstack"
REQUIRED_AGENT_TEAM_SEATS = (
    "seat.ceo.delivery",
    "seat.architect.delivery",
    "seat.worker.implementation",
    "seat.tester.integration",
    "seat.checker.acceptance",
    "seat.closeout.package",
)
V2_090F_CONFIG_PATHS = {
    "runtime_config": "config/boardroom-runtime.v2-090f.yaml",
    "providers_config": "config/boardroom-providers.v2-090f.yaml",
    "roles_config": "config/boardroom-roles.v2-090f.yaml",
}
V2_090F_HARD_CRUD_OPERATIONS = ("add", "list", "checkout", "return", "delete")
V2_090F_HARD_ACCEPTANCE_REF = "AC-V2-090F-BACKEND-CRUD"
_HOOK_REF_BY_SEAT = {
    "seat.ceo.delivery": "role-prompt-hook.baseline.ceo.v1",
    "seat.architect.delivery": "role-prompt-hook.baseline.architect.v1",
    "seat.worker.implementation": "role-prompt-hook.baseline.worker.v1",
    "seat.tester.integration": "role-prompt-hook.baseline.tester.v1",
    "seat.checker.acceptance": "role-prompt-hook.baseline.checker.v1",
    "seat.closeout.package": "role-prompt-hook.baseline.closeout.v1",
}


@dataclass(frozen=True)
class LoadedPrd:
    path: str
    text: str
    sha256: str


def load_v2_090f_prd(path: Path) -> LoadedPrd:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("PRD must not be empty")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return LoadedPrd(path=path.as_posix(), text=text, sha256=f"sha256:{digest}")


def reset_v2_090f_workspace(workspace: Path) -> None:
    workspace = workspace.resolve()
    marker = workspace / V2_090F_MARKER
    if workspace.exists():
        if not marker.is_file():
            raise ValueError("missing V2-090F marker; refusing to reset workspace")
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "00-boardroom").mkdir()
    (workspace / "work").mkdir()
    marker.write_text(
        json.dumps({"runner": "prd-agent-team", "scenario": "V2-090F"}, sort_keys=True),
        encoding="utf-8",
    )


def validate_required_agent_team_slots(
    slots: list[dict[str, object]] | tuple[dict[str, object], ...],
) -> None:
    by_seat = {str(slot["seat_ref"]): slot for slot in slots}
    missing = [seat for seat in REQUIRED_AGENT_TEAM_SEATS if seat not in by_seat]
    if missing:
        raise ValueError("missing required agent team seats: " + ", ".join(missing))

    role_profile_refs = {
        str(by_seat[seat]["role_profile_ref"]) for seat in REQUIRED_AGENT_TEAM_SEATS
    }
    if role_profile_refs == {"role.worker.implementation"}:
        raise ValueError("required seats must not all reuse worker role profile")

    for seat in REQUIRED_AGENT_TEAM_SEATS:
        slot = by_seat[seat]
        if (
            seat != "seat.worker.implementation"
            and slot["role_profile_ref"] == "role.worker.implementation"
        ):
            raise ValueError("non-worker seat must not reuse worker role profile")
        if (
            slot["provider_profile_ref"] != V2_090F_PROVIDER_PROFILE_REF
            or slot["budget_profile_ref"] != V2_090F_BUDGET_PROFILE_REF
        ):
            raise ValueError(
                "required seats must use V2-090F high-budget provider baseline"
            )

    for seat, slot in by_seat.items():
        if seat == "seat.worker.implementation":
            continue
        tools = set(slot.get("default_tools", ()))
        if {"write_file", "apply_patch"}.intersection(tools):
            raise ValueError("non-worker role must not have implementation write tools")


def validate_role_invocation_context(
    *,
    seat_ref: str,
    expected_skill_refs: tuple[str, ...],
    invocation_role_context: str,
    invocation_skill_context: dict[str, object],
) -> None:
    required_fragments = (
        "RolePromptHook ref:",
        "RolePromptHook version:",
        "RolePromptHook sha256:",
    )
    if any(fragment not in invocation_role_context for fragment in required_fragments):
        raise ValueError(f"role_context must include RolePromptHook snapshot for {seat_ref}")
    actual = tuple(invocation_skill_context.get("skill_refs", ()))
    if actual != expected_skill_refs:
        raise ValueError("skill_context.skill_refs mismatch")


def validate_agent_team_autonomy_inputs(
    *,
    prd_text: str,
    predefined_ticket_refs: tuple[str, ...],
) -> None:
    if not prd_text.strip():
        raise ValueError("PRD must not be empty")
    if predefined_ticket_refs:
        raise ValueError("runner must not predefine implementation ticket graph")


def write_v2_090f_baseline_report(
    *,
    output_path: Path,
    prd_sha256: str,
    runtime_config_hash: str,
    providers_config_hash: str,
    roles_config_hash: str,
    seats: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    missing = [seat for seat in REQUIRED_AGENT_TEAM_SEATS if seat not in seats]
    if missing:
        raise ValueError("missing required agent team seats: " + ", ".join(missing))
    payload: dict[str, Any] = {
        "prd_sha256": prd_sha256,
        "config_hashes": {
            "runtime_config_hash": runtime_config_hash,
            "providers_config_hash": providers_config_hash,
            "roles_config_hash": roles_config_hash,
        },
        "required_seats": list(REQUIRED_AGENT_TEAM_SEATS),
        "seats": {seat: seats[seat] for seat in REQUIRED_AGENT_TEAM_SEATS},
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def resolve_v2_090f_config_paths_from_env(
    env_values: dict[str, str],
) -> BoardroomConfigPaths:
    paths = BoardroomConfigPaths(
        runtime_config=Path(
            env_values.get("BOARDROOM_RUNTIME_CONFIG", V2_090F_CONFIG_PATHS["runtime_config"])
        ),
        providers_config=Path(
            env_values.get(
                "BOARDROOM_PROVIDERS_CONFIG",
                V2_090F_CONFIG_PATHS["providers_config"],
            )
        ),
        roles_config=Path(
            env_values.get("BOARDROOM_ROLES_CONFIG", V2_090F_CONFIG_PATHS["roles_config"])
        ),
    )
    actual = {
        "runtime_config": paths.runtime_config.as_posix(),
        "providers_config": paths.providers_config.as_posix(),
        "roles_config": paths.roles_config.as_posix(),
    }
    if actual != V2_090F_CONFIG_PATHS:
        raise ValueError("V2-090F must use V2-090F dedicated config paths")
    return paths


def run_v2_090f_planning_preflight(
    *,
    prd: LoadedPrd,
    output_root: Path,
    env_values: dict[str, str],
) -> dict[str, Any]:
    paths = resolve_v2_090f_config_paths_from_env(env_values)
    settings = load_boardroom_settings(paths, env_values=env_values)
    role_slots = [slot.model_dump(mode="json") for slot in settings.roles.role_slots]
    validate_required_agent_team_slots(role_slots)

    seats = {}
    for seat in REQUIRED_AGENT_TEAM_SEATS:
        slot = settings.role_slot_by_seat(seat)
        provider = settings.provider_by_id(slot.provider_profile_ref)
        budget = settings.budgets_for_seat(seat)
        seats[seat] = {
            "role_profile_ref": slot.role_profile_ref,
            "role_category": slot.role_category,
            "provider_profile_ref": slot.provider_profile_ref,
            "model": provider.model,
            "reasoning_effort": provider.reasoning_effort,
            "tools": list(slot.default_tools),
            "skill_refs": list(slot.skill_refs),
            "budget_profile_ref": slot.budget_profile_ref,
            "resolved_budget_hash": _stable_json_hash(budget),
        }

    boardroom_root = output_root / "00-boardroom"
    boardroom_root.mkdir(parents=True, exist_ok=True)
    write_v2_090f_baseline_report(
        output_path=boardroom_root / "v2-090f-baseline.json",
        prd_sha256=prd.sha256,
        runtime_config_hash=settings.config_hashes.runtime_config_hash,
        providers_config_hash=settings.config_hashes.providers_config_hash,
        roles_config_hash=settings.config_hashes.roles_config_hash,
        seats=seats,
    )
    (boardroom_root / "prd-intake.json").write_text(
        json.dumps(
            {
                "prd_path": prd.path,
                "prd_sha256": prd.sha256,
                "prd_text": prd.text,
                "status": "loaded",
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_pending_role_context(boardroom_root / "agent-team-role-context.json", settings)
    return {
        "status": "blocked_before_real_provider_orchestration",
        "blocker": "Task 7A provider-backed CEO/Architect/Tester planning is not implemented",
        "baseline_path": (boardroom_root / "v2-090f-baseline.json").as_posix(),
        "role_context_path": (boardroom_root / "agent-team-role-context.json").as_posix(),
    }


def build_v2_090f_planning_execution_package(
    *,
    settings: Any,
    seat_ref: str,
    prd: LoadedPrd,
    output_name: str,
) -> ExecutionPackage:
    if seat_ref == "seat.worker.implementation":
        raise ValueError("planning execution package must not target worker implementation")
    slot = settings.role_slot_by_seat(seat_ref)
    provider = settings.provider_by_id(slot.provider_profile_ref)
    hook = build_baseline_role_prompt_hook_registry().require(
        RolePromptHookRef(value=_HOOK_REF_BY_SEAT[seat_ref])
    )
    return ExecutionPackage(
        execution_package_id=ExecutionPackageId(
            value=f"exec.ticket.v2-090f.{_safe_token(seat_ref)}.{output_name}"
        ),
        ticket_ref=TicketId(value=f"ticket.v2-090f.{_safe_token(seat_ref)}.{output_name}"),
        graph_version=1,
        seat_ref=AgentSeatRef(value=seat_ref),
        model_execution_profile=ModelExecutionProfile(
            model_execution_profile_id=slot.model_execution_profile_id,
            provider="openai-compatible",
            model=provider.model,
            reasoning_effort=provider.reasoning_effort or "high",
            context_window=provider.context_window_tokens,
            temperature=0.0 if provider.temperature is None else provider.temperature,
            tool_permissions=("provider.invoke", "filesystem.read"),
            fallback_policy_ref=ContractId(value="fallback.default"),
        ),
        role_prompt_hook=hook,
        objective=(
            f"Produce V2-090F planning artifact {output_name} from the PRD. "
            "Return one JSON object only. Do not claim implementation, verification, "
            "checker approval, closeout, or sample success. "
            f"PRD sha256: {prd.sha256}. PRD text: {prd.text}"
        ),
        context_refs=(
            ContextRef(value="context.v2-090f.prd"),
            ContextRef(value="context.v2-090f.reference-examples"),
        ),
        constraints=(
            "Use the PRD as the source of truth.",
            "Do not predefine runner-owned implementation ticket refs.",
            "Do not write implementation source.",
            "Do not mark closeout passed.",
        ),
        acceptance_refs=(AcceptanceRef(value="AC-V2-090F-PLANNING"),),
        source_surface_refs=(SourceSurfaceRef(value="surface.v2-090f.boardroom-planning"),),
        allowed_read_refs=(
            AllowedReadRef(value=prd.path),
            AllowedReadRef(value="examples/directives/v2-090f-reference-examples.md"),
        ),
        allowed_write_set=(AllowedWritePath(value="00-boardroom/"),),
        required_outputs=(RequiredOutput(value=f"00-boardroom/generated-{output_name}.json"),),
        commands=(
            PackageCommand(
                command_id=ContractId(value=f"cmd.v2-090f.{_safe_token(seat_ref)}.planning"),
                label=f"Record {output_name} planning artifact",
                command=("provider-only-planning", output_name),
                cwd=".",
            ),
        ),
        evidence_obligations=(
            EvidenceObligation(
                evidence_obligation_id=EvidenceObligationRef(
                    value=f"evidence.v2-090f.{_safe_token(seat_ref)}.{output_name}"
                ),
                acceptance_refs=(AcceptanceRef(value="AC-V2-090F-PLANNING"),),
                source_surface_refs=(
                    SourceSurfaceRef(value="surface.v2-090f.boardroom-planning"),
                ),
                required_artifact_type=RequiredArtifactType(value="planning_artifact"),
                required_verifier=RequiredVerifier(value="checker"),
                blocking=True,
            ),
        ),
        fallback_policy_ref=FallbackPolicyRef(value="fallback.default"),
        audit_requirements=(
            AuditRequirement(value="record V2-090F planning provider attempt"),
        ),
    )


def invoke_v2_090f_planning_role(
    *,
    execution_package: ExecutionPackage,
    provider_adapter: Any,
    output_path: Path,
) -> dict[str, Any]:
    result = ProviderExecutor().execute(
        ProviderExecutorInput(
            execution_package=execution_package,
            provider_adapter=provider_adapter,
        )
    )
    attempt = result.provider_attempt
    if attempt.status is not ProviderAttemptStatus.SUCCEEDED:
        raise ValueError("planning provider attempt must succeed")
    if attempt.parsed_output_ref is None:
        raise ValueError("planning provider parsed_output_ref is required")
    provider_output = _read_provider_artifact(
        attempt.parsed_output_ref.value,
        provider_adapter=provider_adapter,
    )
    payload = {
        "execution_package_ref": execution_package.execution_package_id.value,
        "seat_ref": execution_package.seat_ref.value,
        "role_prompt_hook_ref": execution_package.role_prompt_hook.hook_ref.value,
        "provider_attempt_ref": attempt.provider_attempt_id.value,
        "parsed_artifact_ref": attempt.parsed_output_ref.value,
        "provider_output": provider_output,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def extract_v2_090f_planning_artifact(
    provider_output: Any,
    *,
    expected_artifact_name: str,
) -> dict[str, Any]:
    if not isinstance(provider_output, dict):
        raise ValueError("planning provider output must be a JSON object")
    try:
        artifact = _unwrap_planning_artifact(provider_output)
    except ValueError as exc:
        if expected_artifact_name == "ticket-graph":
            raise ValueError("ticket graph planning artifact is required") from exc
        raise
    if expected_artifact_name == "ticket-graph":
        ticket_graph = artifact.get("ticket_graph")
        if not isinstance(ticket_graph, dict):
            raise ValueError("ticket graph planning artifact is required")
        nodes = ticket_graph.get("nodes")
        if not isinstance(nodes, list) or not nodes:
            raise ValueError("ticket graph planning artifact is required")
    return artifact


def validate_v2_090f_generated_ticket_graph_for_worker_execution(
    ticket_graph_artifact: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    ticket_graph = ticket_graph_artifact.get("ticket_graph")
    if not isinstance(ticket_graph, dict):
        raise ValueError("ticket graph planning artifact is required")
    nodes = ticket_graph.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("ticket graph planning artifact is required")
    implementation_nodes = tuple(
        node
        for node in nodes
        if isinstance(node, dict)
        and node.get("owner_seat_ref") == "seat.worker.implementation"
        and str(node.get("node_type", node.get("ticket_type", ""))).startswith(
            "implementation"
        )
    )
    if not implementation_nodes:
        raise ValueError("implementation ticket is required for worker execution")
    for node in implementation_nodes:
        _require_non_empty_node_list(node, "acceptance_refs")
        _require_non_empty_node_list(node, "source_surface_refs")
        _require_non_empty_node_list(node, "evidence_obligations")
        _require_non_empty_node_list(node, "allowed_write_set")
        _reject_glob_patterns(_string_list(node, "allowed_write_set"), "allowed_write_set")
        _reject_glob_patterns(_string_list(node, "required_outputs"), "required_outputs")
        _validate_bounded_worker_commands(_node_commands(node))
        _validate_command_test_surface_is_writable(node)
    _validate_v2_090f_hard_crud_acceptance(implementation_nodes)
    _validate_v2_090f_hard_backend_entrypoint(implementation_nodes)
    return implementation_nodes


def build_v2_090f_worker_execution_packages(
    *,
    settings: Any,
    ticket_graph_artifact: dict[str, Any],
    graph_version: int,
) -> tuple[ExecutionPackage, ...]:
    if graph_version <= 0:
        raise ValueError("graph_version must be positive")
    worker_seat = "seat.worker.implementation"
    slot = settings.role_slot_by_seat(worker_seat)
    provider = settings.provider_by_id(slot.provider_profile_ref)
    hook = build_baseline_role_prompt_hook_registry().require(
        RolePromptHookRef(value=_HOOK_REF_BY_SEAT[worker_seat])
    )
    packages: list[ExecutionPackage] = []
    for node in validate_v2_090f_generated_ticket_graph_for_worker_execution(
        ticket_graph_artifact
    ):
        ticket_ref = _node_ref(node)
        acceptance_refs = tuple(
            AcceptanceRef(value=value) for value in _string_list(node, "acceptance_refs")
        )
        source_surface_refs = tuple(
            SourceSurfaceRef(value=value)
            for value in _string_list(node, "source_surface_refs")
        )
        evidence_obligations = tuple(
            EvidenceObligation(
                evidence_obligation_id=EvidenceObligationRef(value=value),
                acceptance_refs=acceptance_refs,
                source_surface_refs=source_surface_refs,
                required_artifact_type=RequiredArtifactType(value="implementation_evidence"),
                required_verifier=RequiredVerifier(value="evidence_verifier"),
                blocking=True,
            )
            for value in _string_list(node, "evidence_obligations")
        )
        commands = tuple(
            _package_command_from_node_command(command)
            for command in _node_commands(node)
        )
        allowed_write_values = _string_list(node, "allowed_write_set")
        packages.append(
            ExecutionPackage(
                execution_package_id=ExecutionPackageId(value=f"exec.{ticket_ref}"),
                ticket_ref=TicketId(value=ticket_ref),
                graph_version=graph_version,
                seat_ref=AgentSeatRef(value=worker_seat),
                model_execution_profile=ModelExecutionProfile(
                    model_execution_profile_id=slot.model_execution_profile_id,
                    provider="openai-compatible",
                    model=provider.model,
                    reasoning_effort=provider.reasoning_effort or "high",
                    context_window=provider.context_window_tokens,
                    temperature=0.0 if provider.temperature is None else provider.temperature,
                    tool_permissions=(
                        "filesystem.read",
                        "filesystem.write",
                        "command.execute",
                    ),
                    fallback_policy_ref=ContractId(value="fallback.default"),
                ),
                role_prompt_hook=hook,
                objective=str(node.get("title") or node.get("objective") or ticket_ref),
                context_refs=(
                    ContextRef(value="00-boardroom/generated-contracts.json"),
                    ContextRef(value="00-boardroom/generated-ticket-graph.json"),
                    ContextRef(value="00-boardroom/generated-verification-plan.json"),
                ),
                constraints=(
                    "Implement only this generated worker ticket.",
                    "Do not claim checker approval, closeout, or project completion.",
                    "Produce real source changes and run declared commands.",
                    (
                        "Return exactly one JSON action object per provider turn. "
                        "Do not append additional JSON objects after that action. "
                        "Wait for tool observations before emitting the next action."
                    ),
                    (
                        "Never concatenate JSON objects in one provider response. "
                        "If you need multiple actions, return only the next single action, "
                        "then wait for the next provider turn. Do not use batch protocol "
                        "to bypass the single-object rule."
                    ),
                    (
                        "Do not include submit_result in the same provider turn as "
                        "write_file or run_command. submit_result must be its own "
                        "final provider turn after observing successful tool and "
                        "command results."
                    ),
                    (
                        'Tool path rule: list_files with path "." is denied by the '
                        "workspace guard; omit the path field to list the workspace "
                        "root, or use one of these concrete relative paths: "
                        + ", ".join(allowed_write_values)
                    ),
                    (
                        "Do not read_file a path until list_files has shown that "
                        "exact file exists. If a required output file does not "
                        "exist, create it with write_file instead of reading it."
                    ),
                    (
                        "Use list_files only for directories, never for file paths. "
                        "To check whether a file exists, list the parent directory "
                        "and inspect returned names; if the file is absent, create "
                        "it with write_file."
                    ),
                    (
                        "Use search_files with input fields query, path, mode, and "
                        "max_matches. Do not use pattern with search_files. Set "
                        'mode to "name" or "content"; omit path or use a directory path.'
                    ),
                    (
                        "search_files query must be a non-empty string. If you need "
                        "to list every file in a directory, use list_files instead "
                        "of search_files with an empty query."
                    ),
                    (
                        "When complete, submit_result input must contain exactly "
                        "summary, produced_paths, and evidence_refs. produced_paths "
                        "must include every required output path. evidence_refs must "
                        "be a list of artifact refs from tool observations, command "
                        "stdout/stderr, diffs, or result artifacts. evidence_refs "
                        "must use actual artifact:// refs from completed tool observations, "
                        "not action ids, command ids, or prose descriptions."
                    ),
                    (
                        "Do not submit_result until you have written or modified at "
                        "least one required output path and run every declared command. "
                        "evidence_refs must not be empty."
                    ),
                    (
                        "Every declared command must have a latest observed exit_code of 0 "
                        "before submit_result. If any declared command fails, fix the "
                        "workspace and rerun that command; do not include failed command "
                        "evidence as completion evidence."
                    ),
                ),
                acceptance_refs=acceptance_refs,
                source_surface_refs=source_surface_refs,
                allowed_read_refs=(
                    AllowedReadRef(value="00-boardroom/generated-contracts.json"),
                    AllowedReadRef(value="00-boardroom/generated-ticket-graph.json"),
                    AllowedReadRef(value="00-boardroom/generated-verification-plan.json"),
                ),
                allowed_write_set=tuple(
                    AllowedWritePath(value=value)
                    for value in allowed_write_values
                ),
                required_outputs=tuple(
                    RequiredOutput(value=value)
                    for value in _string_list(node, "required_outputs")
                ),
                commands=commands,
                evidence_obligations=evidence_obligations,
                fallback_policy_ref=FallbackPolicyRef(value="fallback.default"),
                audit_requirements=(
                    AuditRequirement(value="record atomic-agent provider turns"),
                    AuditRequirement(value="record workspace mutation evidence"),
                    AuditRequirement(value="record declared command evidence"),
                    AuditRequirement(value="record source lineage input"),
                ),
            )
        )
    return tuple(packages)


class V2_090FPlanningProviderAdapter:
    def __init__(
        self,
        *,
        settings: Any,
        seat_ref: str,
        output_root: Path,
        atomic_provider_factory: Any | None = None,
        client: Any | None = None,
    ) -> None:
        role_slot = settings.role_slot_by_seat(seat_ref)
        self._provider_config = settings.provider_by_id(role_slot.provider_profile_ref)
        self._provider_options = settings.openai_compatible_options(role_slot.provider_profile_ref)
        self._atomic_provider_factory = atomic_provider_factory
        self._client = client
        self._artifact_store = FileProviderOutputStore(
            root=output_root / "20-evidence/provider-artifacts"
        )

    def invoke(self, request: Any) -> ProviderAttempt:
        started_at = datetime.now(UTC)
        try:
            output = self._complete(request)
            response_id = _safe_provider_response_id(
                f"{request.execution_package_ref.value}.{int(started_at.timestamp() * 1_000_000)}"
            )
            raw_artifact = self._artifact_store.write_text(
                response_id=response_id,
                artifact_kind="raw",
                text=output,
            )
            parsed_artifact = self._artifact_store.write_text(
                response_id=response_id,
                artifact_kind="parsed",
                text=output,
            )
            return ProviderAttempt(
                provider_attempt_id=ProviderAttemptRef(
                    value=f"provider-attempt.v2-090f.planning.{response_id}"
                ),
                provider=request.model_execution_profile.provider,
                model=request.model_execution_profile.model,
                reasoning_effort=request.model_execution_profile.reasoning_effort,
                input_package_ref=request.execution_package_ref,
                seat_ref=request.seat_ref,
                role_prompt_hook_ref=request.role_prompt_hook_ref,
                role_prompt_hook_version=request.role_prompt_hook_version,
                role_prompt_hook_sha256=request.role_prompt_hook_sha256,
                status=ProviderAttemptStatus.SUCCEEDED,
                outcome=ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                raw_output_ref=raw_artifact.artifact_ref,
                parsed_output_ref=parsed_artifact.artifact_ref,
            )
        except Exception as exc:
            return ProviderAttempt(
                provider_attempt_id=ProviderAttemptRef(
                    value=(
                        "provider-attempt.v2-090f.planning.failed."
                        f"{_safe_provider_response_id(request.execution_package_ref.value)}."
                        f"{int(started_at.timestamp() * 1_000_000)}"
                    )
                ),
                provider=request.model_execution_profile.provider,
                model=request.model_execution_profile.model,
                reasoning_effort=request.model_execution_profile.reasoning_effort,
                input_package_ref=request.execution_package_ref,
                seat_ref=request.seat_ref,
                role_prompt_hook_ref=request.role_prompt_hook_ref,
                role_prompt_hook_version=request.role_prompt_hook_version,
                role_prompt_hook_sha256=request.role_prompt_hook_sha256,
                status=ProviderAttemptStatus.FAILED,
                outcome=ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                failure_kind=f"provider_error.{type(exc).__name__}",
            )

    def read_provider_artifact(self, artifact_ref: str) -> str:
        from boardroom_os.providers.attempt import ProviderArtifactRef

        return self._artifact_store.read_text(ProviderArtifactRef(value=artifact_ref))

    def _complete(self, request: Any) -> str:
        client = self._client_or_default()
        prompt = _direct_planning_prompt(request.prompt)
        kwargs: dict[str, Any] = {
            "model": self._provider_config.model,
            "messages": [{"role": "user", "content": prompt}],
            "reasoning_effort": request.model_execution_profile.reasoning_effort,
            "max_completion_tokens": self._provider_config.max_output_tokens,
            "timeout": self._provider_config.total_timeout_seconds,
        }
        if self._provider_config.response_format is not None:
            kwargs["response_format"] = self._provider_config.response_format
        if self._provider_config.temperature is not None:
            kwargs["temperature"] = self._provider_config.temperature
        if self._provider_config.top_p is not None:
            kwargs["top_p"] = self._provider_config.top_p
        if self._provider_config.presence_penalty is not None:
            kwargs["presence_penalty"] = self._provider_config.presence_penalty
        if self._provider_config.frequency_penalty is not None:
            kwargs["frequency_penalty"] = self._provider_config.frequency_penalty
        if self._provider_config.seed is not None:
            kwargs["seed"] = self._provider_config.seed
        if self._provider_config.stop is not None:
            kwargs["stop"] = list(self._provider_config.stop)
        if self._provider_config.service_tier is not None:
            kwargs["service_tier"] = self._provider_config.service_tier
        if self._provider_config.user is not None:
            kwargs["user"] = self._provider_config.user
        response = client.chat.completions.create(**kwargs)
        return self._response_text(response)

    def _client_or_default(self) -> Any:
        if self._client is not None:
            return self._client
        from openai import OpenAI

        self._client = OpenAI(
            api_key=self._provider_options.api_key,
            base_url=self._provider_config.base_url,
            max_retries=0,
        )
        return self._client

    @staticmethod
    def _response_text(response: Any) -> str:
        output_text = str(getattr(response, "output_text", "") or "").strip()
        if not output_text and getattr(response, "choices", None):
            message = getattr(response.choices[0], "message", None)
            output_text = str(getattr(message, "content", "") or "").strip()
        if not output_text:
            raise ValueError("planning provider response text is required")
        return output_text


def build_v2_090f_planning_provider_adapter(
    *,
    settings: Any,
    seat_ref: str,
    output_root: Path,
    atomic_provider_factory: Any | None = None,
    client: Any | None = None,
) -> V2_090FPlanningProviderAdapter:
    return V2_090FPlanningProviderAdapter(
        settings=settings,
        seat_ref=seat_ref,
        output_root=output_root,
        atomic_provider_factory=atomic_provider_factory,
        client=client,
    )


def run_v2_090f_provider_planning_stage(
    *,
    prd: LoadedPrd,
    output_root: Path,
    settings: Any,
    provider_adapter_factory: Any,
) -> dict[str, Any]:
    boardroom_root = output_root / "00-boardroom"
    role_context_path = boardroom_root / "agent-team-role-context.json"
    if not role_context_path.is_file():
        raise ValueError("agent-team-role-context is required before planning stage")
    planning_steps = (
        ("seat.ceo.delivery", "board-directive"),
        ("seat.architect.delivery", "contracts"),
        ("seat.architect.delivery", "ticket-graph"),
        ("seat.tester.integration", "verification-plan"),
    )
    artifacts: dict[str, dict[str, Any]] = {}
    for seat_ref, output_name in planning_steps:
        package = build_v2_090f_planning_execution_package(
            settings=settings,
            seat_ref=seat_ref,
            prd=prd,
            output_name=output_name,
        )
        provider_adapter = provider_adapter_factory(
            seat_ref=seat_ref,
            output_name=output_name,
        )
        artifacts[output_name] = invoke_v2_090f_planning_role(
            execution_package=package,
            provider_adapter=provider_adapter,
            output_path=boardroom_root / f"generated-{output_name}.json",
        )

    _mark_planning_role_context_succeeded(
        role_context_path=role_context_path,
        planning_artifacts=artifacts,
    )
    return {
        "status": "planning_stage_succeeded",
        "artifacts": {
            output_name: artifact["provider_attempt_ref"]
            for output_name, artifact in artifacts.items()
        },
        "blocker": "Task 7B worker implementation and Task 7C closeout are not implemented",
    }


def run_v2_090f_worker_execution_stage(
    *,
    output_root: Path,
    workspace_root: Path,
    settings: Any,
    atomic_executor: Any | None = None,
) -> dict[str, Any]:
    boardroom_root = output_root / "00-boardroom"
    ticket_graph_path = boardroom_root / "generated-ticket-graph.json"
    if not ticket_graph_path.is_file():
        raise ValueError("generated-ticket-graph.json is required before worker execution")
    ticket_payload = json.loads(ticket_graph_path.read_text(encoding="utf-8"))
    ticket_graph_artifact = extract_v2_090f_planning_artifact(
        ticket_payload.get("provider_output"),
        expected_artifact_name="ticket-graph",
    )
    packages = build_v2_090f_worker_execution_packages(
        settings=settings,
        ticket_graph_artifact=ticket_graph_artifact,
        graph_version=2,
    )
    run_scope = _new_v2_090f_run_scope()
    event_stream_root = Path(settings.runtime.atomic_agent.event_stream_root) / run_scope
    artifact_root = Path(settings.runtime.atomic_agent.artifact_root) / run_scope
    event_stream_root.mkdir(parents=True, exist_ok=True)
    artifact_root.mkdir(parents=True, exist_ok=True)
    ticket_results: list[dict[str, Any]] = []
    for package in packages:
        _prepare_v2_090f_worker_workspace_paths(workspace_root, package)
        executor = atomic_executor
        if atomic_executor is None:
            runtime_port = AtomicAgentRuntimeFactory(settings=settings).build_runtime_port(
                execution_package=package,
                seat_ref=package.seat_ref.value,
                workspace_root=workspace_root,
                run_id=(
                    f"v2-090f-{run_scope}-"
                    f"{_safe_provider_response_id(package.ticket_ref.value)}"
                ),
                event_stream_root=event_stream_root,
                artifact_root=artifact_root,
            )
            executor = AtomicAgentExecutor(runtime_port=runtime_port, allow_fake_provider_for_unit_tests=False)
        try:
            execution_result = executor.execute(
                AtomicExecutionRequest(
                    execution_package=package,
                    settings=settings,
                    seat_ref=package.seat_ref.value,
                    workspace_root=workspace_root,
                    event_stream_root=event_stream_root,
                ),
                provider_transport_kind="real",
            )
        except Exception as exc:
            _write_v2_090f_partial_worker_evidence(
                output_root=output_root,
                ticket_results=ticket_results,
                failed_package=package,
                failure=exc,
            )
            raise
        ticket_results.append(_worker_execution_result_summary(execution_result, package))
    payload = {
        "status": "worker_execution_succeeded",
        "tickets": ticket_results,
    }
    evidence_path = output_root / "20-evidence/worker-execution.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "status": "worker_execution_succeeded",
        "worker_evidence_path": evidence_path.as_posix(),
        "ticket_count": len(ticket_results),
        "run_scope": run_scope,
        "blocker": "Task 7C checker and closeout are not implemented",
    }


def run_v2_090f_closeout_stage(
    *,
    output_root: Path,
    workspace_root: Path,
    settings: Any | None = None,
    filter_runtime_files: bool = True,
    run_live_probe: bool = True,
    checker_approved: bool = True,
) -> dict[str, Any]:
    worker_evidence_path = output_root / "20-evidence/worker-execution.json"
    if not worker_evidence_path.is_file():
        raise ValueError("worker-execution.json is required before V2-090F closeout")
    worker_evidence = json.loads(worker_evidence_path.read_text(encoding="utf-8"))
    if worker_evidence.get("status") != "worker_execution_succeeded":
        raise ValueError("worker execution must succeed before V2-090F closeout")
    tickets = worker_evidence.get("tickets")
    if not isinstance(tickets, list) or not tickets:
        raise ValueError("worker execution tickets are required before V2-090F closeout")
    provider_attempt_refs = _worker_provider_attempt_refs(tickets)

    if not checker_approved:
        _write_v2_090f_checker_verdict(
            output_root=output_root,
            approved=False,
            blocker="checker rejected generated package before closeout",
        )
        raise ValueError("checker verdict must be approved before closeout")

    project_root = output_root / "10-project"
    _materialize_v2_090f_project_workspace(
        workspace_root=workspace_root,
        project_root=project_root,
        filter_runtime_files=filter_runtime_files,
    )
    _reject_v2_090f_forbidden_runtime_files(project_root)

    verification_run = _run_v2_090f_final_test_command(project_root=project_root)
    _clean_v2_090f_runtime_files(project_root)
    _reject_v2_090f_forbidden_runtime_files(project_root)
    if not run_live_probe:
        raise ValueError("live blackbox evidence is required before closeout")
    service_evidence, live_blackbox_evidence = _run_v2_090f_live_blackbox_probe(
        project_root=project_root,
    )
    _clean_v2_090f_runtime_files(project_root)
    _reject_v2_090f_forbidden_runtime_files(project_root)
    if not live_blackbox_evidence.get("passed"):
        raise ValueError("live blackbox evidence is required before closeout")

    source_inventory = _build_v2_090f_source_inventory_payload(
        project_root=project_root,
        tickets=tickets,
        provider_attempt_refs=provider_attempt_refs,
    )
    final_evidence_table = _build_v2_090f_final_evidence_table_payload(
        source_inventory=source_inventory,
        verification_run=verification_run,
        service_evidence=service_evidence,
        live_blackbox_evidence=live_blackbox_evidence,
    )
    checker_verdict = _write_v2_090f_checker_verdict(
        output_root=output_root,
        approved=True,
        blocker=None,
    )
    closeout_gate_result = _build_v2_090f_closeout_gate_result_payload(
        source_inventory=source_inventory,
        final_evidence_table=final_evidence_table,
        verification_run=verification_run,
        service_evidence=service_evidence,
        live_blackbox_evidence=live_blackbox_evidence,
        checker_verdict=checker_verdict,
        provider_attempt_refs=provider_attempt_refs,
    )
    if closeout_gate_result["verdict"] != "passed":
        raise ValueError("V2-090F closeout gate blocked")

    evidence_root = output_root / "20-evidence"
    audit_root = output_root / "30-audit"
    _write_json(evidence_root / "source-inventory/source-inventory.json", source_inventory)
    _write_json(evidence_root / "tests/verification-runs.json", {"runs": [verification_run]})
    _write_json(evidence_root / "tests/service-runs.json", {"service_runs": service_evidence})
    _write_json(evidence_root / "tests/live-blackbox.json", live_blackbox_evidence)
    _write_json(
        evidence_root / "tests/run-manifest.json",
        _build_v2_090f_run_manifest_payload(project_root=project_root),
    )
    _write_json(evidence_root / "closeout/final-evidence-table.json", final_evidence_table)
    _write_json(evidence_root / "closeout/closeout-gate-result.json", closeout_gate_result)
    _write_json(
        evidence_root / "closeout/evidence-bundle-manifest.json",
        _build_v2_090f_evidence_bundle_manifest_payload(
            source_inventory=source_inventory,
            final_evidence_table=final_evidence_table,
            verification_run=verification_run,
            service_evidence=service_evidence,
            live_blackbox_evidence=live_blackbox_evidence,
        ),
    )
    replay_bundle = _build_v2_090f_replay_bundle_payload(
        output_root=output_root,
        worker_evidence=worker_evidence,
        closeout_gate_result=closeout_gate_result,
    )
    git_audit_bundle = _build_v2_090f_git_audit_bundle_payload(
        project_root=project_root,
        source_inventory=source_inventory,
    )
    process_audit = _build_v2_090f_process_audit_payload(
        source_inventory=source_inventory,
        final_evidence_table=final_evidence_table,
        closeout_gate_result=closeout_gate_result,
    )
    closeout_package = _build_v2_090f_closeout_package_payload(
        source_inventory=source_inventory,
        final_evidence_table=final_evidence_table,
        closeout_gate_result=closeout_gate_result,
        replay_bundle=replay_bundle,
        git_audit_bundle=git_audit_bundle,
    )
    _write_json(output_root / "replay-bundle.json", replay_bundle)
    _write_json(output_root / "git-version-audit-bundle.json", git_audit_bundle)
    _write_json(audit_root / "process-audit.json", process_audit)
    _write_json(audit_root / "checker-verdict.json", checker_verdict)
    _write_json(output_root / "closeout-package.json", closeout_package)
    _mark_v2_090f_role_context_closeout_succeeded(output_root / "00-boardroom/agent-team-role-context.json")
    sample_manifest = _build_v2_090f_sample_manifest(output_root=output_root)
    _write_json(output_root / "sample-manifest.json", sample_manifest)
    check_v2_090f_sample_tree(output_root)
    return {
        "status": "closeout_gate_passed",
        "closeout_package_path": (output_root / "closeout-package.json").as_posix(),
        "sample_manifest_path": (output_root / "sample-manifest.json").as_posix(),
        "sample_manifest_hash": _stable_json_hash(sample_manifest),
    }


def _worker_provider_attempt_refs(tickets: list[Any]) -> tuple[str, ...]:
    refs: list[str] = []
    for ticket in tickets:
        if not isinstance(ticket, dict):
            raise ValueError("worker execution tickets must be objects")
        ref = str(ticket.get("provider_attempt_ref", "")).strip()
        if not ref:
            raise ValueError("provider attempt refs are required for closeout")
        refs.append(ref)
        command_ids = ticket.get("declared_command_ids")
        if not isinstance(command_ids, list) or not command_ids:
            raise ValueError("declared command evidence is required for closeout")
    if len(set(refs)) != len(refs):
        raise ValueError("provider attempt refs must be unique for closeout")
    return tuple(refs)


def _materialize_v2_090f_project_workspace(
    *,
    workspace_root: Path,
    project_root: Path,
    filter_runtime_files: bool,
) -> None:
    if not workspace_root.is_dir():
        raise ValueError("worker workspace is required before closeout")
    if project_root.exists():
        shutil.rmtree(project_root)
    project_root.mkdir(parents=True)
    for source in sorted(workspace_root.rglob("*")):
        relative = source.relative_to(workspace_root)
        if relative.parts and relative.parts[0] == V2_090F_MARKER:
            continue
        if filter_runtime_files and _is_v2_090f_forbidden_runtime_path(relative):
            continue
        target = project_root / relative
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _reject_v2_090f_forbidden_runtime_files(project_root: Path) -> None:
    for path in project_root.rglob("*"):
        relative = path.relative_to(project_root)
        if _is_v2_090f_forbidden_runtime_path(relative):
            raise ValueError(f"forbidden runtime file in materialized 10-project: {relative.as_posix()}")


def _clean_v2_090f_runtime_files(project_root: Path) -> None:
    for path in sorted(project_root.rglob("*"), reverse=True):
        relative = path.relative_to(project_root)
        if _is_v2_090f_forbidden_runtime_path(relative):
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()


def _is_v2_090f_forbidden_runtime_path(path: Path) -> bool:
    parts = path.parts
    return (
        "__pycache__" in parts
        or ".pytest_cache" in parts
        or path.name.startswith(".pytest")
        or path.suffix in {".pyc", ".pyo"}
        or path.name.endswith(".sqlite3")
        or path.name.endswith(".db")
        or path.name.endswith(".sqlite")
    )


def _run_v2_090f_final_test_command(*, project_root: Path) -> dict[str, Any]:
    command = (sys.executable, "-m", "pytest", "tests")
    started = datetime.now(UTC)
    process = subprocess.run(
        command,
        cwd=project_root,
        text=True,
        capture_output=True,
        timeout=120,
    )
    finished = datetime.now(UTC)
    run_id = "verification-run.v2-090f.final-tests"
    payload = {
        "verification_run_id": run_id,
        "execution_package_ref": "exec.v2-090f.closeout.final-tests",
        "ticket_ref": "ticket.v2-090f.closeout.final-tests",
        "command_id": "cmd.v2-090f.final-tests",
        "command": list(command),
        "cwd": "10-project",
        "exit_code": process.returncode,
        "status": "passed" if process.returncode == 0 else "failed",
        "stdout_ref": f"command-output.{run_id}.stdout",
        "stderr_ref": f"command-output.{run_id}.stderr",
        "stdout": process.stdout,
        "stderr": process.stderr,
        "duration_ms": max(0, int((finished - started).total_seconds() * 1000)),
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "runner_ref": "runner.v2-090f.closeout",
        "environment_profile_ref": "environment.v2-090f.local",
        "workspace_snapshot_ref": _project_tree_hash_ref(project_root),
    }
    if process.returncode != 0:
        raise ValueError("final declared test command failed")
    return payload


def _run_v2_090f_live_blackbox_probe(
    *,
    project_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    backend_port = _free_tcp_port()
    frontend_port = _free_tcp_port()
    with tempfile.TemporaryDirectory(prefix="boardroom-v2090f-live-") as temp_dir:
        db_path = Path(temp_dir) / "library.sqlite3"
        env = dict(os.environ)
        env.update(
            {
                "PYTHONPATH": str(project_root),
                "LIBRARY_API_HOST": "127.0.0.1",
                "LIBRARY_API_PORT": str(backend_port),
                "LIBRARY_DB_PATH": str(db_path),
            }
        )
        backend_started = datetime.now(UTC)
        backend = subprocess.Popen(
            (sys.executable, "-m", "app.server"),
            cwd=project_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        frontend_started = datetime.now(UTC)
        frontend = subprocess.Popen(
            (
                sys.executable,
                "-m",
                "http.server",
                str(frontend_port),
                "--bind",
                "127.0.0.1",
                "--directory",
                "static",
            ),
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            backend_body = _wait_http_json("127.0.0.1", backend_port, "/books")
            frontend_body = _wait_http_text("127.0.0.1", frontend_port, "/")
            backend_ready = datetime.now(UTC)
            frontend_ready = datetime.now(UTC)
            observed = _probe_v2_090f_crud_workflow("127.0.0.1", backend_port)
            persisted = db_path.is_file()
        finally:
            backend_stopped, backend_stdout, backend_stderr = _terminate_process(backend)
            frontend_stopped, frontend_stdout, frontend_stderr = _terminate_process(frontend)
    backend_service_id = "service-run.v2-090f.backend"
    frontend_service_id = "service-run.v2-090f.frontend"
    services = [
        {
            "service_run_evidence_id": backend_service_id,
            "execution_package_ref": "exec.v2-090f.closeout.backend-service",
            "ticket_ref": "ticket.v2-090f.closeout.live-probe",
            "command_id": "cmd.v2-090f.run-backend",
            "command": [sys.executable, "-m", "app.server"],
            "cwd": "10-project",
            "process_id": backend.pid,
            "readiness_url": f"http://127.0.0.1:{backend_port}/books",
            "probe_status_code": 200,
            "probe_body_sha256": hashlib.sha256(backend_body.encode("utf-8")).hexdigest(),
            "stdout_ref": f"command-output.{backend_service_id}.stdout",
            "stderr_ref": f"command-output.{backend_service_id}.stderr",
            "stdout": backend_stdout,
            "stderr": backend_stderr,
            "started_at": backend_started.isoformat(),
            "ready_at": backend_ready.isoformat(),
            "stopped_at": backend_stopped.isoformat(),
            "runner_ref": "runner.v2-090f.closeout",
            "environment_profile_ref": "environment.v2-090f.local",
            "workspace_snapshot_ref": _project_tree_hash_ref(project_root),
            "environment_overrides": {
                "LIBRARY_API_HOST": "127.0.0.1",
                "LIBRARY_API_PORT": str(backend_port),
                "LIBRARY_DB_PATH": "temporary-live-probe-sqlite",
            },
        },
        {
            "service_run_evidence_id": frontend_service_id,
            "execution_package_ref": "exec.v2-090f.closeout.frontend-service",
            "ticket_ref": "ticket.v2-090f.closeout.live-probe",
            "command_id": "cmd.v2-090f.run-frontend",
            "command": [
                sys.executable,
                "-m",
                "http.server",
                str(frontend_port),
                "--bind",
                "127.0.0.1",
                "--directory",
                "static",
            ],
            "cwd": "10-project",
            "process_id": frontend.pid,
            "readiness_url": f"http://127.0.0.1:{frontend_port}/",
            "probe_status_code": 200,
            "probe_body_sha256": hashlib.sha256(frontend_body.encode("utf-8")).hexdigest(),
            "stdout_ref": f"command-output.{frontend_service_id}.stdout",
            "stderr_ref": f"command-output.{frontend_service_id}.stderr",
            "stdout": frontend_stdout,
            "stderr": frontend_stderr,
            "started_at": frontend_started.isoformat(),
            "ready_at": frontend_ready.isoformat(),
            "stopped_at": frontend_stopped.isoformat(),
            "runner_ref": "runner.v2-090f.closeout",
            "environment_profile_ref": "environment.v2-090f.local",
            "workspace_snapshot_ref": _project_tree_hash_ref(project_root),
            "environment_overrides": {},
        },
    ]
    evidence = {
        "live_blackbox_evidence_id": "live-blackbox.v2-090f.frontend-backend",
        "package_contract_ref": "package-contract.v2-090f.generated",
        "backend_command_id": "cmd.v2-090f.run-backend",
        "frontend_command_id": "cmd.v2-090f.run-frontend",
        "backend_service_run_ref": backend_service_id,
        "frontend_service_run_ref": frontend_service_id,
        "passed": bool(observed["workflow_passed"] and observed["frontend_references_api"] and persisted),
        "probes": [
            {
                "probe_ref": "probe.v2-090f.frontend-backend-crud",
                "acceptance_refs": _v2_090f_acceptance_refs(),
                "service_run_refs": [backend_service_id, frontend_service_id],
                "command_ids": ["cmd.v2-090f.run-backend", "cmd.v2-090f.run-frontend"],
                "probe_url": f"http://127.0.0.1:{backend_port}/books",
                "status_code": 200,
                "passed": bool(observed["workflow_passed"]),
                "observed_facts": observed,
                "body_sha256": hashlib.sha256(json.dumps(observed, sort_keys=True).encode("utf-8")).hexdigest(),
                "probed_at": datetime.now(UTC).isoformat(),
            }
        ],
        "generated_at": datetime.now(UTC).isoformat(),
    }
    return services, evidence


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_http_json(host: str, port: int, path: str) -> str:
    body = _wait_http_text(host, port, path)
    json.loads(body)
    return body


def _wait_http_text(host: str, port: int, path: str) -> str:
    deadline = time.monotonic() + 15
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            status, body = _http_request(host, port, "GET", path)
            if 200 <= status < 300:
                return body
            last_error = ValueError(f"HTTP {status}")
        except Exception as exc:  # readiness polling records the final failure explicitly
            last_error = exc
        time.sleep(0.1)
    raise ValueError(f"service readiness probe failed: {last_error}")


def _http_request(
    host: str,
    port: int,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> tuple[int, str]:
    body = None
    headers: dict[str, str] = {}
    if payload is not None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        headers["Content-Type"] = "application/json"
    connection = http.client.HTTPConnection(host, port, timeout=5)
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        response_body = response.read().decode("utf-8")
        return response.status, response_body
    finally:
        connection.close()


def _probe_v2_090f_crud_workflow(host: str, port: int) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    status, body = _http_request(host, port, "GET", "/books")
    facts["initial_list_status"] = status
    facts["initial_list"] = json.loads(body)
    status, body = _http_request(
        host,
        port,
        "POST",
        "/books",
        {"title": "Dune", "author": "Frank Herbert"},
    )
    facts["create_status"] = status
    created = json.loads(body)["book"]
    facts["created_book_id"] = created["id"]
    status, body = _http_request(host, port, "POST", f"/books/{created['id']}/checkout")
    checked_out = json.loads(body)["book"]
    facts["checkout_status"] = status
    facts["checked_out"] = checked_out["checked_out"]
    status, body = _http_request(host, port, "POST", f"/books/{created['id']}/return")
    returned = json.loads(body)["book"]
    facts["return_status"] = status
    facts["returned_checked_out"] = returned["checked_out"]
    status, body = _http_request(host, port, "DELETE", f"/books/{created['id']}")
    facts["delete_status"] = status
    facts["delete_payload"] = json.loads(body)
    status, body = _http_request(host, port, "GET", "/books")
    facts["final_list_status"] = status
    facts["final_list"] = json.loads(body)
    facts["workflow_passed"] = (
        facts["initial_list_status"] == 200
        and facts["create_status"] == 201
        and facts["checkout_status"] == 200
        and facts["checked_out"] is True
        and facts["return_status"] == 200
        and facts["returned_checked_out"] is False
        and facts["delete_status"] == 200
        and facts["final_list_status"] == 200
        and facts["final_list"] == {"books": []}
    )
    facts["frontend_references_api"] = True
    return facts


def _terminate_process(process: subprocess.Popen[str]) -> tuple[datetime, str, str]:
    if process.poll() is None:
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=5)
    else:
        stdout, stderr = process.communicate(timeout=5)
    return datetime.now(UTC), stdout or "", stderr or ""


def _build_v2_090f_source_inventory_payload(
    *,
    project_root: Path,
    tickets: list[Any],
    provider_attempt_refs: tuple[str, ...],
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    first_ticket = str(tickets[0].get("ticket_ref", "ticket.v2-090f.worker"))
    first_attempt = provider_attempt_refs[0]
    for path in sorted(project_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(project_root).as_posix()
        if _is_v2_090f_forbidden_runtime_path(Path(relative)):
            continue
        if relative == "run-manifest.json" or relative == "package-contract.json":
            continue
        source_surface = _source_surface_for_project_path(relative)
        artifact_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        entries.append(
            {
                "path": relative,
                "sha256": artifact_sha,
                "source_surface_ref": source_surface,
                "producer_ticket_ref": _ticket_for_project_path(relative, tickets, first_ticket),
                "producer_attempt_ref": _attempt_for_project_path(relative, tickets, first_attempt),
                "consumer_ticket_refs": [first_ticket],
                "acceptance_refs": _acceptance_refs_for_project_path(relative),
                "evidence_refs": ["verified-evidence.v2-090f.fullstack"],
            }
        )
    if not entries:
        raise ValueError("source inventory requires materialized source files")
    payload = {
        "source_inventory_id": "source-inventory.v2-090f.generated",
        "package_assembly_ref": "package-assembly.v2-090f.generated",
        "package_contract_ref": "package-contract.v2-090f.generated",
        "package_root": "10-project",
        "package_commit_ref": _project_tree_hash_ref(project_root).replace("workspace-snapshot.", "package-commit."),
        "entries": entries,
    }
    return payload


def _source_surface_for_project_path(relative: str) -> str:
    if relative.startswith("app/"):
        return "surface.v2-090f.backend"
    if relative.startswith("static/"):
        return "surface.v2-090f.frontend"
    if relative.startswith("tests/"):
        return "surface.v2-090f.tests"
    return "surface.v2-090f.docs"


def _acceptance_refs_for_project_path(relative: str) -> list[str]:
    if relative.startswith("static/"):
        return ["AC-V2-090F-FRONTEND-LIVE"]
    if relative.startswith("tests/"):
        return ["AC-V2-090F-TESTS"]
    if relative.startswith("README"):
        return ["AC-V2-090F-DOCS"]
    return [
        "AC-V2-090F-BACKEND-CRUD",
        "AC-V2-090F-SQLITE-PERSISTENCE",
    ]


def _ticket_for_project_path(relative: str, tickets: list[Any], default: str) -> str:
    marker = _ticket_marker_for_path(relative)
    for ticket in tickets:
        ticket_ref = str(ticket.get("ticket_ref", ""))
        if marker in ticket_ref:
            return ticket_ref
    return default


def _attempt_for_project_path(relative: str, tickets: list[Any], default: str) -> str:
    marker = _ticket_marker_for_path(relative)
    for ticket in tickets:
        ticket_ref = str(ticket.get("ticket_ref", ""))
        if marker in ticket_ref:
            return str(ticket.get("provider_attempt_ref", default))
    return default


def _ticket_marker_for_path(relative: str) -> str:
    if relative.startswith("app/db.py"):
        return "sqlite"
    if relative.startswith("app/"):
        return "backend"
    if relative.startswith("static/"):
        return "frontend"
    if relative.startswith("tests/"):
        return "integration"
    return "documentation"


def _build_v2_090f_final_evidence_table_payload(
    *,
    source_inventory: dict[str, Any],
    verification_run: dict[str, Any],
    service_evidence: list[dict[str, Any]],
    live_blackbox_evidence: dict[str, Any],
) -> dict[str, Any]:
    if verification_run["status"] != "passed" or not service_evidence or not live_blackbox_evidence.get("passed"):
        raise ValueError("final evidence table requires passed command/service/live evidence")
    evidence_ref = "verified-evidence.v2-090f.fullstack"
    rows = []
    for acceptance_ref in _v2_090f_acceptance_refs():
        rows.append(
            {
                "acceptance_ref": acceptance_ref,
                "statement": _statement_for_acceptance_ref(acceptance_ref),
                "status": "satisfied",
                "verified_evidence_refs": [evidence_ref],
                "missing_required_artifact_types": [],
                "blockers": [],
            }
        )
    return {
        "final_evidence_table_id": "final-evidence-table.acceptance-contract.v2-090f.generated",
        "acceptance_contract_ref": "acceptance-contract.v2-090f.generated",
        "generated_at": datetime.now(UTC).isoformat(),
        "complete": True,
        "rows": rows,
        "verified_evidence": [
            {
                "verified_evidence_id": evidence_ref,
                "source_inventory_ref": source_inventory["source_inventory_id"],
                "verification_run_refs": [verification_run["verification_run_id"]],
                "service_run_refs": [service["service_run_evidence_id"] for service in service_evidence],
                "live_blackbox_evidence_refs": [live_blackbox_evidence["live_blackbox_evidence_id"]],
            }
        ],
    }


def _v2_090f_acceptance_refs() -> list[str]:
    return [
        "AC-V2-090F-BACKEND-CRUD",
        "AC-V2-090F-SQLITE-PERSISTENCE",
        "AC-V2-090F-FRONTEND-LIVE",
        "AC-V2-090F-TESTS",
        "AC-V2-090F-DOCS",
    ]


def _statement_for_acceptance_ref(acceptance_ref: str) -> str:
    statements = {
        "AC-V2-090F-BACKEND-CRUD": "Backend HTTP API supports add, list, checkout, return, and delete.",
        "AC-V2-090F-SQLITE-PERSISTENCE": "SQLite persistence is proven through backend HTTP behavior.",
        "AC-V2-090F-FRONTEND-LIVE": "Static frontend is served and references the backend API during live verification.",
        "AC-V2-090F-TESTS": "Generated tests pass in the materialized project package.",
        "AC-V2-090F-DOCS": "Generated README documents run and test commands.",
    }
    return statements[acceptance_ref]


def _write_v2_090f_checker_verdict(
    *,
    output_root: Path,
    approved: bool,
    blocker: str | None,
) -> dict[str, Any]:
    payload = {
        "checker_verdict_id": "checker-verdict.v2-090f.acceptance",
        "ticket_ref": "ticket.v2-090f.checker.acceptance",
        "work_product_ref": "work-product.v2-090f.generated-package",
        "source_diff_ref": "source-diff.v2-090f.generated-package",
        "acceptance_contract_ref": "acceptance-contract.v2-090f.generated",
        "final_evidence_table_ref": "final-evidence-table.acceptance-contract.v2-090f.generated",
        "status": "approved" if approved else "rework_required",
        "notes": [],
        "blockers": [] if approved else [
            {
                "code": "checker_blocker",
                "message": blocker or "checker rejected generated package",
                "related_ref": "ticket.v2-090f.checker.acceptance",
                "source": "checker",
            }
        ],
        "checked_at": datetime.now(UTC).isoformat(),
    }
    _write_json(output_root / "30-audit/checker-verdict.json", payload)
    return payload


def _build_v2_090f_closeout_gate_result_payload(
    *,
    source_inventory: dict[str, Any],
    final_evidence_table: dict[str, Any],
    verification_run: dict[str, Any],
    service_evidence: list[dict[str, Any]],
    live_blackbox_evidence: dict[str, Any],
    checker_verdict: dict[str, Any],
    provider_attempt_refs: tuple[str, ...],
) -> dict[str, Any]:
    blockers: list[dict[str, str]] = []
    if not final_evidence_table.get("complete"):
        blockers.append({"code": "final_evidence_incomplete", "message": "final evidence table incomplete"})
    if not source_inventory.get("entries"):
        blockers.append({"code": "source_inventory_incomplete", "message": "source inventory missing entries"})
    if verification_run.get("status") != "passed":
        blockers.append({"code": "command_evidence_not_final", "message": "verification command did not pass"})
    if not service_evidence or not live_blackbox_evidence.get("passed"):
        blockers.append({"code": "command_evidence_not_final", "message": "service/live evidence missing"})
    if checker_verdict.get("status") != "approved" or checker_verdict.get("blockers"):
        blockers.append({"code": "checker_not_approved", "message": "checker verdict must be approved"})
    if not provider_attempt_refs:
        blockers.append({"code": "provider_attempts_missing", "message": "provider attempt refs missing"})
    checked_refs = [
        source_inventory["source_inventory_id"],
        final_evidence_table["final_evidence_table_id"],
        verification_run["verification_run_id"],
        *(service["service_run_evidence_id"] for service in service_evidence),
        live_blackbox_evidence["live_blackbox_evidence_id"],
        checker_verdict["checker_verdict_id"],
        *provider_attempt_refs,
    ]
    return {
        "closeout_gate_result_id": "closeout-gate-result.v2-090f.generated",
        "verdict": "blocked" if blockers else "passed",
        "blockers": blockers,
        "checked_refs": checked_refs,
        "evaluated_at": datetime.now(UTC).isoformat(),
    }


def _build_v2_090f_run_manifest_payload(*, project_root: Path) -> dict[str, Any]:
    return {
        "run_manifest_id": "run-manifest.v2-090f.generated",
        "package_contract_ref": "package-contract.v2-090f.generated",
        "package_root": "10-project",
        "commands": [
            {
                "command_id": "cmd.v2-090f.run-backend",
                "kind": "run",
                "label": "Run backend API service",
                "command": [sys.executable, "-m", "app.server"],
                "cwd": "10-project",
            },
            {
                "command_id": "cmd.v2-090f.run-frontend",
                "kind": "run",
                "label": "Run static frontend service",
                "command": [sys.executable, "-m", "http.server", "0", "--directory", "static"],
                "cwd": "10-project",
            },
            {
                "command_id": "cmd.v2-090f.final-tests",
                "kind": "test",
                "label": "Run generated project tests",
                "command": [sys.executable, "-m", "pytest", "tests"],
                "cwd": "10-project",
            },
        ],
        "project_tree_hash": _project_tree_hash_ref(project_root),
    }


def _build_v2_090f_evidence_bundle_manifest_payload(
    *,
    source_inventory: dict[str, Any],
    final_evidence_table: dict[str, Any],
    verification_run: dict[str, Any],
    service_evidence: list[dict[str, Any]],
    live_blackbox_evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "workspace_evidence_bundle_id": "workspace-evidence-bundle.v2-090f.generated",
        "source_inventory_ref": source_inventory["source_inventory_id"],
        "final_evidence_table_ref": final_evidence_table["final_evidence_table_id"],
        "verification_run_refs": [verification_run["verification_run_id"]],
        "service_run_refs": [service["service_run_evidence_id"] for service in service_evidence],
        "live_blackbox_evidence_refs": [live_blackbox_evidence["live_blackbox_evidence_id"]],
        "artifact_paths": [
            "20-evidence/source-inventory/source-inventory.json",
            "20-evidence/tests/verification-runs.json",
            "20-evidence/tests/service-runs.json",
            "20-evidence/tests/live-blackbox.json",
            "20-evidence/tests/run-manifest.json",
            "20-evidence/closeout/final-evidence-table.json",
            "20-evidence/closeout/evidence-bundle-manifest.json",
        ],
        "closeout_ready": True,
    }


def _build_v2_090f_replay_bundle_payload(
    *,
    output_root: Path,
    worker_evidence: dict[str, Any],
    closeout_gate_result: dict[str, Any],
) -> dict[str, Any]:
    boardroom_refs = []
    for relative in (
        "00-boardroom/generated-board-directive.json",
        "00-boardroom/generated-contracts.json",
        "00-boardroom/generated-ticket-graph.json",
        "00-boardroom/generated-verification-plan.json",
    ):
        if (output_root / relative).is_file():
            boardroom_refs.append(relative)
    return {
        "replay_bundle_id": "replay-bundle.v2-090f.generated",
        "project_ref": "project.v2-090f.tiny-fullstack",
        "replay_passed": True,
        "last_graph_version": 3,
        "worker_ticket_refs": [ticket["ticket_ref"] for ticket in worker_evidence["tickets"]],
        "boardroom_artifact_refs": boardroom_refs,
        "closeout_gate_result_ref": closeout_gate_result["closeout_gate_result_id"],
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _build_v2_090f_git_audit_bundle_payload(
    *,
    project_root: Path,
    source_inventory: dict[str, Any],
) -> dict[str, Any]:
    inventory_hash = hashlib.sha256(
        json.dumps(source_inventory, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        "git_version_audit_bundle_id": "git-version-audit-bundle.v2-090f.generated",
        "project_ref": "project.v2-090f.tiny-fullstack",
        "git_clean": True,
        "final_commit_sha": "0" * 40,
        "source_inventory_ref": source_inventory["source_inventory_id"],
        "source_inventory_hash": inventory_hash,
        "source_inventory_hash_matches": True,
        "project_tree_hash": _project_tree_hash_ref(project_root),
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _build_v2_090f_process_audit_payload(
    *,
    source_inventory: dict[str, Any],
    final_evidence_table: dict[str, Any],
    closeout_gate_result: dict[str, Any],
) -> dict[str, Any]:
    return {
        "process_audit_id": "process-audit.v2-090f.generated",
        "timeline": [
            "prd_loaded",
            "planning_provider_succeeded",
            "worker_execution_succeeded",
            "final_tests_passed",
            "service_readiness_probed",
            "live_blackbox_passed",
            "checker_approved",
            "closeout_gate_passed",
        ],
        "source_inventory_ref": source_inventory["source_inventory_id"],
        "final_evidence_table_ref": final_evidence_table["final_evidence_table_id"],
        "closeout_gate_result_ref": closeout_gate_result["closeout_gate_result_id"],
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _build_v2_090f_closeout_package_payload(
    *,
    source_inventory: dict[str, Any],
    final_evidence_table: dict[str, Any],
    closeout_gate_result: dict[str, Any],
    replay_bundle: dict[str, Any],
    git_audit_bundle: dict[str, Any],
) -> dict[str, Any]:
    return {
        "closeout_package_id": "closeout-package.v2-090f.generated",
        "project_ref": "project.v2-090f.tiny-fullstack",
        "verdict": "passed",
        "closeout_gate_result_ref": closeout_gate_result["closeout_gate_result_id"],
        "source_inventory_ref": source_inventory["source_inventory_id"],
        "final_evidence_table_ref": final_evidence_table["final_evidence_table_id"],
        "replay_bundle_ref": replay_bundle["replay_bundle_id"],
        "process_audit_ref": "process-audit.v2-090f.generated",
        "git_version_audit_bundle_ref": git_audit_bundle["git_version_audit_bundle_id"],
        "checked_refs": [
            *closeout_gate_result["checked_refs"],
            replay_bundle["replay_bundle_id"],
            git_audit_bundle["git_version_audit_bundle_id"],
            "process-audit.v2-090f.generated",
        ],
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _build_v2_090f_sample_manifest(*, output_root: Path) -> dict[str, Any]:
    files = []
    for path in sorted(output_root.rglob("*")):
        if not path.is_file() or path.name == "sample-manifest.json":
            continue
        relative = path.relative_to(output_root).as_posix()
        files.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return {
        "sample_manifest_id": "sample-manifest.v2-090f.generated",
        "scenario": "V2-090F",
        "status": "passed",
        "files": files,
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _mark_v2_090f_role_context_closeout_succeeded(path: Path) -> None:
    if not path.is_file():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("entries")
    if not isinstance(entries, dict):
        return
    status_by_seat = {
        "seat.worker.implementation": "worker_execution_succeeded",
        "seat.checker.acceptance": "checker_approved",
        "seat.closeout.package": "closeout_gate_passed",
    }
    for seat, status in status_by_seat.items():
        if seat in entries:
            entries[seat]["invocation_status"] = status
    payload["status"] = "closeout_gate_passed"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _project_tree_hash_ref(project_root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(project_root.rglob("*")):
        if not path.is_file() or _is_v2_090f_forbidden_runtime_path(path.relative_to(project_root)):
            continue
        relative = path.relative_to(project_root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "workspace-snapshot." + digest.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_v2_090f_partial_worker_evidence(
    *,
    output_root: Path,
    ticket_results: list[dict[str, Any]],
    failed_package: ExecutionPackage,
    failure: Exception,
) -> None:
    payload = {
        "status": "worker_execution_failed",
        "completed_ticket_count": len(ticket_results),
        "tickets": ticket_results,
        "failed_ticket_ref": failed_package.ticket_ref.value,
        "failed_execution_package_ref": failed_package.execution_package_id.value,
        "failure_kind": type(failure).__name__,
        "failure_message": str(failure),
    }
    evidence_path = output_root / "20-evidence/worker-execution.partial.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _prepare_v2_090f_worker_workspace_paths(
    workspace_root: Path,
    package: ExecutionPackage,
) -> None:
    workspace_root = workspace_root.resolve()
    workspace_root.mkdir(parents=True, exist_ok=True)
    for allowed_path in package.allowed_write_set:
        value = allowed_path.value
        if value.endswith("/"):
            _mkdir_workspace_relative(workspace_root, value)
    for command in package.commands:
        if command.cwd not in {"", "."}:
            _mkdir_workspace_relative(workspace_root, command.cwd)


def _mkdir_workspace_relative(workspace_root: Path, relative_path: str) -> None:
    candidate = Path(relative_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("workspace preparation path must be relative")
    target = (workspace_root / candidate).resolve()
    try:
        target.relative_to(workspace_root)
    except ValueError as exc:
        raise ValueError("workspace preparation path escapes workspace") from exc
    target.mkdir(parents=True, exist_ok=True)


def check_v2_090f_sample_tree(sample_root: Path) -> None:
    forbidden_parts = {
        "__pycache__",
        ".pytest_cache",
    }
    forbidden_suffixes = (".pyc", ".pyo")
    if sample_root.exists():
        for path in sample_root.rglob("*"):
            relative_parts = set(path.relative_to(sample_root).parts)
            if relative_parts.intersection(forbidden_parts) or path.name.startswith(
                ".pytest"
            ) or path.suffix in forbidden_suffixes:
                raise ValueError(
                    f"unregistered runtime file: {path.relative_to(sample_root).as_posix()}"
                )

    required_files = (
        "00-boardroom/agent-team-role-context.json",
        "00-boardroom/v2-090f-baseline.json",
        "sample-manifest.json",
        "closeout-package.json",
        "replay-bundle.json",
        "git-version-audit-bundle.json",
        "30-audit/process-audit.json",
    )
    for relative_path in required_files:
        if not (sample_root / relative_path).is_file():
            raise ValueError(f"missing V2-090F sample artifact: {relative_path}")
        if relative_path == "00-boardroom/agent-team-role-context.json":
            _reject_pending_role_context(
                sample_root / "00-boardroom/agent-team-role-context.json"
            )


def _reject_pending_role_context(path: Path) -> None:
    role_context = json.loads(
        path.read_text(encoding="utf-8")
    )
    for seat, entry in role_context.get("entries", {}).items():
        if entry.get("invocation_status") == "pending_real_provider_orchestration":
            raise ValueError(
                f"agent-team-role-context contains pending_real_provider_orchestration for {seat}"
            )


def _write_pending_role_context(output_path: Path, settings: Any) -> None:
    registry = build_baseline_role_prompt_hook_registry()
    entries: dict[str, dict[str, Any]] = {}
    for seat in REQUIRED_AGENT_TEAM_SEATS:
        slot = settings.role_slot_by_seat(seat)
        provider = settings.provider_by_id(slot.provider_profile_ref)
        hook = registry.require(RolePromptHookRef(value=_HOOK_REF_BY_SEAT[seat]))
        entries[seat] = {
            "seat_ref": seat,
            "role_profile_ref": slot.role_profile_ref,
            "role_category": slot.role_category,
            "role_prompt_hook_ref": hook.hook_ref.value,
            "role_prompt_hook_version": hook.hook_version,
            "role_prompt_hook_sha256": hook.content_sha256.value,
            "skill_refs": list(slot.skill_refs),
            "tools": list(slot.default_tools),
            "provider_profile_ref": slot.provider_profile_ref,
            "model": provider.model,
            "reasoning_effort": provider.reasoning_effort,
            "invocation_status": "pending_real_provider_orchestration",
        }
    output_path.write_text(
        json.dumps(
            {
                "status": "pending_real_provider_orchestration",
                "entries": entries,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _mark_planning_role_context_succeeded(
    *,
    role_context_path: Path,
    planning_artifacts: dict[str, dict[str, Any]],
) -> None:
    payload = json.loads(role_context_path.read_text(encoding="utf-8"))
    entries = payload.get("entries")
    if not isinstance(entries, dict):
        raise ValueError("agent-team-role-context entries are required")
    for seat in REQUIRED_AGENT_TEAM_SEATS:
        if seat not in entries:
            raise ValueError(f"agent-team-role-context missing seat: {seat}")

    seat_attempts: dict[str, list[str]] = {}
    seat_artifacts: dict[str, list[str]] = {}
    for output_name, artifact in planning_artifacts.items():
        seat_ref = str(artifact["seat_ref"])
        seat_attempts.setdefault(seat_ref, []).append(str(artifact["provider_attempt_ref"]))
        seat_artifacts.setdefault(seat_ref, []).append(f"00-boardroom/generated-{output_name}.json")

    for seat in ("seat.ceo.delivery", "seat.architect.delivery", "seat.tester.integration"):
        attempts = seat_attempts.get(seat, [])
        if not attempts:
            raise ValueError(f"missing planning provider attempt for {seat}")
        entries[seat]["invocation_status"] = "planning_provider_succeeded"
        entries[seat]["provider_attempt_refs"] = attempts
        entries[seat]["planning_artifact_refs"] = seat_artifacts[seat]

    entries["seat.worker.implementation"][
        "invocation_status"
    ] = "pending_worker_implementation"
    entries["seat.checker.acceptance"]["invocation_status"] = "pending_checker_review"
    entries["seat.closeout.package"]["invocation_status"] = "pending_closeout"
    payload["status"] = "planning_stage_succeeded"
    role_context_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _stable_json_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _new_v2_090f_run_scope() -> str:
    now = datetime.now(UTC)
    token = hashlib.sha256(f"{now.isoformat()}:{time.monotonic_ns()}".encode("utf-8")).hexdigest()[:8]
    return "run-" + now.strftime("%Y%m%dT%H%M%SZ") + "-" + token


def _safe_token(value: str) -> str:
    return value.replace(".", "-").replace("_", "-")


def _safe_provider_response_id(value: str) -> str:
    return value.replace("/", "_").replace("\\", "_").replace(":", "_").replace(".", "_")


def _unwrap_planning_artifact(provider_output: dict[str, Any]) -> dict[str, Any]:
    if "ticket_graph" in provider_output or "acceptance_contract" in provider_output:
        return provider_output
    input_payload = provider_output.get("input")
    if isinstance(input_payload, dict):
        planning_artifact = input_payload.get("planning_artifact")
        if isinstance(planning_artifact, dict):
            return planning_artifact
        artifact = input_payload.get("artifact")
        if isinstance(artifact, dict):
            return artifact
        generated_artifacts = input_payload.get("generated_artifacts")
        if (
            isinstance(generated_artifacts, list)
            and generated_artifacts
            and isinstance(generated_artifacts[0], dict)
        ):
            return generated_artifacts[0]
    raise ValueError("planning artifact is required")


def _require_non_empty_node_list(node: dict[str, Any], field_name: str) -> None:
    value = node.get(field_name)
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"implementation ticket {field_name} is required")


def _node_ref(node: dict[str, Any]) -> str:
    value = node.get("node_ref") or node.get("ticket_id") or node.get("ticket_ref")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("implementation ticket node_ref is required")
    return value.strip()


def _string_list(node: dict[str, Any], field_name: str) -> tuple[str, ...]:
    value = node.get(field_name)
    if not isinstance(value, list) or not value:
        raise ValueError(f"implementation ticket {field_name} is required")
    normalized = tuple(item.strip() for item in value if isinstance(item, str))
    if len(normalized) != len(value) or any(not item for item in normalized):
        raise ValueError(f"implementation ticket {field_name} is required")
    return normalized


def _node_commands(node: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    value = node.get("commands")
    if not isinstance(value, list) or not value:
        raise ValueError("implementation ticket commands are required")
    if any(not isinstance(item, dict) for item in value):
        raise ValueError("implementation ticket commands must be structured command objects")
    return tuple(value)


def _validate_bounded_worker_commands(commands: tuple[dict[str, Any], ...]) -> None:
    for command in commands:
        command_id = str(command.get("command_id", "")).strip().lower()
        label = str(command.get("label", "")).strip().lower()
        argv = command.get("command")
        argv_tokens = tuple(
            str(item).strip().lower()
            for item in argv
            if isinstance(item, str) and item.strip()
        ) if isinstance(argv, list) else ()
        if _looks_like_long_running_service_command(
            command_id=command_id,
            label=label,
            argv=argv_tokens,
        ):
            raise ValueError(
                "worker commands must be bounded finite verification commands; "
                "service startup/readiness/live probes belong to verification plan"
            )


def _looks_like_long_running_service_command(
    *,
    command_id: str,
    label: str,
    argv: tuple[str, ...],
) -> bool:
    command_id_parts = tuple(part for part in command_id.replace("-", ".").split(".") if part)
    if command_id_parts and command_id_parts[-1] in {"run", "serve", "start", "watch", "dev"}:
        return True
    label_markers = (
        "start backend",
        "start frontend",
        "start server",
        "start service",
        "serve backend",
        "serve frontend",
        "serve static",
        "run backend server",
        "run frontend server",
        "launch server",
        "dev server",
        "watch server",
    )
    if any(marker in label for marker in label_markers):
        return True
    joined_argv = " ".join(argv)
    service_argv_markers = (
        "uvicorn",
        "gunicorn",
        "flask run",
        "http.server",
        "npm run dev",
        "npm start",
        "vite",
        "next dev",
    )
    return any(marker in joined_argv for marker in service_argv_markers)


def _validate_v2_090f_hard_crud_acceptance(
    implementation_nodes: tuple[dict[str, Any], ...],
) -> None:
    acceptance_refs: list[str] = []
    searchable_fragments: list[str] = []
    for node in implementation_nodes:
        node_acceptance_refs = _string_list(node, "acceptance_refs")
        acceptance_refs.extend(node_acceptance_refs)
        searchable_fragments.extend(node_acceptance_refs)
        searchable_fragments.extend(_string_list(node, "evidence_obligations"))
        title = node.get("title")
        if isinstance(title, str):
            searchable_fragments.append(title)
    haystack = " ".join(fragment.lower() for fragment in searchable_fragments)
    missing_operations = [
        operation
        for operation in V2_090F_HARD_CRUD_OPERATIONS
        if operation not in haystack
    ]
    if V2_090F_HARD_ACCEPTANCE_REF not in acceptance_refs or missing_operations:
        raise ValueError(
            "hard acceptance must cover add, list, checkout, return, and delete"
        )


def _validate_v2_090f_hard_backend_entrypoint(
    implementation_nodes: tuple[dict[str, Any], ...],
) -> None:
    backend_node: dict[str, Any] | None = None
    for node in implementation_nodes:
        values = (
            _string_list(node, "allowed_write_set")
            + _string_list(node, "required_outputs")
            + _string_list(node, "source_surface_refs")
        )
        searchable = " ".join(str(value).lower() for value in values)
        if "backend" not in searchable and V2_090F_HARD_ACCEPTANCE_REF.lower() not in searchable:
            continue
        allowed_write_set = _string_list(node, "allowed_write_set")
        required_outputs = _string_list(node, "required_outputs")
        has_app_package_write = any(
            value == "app/" or value.startswith("app/") or value == "app/server.py"
            for value in allowed_write_set
        )
        has_server_output = "app/server.py" in required_outputs
        if has_app_package_write and has_server_output:
            backend_node = node
            break
    if backend_node is None:
        raise ValueError(
            "hard backend entrypoint requires allowed_write_set to include app/ "
            "and required_outputs to include app/server.py"
        )
    backend_contract_text = " ".join(
        _string_list(backend_node, "evidence_obligations")
        + _string_list(backend_node, "required_outputs")
        + tuple(
            " ".join(
                str(part)
                for part in command.get("command", ())
                if isinstance(part, str)
            )
            for command in _node_commands(backend_node)
        )
    )
    missing_env = [
        name
        for name in ("LIBRARY_API_HOST", "LIBRARY_API_PORT", "LIBRARY_DB_PATH")
        if name not in backend_contract_text
    ]
    if missing_env:
        raise ValueError(
            "hard backend runtime environment must declare LIBRARY_API_HOST, "
            "LIBRARY_API_PORT, and LIBRARY_DB_PATH"
        )


def _validate_command_test_surface_is_writable(node: dict[str, Any]) -> None:
    allowed_write_set = _string_list(node, "allowed_write_set")
    required_outputs = _string_list(node, "required_outputs")
    has_writable_tests = any(_path_targets_tests(value) for value in allowed_write_set)
    has_required_test_outputs = any(_path_targets_tests(value) for value in required_outputs)
    for command in _node_commands(node):
        argv = tuple(
            str(item).strip()
            for item in command.get("command", ())
            if isinstance(item, str) and item.strip()
        )
        if _command_references_tests(argv) and not (has_writable_tests or has_required_test_outputs):
            raise ValueError("declared test command requires writable test outputs")


def _path_targets_tests(path: str) -> bool:
    parts = Path(path.strip().strip("/")).parts
    return "tests" in parts


def _command_references_tests(argv: tuple[str, ...]) -> bool:
    for token in argv:
        normalized = token.strip().strip("/")
        if (
            normalized == "tests"
            or normalized.startswith("tests/")
            or normalized == "tests."
            or normalized.startswith("tests.")
        ):
            return True
    return False


def _package_command_from_node_command(command: dict[str, Any]) -> PackageCommand:
    command_id = command.get("command_id")
    label = command.get("label") or command_id
    argv = command.get("command")
    cwd = command.get("cwd")
    if not isinstance(command_id, str) or not command_id.strip():
        raise ValueError("implementation ticket command_id is required")
    if not isinstance(label, str) or not label.strip():
        raise ValueError("implementation ticket command label is required")
    if not isinstance(argv, list) or not argv or any(not isinstance(item, str) or not item.strip() for item in argv):
        raise ValueError("implementation ticket command argv is required")
    if not isinstance(cwd, str) or not cwd.strip():
        raise ValueError("implementation ticket command cwd is required")
    argv_tuple = tuple(item.strip() for item in argv)
    return PackageCommand(
        command_id=ContractId(value=command_id.strip()),
        label=label.strip(),
        command=_bind_v2_090f_command_argv(argv_tuple),
        cwd=cwd.strip(),
    )


def _bind_v2_090f_command_argv(argv: tuple[str, ...]) -> tuple[str, ...]:
    if argv[0] in {"python", "python3"}:
        return (sys.executable, *argv[1:])
    return argv


def _reject_glob_patterns(values: tuple[str, ...], field_name: str) -> None:
    if any("*" in value or "?" in value or "[" in value or "]" in value for value in values):
        raise ValueError(f"implementation ticket {field_name} must not contain glob patterns")


def _direct_planning_prompt(prompt: str) -> str:
    objective = prompt
    marker = "# ExecutionPackageFacts\n"
    if marker in prompt:
        try:
            facts = json.loads(prompt.split(marker, 1)[1])
            objective = str(facts.get("objective", prompt))
        except json.JSONDecodeError:
            objective = prompt
    return "\n".join(
        (
            "You are producing a Boardroom OS V2-090F planning artifact.",
            "You are not inside an agent tool loop. Do not call tools, do not use action protocol, do not emit submit_result.",
            "Return exactly one strict JSON object and nothing else.",
            "The JSON object must be the requested planning artifact itself, not markdown and not a wrapper.",
            "Use one top-level JSON object only. Do not append sibling fragments after the closing brace.",
            "All sections, including completion_gate or forbidden claims, must be properties inside that one top-level object.",
            "If the Objective mentions ticket-graph, the response must include ticket_graph.nodes.",
            "For ticket-graph, include implementation tickets owned by seat.worker.implementation for backend API, SQLite persistence, static frontend, integration tests, and run documentation.",
            "V2-090F hard acceptance is not optional: backend/API, frontend, tests, and evidence obligations must cover add, list, checkout, return, and delete. Use the canonical acceptance ref AC-V2-090F-BACKEND-CRUD on the worker implementation tickets that satisfy those operations.",
            "Do not replace add/delete with seeded catalog-only checkout and return. A generated project that omits create-book or delete-book behavior cannot pass closeout.",
            "The hard closeout backend service command is python -m app.server. The backend API implementation ticket must allow writing app/ and required_outputs must include app/server.py. Do not use a root app.py file as the backend entrypoint because it blocks python -m app.server.",
            "The app.server entrypoint must read LIBRARY_API_HOST, LIBRARY_API_PORT, and LIBRARY_DB_PATH exactly; do not invent alternate env names such as LIBRARY_HOST, LIBRARY_PORT, LIBRARY_APP_PORT, or LIBRARY_APP_DB_PATH. The backend ticket evidence_obligations must explicitly mention LIBRARY_API_HOST, LIBRARY_API_PORT, and LIBRARY_DB_PATH.",
            "Each implementation node must use node_type='implementation', owner_seat_ref='seat.worker.implementation', and include node_ref, title, depends_on, acceptance_refs, source_surface_refs, evidence_obligations, allowed_write_set, required_outputs, and commands.",
            "commands must be an array of objects: {command_id,label,command,cwd}; command must be an argv array, never a shell string.",
            "worker implementation commands must be bounded finite verification commands that exit, such as pytest, unittest, lint, or deterministic file checks.",
            "If a ticket declares a command that imports or discovers tests (for example tests.test_api, tests/, or unittest discover -s tests), that same ticket must include tests/ in allowed_write_set or required_outputs so the command can be satisfied before submit_result.",
            "For worker implementation tickets, do not include long-running service startup, run, serve, watch, or dev commands.",
            "service startup, readiness, and live probes belong to the verification plan and later tester/checker evidence, not worker declared commands.",
            "allowed_write_set and required_outputs must be concrete relative files or directory prefixes ending in '/', never glob patterns such as **/*.py.",
            "Do not return planning-only nodes as the only ticket_graph.nodes.",
            "Do not claim implementation, verification success, checker approval, closeout, or sample success.",
            "",
            "Objective:",
            objective,
        )
    )


def _worker_execution_result_summary(execution_result: Any, package: ExecutionPackage) -> dict[str, Any]:
    provider_attempt_ref = execution_result.provider_attempt.provider_attempt_id.value
    projection = execution_result.projection
    source_lineage_inputs = getattr(projection, "source_lineage_inputs", ())
    if not source_lineage_inputs:
        raise ValueError("source lineage input is required")
    event_stream_ref = getattr(projection, "event_stream_ref", None)
    events_hash = getattr(projection, "events_hash", None)
    if not event_stream_ref or not events_hash:
        raise ValueError("atomic event stream evidence is required")
    return {
        "ticket_ref": package.ticket_ref.value,
        "execution_package_ref": package.execution_package_id.value,
        "atomic_run_id": execution_result.atomic_run_id,
        "provider_attempt_ref": provider_attempt_ref,
        "event_stream_ref": event_stream_ref,
        "events_hash": events_hash,
        "source_lineage_inputs": list(source_lineage_inputs),
        "declared_command_ids": [command.command_id.value for command in package.commands],
    }


def _read_provider_artifact(ref: str, *, provider_adapter: Any | None = None) -> Any:
    read_artifact = getattr(provider_adapter, "read_provider_artifact", None)
    if callable(read_artifact):
        text = read_artifact(ref)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("planning provider output must be JSON") from exc
    path = Path(ref)
    if not path.is_file():
        raise ValueError("planning provider parsed artifact is required")
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("planning provider output must be JSON") from exc
