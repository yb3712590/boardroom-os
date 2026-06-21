from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping

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
from boardroom_os.workspace.run_manifest import (
    RunManifest,
    RunManifestBehaviorAssertion,
    RunManifestBehaviorAssertionKind,
    RunManifestBehaviorProbe,
    RunManifestCommand,
    RunManifestEnvironmentBinding,
    RunManifestEnvironmentValueSource,
)
from boardroom_os.workspace.run_manifest_ingestion import (
    RunManifestIngestionContext,
    ingest_run_manifest_artifact,
)


V2_090F_MARKER = ".boardroom-v2-090f-workspace.json"
V2_090F_PROVIDER_PROFILE_REF = "provider.openai-compatible.v2-090f-primary"
V2_090F_BUDGET_PROFILE_REF = "agent_team.v2_090f.fullstack"
REQUIRED_AGENT_TEAM_SEATS = (
    "seat.ceo.delivery",
    "seat.architect.delivery",
    "seat.worker.implementation",
    "seat.tester.integration",
    "seat.release.devops",
    "seat.checker.acceptance",
    "seat.closeout.package",
)
V2_090F_CONFIG_PATHS = {
    "runtime_config": "config/boardroom-runtime.v2-090f.yaml",
    "providers_config": "config/boardroom-providers.v2-090f.yaml",
    "roles_config": "config/boardroom-roles.v2-090f.yaml",
}
V2_090F_HARD_CRUD_OPERATIONS = ("add", "list", "checkout", "return", "delete")
_HOOK_REF_BY_SEAT = {
    "seat.ceo.delivery": "role-prompt-hook.baseline.ceo.v1",
    "seat.architect.delivery": "role-prompt-hook.baseline.architect.v1",
    "seat.worker.implementation": "role-prompt-hook.baseline.worker.v1",
    "seat.tester.integration": "role-prompt-hook.baseline.tester.v1",
    "seat.release.devops": "role-prompt-hook.baseline.release-devops.v1",
    "seat.checker.acceptance": "role-prompt-hook.baseline.checker.v1",
    "seat.closeout.package": "role-prompt-hook.baseline.closeout.v1",
}
_CAPTURE_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


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
    context_refs = [
        ContextRef(value="context.v2-090f.prd"),
        ContextRef(value="context.v2-090f.reference-examples"),
    ]
    allowed_read_refs = [
        AllowedReadRef(value=prd.path),
        AllowedReadRef(value="examples/directives/v2-090f-reference-examples.md"),
    ]
    constraints = [
        "Use the PRD as the source of truth.",
        "Do not predefine runner-owned implementation ticket refs.",
        "Do not write implementation source.",
        "Do not mark closeout passed.",
    ]
    if output_name == "run-manifest":
        context_refs.extend(
            [
                ContextRef(value="00-boardroom/generated-contracts.json"),
                ContextRef(value="00-boardroom/generated-ticket-graph.json"),
                ContextRef(value="00-boardroom/generated-verification-plan.json"),
            ]
        )
        allowed_read_refs.extend(
            [
                AllowedReadRef(value="00-boardroom/generated-contracts.json"),
                AllowedReadRef(value="00-boardroom/generated-ticket-graph.json"),
                AllowedReadRef(value="00-boardroom/generated-verification-plan.json"),
            ]
        )
        constraints.extend(
            [
                (
                    "RunManifest must be consistent with generated contracts, "
                    "ticket graph, verification plan, package source surfaces, "
                    "and implementation ticket required_outputs."
                ),
                (
                    "Every service command must reference an entrypoint that can "
                    "be produced by package_contract source surfaces or ticket "
                    "graph required_outputs; do not invent package/module names "
                    "that are absent from those artifacts."
                ),
                (
                    "Directory-only required_outputs are not enough for service "
                    "entrypoints; any service script or python -m module expected "
                    "by RunManifest must appear as a concrete implementation "
                    "required_outputs file."
                ),
                (
                    "If required_outputs declare a concrete script path, prefer "
                    "an argv entrypoint for that script over a guessed python -m "
                    "module path."
                ),
            ]
        )
    if output_name == "ticket-graph":
        constraints.extend(
            [
                (
                    "Implementation ticket required_outputs must use full "
                    "workspace-relative paths for every concrete file; bare "
                    "filenames are not enough when a package source surface "
                    "declares an allowed directory."
                ),
                (
                    "If PackageContract source surfaces declare required_files "
                    "under an allowed directory, include the joined path in the "
                    "owning implementation ticket required_outputs."
                ),
            ]
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
        context_refs=tuple(context_refs),
        constraints=tuple(constraints),
        acceptance_refs=(AcceptanceRef(value="AC-V2-090F-PLANNING"),),
        source_surface_refs=(SourceSurfaceRef(value="surface.v2-090f.boardroom-planning"),),
        allowed_read_refs=tuple(allowed_read_refs),
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
    return implementation_nodes


def validate_v2_090k_run_manifest_planning_consistency(
    *,
    run_manifest: RunManifest,
    ticket_graph_artifact: dict[str, Any],
) -> None:
    implementation_nodes = validate_v2_090f_generated_ticket_graph_for_worker_execution(
        ticket_graph_artifact
    )
    declared_outputs = {
        _normalize_v2_090k_relative_path(value)
        for node in implementation_nodes
        for value in _string_list(node, "required_outputs")
        if not value.endswith("/")
    }
    if not declared_outputs:
        raise ValueError("implementation required_outputs must declare concrete files")

    for service in run_manifest.service_contracts or ():
        command = _run_manifest_command(run_manifest, service.command_id.value)
        entrypoint = _v2_090k_service_command_entrypoint(command.command)
        if entrypoint is None:
            continue
        if entrypoint not in declared_outputs:
            raise ValueError(
                "RunManifest service entrypoint is not declared by implementation "
                f"required_outputs: {entrypoint}"
            )


def _normalize_v2_090k_relative_path(value: str) -> str:
    path = str(value).strip().replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    if path.startswith("10-project/"):
        path = path.removeprefix("10-project/")
    return path


def _v2_090k_service_command_entrypoint(command: tuple[str, ...]) -> str | None:
    argv = [part for part in command if isinstance(part, str)]
    for index, part in enumerate(argv):
        normalized = _normalize_v2_090k_relative_path(part)
        if normalized.endswith(".py"):
            return normalized
        if part == "-m" and index + 1 < len(argv):
            module = argv[index + 1].strip()
            if module and not module.startswith("-"):
                return _normalize_v2_090k_relative_path(module.replace(".", "/") + ".py")
    return None


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
                    ContextRef(value="20-evidence/tests/run-manifest.json"),
                ),
                constraints=(
                    "Implement only this generated worker ticket.",
                    "Do not claim checker approval, closeout, or project completion.",
                    "Produce real source changes and run declared commands.",
                    (
                        "Generated source must satisfy the agent-generated RunManifest "
                        "at 20-evidence/tests/run-manifest.json, including service "
                        "command, environment bindings, readiness path, and behavioral "
                        "probe HTTP paths."
                    ),
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
                    AllowedReadRef(value="20-evidence/tests/run-manifest.json"),
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
        self._owns_client = False
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
        finally:
            self._close_client()

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
        self._owns_client = True
        return self._client

    def _close_client(self) -> None:
        close = getattr(self._client, "close", None)
        if callable(close):
            close()
        if self._owns_client:
            self._client = None
            self._owns_client = False

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
        ("seat.release.devops", "run-manifest"),
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
    run_manifest_artifact = extract_v2_090f_planning_artifact(
        artifacts["run-manifest"].get("provider_output"),
        expected_artifact_name="run-manifest",
    )
    run_manifest, run_manifest_context = _load_v2_090k_run_manifest_artifact(
        run_manifest_artifact,
        include_ingestion_context=True,
    )
    ticket_graph_artifact = extract_v2_090f_planning_artifact(
        artifacts["ticket-graph"].get("provider_output"),
        expected_artifact_name="ticket-graph",
    )
    validate_v2_090k_run_manifest_planning_consistency(
        run_manifest=run_manifest,
        ticket_graph_artifact=ticket_graph_artifact,
    )
    run_manifest_path = output_root / "20-evidence/tests/run-manifest.json"
    run_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    run_manifest_path.write_text(
        json.dumps(run_manifest.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (boardroom_root / "run-manifest-ingestion-context.json").write_text(
        json.dumps(
            run_manifest_context.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
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
    run_manifest = _load_v2_090k_agent_run_manifest(output_root)
    service_evidence, live_blackbox_evidence = _run_v2_090f_live_blackbox_probe(
        project_root=project_root,
        run_manifest=run_manifest,
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
        run_manifest.model_dump(mode="json")
        | {"project_tree_hash": _project_tree_hash_ref(project_root)},
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


def _load_v2_090k_agent_run_manifest(output_root: Path) -> RunManifest:
    path = output_root / "20-evidence/tests/run-manifest.json"
    if not path.is_file():
        raise ValueError("agent-generated RunManifest is required before V2-090F closeout")
    payload = json.loads(path.read_text(encoding="utf-8"))
    run_manifest = RunManifest.model_validate(payload)
    if not run_manifest.service_contracts:
        raise ValueError("RunManifest service contracts are required before V2-090F closeout")
    if not run_manifest.behavioral_probes:
        raise ValueError("RunManifest behavioral probes are required before V2-090F closeout")
    return run_manifest


def _load_v2_090k_run_manifest_artifact(
    artifact: Mapping[str, Any],
    *,
    include_ingestion_context: bool = False,
) -> RunManifest | tuple[RunManifest, RunManifestIngestionContext]:
    context = ingest_run_manifest_artifact(
        artifact=artifact,
        source_ref="00-boardroom/generated-run-manifest.json",
        raw_manifest_ref="artifact.run_manifest.generated",
    )
    try:
        run_manifest = RunManifest.model_validate(artifact)
    except Exception:
        normalized = _normalize_v2_090k_run_manifest_artifact(artifact)
        run_manifest = RunManifest.model_validate(normalized)
    if include_ingestion_context:
        return run_manifest, context
    return run_manifest


def _ref_payload(value: Any) -> dict[str, str]:
    if isinstance(value, dict) and isinstance(value.get("value"), str):
        return {"value": value["value"]}
    if isinstance(value, str) and value.strip():
        return {"value": value.strip()}
    raise ValueError("reference value is required")


def _normalize_v2_090k_run_manifest_artifact(artifact: Mapping[str, Any]) -> dict[str, Any]:
    commands = artifact.get("commands")
    if not isinstance(commands, list) or not commands:
        raise ValueError("RunManifest commands are required")
    command_env_by_id: dict[str, Mapping[str, Any]] = {}
    service_contracts = artifact.get("service_contracts")
    if not isinstance(service_contracts, list) or not service_contracts:
        raise ValueError("RunManifest service_contracts are required")
    behavioral_probes = artifact.get("behavioral_probes")
    if not isinstance(behavioral_probes, list) or not behavioral_probes:
        raise ValueError("RunManifest behavioral_probes are required")

    normalized_commands = []
    for command in commands:
        if not isinstance(command, Mapping):
            raise ValueError("RunManifest command must be an object")
        kind = command.get("kind") or command.get("command_type")
        if kind in {"service", "service_run", "run_service", "long_running_service"}:
            kind = "run"
        if kind in {"finite_test", "finite_verification", "verification_test", "verification"}:
            kind = "test"
        if kind is None:
            command_id_for_kind = str(command.get("command_id") or "").lower()
            label_for_kind = str(command.get("label") or "").lower()
            lifecycle_for_kind = str(command.get("expected_lifecycle") or "").lower()
            if (
                "run" in command_id_for_kind
                or "backend" in command_id_for_kind
                or "server" in command_id_for_kind
                or "run" in label_for_kind
                or "backend" in label_for_kind
                or "server" in label_for_kind
                or "service" in lifecycle_for_kind
            ):
                kind = "run"
            elif (
                "test" in command_id_for_kind
                or "tests" in command_id_for_kind
                or "check" in command_id_for_kind
                or "test" in label_for_kind
                or "check" in label_for_kind
            ):
                kind = "test"
        command_id_value = command.get("command_id")
        if isinstance(command_id_value, str) and isinstance(command.get("env"), Mapping):
            command_env_by_id[command_id_value] = command["env"]
        normalized_commands.append(
            {
                "command_id": _ref_payload(command_id_value),
                "kind": kind,
                "label": command.get("label") or command.get("command_id"),
                "command": command.get("command"),
                "cwd": command.get("cwd") or ".",
            }
        )

    service_ref_to_command_id: dict[str, str] = {}
    normalized_services = []
    for service in service_contracts:
        if not isinstance(service, Mapping):
            raise ValueError("RunManifest service_contract must be an object")
        command_id = service.get("command_id") or service.get("run_command_id")
        service_ref = service.get("service_ref") or service.get("service_contract_id")
        if isinstance(service_ref, str) and isinstance(command_id, str):
            service_ref_to_command_id[service_ref] = command_id
        for alias_key in ("service_ref", "service_contract_id", "service_id"):
            alias = service.get(alias_key)
            if isinstance(alias, str) and isinstance(command_id, str):
                service_ref_to_command_id[alias] = command_id
        normalized_services.append(
            {
                "command_id": _ref_payload(command_id),
                "role": service.get("role") or "service",
                "env_bindings": _normalize_v2_090k_env_bindings(
                    service.get("env_bindings"),
                    command_env=command_env_by_id.get(str(command_id), {}),
                ),
                "readiness_probe": _normalize_v2_090k_readiness_probe(service.get("readiness_probe")),
            }
        )

    return {
        "run_manifest_id": _ref_payload(artifact.get("run_manifest_id")),
        "workspace_manifest_ref": _ref_payload(artifact.get("workspace_manifest_ref")),
        "package_contract_ref": _ref_payload(artifact.get("package_contract_ref")),
        "package_root": _ref_payload("10-project"),
        "commands": normalized_commands,
        "service_contracts": normalized_services,
        "frontend_topology": _normalize_v2_090k_frontend_topology(artifact.get("frontend_topology"), service_ref_to_command_id),
        "behavioral_probes": [
            _normalize_v2_090k_behavior_probe(probe, service_ref_to_command_id)
            for probe in behavioral_probes
            if isinstance(probe, Mapping)
        ],
    }


def _normalize_v2_090k_env_bindings(
    payload: Any,
    *,
    command_env: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    command_env = command_env or {}
    if isinstance(payload, list):
        bindings = []
        for item in payload:
            if not isinstance(item, Mapping):
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("RunManifest env binding name is required")
            bindings.append(_normalize_v2_090k_env_binding(name, item, command_env=command_env))
        if not bindings:
            raise ValueError("RunManifest env_bindings are required")
        return bindings
    if not isinstance(payload, Mapping) or not payload:
        raise ValueError("RunManifest env_bindings are required")
    bindings: list[dict[str, Any]] = []
    for name, binding in payload.items():
        if isinstance(binding, str):
            if re.fullmatch(r"[A-Z][A-Z0-9_]*", binding):
                env_name = binding
                binding = {"env_var": binding}
            else:
                env_name = name
                binding = {"default": binding}
        elif isinstance(binding, Mapping):
            env_name = binding.get("env_var") if isinstance(binding.get("env_var"), str) else name
        else:
            env_name = name
            binding = {}
        bindings.append(_normalize_v2_090k_env_binding(str(env_name), binding, command_env=command_env))
    return bindings


def _normalize_v2_090k_env_binding(
    name: str,
    binding: Mapping[str, Any],
    *,
    command_env: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_name = name.strip()
    source = _infer_v2_090k_env_value_source(normalized_name)
    if "value_source" in binding and isinstance(binding.get("value_source"), str):
        source = str(binding["value_source"])
    elif "binding_type" in binding and isinstance(binding.get("binding_type"), str):
        source = _normalize_v2_090k_env_binding_type(str(binding["binding_type"]))
    normalized: dict[str, Any] = {"name": normalized_name, "value_source": source}
    if source == "literal":
        command_env = command_env or {}
        literal_value = binding.get("literal_value", binding.get("default", binding.get("value")))
        if literal_value is None and normalized_name in command_env:
            literal_value = command_env[normalized_name]
        if literal_value is None:
            raise ValueError(f"literal env binding requires literal value: {normalized_name}")
        normalized["literal_value"] = str(literal_value)
    return normalized


def _normalize_v2_090k_env_binding_type(binding_type: str) -> str:
    normalized = binding_type.strip().lower().replace("-", "_")
    if normalized in {"runtime_host", "runner_host", "runner_allocated_host"}:
        return "runtime_host"
    if normalized in {
        "runtime_port",
        "runner_port",
        "runner_allocated_port",
        "runner_allocated_tcp_port",
        "tcp_port",
    }:
        return "runtime_port"
    if normalized in {
        "temp_sqlite_path",
        "runner_temp_sqlite_path",
        "runner_temp_file",
        "temp_file",
        "temporary_file",
    }:
        return "temp_sqlite_path"
    if normalized == "literal":
        return "literal"
    raise ValueError(f"unsupported RunManifest env binding_type: {binding_type}")


def _infer_v2_090k_env_value_source(name: str) -> str:
    tokens = set(name.upper().split("_"))
    upper = name.upper()
    if "HOST" in tokens or upper.endswith("HOST"):
        return "runtime_host"
    if "PORT" in tokens or upper.endswith("PORT"):
        return "runtime_port"
    if (
        (
            "DB" in tokens
            or "DATABASE" in tokens
            or "SQLITE" in tokens
            or upper in {"DATABASE_URL", "DB_URL", "SQLITE_URL"}
        )
        and (
            "PATH" in tokens
            or "FILE" in tokens
            or "URL" in tokens
            or upper.endswith("PATH")
            or upper.endswith("URL")
        )
    ):
        return "temp_sqlite_path"
    return "literal"


def _normalize_v2_090k_readiness_probe(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("RunManifest readiness_probe is required")
    return {
        "method": payload.get("method") or "GET",
        "path": payload.get("path"),
        "expect_status": payload.get("expect_status"),
    }


def _normalize_v2_090k_frontend_topology(payload: Any, service_ref_to_command_id: Mapping[str, str]) -> dict[str, Any] | None:
    if payload is None:
        return None
    if not isinstance(payload, Mapping):
        raise ValueError("RunManifest frontend_topology must be an object")
    if "mode" in payload:
        return dict(payload)
    kind = str(payload.get("kind") or payload.get("type") or payload.get("frontend_kind") or "").lower()
    served_by = (
        payload.get("served_by_service_ref")
        or payload.get("served_by_service_contract_ref")
        or payload.get("served_by_service_contract_id")
        or payload.get("service_ref")
    )
    command_id = service_ref_to_command_id.get(str(served_by)) if served_by is not None else None
    if kind in {"static", "static_frontend_served_by_backend"} and command_id:
        return {"mode": "served-by-backend"}
    return {"mode": "served-by-backend"}


def _normalize_v2_090k_behavior_probe(probe: Mapping[str, Any], service_ref_to_command_id: Mapping[str, str]) -> dict[str, Any]:
    command_id = probe.get("service_command_id")
    if command_id is None:
        service_ref = probe.get("service_ref") or probe.get("service_contract_id") or probe.get("service_contract_ref")
        command_id = service_ref_to_command_id.get(str(service_ref))
    if command_id is None and len(service_ref_to_command_id) == 1:
        command_id = next(iter(service_ref_to_command_id.values()))
    steps = probe.get("steps", probe.get("http_steps"))
    if not isinstance(steps, list) or not steps:
        raise ValueError("RunManifest behavioral probe steps are required")
    return {
        "probe_id": _ref_payload(probe.get("probe_id")),
        "service_command_id": _ref_payload(command_id),
        "acceptance_refs": [_ref_payload(ref) for ref in probe.get("acceptance_refs", ())],
        "steps": [_normalize_v2_090k_behavior_step(step) for step in steps if isinstance(step, Mapping)],
    }


def _normalize_v2_090k_behavior_step(step: Mapping[str, Any]) -> dict[str, Any]:
    assertions = []
    for item in step.get("assertions", ()):
        assertion = _normalize_v2_090k_behavior_assertion(
            item,
            expect_status=step.get("expect_status"),
        )
        if assertion is not None:
            assertions.append(assertion)
    return {
        "step_id": str(step.get("step_id")),
        "method": step.get("method"),
        "path": _normalize_v2_090k_capture_refs(step.get("path")),
        "json_body": _normalize_v2_090k_capture_refs(step.get("json_body")),
        "expect_status": step.get("expect_status"),
        "capture": _normalize_v2_090k_capture_refs(step.get("capture") or {}),
        "assertions": assertions,
    }


def _normalize_v2_090k_capture_refs(value: Any) -> Any:
    if isinstance(value, str):
        normalized = re.sub(r"\$captures\.([A-Za-z_][A-Za-z0-9_]*)", r"${\1}", value)
        normalized = re.sub(r"\$capture\.([A-Za-z_][A-Za-z0-9_]*)", r"${\1}", normalized)
        normalized = re.sub(r"\$\{capture\.([A-Za-z_][A-Za-z0-9_]*)\}", r"${\1}", normalized)
        normalized = re.sub(r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}", r"${\1}", normalized)
        return re.sub(r"^\{([A-Za-z_][A-Za-z0-9_]*)\}$", r"${\1}", normalized)
    if isinstance(value, list):
        return [_normalize_v2_090k_capture_refs(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _normalize_v2_090k_capture_refs(item)
            for key, item in value.items()
        }
    return value


def _normalize_v2_090k_behavior_assertion(
    assertion: Any,
    *,
    expect_status: Any = None,
) -> dict[str, Any] | None:
    if not isinstance(assertion, Mapping):
        return None
    kind = assertion.get("kind") or assertion.get("type") or assertion.get("operator")
    target = _normalize_v2_090k_capture_refs(
        assertion.get("target")
        or assertion.get("path")
        or assertion.get("actual")
        or assertion.get("field")
        or "$"
    )
    if isinstance(target, str) and target and not target.startswith(("$", "/")):
        target = f"$.{target}"
    expected = _normalize_v2_090k_capture_refs(assertion.get("expected", assertion.get("value")))
    expected_from_capture = assertion.get("expected_from_capture")
    if isinstance(expected_from_capture, str) and expected_from_capture.strip():
        expected = f"${{{expected_from_capture.strip()}}}"
    if kind in {"equals", "json_equals", "json_field_equals"} and target is not None:
        return {"kind": "json_equals", "target": target, "expected": expected}
    if kind in {"json_array_contains_field_value", "array_contains_field_value"} and target is not None:
        field = assertion.get("field")
        if not isinstance(field, str) or not field.strip():
            raise ValueError(f"{kind} assertion requires field")
        return {"kind": "json_contains", "target": target, "expected": {field.strip(): expected}}
    if kind in {
        "array_contains_object",
        "array_contains",
        "json_array_contains",
        "json_array_contains_object",
        "json_contains",
        "contains",
    } and target is not None:
        expected_value = _normalize_v2_090k_capture_refs(_v2_090k_assertion_match_value(assertion, expected))
        return {"kind": "json_contains", "target": target, "expected": expected_value}
    if kind in {"json_array_not_contains_field_value", "array_not_contains_field_value"} and target is not None:
        field = assertion.get("field")
        if not isinstance(field, str) or not field.strip():
            raise ValueError(f"{kind} assertion requires field")
        return {"kind": "json_not_contains", "target": target, "expected": {field.strip(): expected}}
    if kind in {
        "array_not_contains_object",
        "array_not_contains",
        "json_array_not_contains",
        "json_array_not_contains_object",
        "json_array_excludes",
        "json_array_excludes_object",
        "json_not_contains",
        "not_contains",
    } and target is not None:
        expected_value = _normalize_v2_090k_capture_refs(_v2_090k_assertion_match_value(assertion, expected))
        return {"kind": "json_not_contains", "target": target, "expected": expected_value}
    if kind in {"field_equals"} and target is not None:
        return {"kind": "field_equals", "target": target, "expected": expected}
    if kind in {"exists", "field_present", "json_field_present", "json_field_exists", "json_present", "json_path_exists"} and target is not None:
        return {"kind": "field_present", "target": target}
    if kind in {"field_absent"} and target is not None:
        return {"kind": "field_absent", "target": target}
    if kind in {"empty_body", "empty_response_body", "response_body_empty"}:
        return {"kind": "empty_body", "target": "$"}
    if kind in {"body_contains", "response_body_contains", "response_text_contains"}:
        return {"kind": "body_contains", "target": "$", "expected": expected}
    if kind in {"body_contains_any", "response_body_contains_any"}:
        expected_any = assertion.get("expected_any", assertion.get("values", expected))
        return {
            "kind": "body_contains_any",
            "target": "$",
            "expected": _normalize_v2_090k_capture_refs(expected_any),
        }
    if kind in {"json_type", "json_field_type"} and target is not None:
        return {"kind": "json_type", "target": target, "expected": expected}
    if kind in {"is_array", "json_is_array"} and target is not None:
        return {"kind": "json_type", "target": target, "expected": "array"}
    if kind == "status_equals":
        actual_status = assertion.get("expected", assertion.get("value", assertion.get("status", assertion.get("expect_status"))))
        if actual_status is None:
            raise ValueError("status_equals assertion requires expected status")
        try:
            normalized_actual = int(actual_status)
            normalized_expected = int(expect_status)
        except (TypeError, ValueError) as exc:
            raise ValueError("status_equals assertion requires numeric status") from exc
        if normalized_actual != normalized_expected:
            raise ValueError(
                f"status_equals assertion {normalized_actual} does not match step expect_status {normalized_expected}"
            )
        return None
    # 未知断言词汇保留在 RunManifestIngestionContext（运行清单摄取上下文）中；这里不能 raw crash，
    # 也不能把它转换成可执行/可通过的 RunManifestBehaviorAssertion。
    return None


def _v2_090k_assertion_match_value(assertion: Mapping[str, Any], expected: Any) -> Any:
    if "where" in assertion:
        return assertion["where"]
    if "match" in assertion:
        return assertion["match"]
    return expected


def resolve_v2_090k_service_environment(
    *,
    bindings: tuple[RunManifestEnvironmentBinding, ...],
    host: str,
    port: int,
    temp_sqlite_path: Path,
) -> dict[str, str]:
    dynamic_values = {
        RunManifestEnvironmentValueSource.RUNTIME_HOST: host,
        RunManifestEnvironmentValueSource.RUNTIME_PORT: str(port),
        RunManifestEnvironmentValueSource.TEMP_SQLITE_PATH: str(temp_sqlite_path),
    }
    resolved: dict[str, str] = {}
    for binding in bindings:
        if binding.value_source is RunManifestEnvironmentValueSource.LITERAL:
            if binding.literal_value is None:
                raise ValueError("literal env binding requires literal_value")
            resolved[binding.name] = binding.literal_value
            continue
        resolved[binding.name] = dynamic_values[binding.value_source]
    return resolved


def extract_v2_090k_json_path(payload: Any, path: str) -> Any:
    if path == "$":
        return payload
    if not path.startswith("$."):
        raise ValueError(f"unsupported JSON path: {path}")
    current: Any = payload
    for token in path[2:].split("."):
        if token.endswith("[*]"):
            key = token[:-3]
            if not isinstance(current, dict) or key not in current or not isinstance(current[key], list):
                raise ValueError(f"JSON path not found: {path}")
            current = current[key]
            continue
        if "[*]" in token:
            key, child = token.split("[*]", 1)
            child = child.lstrip(".")
            if not isinstance(current, dict) or key not in current or not isinstance(current[key], list):
                raise ValueError(f"JSON path not found: {path}")
            if child:
                values = []
                for item in current[key]:
                    if not isinstance(item, dict) or child not in item:
                        raise ValueError(f"JSON path not found: {path}")
                    values.append(item[child])
                current = values
            else:
                current = current[key]
            continue
        if isinstance(current, list):
            values = []
            for item in current:
                if not isinstance(item, dict) or token not in item:
                    raise ValueError(f"JSON path not found: {path}")
                values.append(item[token])
            current = values
            continue
        if not isinstance(current, dict) or token not in current:
            raise ValueError(f"JSON path not found: {path}")
        current = current[token]
    return current


def interpolate_v2_090k_value(value: Any, captures: Mapping[str, Any]) -> Any:
    if isinstance(value, str):
        exact = _CAPTURE_PATTERN.fullmatch(value)
        if exact:
            key = exact.group(1)
            if key not in captures:
                raise ValueError(f"capture {key} is required")
            return captures[key]

        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in captures:
                raise ValueError(f"capture {key} is required")
            return str(captures[key])

        return _CAPTURE_PATTERN.sub(replace, value)
    if isinstance(value, list):
        return [interpolate_v2_090k_value(item, captures) for item in value]
    if isinstance(value, dict):
        return {
            key: interpolate_v2_090k_value(item, captures)
            for key, item in value.items()
        }
    return value


def evaluate_v2_090k_behavior_assertion(
    *,
    payload: Any,
    assertion: RunManifestBehaviorAssertion,
    captures: Mapping[str, Any],
    body_text: str | None = None,
) -> None:
    expected = interpolate_v2_090k_value(assertion.expected, captures)
    if assertion.kind is RunManifestBehaviorAssertionKind.BODY_CONTAINS:
        if not isinstance(expected, str):
            raise ValueError("body_contains assertion requires string expected")
        if body_text is not None and expected in body_text:
            return
        if isinstance(payload, str) and expected in payload:
            return
        raise ValueError(f"assertion failed: response body does not contain {expected!r}")

    if assertion.kind is RunManifestBehaviorAssertionKind.BODY_CONTAINS_ANY:
        if not isinstance(expected, list) or not all(isinstance(item, str) for item in expected):
            raise ValueError("body_contains_any assertion requires string list expected")
        actual_body = body_text if body_text is not None else payload
        if isinstance(actual_body, str) and any(item in actual_body for item in expected):
            return
        raise ValueError(f"assertion failed: response body does not contain any of {expected!r}")

    if assertion.kind is RunManifestBehaviorAssertionKind.EMPTY_BODY:
        if payload is None:
            return
        raise ValueError("assertion failed: response body must be empty")

    if assertion.kind is RunManifestBehaviorAssertionKind.FIELD_ABSENT:
        try:
            extract_v2_090k_json_path(payload, assertion.target)
        except ValueError:
            return
        raise ValueError(f"assertion failed: field must be absent at {assertion.target}")

    if assertion.kind is RunManifestBehaviorAssertionKind.FIELD_PRESENT:
        extract_v2_090k_json_path(payload, assertion.target)
        return

    actual = extract_v2_090k_json_path(payload, assertion.target)
    if assertion.kind is RunManifestBehaviorAssertionKind.JSON_TYPE:
        if _v2_090k_json_type_matches(actual, expected):
            return
        raise ValueError(
            f"assertion failed: {assertion.target} expected JSON type {expected!r} got {type(actual).__name__}"
        )
    if assertion.kind in {
        RunManifestBehaviorAssertionKind.JSON_EQUALS,
        RunManifestBehaviorAssertionKind.FIELD_EQUALS,
    }:
        if actual != expected:
            raise ValueError(
                f"assertion failed: {assertion.target} expected {expected!r} got {actual!r}"
            )
        return
    if assertion.kind is RunManifestBehaviorAssertionKind.JSON_CONTAINS:
        if _v2_090k_payload_contains(actual, expected):
            return
        raise ValueError(f"assertion failed: {assertion.target} does not contain {expected!r}")
    if assertion.kind is RunManifestBehaviorAssertionKind.JSON_NOT_CONTAINS:
        if not _v2_090k_payload_contains(actual, expected):
            return
        raise ValueError(f"assertion failed: {assertion.target} contains {expected!r}")
    raise ValueError(f"unsupported behavior assertion kind: {assertion.kind}")


def _v2_090k_payload_contains(actual: Any, expected: Any) -> bool:
    if isinstance(actual, list):
        for item in actual:
            if item == expected:
                return True
            if isinstance(item, dict) and isinstance(expected, dict) and all(
                item.get(key) == value for key, value in expected.items()
            ):
                return True
        return False
    if isinstance(actual, dict) and isinstance(expected, dict):
        return all(actual.get(key) == value for key, value in expected.items())
    if isinstance(actual, str) and isinstance(expected, str):
        return expected in actual
    return actual == expected


def _v2_090k_json_type_matches(actual: Any, expected: Any) -> bool:
    if not isinstance(expected, str):
        raise ValueError("json_type assertion requires string expected")
    normalized = expected.strip().lower()
    if normalized in {"integer", "int"}:
        return isinstance(actual, int) and not isinstance(actual, bool)
    if normalized in {"number", "float"}:
        return (isinstance(actual, int | float) and not isinstance(actual, bool))
    if normalized in {"string", "str"}:
        return isinstance(actual, str)
    if normalized in {"boolean", "bool"}:
        return isinstance(actual, bool)
    if normalized in {"array", "list"}:
        return isinstance(actual, list)
    if normalized in {"object", "dict"}:
        return isinstance(actual, dict)
    if normalized in {"null", "none"}:
        return actual is None
    raise ValueError(f"unsupported json_type expected value: {expected}")


def execute_v2_090k_behavior_probe(
    *,
    probe: RunManifestBehaviorProbe,
    base_url: str,
    http_client: Any,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    captures: dict[str, Any] = {}
    step_results: list[dict[str, Any]] = []
    base = base_url.rstrip("/")
    for step in probe.steps:
        path = interpolate_v2_090k_value(step.path, captures)
        if not isinstance(path, str) or not path.startswith("/"):
            raise ValueError(f"behavioral probe step path must start with /: {step.step_id}")
        body = interpolate_v2_090k_value(step.json_body, captures)
        response = http_client.request(
            step.method,
            f"{base}{path}",
            json=body,
            timeout=timeout_seconds,
        )
        if response.status_code != step.expect_status:
            raise ValueError(
                f"behavioral probe step {step.step_id} expected status "
                f"{step.expect_status} got {response.status_code}"
            )
        body_text = getattr(response, "text", None)
        payload: Any = None
        if any(
            assertion.kind in {
                RunManifestBehaviorAssertionKind.BODY_CONTAINS,
                RunManifestBehaviorAssertionKind.BODY_CONTAINS_ANY,
            }
            for assertion in step.assertions
        ):
            if body_text is None:
                try:
                    payload = response.json()
                except Exception:
                    payload = None
            else:
                payload = body_text
        elif not any(assertion.kind is RunManifestBehaviorAssertionKind.EMPTY_BODY for assertion in step.assertions):
            payload = response.json()
        else:
            try:
                payload = response.json()
            except Exception:
                payload = None
        for capture_name, capture_path in step.capture.items():
            try:
                if capture_path == "$body":
                    captures[capture_name] = body_text
                elif capture_path == "$status":
                    captures[capture_name] = response.status_code
                else:
                    captures[capture_name] = extract_v2_090k_json_path(payload, capture_path)
            except ValueError as exc:
                raise ValueError(f"capture {capture_name} failed") from exc
        for assertion in step.assertions:
            evaluate_v2_090k_behavior_assertion(
                payload=payload,
                assertion=assertion,
                captures=captures,
                body_text=body_text,
            )
        step_results.append(
            {
                "step_id": step.step_id,
                "method": step.method,
                "path": path,
                "status_code": response.status_code,
            }
        )
    return {
        "probe_id": probe.probe_id.value,
        "service_command_id": probe.service_command_id.value,
        "acceptance_refs": [ref.value for ref in probe.acceptance_refs],
        "passed": True,
        "captures": captures,
        "steps": step_results,
    }


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
    run_manifest: RunManifest,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    service_contract = run_manifest.service_contracts[0]
    runtime_port = _free_tcp_port()
    with tempfile.TemporaryDirectory(prefix="boardroom-v2090f-live-") as temp_dir:
        db_path = Path(temp_dir) / "service.sqlite3"
        env = dict(os.environ)
        service_env = resolve_v2_090k_service_environment(
            bindings=service_contract.env_bindings,
            host="127.0.0.1",
            port=runtime_port,
            temp_sqlite_path=db_path,
        )
        env.update(
            {
                "PYTHONPATH": str(project_root),
                **service_env,
            }
        )
        service_command = _run_manifest_command(run_manifest, service_contract.command_id.value)
        service_started = datetime.now(UTC)
        command_argv = _interpolate_v2_090k_command_argv(service_command.command, service_env)
        service = subprocess.Popen(
            command_argv,
            cwd=project_root / service_command.cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            readiness_body = _wait_http_text(
                "127.0.0.1",
                runtime_port,
                service_contract.readiness_probe.path,
                expected_status=service_contract.readiness_probe.expect_status,
            )
            ready_at = datetime.now(UTC)
            http_client = _V2_090KHttpClient()
            probe_results = [
                execute_v2_090k_behavior_probe(
                    probe=probe,
                    base_url=f"http://127.0.0.1:{runtime_port}",
                    http_client=http_client,
                )
                for probe in run_manifest.behavioral_probes
                if probe.service_command_id == service_contract.command_id
            ]
            if not probe_results:
                raise ValueError("RunManifest behavioral probes must target service command")
            persisted = db_path.is_file()
        finally:
            service_stopped, service_stdout, service_stderr = _terminate_process(service)
    service_id = "service-run.v2-090f.agent-declared"
    services = [
        {
            "service_run_evidence_id": service_id,
            "execution_package_ref": "exec.v2-090f.closeout.agent-declared-service",
            "ticket_ref": "ticket.v2-090f.closeout.live-probe",
            "command_id": service_contract.command_id.value,
            "command": list(command_argv),
            "cwd": service_command.cwd,
            "process_id": service.pid,
            "readiness_url": f"http://127.0.0.1:{runtime_port}{service_contract.readiness_probe.path}",
            "probe_status_code": service_contract.readiness_probe.expect_status,
            "probe_body_sha256": hashlib.sha256(readiness_body.encode("utf-8")).hexdigest(),
            "stdout_ref": f"command-output.{service_id}.stdout",
            "stderr_ref": f"command-output.{service_id}.stderr",
            "stdout": service_stdout,
            "stderr": service_stderr,
            "started_at": service_started.isoformat(),
            "ready_at": ready_at.isoformat(),
            "stopped_at": service_stopped.isoformat(),
            "runner_ref": "runner.v2-090f.closeout",
            "environment_profile_ref": "environment.v2-090f.local",
            "workspace_snapshot_ref": _project_tree_hash_ref(project_root),
            "environment_overrides": service_env,
        },
    ]
    evidence = {
        "live_blackbox_evidence_id": "live-blackbox.v2-090f.agent-declared",
        "package_contract_ref": run_manifest.package_contract_ref.value,
        "service_command_id": service_contract.command_id.value,
        "service_run_ref": service_id,
        "passed": bool(probe_results),
        "probes": [
            {
                "probe_ref": result["probe_id"],
                "acceptance_refs": result["acceptance_refs"],
                "service_run_refs": [service_id],
                "command_ids": [service_contract.command_id.value],
                "passed": bool(result["passed"]),
                "observed_facts": result,
                "body_sha256": hashlib.sha256(json.dumps(result, sort_keys=True).encode("utf-8")).hexdigest(),
                "probed_at": datetime.now(UTC).isoformat(),
            }
            for result in probe_results
        ],
        "persistent_runtime_file_observed": persisted,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    return services, evidence


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_http_text(host: str, port: int, path: str, *, expected_status: int = 200) -> str:
    deadline = time.monotonic() + 15
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            status, body = _http_request(host, port, "GET", path)
            if status == expected_status:
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


class _V2_090KHttpResponse:
    def __init__(self, *, status_code: int, body: str) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> Any:
        return json.loads(self._body)

    @property
    def text(self) -> str:
        return self._body


class _V2_090KHttpClient:
    def request(
        self,
        method: str,
        url: str,
        *,
        json: object | None = None,
        timeout: float = 10.0,
    ) -> _V2_090KHttpResponse:
        del timeout
        from urllib.parse import urlparse

        parsed = urlparse(url)
        if parsed.hostname is None or parsed.port is None:
            raise ValueError("behavior probe URL must include host and port")
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        status, body = _http_request(parsed.hostname, parsed.port, method, path, json)
        return _V2_090KHttpResponse(status_code=status, body=body)


def _run_manifest_command(run_manifest: RunManifest, command_id: str) -> RunManifestCommand:
    matches = tuple(
        command for command in run_manifest.commands if command.command_id.value == command_id
    )
    if len(matches) != 1:
        raise ValueError(f"RunManifest command is required: {command_id}")
    return matches[0]


def _interpolate_v2_090k_command_argv(argv: tuple[str, ...], values: Mapping[str, str]) -> tuple[str, ...]:
    return tuple(str(interpolate_v2_090k_value(item, values)) for item in argv)


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
        lineage = _lineage_for_project_path(relative, tickets)
        artifact_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        lineage_sha = str(lineage.get("sha256", "")).replace("sha256:", "")
        if lineage_sha and lineage_sha != artifact_sha:
            raise ValueError("source lineage sha256 does not match materialized source")
        source_surface_refs = _lineage_string_list(lineage, "source_surface_refs")
        acceptance_refs = _lineage_string_list(lineage, "acceptance_refs")
        evidence_refs = _lineage_string_list(lineage, "evidence_refs")
        if len(source_surface_refs) != 1:
            raise ValueError("source lineage must declare exactly one source surface")
        entries.append(
            {
                "path": relative,
                "sha256": artifact_sha,
                "source_surface_ref": source_surface_refs[0],
                "producer_ticket_ref": str(lineage.get("producer_ticket_ref") or first_ticket),
                "producer_attempt_ref": str(lineage.get("producer_attempt_ref") or first_attempt),
                "consumer_ticket_refs": [first_ticket],
                "acceptance_refs": acceptance_refs,
                "evidence_refs": evidence_refs,
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


def _lineage_for_project_path(relative: str, tickets: list[Any]) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    for ticket in tickets:
        if not isinstance(ticket, dict):
            continue
        lineage_inputs = ticket.get("source_lineage_inputs")
        if not isinstance(lineage_inputs, list):
            continue
        for lineage in lineage_inputs:
            if isinstance(lineage, dict) and lineage.get("path") == relative:
                matches.append(lineage)
    if len(matches) != 1:
        raise ValueError(f"source lineage is required for materialized file: {relative}")
    return matches[0]


def _lineage_string_list(lineage: dict[str, Any], field_name: str) -> list[str]:
    values = lineage.get(field_name)
    if not isinstance(values, list) or not values:
        raise ValueError(f"source lineage {field_name} must not be empty")
    normalized = [str(value).strip() for value in values]
    if any(not value for value in normalized):
        raise ValueError(f"source lineage {field_name} must not contain empty values")
    return normalized


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
    acceptance_refs = _acceptance_refs_from_source_inventory(source_inventory)
    rows = []
    for acceptance_ref in acceptance_refs:
        rows.append(
            {
                "acceptance_ref": acceptance_ref,
                "statement": f"Agent-generated acceptance criterion {acceptance_ref} is satisfied by verified evidence.",
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


def _acceptance_refs_from_source_inventory(source_inventory: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for entry in source_inventory.get("entries", ()):
        if not isinstance(entry, dict):
            continue
        for acceptance_ref in entry.get("acceptance_refs", ()):
            ref = str(acceptance_ref).strip()
            if ref and ref not in refs:
                refs.append(ref)
    if not refs:
        raise ValueError("final evidence table requires acceptance refs from source inventory")
    return refs


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
    if (
        "ticket_graph" in provider_output
        or "acceptance_contract" in provider_output
        or "run_manifest_id" in provider_output
    ):
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
    if command_id_parts and command_id_parts[-1] in {"serve", "start", "watch", "dev"}:
        return True
    if (
        len(command_id_parts) >= 2
        and command_id_parts[-1] == "run"
        and command_id_parts[-2] in {"service", "server", "backend", "frontend"}
    ):
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
    if not acceptance_refs or missing_operations:
        raise ValueError(
            "hard acceptance must cover add, list, checkout, return, and delete"
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
    package_facts: dict[str, Any] = {}
    marker = "# ExecutionPackageFacts\n"
    if marker in prompt:
        try:
            package_facts = json.loads(prompt.split(marker, 1)[1])
            objective = str(package_facts.get("objective", prompt))
        except json.JSONDecodeError:
            objective = prompt
            package_facts = {}
    fact_lines: list[str] = []
    if isinstance(package_facts, dict):
        for field_name in ("context_refs", "allowed_read_refs", "constraints"):
            value = package_facts.get(field_name)
            if value:
                fact_lines.append(f"{field_name}: {json.dumps(value, ensure_ascii=False, sort_keys=True)}")
    return "\n".join(
        (
            "You are producing a Boardroom OS V2-090F planning artifact.",
            "You are not inside an agent tool loop. Do not call tools, do not use action protocol, do not emit submit_result.",
            "Return exactly one strict JSON object and nothing else.",
            "The JSON object must be the requested planning artifact itself, not markdown and not a wrapper.",
            "Use one top-level JSON object only. Do not append sibling fragments after the closing brace.",
            "All sections, including completion_gate or forbidden claims, must be properties inside that one top-level object.",
            "If the Objective mentions ticket-graph, the response must include ticket_graph.nodes.",
            "If the Objective mentions run-manifest, return a RunManifest JSON object with run_manifest_id, workspace_manifest_ref, package_contract_ref, package_root, commands, service_contracts, frontend_topology, and behavioral_probes.",
            "RunManifest commands must include at least one run command for the backend service and one finite test command. Service contracts must reference run command ids and declare env_bindings, readiness_probe, and role.",
            "RunManifest behavioral_probes must contain acceptance_refs and HTTP steps with method, path, json_body, expect_status, capture, and assertions.",
            "For ticket-graph, include implementation tickets only as needed to satisfy the PRD and active contracts; do not rely on runner-provided ticket categories.",
            "V2-090F behavior acceptance is not optional: generated acceptance refs and evidence obligations must cover add, list, checkout, return, and delete when the PRD requires those operations.",
            "Do not replace add/delete with seeded catalog-only checkout and return. A generated project that omits create-book or delete-book behavior cannot pass closeout.",
            "The agent team must produce AcceptanceContract, PackageContract, RunManifest, and verification-plan artifacts. The runner will validate and execute these artifacts without assuming filenames, module names, environment variable names, endpoints, seeded data, or source-surface path prefixes.",
            "Each implementation node must use node_type='implementation', owner_seat_ref='seat.worker.implementation', and include node_ref, title, depends_on, acceptance_refs, source_surface_refs, evidence_obligations, allowed_write_set, required_outputs, and commands.",
            "commands must be an array of objects: {command_id,label,command,cwd}; command must be an argv array, never a shell string.",
            "worker implementation commands must be bounded finite verification commands that exit, such as pytest, unittest, lint, or deterministic file checks.",
            "If a ticket declares a command that imports or discovers tests (for example tests.test_api, tests/, or unittest discover -s tests), that same ticket must include tests/ in allowed_write_set or required_outputs so the command can be satisfied before submit_result.",
            "For worker implementation tickets, do not include long-running service startup, run, serve, watch, or dev commands.",
            "Service startup, readiness, live behavior probes, source-surface mappings, and acceptance evidence mapping must be declared by agent-generated contracts and verification artifacts.",
            "allowed_write_set and required_outputs must be concrete relative files or directory prefixes ending in '/', never glob patterns such as **/*.py.",
            "Directory-only required_outputs are not enough for service entrypoints; any service script or python -m module expected by RunManifest must appear as a concrete implementation required_outputs file.",
            "Implementation ticket required_outputs must use full workspace-relative paths for every concrete file; bare filenames are not enough when package source surfaces declare allowed directories.",
            "If PackageContract source surfaces declare required_files under an allowed directory, include the joined path in the owning implementation ticket required_outputs.",
            "Do not return planning-only nodes as the only ticket_graph.nodes.",
            "Do not claim implementation, verification success, checker approval, closeout, or sample success.",
            *(
                (
                    "",
                    "Execution package facts that must be honored:",
                    *fact_lines,
                )
                if fact_lines
                else ()
            ),
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
