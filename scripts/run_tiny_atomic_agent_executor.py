from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import traceback
from datetime import UTC, datetime
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


def main() -> int:
    try:
        settings = load_boardroom_settings(
            BoardroomConfigPaths(
                runtime_config=Path(os.environ.get("BOARDROOM_RUNTIME_CONFIG", "config/boardroom-runtime.example.yaml")),
                providers_config=Path(os.environ.get("BOARDROOM_PROVIDERS_CONFIG", "config/boardroom-providers.example.yaml")),
                roles_config=Path(os.environ.get("BOARDROOM_ROLES_CONFIG", "config/boardroom-roles.example.yaml")),
            ),
            env_values=dict(os.environ),
        )
        workspace_root = Path(os.environ.get("BOARDROOM_EVIDENCE_ROOT", ".evidence")) / "atomic-agent" / "proving-workspace"
        workspace_root.mkdir(parents=True, exist_ok=True)
        (workspace_root / "work").mkdir(parents=True, exist_ok=True)
        package = _execution_package()
        run_id = _new_run_id(settings.runtime.atomic_agent.run_id_prefix)
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
                event_stream_root=Path(settings.runtime.atomic_agent.event_stream_root).resolve(),
            ),
            provider_transport_kind="real",
        )
        print(
            json.dumps(
                {
                    "atomic_run_id": result.atomic_run_id,
                    "event_stream_ref": result.projection.event_stream_ref,
                    "events_hash": result.projection.events_hash,
                    "provider_attempt_ref": result.provider_attempt.provider_attempt_id.value,
                    "work_product_ref": result.projection.work_product_submission.work_product.work_product_id.value,
                    "source_lineage_inputs": result.projection.source_lineage_inputs,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    except Exception as exc:
        print(f"{exc.__class__.__name__}: {exc}", file=sys.stderr)
        if os.environ.get("BOARDROOM_DEBUG_TRACEBACK") == "1":
            traceback.print_exc(file=sys.stderr)
        return 1


def _execution_package() -> ExecutionPackage:
    model_execution_profile = ModelExecutionProfile(
        model_execution_profile_id="model-profile.worker.implementation.primary",
        provider="openai-compatible",
        model="gpt-5.5",
        reasoning_effort="high",
        context_window=400000,
        temperature=0.0,
        tool_permissions=("filesystem.read", "filesystem.write", "command.execute"),
        fallback_policy_ref="fallback.default",
    )
    evidence_obligation = EvidenceObligation(
        evidence_obligation_id=EvidenceObligationRef(value="evidence.proving.output"),
        acceptance_refs=(AcceptanceRef(value="AC-PROVING-OUTPUT"),),
        source_surface_refs=(SourceSurfaceRef(value="surface.proving.work"),),
        required_artifact_type=RequiredArtifactType(value="source_patch"),
        required_verifier=RequiredVerifier(value="checker"),
        blocking=True,
    )
    check_code = (
        "from pathlib import Path; "
        "p=Path('work/real-provider-output.txt'); "
        "raise SystemExit(0 if p.exists() and p.read_text(encoding='utf-8').strip() else 3)"
    )
    command = PackageCommand(
        command_id=ContractId(value="cmd.check-output"),
        label="Check real provider output",
        command=(sys.executable, "-c", check_code),
        cwd=".",
    )
    return ExecutionPackage(
        execution_package_id=ExecutionPackageId(value="exec.ticket.tiny.atomic.1"),
        ticket_ref=TicketId(value="ticket.tiny.atomic"),
        graph_version=1,
        seat_ref=AgentSeatRef(value="seat.worker.implementation"),
        model_execution_profile=model_execution_profile,
        role_prompt_hook=_baseline_worker_role_prompt_hook(),
        objective=(
            "Create work/real-provider-output.txt with a short non-empty sentence, "
            "run cmd.check-output, then submit the result. The final submit_result action must be exactly one JSON object "
            "with top-level action_id, action, reason_summary, and input fields. The input field must contain "
            'summary, produced_paths as ["work/real-provider-output.txt"], and evidence_refs as ["cmd.check-output"].'
        ),
        context_refs=(ContextRef(value="context.v2-090h.proving"),),
        constraints=(
            "Only write under work/.",
            "Use run_command with cmd.check-output before submit_result.",
            (
                "For submit_result, do not use action_envelope. Use this shape: "
                '{"action_id":"act.submit-result","action":"submit_result","reason_summary":"done",'
                '"input":{"summary":"Created and verified work/real-provider-output.txt",'
                '"produced_paths":["work/real-provider-output.txt"],"evidence_refs":["cmd.check-output"]}}'
            ),
        ),
        acceptance_refs=(AcceptanceRef(value="AC-PROVING-OUTPUT"),),
        source_surface_refs=(SourceSurfaceRef(value="surface.proving.work"),),
        allowed_read_refs=(AllowedReadRef(value="README.md"),),
        allowed_write_set=(AllowedWritePath(value="work/"),),
        required_outputs=(RequiredOutput(value="work/real-provider-output.txt"),),
        commands=(command,),
        evidence_obligations=(evidence_obligation,),
        fallback_policy_ref=FallbackPolicyRef(value="fallback.default"),
        audit_requirements=(AuditRequirement(value="record atomic provider and command evidence"),),
    )


def _new_run_id(prefix: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}.tiny-proving.{stamp}.{uuid4().hex[:8]}"


def _baseline_worker_role_prompt_hook():
    return build_baseline_role_prompt_hook_registry().require(
        RolePromptHookRef(value="role-prompt-hook.baseline.worker.v1")
    )


if __name__ == "__main__":
    raise SystemExit(main())
