from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sys
import traceback
from typing import Any
from uuid import uuid4

from boardroom_os.agents.profiles import ModelExecutionProfile
from boardroom_os.agents.role_prompt_hooks import (
    RolePromptHookRef,
    build_baseline_role_prompt_hook_registry,
)
from boardroom_os.agents.seat import AgentSeatRef
from boardroom_os.config.boardroom import BoardroomConfigPaths, load_boardroom_settings
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
from boardroom_os.execution.atomic_executor import (
    AtomicAgentExecutor,
    AtomicAgentRuntimeFactory,
    AtomicExecutionRequest,
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
from boardroom_os.graph.ticket import TicketId


METRIC_NAME = "action.rejected / provider.turn.completed"


@dataclass(frozen=True)
class TicketSpec:
    suffix: str
    execution_package_id: str
    ticket_ref: str
    acceptance_ref: str
    source_surface_ref: str
    evidence_obligation_id: str
    output_path: str
    command_id: str
    command_label: str
    check_code: str
    objective: str
    submit_summary: str


def main() -> int:
    try:
        report = run_probe()
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0 if all(ticket["success"] for ticket in report["tickets"]) else 1
    except Exception as exc:
        print(f"{exc.__class__.__name__}: {exc}", file=sys.stderr)
        if os.environ.get("BOARDROOM_DEBUG_TRACEBACK") == "1":
            traceback.print_exc(file=sys.stderr)
        return 1


def run_probe() -> dict[str, Any]:
    settings = load_boardroom_settings(
        BoardroomConfigPaths(
            runtime_config=Path(os.environ.get("BOARDROOM_RUNTIME_CONFIG", "config/boardroom-runtime.example.yaml")),
            providers_config=Path(os.environ.get("BOARDROOM_PROVIDERS_CONFIG", "config/boardroom-providers.example.yaml")),
            roles_config=Path(os.environ.get("BOARDROOM_ROLES_CONFIG", "config/boardroom-roles.example.yaml")),
        ),
        env_values=dict(os.environ),
    )
    workspace_root = Path(os.environ.get("BOARDROOM_EVIDENCE_ROOT", ".evidence")) / "atomic-agent" / "retry-rate-workspace"
    workspace_root.mkdir(parents=True, exist_ok=True)
    (workspace_root / "work").mkdir(parents=True, exist_ok=True)
    event_stream_root = Path(settings.runtime.atomic_agent.event_stream_root).resolve()

    ticket_results: list[dict[str, Any]] = []
    for spec in _ticket_specs():
        package = _execution_package(spec, settings)
        run_id = _new_run_id(settings.runtime.atomic_agent.run_id_prefix, spec.suffix)
        try:
            runtime_port = AtomicAgentRuntimeFactory(settings=settings).build_runtime_port(
                execution_package=package,
                seat_ref="seat.worker.implementation",
                workspace_root=workspace_root,
                run_id=run_id,
            )
            result = AtomicAgentExecutor(
                runtime_port=runtime_port,
                allow_fake_provider_for_unit_tests=False,
            ).execute(
                AtomicExecutionRequest(
                    execution_package=package,
                    settings=settings,
                    seat_ref="seat.worker.implementation",
                    workspace_root=workspace_root,
                    event_stream_root=event_stream_root,
                ),
                provider_transport_kind="real",
            )
            event_summary = _summarize_event_stream(event_stream_root / result.projection.event_stream_ref)
            ticket_results.append(
                {
                    **_ticket_identity(spec, run_id, result.projection.event_stream_ref),
                    **event_summary,
                    "success": True,
                    "provider_attempt_ref": result.provider_attempt.provider_attempt_id.value,
                    "work_product_ref": result.projection.work_product_submission.work_product.work_product_id.value,
                    "events_hash": result.projection.events_hash,
                    "command_exit_codes": event_summary["command_exit_codes"],
                    "workspace_mutation_paths": event_summary["workspace_mutation_paths"],
                    "source_lineage_inputs": result.projection.source_lineage_inputs,
                    "failure": None,
                }
            )
        except Exception as exc:
            event_path = event_stream_root / f"{run_id}.jsonl"
            event_summary = _summarize_event_stream(event_path) if event_path.exists() else _empty_event_summary()
            ticket_results.append(
                {
                    **_ticket_identity(spec, run_id, f"{run_id}.jsonl"),
                    **event_summary,
                    "success": False,
                    "provider_attempt_ref": None,
                    "work_product_ref": None,
                    "events_hash": None,
                    "command_exit_codes": event_summary["command_exit_codes"],
                    "workspace_mutation_paths": event_summary["workspace_mutation_paths"],
                    "source_lineage_inputs": (),
                    "failure": {
                        "type": exc.__class__.__name__,
                        "message": str(exc),
                    },
                }
            )
    return _build_report(ticket_results)


def _ticket_specs() -> tuple[TicketSpec, ...]:
    return (
        TicketSpec(
            suffix="note",
            execution_package_id="exec.ticket.retry-rate.note.1",
            ticket_ref="ticket.retry-rate.note",
            acceptance_ref="AC-RETRY-RATE-NOTE",
            source_surface_ref="surface.retry-rate.note",
            evidence_obligation_id="evidence.retry-rate.note",
            output_path="work/retry-rate-note.txt",
            command_id="cmd.check-note",
            command_label="Check retry-rate note",
            check_code=(
                "from pathlib import Path; "
                "p=Path('work/retry-rate-note.txt'); "
                "text=p.read_text(encoding='utf-8') if p.exists() else ''; "
                "raise SystemExit(0 if 'retry-rate probe note' in text.lower() else 3)"
            ),
            objective=(
                "Create work/retry-rate-note.txt containing one short sentence that includes "
                "the exact phrase retry-rate probe note, run cmd.check-note, then submit the result."
            ),
            submit_summary="Created and verified work/retry-rate-note.txt",
        ),
        TicketSpec(
            suffix="json",
            execution_package_id="exec.ticket.retry-rate.json.1",
            ticket_ref="ticket.retry-rate.json",
            acceptance_ref="AC-RETRY-RATE-JSON",
            source_surface_ref="surface.retry-rate.json",
            evidence_obligation_id="evidence.retry-rate.json",
            output_path="work/retry-rate-data.json",
            command_id="cmd.check-json",
            command_label="Check retry-rate JSON",
            check_code=(
                "from pathlib import Path; import json; "
                "p=Path('work/retry-rate-data.json'); "
                "data=json.loads(p.read_text(encoding='utf-8')); "
                "raise SystemExit(0 if data == {'probe':'retry-rate','ticket':'json','passed':True} else 3)"
            ),
            objective=(
                "Create work/retry-rate-data.json as exactly "
                '{"probe":"retry-rate","ticket":"json","passed":true}, '
                "run cmd.check-json, then submit the result."
            ),
            submit_summary="Created and verified work/retry-rate-data.json",
        ),
        TicketSpec(
            suffix="python",
            execution_package_id="exec.ticket.retry-rate.python.1",
            ticket_ref="ticket.retry-rate.python",
            acceptance_ref="AC-RETRY-RATE-PYTHON",
            source_surface_ref="surface.retry-rate.python",
            evidence_obligation_id="evidence.retry-rate.python",
            output_path="work/retry_rate_calc.py",
            command_id="cmd.check-python",
            command_label="Check retry-rate Python file",
            check_code=(
                "from pathlib import Path; "
                "p=Path('work/retry_rate_calc.py'); "
                "ns={}; exec(p.read_text(encoding='utf-8'), ns); "
                "raise SystemExit(0 if ns.get('retry_rate')(1, 4) == 0.25 else 3)"
            ),
            objective=(
                "Create work/retry_rate_calc.py defining retry_rate(rejections, provider_turns) "
                "that returns rejections / provider_turns and raises ValueError when provider_turns is 0. "
                "Run cmd.check-python, then submit the result."
            ),
            submit_summary="Created and verified work/retry_rate_calc.py",
        ),
    )


def _execution_package(spec: TicketSpec, settings: Any) -> ExecutionPackage:
    role_slot = settings.role_slot_by_seat("seat.worker.implementation")
    provider_config = settings.provider_by_id(role_slot.provider_profile_ref)
    model_execution_profile = ModelExecutionProfile(
        model_execution_profile_id="model-profile.worker.implementation.primary",
        provider="openai-compatible",
        model=provider_config.model,
        reasoning_effort=provider_config.reasoning_effort or "high",
        context_window=provider_config.context_window_tokens,
        temperature=0.0 if provider_config.temperature is None else provider_config.temperature,
        tool_permissions=("filesystem.read", "filesystem.write", "command.execute"),
        fallback_policy_ref="fallback.default",
    )
    evidence_obligation = EvidenceObligation(
        evidence_obligation_id=EvidenceObligationRef(value=spec.evidence_obligation_id),
        acceptance_refs=(AcceptanceRef(value=spec.acceptance_ref),),
        source_surface_refs=(SourceSurfaceRef(value=spec.source_surface_ref),),
        required_artifact_type=RequiredArtifactType(value="source_patch"),
        required_verifier=RequiredVerifier(value="checker"),
        blocking=True,
    )
    command = PackageCommand(
        command_id=ContractId(value=spec.command_id),
        label=spec.command_label,
        command=(sys.executable, "-c", spec.check_code),
        cwd=".",
    )
    return ExecutionPackage(
        execution_package_id=ExecutionPackageId(value=spec.execution_package_id),
        ticket_ref=TicketId(value=spec.ticket_ref),
        graph_version=1,
        seat_ref=AgentSeatRef(value="seat.worker.implementation"),
        model_execution_profile=model_execution_profile,
        role_prompt_hook=_baseline_worker_role_prompt_hook(),
        objective=(
            f"{spec.objective} The final submit_result action must be exactly one JSON object "
            "with top-level action_id, action, reason_summary, and input fields. The input field must contain "
            f'summary, produced_paths as ["{spec.output_path}"], and evidence_refs as ["{spec.command_id}"].'
        ),
        context_refs=(ContextRef(value=f"context.v2-090h.retry-rate.{spec.suffix}"),),
        constraints=(
            "Only write under work/.",
            f"Use run_command with {spec.command_id} before submit_result.",
            (
                "For submit_result, do not use action_envelope. Use this shape: "
                '{"action_id":"act.submit-result","action":"submit_result","reason_summary":"done",'
                f'"input":{{"summary":"{spec.submit_summary}",'
                f'"produced_paths":["{spec.output_path}"],"evidence_refs":["{spec.command_id}"]}}}}'
            ),
        ),
        acceptance_refs=(AcceptanceRef(value=spec.acceptance_ref),),
        source_surface_refs=(SourceSurfaceRef(value=spec.source_surface_ref),),
        allowed_read_refs=(AllowedReadRef(value="README.md"),),
        allowed_write_set=(AllowedWritePath(value="work/"),),
        required_outputs=(RequiredOutput(value=spec.output_path),),
        commands=(command,),
        evidence_obligations=(evidence_obligation,),
        fallback_policy_ref=FallbackPolicyRef(value="fallback.default"),
        audit_requirements=(AuditRequirement(value="record atomic retry-rate evidence"),),
    )


def _summarize_event_stream(event_stream_path: Path) -> dict[str, Any]:
    events = _read_events(event_stream_path)
    provider_turn_completed_count = _count_events(events, "provider.turn.completed")
    action_rejected_events = [event for event in events if event.get("type") == "action.rejected"]
    action_rejected_count = len(action_rejected_events)
    retryable_action_rejected_count = sum(
        1
        for event in action_rejected_events
        if bool(((event.get("payload") or {}).get("error") or {}).get("retryable"))
    )
    terminal_event_type = _terminal_event_type(events)
    return {
        "terminal_event_type": terminal_event_type,
        "provider_turn_completed_count": provider_turn_completed_count,
        "action_rejected_count": action_rejected_count,
        "retryable_action_rejected_count": retryable_action_rejected_count,
        "retry_rate": _retry_rate(action_rejected_count, provider_turn_completed_count),
        "command_exit_codes": _event_command_exit_codes(events),
        "workspace_mutation_paths": _event_workspace_mutation_paths(events),
    }


def _build_report(ticket_results: list[dict[str, Any]]) -> dict[str, Any]:
    provider_turn_count = sum(ticket["provider_turn_completed_count"] for ticket in ticket_results)
    rejected_count = sum(ticket["action_rejected_count"] for ticket in ticket_results)
    retryable_rejected_count = sum(ticket["retryable_action_rejected_count"] for ticket in ticket_results)
    return {
        "metric": METRIC_NAME,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "summary": {
            "ticket_count": len(ticket_results),
            "success_count": sum(1 for ticket in ticket_results if ticket["success"]),
            "failure_count": sum(1 for ticket in ticket_results if not ticket["success"]),
            "provider_turn_completed_count": provider_turn_count,
            "action_rejected_count": rejected_count,
            "retryable_action_rejected_count": retryable_rejected_count,
            "retry_rate": _retry_rate(rejected_count, provider_turn_count),
        },
        "tickets": ticket_results,
    }


def _read_events(event_stream_path: Path) -> list[dict[str, Any]]:
    with event_stream_path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _count_events(events: list[dict[str, Any]], event_type: str) -> int:
    return sum(1 for event in events if event.get("type") == event_type)


def _terminal_event_type(events: list[dict[str, Any]]) -> str | None:
    for event in reversed(events):
        event_type = event.get("type")
        if event_type in {"run.completed", "run.failed"}:
            return event_type
    return None


def _retry_rate(action_rejected_count: int, provider_turn_completed_count: int) -> float:
    if provider_turn_completed_count == 0:
        return 0.0
    return action_rejected_count / provider_turn_completed_count


def _event_command_exit_codes(events: list[dict[str, Any]]) -> dict[str, int]:
    exit_codes: dict[str, int] = {}
    for event in events:
        if event.get("type") != "command.completed":
            continue
        payload = event.get("payload") or {}
        command_id = payload.get("command_id")
        exit_code = payload.get("exit_code")
        if isinstance(command_id, str) and isinstance(exit_code, int):
            exit_codes[command_id] = exit_code
    return exit_codes


def _event_workspace_mutation_paths(events: list[dict[str, Any]]) -> tuple[str, ...]:
    paths: list[str] = []
    for event in events:
        if event.get("type") != "workspace.mutation.recorded":
            continue
        payload = event.get("payload") or {}
        path = payload.get("path")
        if isinstance(path, str):
            paths.append(path)
    return tuple(paths)


def _empty_event_summary() -> dict[str, Any]:
    return {
        "terminal_event_type": None,
        "provider_turn_completed_count": 0,
        "action_rejected_count": 0,
        "retryable_action_rejected_count": 0,
        "retry_rate": 0.0,
        "command_exit_codes": {},
        "workspace_mutation_paths": (),
    }


def _ticket_identity(spec: TicketSpec, run_id: str, event_stream_ref: str) -> dict[str, str]:
    return {
        "ticket_ref": spec.ticket_ref,
        "execution_package_id": spec.execution_package_id,
        "objective": spec.objective,
        "required_output": spec.output_path,
        "atomic_run_id": run_id,
        "event_stream_ref": event_stream_ref,
    }


def _new_run_id(prefix: str, suffix: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}.retry-rate.{suffix}.{stamp}.{uuid4().hex[:8]}"


def _baseline_worker_role_prompt_hook():
    return build_baseline_role_prompt_hook_registry().require(
        RolePromptHookRef(value="role-prompt-hook.baseline.worker.v1")
    )


if __name__ == "__main__":
    raise SystemExit(main())
