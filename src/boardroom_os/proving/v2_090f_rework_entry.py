from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from boardroom_os.closeout.gate import CloseoutGateResult, CloseoutGateVerdict
from boardroom_os.contracts.types import AcceptanceRef, ContractId, EvidenceObligationRef, SourceSurfaceRef
from boardroom_os.rework.blocker_projection import (
    BlockerProjectionContext,
    project_closeout_gate_blockers,
)
from boardroom_os.rework.model import ReworkActorKind, ReworkCycleId, RunId
from boardroom_os.proving.v2_100_rework_loop import (
    V2_100ScenarioInput,
    V2_100ScenarioTerminalStatus,
    export_v2_100_rework_audit,
    run_v2_100_rework_loop_for_request,
)


class V2_090FReworkEntryStatus(StrEnum):
    PASSED_WITHOUT_REWORK_CANDIDATE = "passed_without_rework_candidate"
    REWORK_ACCEPTED_CANDIDATE = "rework_accepted_candidate"
    REWORK_ESCALATED_OR_EXHAUSTED = "rework_escalated_or_exhausted"
    BLOCKED_BY_MISSING_REWORK_ENTRY = "blocked_by_missing_rework_entry"


class V2_090FTicketGraphNodeSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    owner_seat_ref: str
    status: str
    acceptance_ref_count: int = Field(ge=0)
    evidence_obligation_count: int = Field(ge=0)


class V2_090FTicketGraphSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    graph_version: int = Field(gt=0)
    source_ref: str
    nodes: tuple[V2_090FTicketGraphNodeSnapshot, ...]
    edges: tuple[tuple[str, str], ...] = ()
    ticket_graph_patch_ref: str | None = None

    @model_validator(mode="after")
    def _validate_patch_binding(self) -> "V2_090FTicketGraphSnapshot":
        if "after-rework" in self.source_ref and not self.ticket_graph_patch_ref:
            raise ValueError("after-rework graph requires ticket_graph_patch_ref")
        if not self.nodes:
            raise ValueError("ticket graph snapshot nodes must not be empty")
        return self


class V2_090FReworkEntryValidationInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    output_root: Path
    workspace_root: Path
    run_id: str
    cycle_id: str
    max_rounds: int = Field(gt=0)
    require_real_provider: bool = True


class V2_090FReworkEntryValidationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: V2_090FReworkEntryStatus
    before_graph_json_path: Path
    before_graph_mermaid_path: Path
    after_graph_json_path: Path | None = None
    after_graph_mermaid_path: Path | None = None
    blocker_report_path: Path
    rework_request_path: Path | None = None
    rework_plan_path: Path | None = None
    ticket_graph_patch_path: Path | None = None
    terminal_path: Path
    report_path: Path
    checked_refs: tuple[str, ...]

    @model_validator(mode="after")
    def _validate_rework_accepted_paths(self) -> "V2_090FReworkEntryValidationResult":
        if self.status is not V2_090FReworkEntryStatus.REWORK_ACCEPTED_CANDIDATE:
            return self
        required_paths = {
            "after_graph_json_path": self.after_graph_json_path,
            "after_graph_mermaid_path": self.after_graph_mermaid_path,
            "rework_request_path": self.rework_request_path,
            "rework_plan_path": self.rework_plan_path,
            "ticket_graph_patch_path": self.ticket_graph_patch_path,
        }
        missing = [name for name, value in required_paths.items() if value is None]
        if missing:
            raise ValueError(
                "rework_accepted_candidate requires paths: " + ", ".join(missing)
            )
        return self


def _node_ref(node: dict[str, Any]) -> str:
    value = node.get("node_ref") or node.get("ticket_id")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("ticket graph node requires node_ref or ticket_id")
    return value.strip()


def _node_status(node: dict[str, Any]) -> str:
    value = node.get("status", "unknown")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("ticket graph node status must be text")
    return value.strip()


def _count_list_field(node: dict[str, Any], field_name: str) -> int:
    value = node.get(field_name)
    if value is None:
        return 0
    if not isinstance(value, list):
        raise ValueError(f"ticket graph {field_name} must be a list")
    return len(value)


def load_v2_090f_ticket_graph_snapshot(output_root: Path) -> V2_090FTicketGraphSnapshot:
    """Read generated ticket graph and return a before-rework snapshot."""

    source_path = Path(output_root) / "00-boardroom" / "generated-ticket-graph.json"
    data = json.loads(source_path.read_text(encoding="utf-8"))
    ticket_graph = data.get("provider_output", {}).get("ticket_graph")
    if not isinstance(ticket_graph, dict):
        raise ValueError("generated-ticket-graph.json requires provider_output.ticket_graph")
    raw_nodes = ticket_graph.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise ValueError("ticket graph snapshot nodes must not be empty")

    nodes: list[V2_090FTicketGraphNodeSnapshot] = []
    edge_set: set[tuple[str, str]] = set()
    for raw_node in raw_nodes:
        if not isinstance(raw_node, dict):
            raise ValueError("ticket graph node must be an object")
        ticket_id = _node_ref(raw_node)
        owner_seat_ref = raw_node.get("owner_seat_ref")
        if not isinstance(owner_seat_ref, str) or not owner_seat_ref.strip():
            raise ValueError("ticket graph node requires owner_seat_ref")
        nodes.append(
            V2_090FTicketGraphNodeSnapshot(
                ticket_id=ticket_id,
                owner_seat_ref=owner_seat_ref.strip(),
                status=_node_status(raw_node),
                acceptance_ref_count=_count_list_field(raw_node, "acceptance_refs"),
                evidence_obligation_count=_count_list_field(raw_node, "evidence_obligations"),
            )
        )
        depends_on = raw_node.get("depends_on", [])
        if depends_on is None:
            depends_on = []
        if not isinstance(depends_on, list):
            raise ValueError("ticket graph depends_on must be a list")
        for dependency in depends_on:
            if not isinstance(dependency, str) or not dependency.strip():
                raise ValueError("ticket graph depends_on entries must be text")
            edge_set.add((dependency.strip(), ticket_id))

    return V2_090FTicketGraphSnapshot(
        graph_version=ticket_graph["graph_version"],
        source_ref="00-boardroom/generated-ticket-graph.json",
        nodes=tuple(nodes),
        edges=tuple(sorted(edge_set)),
    )


def render_v2_090f_ticket_graph_mermaid(snapshot: V2_090FTicketGraphSnapshot) -> str:
    """Render a graph TD Mermaid view for a V2-090F ticket graph snapshot."""

    labels = {
        node.ticket_id: (
            f"{node.ticket_id}\\n{node.owner_seat_ref}\\n{node.status}\\n"
            f"AC:{node.acceptance_ref_count} EV:{node.evidence_obligation_count}"
        )
        for node in snapshot.nodes
    }
    lines = ["graph TD"]
    for node in snapshot.nodes:
        lines.append(f'  "{labels[node.ticket_id]}"')
    for source, target in snapshot.edges:
        source_label = labels.get(source, source)
        target_label = labels.get(target, target)
        lines.append(f'  "{source_label}" --> "{target_label}"')
    return "\n".join(lines) + "\n"


def run_v2_090f_rework_entry_validation(
    validation_input: V2_090FReworkEntryValidationInput,
) -> V2_090FReworkEntryValidationResult:
    """Validate V2-090F closeout or return a fail-closed rework-entry terminal."""

    validation_input = V2_090FReworkEntryValidationInput.model_validate(validation_input)
    output_root = validation_input.output_root
    boardroom_root = output_root / "00-boardroom"
    rework_entry_root = output_root / "20-evidence" / "rework-entry"
    audit_root = output_root / "30-audit"
    rework_entry_root.mkdir(parents=True, exist_ok=True)
    audit_root.mkdir(parents=True, exist_ok=True)

    before_snapshot = load_v2_090f_ticket_graph_snapshot(output_root)
    before_graph_json_path = boardroom_root / "ticket-graph.before-rework.json"
    before_graph_mermaid_path = boardroom_root / "ticket-graph.before-rework.md"
    _write_json(before_graph_json_path, before_snapshot.model_dump(mode="json"))
    before_graph_mermaid_path.write_text(
        render_v2_090f_ticket_graph_mermaid(before_snapshot),
        encoding="utf-8",
    )

    closeout_result = _load_optional_json(
        output_root / "20-evidence" / "closeout" / "closeout-gate-result.json"
    )
    checked_refs = _checked_refs(closeout_result)
    blocker_report_path = rework_entry_root / "blocker-report.json"
    terminal_path = rework_entry_root / "rework-terminal.json"
    report_path = audit_root / "rework-entry-validation.md"

    if _closeout_gate_passed(closeout_result):
        closeout_package_path = output_root / "closeout-package.json"
        if not closeout_package_path.is_file():
            raise ValueError("passed closeout candidate requires closeout-package.json")
        closeout_package = _load_json(closeout_package_path)
        if closeout_package.get("verdict") != "passed":
            raise ValueError("passed closeout candidate requires passed closeout package")

        _write_json(
            blocker_report_path,
            {
                "blockers": [],
                "status": "no_verified_blocker",
                "source_ref": "20-evidence/closeout/closeout-gate-result.json",
            },
        )
        _write_json(
            terminal_path,
            {
                "terminal_status": V2_090FReworkEntryStatus.PASSED_WITHOUT_REWORK_CANDIDATE.value,
                "run_id": validation_input.run_id,
                "cycle_id": validation_input.cycle_id,
                "checked_refs": list(checked_refs),
            },
        )
        report_path.write_text(
            "\n".join(
                (
                    "# V2-090F Rework Entry Validation",
                    "",
                    f"run_id: {validation_input.run_id}",
                    f"terminal_status: {V2_090FReworkEntryStatus.PASSED_WITHOUT_REWORK_CANDIDATE.value}",
                    "",
                    "CloseoutGate passed, so no ReworkRequest was created.",
                    f"before_graph_json: {before_graph_json_path.as_posix()}",
                    f"before_graph_mermaid: {before_graph_mermaid_path.as_posix()}",
                )
            )
            + "\n",
            encoding="utf-8",
        )
        return V2_090FReworkEntryValidationResult(
            status=V2_090FReworkEntryStatus.PASSED_WITHOUT_REWORK_CANDIDATE,
            before_graph_json_path=before_graph_json_path,
            before_graph_mermaid_path=before_graph_mermaid_path,
            blocker_report_path=blocker_report_path,
            terminal_path=terminal_path,
            report_path=report_path,
            checked_refs=checked_refs,
        )

    structured_request = _project_structured_closeout_blockers(
        output_root=output_root,
        validation_input=validation_input,
        closeout_result=closeout_result,
        active_graph_version=before_snapshot.graph_version,
    )
    if structured_request is not None:
        rework_request_path = rework_entry_root / "rework-request.json"
        _write_json(rework_request_path, structured_request.model_dump(mode="json"))
        continuation_result = run_v2_100_rework_loop_for_request(
            _build_v2_100_scenario_input(
                output_root=output_root,
                validation_input=validation_input,
                active_graph_version=before_snapshot.graph_version,
            ),
            request=structured_request,
        )
        continuation_status = _status_value(continuation_result.terminal_status)
        if continuation_status == V2_100ScenarioTerminalStatus.ACCEPTED.value:
            status = V2_090FReworkEntryStatus.REWORK_ACCEPTED_CANDIDATE
        else:
            status = V2_090FReworkEntryStatus.REWORK_ESCALATED_OR_EXHAUSTED
        final_round = continuation_result.rounds[-1]
        patch_ref = _ref_value(final_round.patch.ticket_graph_patch_id)
        after_snapshot = _after_graph_snapshot(
            before_snapshot=before_snapshot,
            continuation_result=continuation_result,
            patch_ref=patch_ref,
        )
        rework_plan_path = rework_entry_root / "rework-plan.json"
        ticket_graph_patch_path = rework_entry_root / "ticket-graph-patch.json"
        _write_json(rework_plan_path, _model_dump(final_round.plan_output.plan))
        _write_json(ticket_graph_patch_path, _model_dump(final_round.patch))

        after_graph_json_path = boardroom_root / "ticket-graph.after-rework.json"
        after_graph_mermaid_path = boardroom_root / "ticket-graph.after-rework.md"
        _write_json(after_graph_json_path, after_snapshot.model_dump(mode="json"))
        after_graph_mermaid_path.write_text(
            render_v2_090f_ticket_graph_mermaid(after_snapshot),
            encoding="utf-8",
        )
        audit_export_path: str | None = None
        if hasattr(continuation_result, "model_dump"):
            audit_export = export_v2_100_rework_audit(
                continuation_result,
                rework_entry_root / "v2-100-audit",
            )
            audit_export_path = audit_export.export_root.as_posix()
        _write_json(
            blocker_report_path,
            {
                "status": "verified_blocker_projected",
                "source_ref": "20-evidence/closeout/closeout-gate-result.json",
                "blockers": [
                    ref["value"]
                    for issue in structured_request.model_dump(mode="json")["issues"]
                    for ref in issue["blocker_refs"]
                ],
            },
        )
        _write_json(
            terminal_path,
            {
                "terminal_status": status.value,
                "run_id": validation_input.run_id,
                "cycle_id": validation_input.cycle_id,
                "checked_refs": list(checked_refs),
                "rework_request_path": rework_request_path.as_posix(),
                "rework_plan_path": rework_plan_path.as_posix(),
                "ticket_graph_patch_path": ticket_graph_patch_path.as_posix(),
                "v2_100_terminal_status": continuation_status,
                "v2_100_audit_path": audit_export_path,
            },
        )
        report_path.write_text(
            "\n".join(
                (
                    "# V2-090F Rework Entry Validation",
                    "",
                    f"run_id: {validation_input.run_id}",
                    f"terminal_status: {status.value}",
                    f"rework_request: {rework_request_path.as_posix()}",
                    f"rework_plan: {rework_plan_path.as_posix()}",
                    f"ticket_graph_patch: {ticket_graph_patch_path.as_posix()}",
                    f"before_graph_json: {before_graph_json_path.as_posix()}",
                    f"after_graph_json: {after_graph_json_path.as_posix()}",
                )
            )
            + "\n",
            encoding="utf-8",
        )
        return V2_090FReworkEntryValidationResult(
            status=status,
            before_graph_json_path=before_graph_json_path,
            before_graph_mermaid_path=before_graph_mermaid_path,
            after_graph_json_path=after_graph_json_path,
            after_graph_mermaid_path=after_graph_mermaid_path,
            blocker_report_path=blocker_report_path,
            rework_request_path=rework_request_path,
            rework_plan_path=rework_plan_path,
            ticket_graph_patch_path=ticket_graph_patch_path,
            terminal_path=terminal_path,
            report_path=report_path,
            checked_refs=checked_refs,
        )

    _write_json(
        blocker_report_path,
        {
            "blockers": [],
            "status": "missing_verified_blocker",
            "source_ref": None,
        },
    )
    _write_json(
        terminal_path,
        {
            "terminal_status": V2_090FReworkEntryStatus.BLOCKED_BY_MISSING_REWORK_ENTRY.value,
            "run_id": validation_input.run_id,
            "cycle_id": validation_input.cycle_id,
            "checked_refs": list(checked_refs),
        },
    )
    report_path.write_text(
        "\n".join(
            (
                "# V2-090F Rework Entry Validation",
                "",
                f"run_id: {validation_input.run_id}",
                f"terminal_status: {V2_090FReworkEntryStatus.BLOCKED_BY_MISSING_REWORK_ENTRY.value}",
                "",
                "No typed verified blocker was available for ReworkRequest projection.",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return V2_090FReworkEntryValidationResult(
        status=V2_090FReworkEntryStatus.BLOCKED_BY_MISSING_REWORK_ENTRY,
        before_graph_json_path=before_graph_json_path,
        before_graph_mermaid_path=before_graph_mermaid_path,
        blocker_report_path=blocker_report_path,
        terminal_path=terminal_path,
        report_path=report_path,
        checked_refs=checked_refs,
    )


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.as_posix()} must contain a JSON object")
    return data


def _load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return _load_json(path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _closeout_gate_passed(payload: dict[str, Any] | None) -> bool:
    if payload is None:
        return False
    return payload.get("verdict") == "passed" and payload.get("blockers") == []


def _checked_refs(payload: dict[str, Any] | None) -> tuple[str, ...]:
    if payload is None:
        return ()
    value = payload.get("checked_refs", [])
    if not isinstance(value, list):
        raise ValueError("closeout gate checked_refs must be a list")
    refs: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("closeout gate checked_refs entries must be text")
        refs.append(item.strip())
    return tuple(refs)


def _project_structured_closeout_blockers(
    *,
    output_root: Path,
    validation_input: V2_090FReworkEntryValidationInput,
    closeout_result: dict[str, Any] | None,
    active_graph_version: int,
) -> Any | None:
    if closeout_result is None:
        return None
    result = CloseoutGateResult.model_validate(closeout_result)
    if result.verdict is CloseoutGateVerdict.PASSED:
        return None
    if not result.blockers:
        return None
    try:
        active_acceptance_refs = tuple(
            AcceptanceRef(value=value)
            for value in _load_active_acceptance_refs(output_root)
        )
        active_source_surface_refs = tuple(
            SourceSurfaceRef(value=value)
            for value in _load_active_source_surface_refs(output_root)
        )
        active_evidence_obligation_refs = tuple(
            EvidenceObligationRef(value=value)
            for value in _load_active_evidence_obligation_refs(output_root)
        )
    except (KeyError, TypeError, ValueError):
        return None
    context = BlockerProjectionContext(
        cycle_id=ReworkCycleId(value=validation_input.cycle_id),
        run_id=RunId(value=validation_input.run_id),
        package_contract_ref=ContractId(value=_load_package_contract_ref(output_root)),
        run_manifest_ref=_load_run_manifest_ref(output_root),
        active_acceptance_refs=active_acceptance_refs,
        active_source_surface_refs=active_source_surface_refs,
        active_evidence_obligation_refs=active_evidence_obligation_refs,
        active_graph_version=active_graph_version,
        requested_by_actor=ReworkActorKind.CLOSEOUT_GATE,
        requested_at=datetime.now(UTC),
    )
    return project_closeout_gate_blockers(result, context)


def _load_generated_contracts(output_root: Path) -> dict[str, Any]:
    return _load_json(output_root / "00-boardroom" / "generated-contracts.json")


def _load_active_acceptance_refs(output_root: Path) -> tuple[str, ...]:
    contracts = _load_generated_contracts(output_root)
    criteria = contracts["acceptance_contract"]["criteria"]
    if not isinstance(criteria, list):
        raise ValueError("acceptance_contract.criteria must be a list")
    refs = tuple(_required_text(item, "acceptance_ref") for item in criteria)
    if not refs:
        raise ValueError("active acceptance refs must not be empty")
    return refs


def _load_active_source_surface_refs(output_root: Path) -> tuple[str, ...]:
    contracts = _load_generated_contracts(output_root)
    surfaces = contracts["package_contract"]["source_surfaces"]
    if not isinstance(surfaces, list):
        raise ValueError("package_contract.source_surfaces must be a list")
    refs = tuple(_required_text(item, "source_surface_ref") for item in surfaces)
    if not refs:
        raise ValueError("active source surface refs must not be empty")
    return refs


def _load_active_evidence_obligation_refs(output_root: Path) -> tuple[str, ...]:
    contracts = _load_generated_contracts(output_root)
    obligations = contracts["evidence_obligations"]
    if not isinstance(obligations, list):
        raise ValueError("evidence_obligations must be a list")
    refs = tuple(_required_text(item, "evidence_obligation_id") for item in obligations)
    if not refs:
        raise ValueError("active evidence obligation refs must not be empty")
    return refs


def _load_package_contract_ref(output_root: Path) -> str:
    contracts = _load_generated_contracts(output_root)
    return _required_text(contracts["package_contract"], "package_contract_id")


def _load_run_manifest_ref(output_root: Path) -> str:
    run_manifest_path = output_root / "00-boardroom" / "generated-run-manifest.json"
    if not run_manifest_path.is_file():
        return "run-manifest.v2-090f.generated"
    run_manifest = _load_json(run_manifest_path)
    value = run_manifest.get("run_manifest_id") or run_manifest.get("run_manifest_ref")
    if value is None:
        return "run-manifest.v2-090f.generated"
    if isinstance(value, dict):
        value = value.get("value")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("run manifest ref must be text")
    return value.strip()


def _required_text(payload: dict[str, Any], field_name: str) -> str:
    value = payload[field_name]
    if isinstance(value, dict):
        value = value.get("value")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be text")
    return value.strip()


def _build_v2_100_scenario_input(
    *,
    output_root: Path,
    validation_input: V2_090FReworkEntryValidationInput,
    active_graph_version: int,
) -> V2_100ScenarioInput:
    request_start_path = (
        output_root / "20-evidence" / "rework-entry" / "rework-request.json"
    )
    return V2_100ScenarioInput(
        project_ref="project.v2-090f",
        snapshot_summary_path=request_start_path,
        run_id=validation_input.run_id,
        cycle_id=validation_input.cycle_id,
        package_contract_ref=_load_package_contract_ref(output_root),
        run_manifest_ref=_load_run_manifest_ref(output_root),
        active_acceptance_refs=_load_active_acceptance_refs(output_root),
        active_source_surface_refs=_load_active_source_surface_refs(output_root),
        active_evidence_obligation_refs=_load_active_evidence_obligation_refs(output_root),
        active_contract_refs=(_load_package_contract_ref(output_root),),
        initial_graph_version=active_graph_version,
        max_rounds=validation_input.max_rounds,
        export_root=output_root / "20-evidence" / "rework-entry" / "v2-100-audit",
        require_real_provider=validation_input.require_real_provider,
    )


def _after_graph_snapshot(
    *,
    before_snapshot: V2_090FTicketGraphSnapshot,
    continuation_result: Any,
    patch_ref: str,
) -> V2_090FTicketGraphSnapshot:
    after_graph_version = continuation_result.final_projection.graph_version
    if after_graph_version <= before_snapshot.graph_version:
        raise ValueError("after graph_version must be greater than before graph_version")
    rework_ticket_refs = _rework_ticket_refs(continuation_result.rounds[-1].patch)
    existing = {node.ticket_id for node in before_snapshot.nodes}
    rework_nodes = tuple(
        V2_090FTicketGraphNodeSnapshot(
            ticket_id=ticket_ref,
            owner_seat_ref="seat.worker.implementation",
            status="ready",
            acceptance_ref_count=1,
            evidence_obligation_count=1,
        )
        for ticket_ref in rework_ticket_refs
        if ticket_ref not in existing
    )
    return V2_090FTicketGraphSnapshot(
        graph_version=after_graph_version,
        source_ref="00-boardroom/ticket-graph.after-rework.json",
        nodes=before_snapshot.nodes + rework_nodes,
        edges=before_snapshot.edges,
        ticket_graph_patch_ref=patch_ref,
    )


def _rework_ticket_refs(patch: Any) -> tuple[str, ...]:
    refs: list[str] = []
    for ref in getattr(patch, "affected_ticket_refs", ()):
        refs.append(_ref_value(ref))
    for operation in getattr(patch, "operations", ()):
        for ref in getattr(operation, "target_ticket_refs", ()):
            refs.append(_ref_value(ref))
    return tuple(dict.fromkeys(ref for ref in refs if ref.startswith("ticket.rework.")))


def _model_dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        if not isinstance(dumped, dict):
            raise ValueError("model_dump must return a dict")
        return dumped
    if isinstance(value, dict):
        return value
    attrs = {
        key: _jsonable(attr)
        for key in dir(value)
        if not key.startswith("_")
        for attr in (getattr(value, key),)
        if not callable(attr)
    }
    if not attrs:
        raise ValueError("value cannot be serialized as JSON object")
    return attrs


def _jsonable(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if hasattr(value, "value"):
        return {"value": value.value}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "__dict__"):
        return {
            key: _jsonable(item)
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return value


def _ref_value(value: Any) -> str:
    raw = value.value if hasattr(value, "value") else value
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("ref value must be text")
    return raw.strip()


def _status_value(value: Any) -> str:
    raw = value.value if hasattr(value, "value") else value
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("status value must be text")
    return raw.strip()
