from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class PrdDeliveryTerminalStatus(StrEnum):
    PASSED_WITHOUT_REWORK = "passed_without_rework"
    PASSED_AFTER_REWORK = "passed_after_rework"
    ESCALATED_OR_EXHAUSTED = "escalated_or_exhausted"
    BLOCKED_FAIL_CLOSED = "blocked_fail_closed"


class PrdDeliveryInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    prd_path: Path | None = None
    prd_text: str | None = None
    workspace_root: Path
    output_root: Path
    runtime_config_path: Path
    providers_config_path: Path
    roles_config_path: Path
    require_real_provider: bool = True
    reset: bool = False
    publish: bool = False

    @model_validator(mode="after")
    def _validate_prd_source(self) -> "PrdDeliveryInput":
        if (self.prd_path is None) == (self.prd_text is None):
            raise ValueError("exactly one of prd_path or prd_text is required")
        if self.prd_text is not None and not self.prd_text.strip():
            raise ValueError("prd_text must not be empty")
        return self


class PrdDeliveryStageResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    closeout_passed: bool
    run_manifest_path: Path | None = None
    graph_refs: tuple[str, ...] = ()
    provider_attempt_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    closeout_refs: tuple[str, ...] = ()
    verified_blocker_refs: tuple[str, ...] = ()
    observed_failure_refs: tuple[str, ...] = ()
    raw_error_ref: str | None = None

    @field_validator(
        "graph_refs",
        "provider_attempt_refs",
        "evidence_refs",
        "closeout_refs",
        "verified_blocker_refs",
        "observed_failure_refs",
    )
    @classmethod
    def _reject_empty_refs(cls, refs: tuple[str, ...]) -> tuple[str, ...]:
        for ref in refs:
            if not ref.strip():
                raise ValueError("refs must not contain empty values")
        return refs


class PrdDeliveryResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    terminal_status: PrdDeliveryTerminalStatus
    run_id: str
    workspace_root: Path
    output_root: Path
    graph_refs: tuple[str, ...] = ()
    provider_attempt_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    closeout_refs: tuple[str, ...] = ()
    checked_refs: tuple[str, ...] = ()
    audit_path: Path | None = None
    rework_cycle_refs: tuple[str, ...] = ()


PrdDeliveryStageRunner = Callable[[PrdDeliveryInput], PrdDeliveryStageResult]
NativeManifestRunner = Callable[[Any], Any]


def run_prd_delivery(
    input: PrdDeliveryInput,
    *,
    stage_runner: PrdDeliveryStageRunner | None = None,
    native_manifest_runner: NativeManifestRunner | None = None,
) -> PrdDeliveryResult:
    delivery_input = PrdDeliveryInput.model_validate(input)
    run_id = _new_run_id()

    provider_blocker = _real_provider_blocker(delivery_input)
    if provider_blocker is not None:
        return _finalize_result(
            PrdDeliveryResult(
                terminal_status=PrdDeliveryTerminalStatus.BLOCKED_FAIL_CLOSED,
                run_id=run_id,
                workspace_root=delivery_input.workspace_root,
                output_root=delivery_input.output_root,
                checked_refs=(provider_blocker,),
                audit_path=_audit_path(delivery_input.output_root),
            )
        )

    runner = stage_runner or _run_default_prd_delivery_stage
    try:
        stage_result = PrdDeliveryStageResult.model_validate(runner(delivery_input))
    except Exception as error:
        raw_error_ref = _write_raw_run_error(delivery_input.output_root, error)
        return _finalize_result(
            PrdDeliveryResult(
                terminal_status=PrdDeliveryTerminalStatus.BLOCKED_FAIL_CLOSED,
                run_id=run_id,
                workspace_root=delivery_input.workspace_root,
                output_root=delivery_input.output_root,
                checked_refs=("stage_runner_exception", raw_error_ref),
                audit_path=_audit_path(delivery_input.output_root),
            )
        )

    if stage_result.closeout_passed:
        return _finalize_result(
            PrdDeliveryResult(
                terminal_status=PrdDeliveryTerminalStatus.PASSED_WITHOUT_REWORK,
                run_id=run_id,
                workspace_root=delivery_input.workspace_root,
                output_root=delivery_input.output_root,
                graph_refs=stage_result.graph_refs,
                provider_attempt_refs=stage_result.provider_attempt_refs,
                evidence_refs=stage_result.evidence_refs,
                closeout_refs=stage_result.closeout_refs,
                checked_refs=("closeout_gate_passed",),
                audit_path=_audit_path(delivery_input.output_root),
            )
        )

    if not stage_result.verified_blocker_refs:
        return _finalize_result(
            PrdDeliveryResult(
                terminal_status=PrdDeliveryTerminalStatus.BLOCKED_FAIL_CLOSED,
                run_id=run_id,
                workspace_root=delivery_input.workspace_root,
                output_root=delivery_input.output_root,
                graph_refs=stage_result.graph_refs,
                provider_attempt_refs=stage_result.provider_attempt_refs,
                evidence_refs=stage_result.evidence_refs,
                closeout_refs=stage_result.closeout_refs,
                checked_refs=_merge_refs(
                    stage_result.observed_failure_refs,
                    ("verified_blocker_missing_for_rework",),
                ),
                audit_path=_audit_path(delivery_input.output_root),
            )
        )

    if stage_result.run_manifest_path is None:
        return _finalize_result(
            PrdDeliveryResult(
                terminal_status=PrdDeliveryTerminalStatus.BLOCKED_FAIL_CLOSED,
                run_id=run_id,
                workspace_root=delivery_input.workspace_root,
                output_root=delivery_input.output_root,
                graph_refs=stage_result.graph_refs,
                provider_attempt_refs=stage_result.provider_attempt_refs,
                evidence_refs=stage_result.evidence_refs,
                closeout_refs=stage_result.closeout_refs,
                checked_refs=stage_result.verified_blocker_refs
                + ("run_manifest_missing_for_rework",),
                audit_path=_audit_path(delivery_input.output_root),
            )
        )

    from boardroom_os.proving.v2_100f_native_manifest_rework import (
        V2_100FNativeManifestReworkInput,
        V2_100FNativeManifestReworkResult,
        run_v2_100f_native_manifest_rework,
    )

    manifest_runner = native_manifest_runner or run_v2_100f_native_manifest_rework
    try:
        native_result = manifest_runner(
            V2_100FNativeManifestReworkInput(
                output_root=delivery_input.output_root,
                workspace_root=delivery_input.workspace_root,
                run_manifest_path=stage_result.run_manifest_path,
                require_real_provider=delivery_input.require_real_provider,
                deterministic_provider_fixture=False,
                runtime_config_path=delivery_input.runtime_config_path.as_posix(),
                providers_config_path=delivery_input.providers_config_path.as_posix(),
                roles_config_path=delivery_input.roles_config_path.as_posix(),
            )
        )
    except Exception as error:
        raw_error_ref = _write_raw_run_error(delivery_input.output_root, error)
        return _finalize_result(
            PrdDeliveryResult(
                terminal_status=PrdDeliveryTerminalStatus.BLOCKED_FAIL_CLOSED,
                run_id=run_id,
                workspace_root=delivery_input.workspace_root,
                output_root=delivery_input.output_root,
                graph_refs=stage_result.graph_refs,
                provider_attempt_refs=stage_result.provider_attempt_refs,
                evidence_refs=stage_result.evidence_refs,
                closeout_refs=stage_result.closeout_refs,
                checked_refs=stage_result.verified_blocker_refs
                + ("native_manifest_runner_exception", raw_error_ref),
                audit_path=_audit_path(delivery_input.output_root),
            )
        )

    return _finalize_result(
        _result_from_native_rework(
            delivery_input=delivery_input,
            run_id=run_id,
            stage_result=stage_result,
            native_result=V2_100FNativeManifestReworkResult.model_validate(native_result),
        )
    )


def _run_default_prd_delivery_stage(
    delivery_input: PrdDeliveryInput,
) -> PrdDeliveryStageResult:
    from boardroom_os.config.boardroom import load_boardroom_settings
    from boardroom_os.proving.v2_090f_prd_agent_team import (
        build_v2_090f_planning_provider_adapter,
        reset_v2_090f_workspace,
        resolve_v2_090f_config_paths_from_env,
        run_v2_090f_closeout_stage,
        run_v2_090f_planning_preflight,
        run_v2_090f_provider_planning_stage,
        run_v2_090f_worker_execution_stage,
        validate_agent_team_autonomy_inputs,
    )

    prd = _load_prd(delivery_input)
    validate_agent_team_autonomy_inputs(prd_text=prd.text, predefined_ticket_refs=())
    if delivery_input.reset:
        reset_v2_090f_workspace(delivery_input.workspace_root)
    env_values = _env_values_for_input(delivery_input)
    run_v2_090f_planning_preflight(
        prd=prd,
        output_root=delivery_input.output_root,
        env_values=env_values,
    )
    settings = load_boardroom_settings(
        paths=resolve_v2_090f_config_paths_from_env(env_values),
        env_values=env_values,
    )
    run_v2_090f_provider_planning_stage(
        prd=prd,
        output_root=delivery_input.output_root,
        settings=settings,
        provider_adapter_factory=lambda seat_ref, output_name: build_v2_090f_planning_provider_adapter(
            settings=settings,
            seat_ref=seat_ref,
            output_root=delivery_input.output_root,
        ),
    )
    try:
        run_v2_090f_worker_execution_stage(
            output_root=delivery_input.output_root,
            workspace_root=delivery_input.workspace_root,
            settings=settings,
        )
        run_v2_090f_closeout_stage(
            output_root=delivery_input.output_root,
            workspace_root=delivery_input.workspace_root,
            settings=settings,
        )
    except Exception as error:
        raw_error_ref = _write_raw_run_error(delivery_input.output_root, error)
        return PrdDeliveryStageResult(
            closeout_passed=False,
            run_manifest_path=_discover_run_manifest_path(delivery_input.output_root),
            graph_refs=_discover_graph_refs(delivery_input.output_root),
            provider_attempt_refs=_discover_provider_attempt_refs(delivery_input.output_root),
            evidence_refs=_discover_evidence_refs(delivery_input.output_root),
            observed_failure_refs=("stage_exception", raw_error_ref),
            raw_error_ref=raw_error_ref,
        )

    return PrdDeliveryStageResult(
        closeout_passed=True,
        run_manifest_path=_discover_run_manifest_path(delivery_input.output_root),
        graph_refs=_discover_graph_refs(delivery_input.output_root),
        provider_attempt_refs=_discover_provider_attempt_refs(delivery_input.output_root),
        evidence_refs=_discover_evidence_refs(delivery_input.output_root),
        closeout_refs=("closeout-gate.passed",),
    )


def _result_from_native_rework(
    *,
    delivery_input: PrdDeliveryInput,
    run_id: str,
    stage_result: PrdDeliveryStageResult,
    native_result: Any,
) -> PrdDeliveryResult:
    terminal_status = _map_native_terminal_status(native_result)
    rework_cycle_refs = _native_rework_refs(native_result)
    checked_refs = stage_result.verified_blocker_refs + (
        f"native_manifest_terminal:{native_result.terminal_status.value}",
    )
    if native_result.blocked_reason_code:
        checked_refs += (f"native_manifest_blocked:{native_result.blocked_reason_code}",)

    return PrdDeliveryResult(
        terminal_status=terminal_status,
        run_id=run_id,
        workspace_root=delivery_input.workspace_root,
        output_root=delivery_input.output_root,
        graph_refs=_merge_refs(
            stage_result.graph_refs,
            (
                native_result.before_graph_ref,
                native_result.seat_assignment_ref,
            ),
        ),
        provider_attempt_refs=_merge_refs(
            stage_result.provider_attempt_refs,
            (native_result.provider_attempt_ref,),
        ),
        evidence_refs=_merge_refs(
            stage_result.evidence_refs,
            native_result.fact_refs,
            (native_result.blackbox_plan_ref,),
        ),
        closeout_refs=stage_result.closeout_refs,
        checked_refs=checked_refs,
        audit_path=_audit_path(delivery_input.output_root),
        rework_cycle_refs=rework_cycle_refs,
    )


def _map_native_terminal_status(
    native_result: Any,
) -> PrdDeliveryTerminalStatus:
    terminal = _terminal_value(native_result)
    if terminal == "passed":
        return PrdDeliveryTerminalStatus.PASSED_AFTER_REWORK
    if terminal == "rework_required":
        return PrdDeliveryTerminalStatus.ESCALATED_OR_EXHAUSTED
    return PrdDeliveryTerminalStatus.BLOCKED_FAIL_CLOSED


def _native_rework_refs(
    native_result: Any,
) -> tuple[str, ...]:
    refs = ["v2-100f-native-manifest-rework"]
    if native_result.rework_request_ref:
        refs.append(native_result.rework_request_ref)
    return tuple(refs)


def _load_prd(delivery_input: PrdDeliveryInput) -> Any:
    from boardroom_os.proving.v2_090f_prd_agent_team import LoadedPrd, load_v2_090f_prd

    if delivery_input.prd_path is not None:
        return load_v2_090f_prd(delivery_input.prd_path)
    assert delivery_input.prd_text is not None
    text = delivery_input.prd_text.strip()
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return LoadedPrd(path="inline://prd", text=text, sha256=f"sha256:{digest}")


def _real_provider_blocker(delivery_input: PrdDeliveryInput) -> str | None:
    if not delivery_input.require_real_provider:
        return None
    if os.environ.get("BOARDROOM_RUN_REAL_PROVIDER_PROVING") != "1":
        return "real_provider_opt_in_missing"
    missing = [
        path.as_posix()
        for path in (
            delivery_input.runtime_config_path,
            delivery_input.providers_config_path,
            delivery_input.roles_config_path,
        )
        if not path.is_file()
    ]
    if missing:
        return "config_path_missing:" + ",".join(missing)
    return None


def _env_values_for_input(delivery_input: PrdDeliveryInput) -> dict[str, str]:
    env_values = dict(os.environ)
    env_values["BOARDROOM_RUNTIME_CONFIG"] = delivery_input.runtime_config_path.as_posix()
    env_values["BOARDROOM_PROVIDERS_CONFIG"] = delivery_input.providers_config_path.as_posix()
    env_values["BOARDROOM_ROLES_CONFIG"] = delivery_input.roles_config_path.as_posix()
    return env_values


def _discover_run_manifest_path(output_root: Path) -> Path | None:
    for path in (
        output_root / "20-evidence" / "tests" / "run-manifest.json",
        output_root / "00-boardroom" / "generated-run-manifest.json",
    ):
        if path.is_file():
            return path
    return None


def _discover_graph_refs(output_root: Path) -> tuple[str, ...]:
    refs: list[str] = []
    if (output_root / "00-boardroom" / "generated-ticket-graph.json").is_file():
        refs.append("00-boardroom/generated-ticket-graph.json")
    if (output_root / "00-boardroom" / "run-manifest-ingestion-context.json").is_file():
        refs.append("00-boardroom/run-manifest-ingestion-context.json")
    return tuple(refs)


def _discover_provider_attempt_refs(output_root: Path) -> tuple[str, ...]:
    refs: list[str] = []
    boardroom_root = output_root / "00-boardroom"
    if boardroom_root.is_dir():
        for path in sorted(boardroom_root.glob("generated-*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            ref = str(payload.get("provider_attempt_ref", "")).strip()
            if ref:
                refs.append(ref)
    worker_path = output_root / "20-evidence" / "worker-execution.json"
    if worker_path.is_file():
        try:
            worker = json.loads(worker_path.read_text(encoding="utf-8"))
        except Exception:
            worker = {}
        for ticket in worker.get("tickets", []):
            if isinstance(ticket, dict):
                ref = str(ticket.get("provider_attempt_ref", "")).strip()
                if ref:
                    refs.append(ref)
    return tuple(dict.fromkeys(refs))


def _discover_evidence_refs(output_root: Path) -> tuple[str, ...]:
    evidence_root = output_root / "20-evidence"
    refs = []
    for relative in (
        "worker-execution.json",
        "tests/run-manifest.json",
        "tests/live-blackbox.json",
        "closeout/final-evidence-table.json",
        "closeout/closeout-gate-result.json",
    ):
        if (evidence_root / relative).is_file():
            refs.append(f"20-evidence/{relative}")
    return tuple(refs)


def _merge_refs(*groups: tuple[str | None, ...]) -> tuple[str, ...]:
    refs: list[str] = []
    for group in groups:
        for ref in group:
            if ref and ref not in refs:
                refs.append(ref)
    return tuple(refs)


def _new_run_id() -> str:
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"run.prd-delivery.{timestamp}"


def _terminal_value(native_result: Any) -> str:
    terminal = getattr(native_result, "terminal_status")
    return str(getattr(terminal, "value", terminal))


def _audit_path(output_root: Path) -> Path:
    return output_root / "30-audit" / "prd-delivery.json"


def _write_raw_run_error(output_root: Path, error: Exception) -> str:
    path = output_root / "30-audit" / "raw-run-error.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{type(error).__name__}: {error}\n", encoding="utf-8")
    return path.as_posix()


def _finalize_result(result: PrdDeliveryResult) -> PrdDeliveryResult:
    assert result.audit_path is not None
    result.audit_path.parent.mkdir(parents=True, exist_ok=True)
    result.audit_path.write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    md_path = result.audit_path.with_suffix(".md")
    md_path.write_text(
        "\n".join(
            (
                "# PRD Delivery Audit",
                "",
                f"- run_id: {result.run_id}",
                f"- terminal_status: {result.terminal_status.value}",
                f"- output_root: {result.output_root.as_posix()}",
                f"- rework_cycle_refs: {', '.join(result.rework_cycle_refs) or 'none'}",
                f"- checked_refs: {', '.join(result.checked_refs) or 'none'}",
                "",
            )
        ),
        encoding="utf-8",
    )
    return result
