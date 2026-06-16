from __future__ import annotations

import hashlib
import json
from pathlib import Path

from boardroom_os.rework.evidence import recheck_rework_attempt
from boardroom_os.rework.model import ReworkOutcomeStatus, ReworkTerminationReason
from boardroom_os.reducers.rework import ReworkTerminalStatus
from boardroom_os.events.types import EventType
from boardroom_os.closeout.gate import CloseoutGateVerdict


def test_resettable_fixture_builds_failing_and_accepted_recheck_inputs(tmp_path: Path) -> None:
    from boardroom_os.proving.v2_100_resettable_fixture import build_v2_100_resettable_fixture

    fixture = build_v2_100_resettable_fixture(package_root=tmp_path / "package")

    assert fixture.failing_recheck_input.target_blocker_refs
    assert fixture.accepted_recheck_input.target_blocker_refs
    assert (
        fixture.failing_recheck_input.attempt.rework_attempt_id
        != fixture.accepted_recheck_input.attempt.rework_attempt_id
    )

    failing_result = recheck_rework_attempt(fixture.failing_recheck_input)
    accepted_result = recheck_rework_attempt(fixture.accepted_recheck_input)

    assert failing_result.status is ReworkOutcomeStatus.REWORK_REQUIRED
    assert failing_result.remaining_blocker_refs
    assert accepted_result.status is ReworkOutcomeStatus.ACCEPTED
    assert accepted_result.accepted_blocker_refs == fixture.accepted_recheck_input.target_blocker_refs


def test_resettable_fixture_round_builders_return_typed_inputs(tmp_path: Path) -> None:
    from boardroom_os.proving.v2_100_resettable_fixture import (
        build_accepted_round_input,
        build_exhausted_round_provider,
        build_two_round_provider,
        build_v2_100_scenario_input,
    )
    from boardroom_os.proving.v2_100_rework_loop import ScenarioRoundBuild, project_snapshot_request

    accepted_build = build_accepted_round_input(tmp_path)
    scenario_input = build_v2_100_scenario_input(package_root=tmp_path / "package", require_real_provider=False)
    request = project_snapshot_request(scenario_input)
    two_round_build = build_two_round_provider(tmp_path).build_round(
        scenario_input,
        request,
        round_index=1,
        started_at_graph_version=scenario_input.initial_graph_version,
    )
    exhausted_build = build_exhausted_round_provider(tmp_path).build_round(
        scenario_input,
        request,
        round_index=1,
        started_at_graph_version=scenario_input.initial_graph_version,
    )

    assert isinstance(accepted_build, ScenarioRoundBuild)
    assert isinstance(two_round_build, ScenarioRoundBuild)
    assert isinstance(exhausted_build, ScenarioRoundBuild)
    assert exhausted_build.round_input.terminal_decision is not None


def test_one_round_accepted_path_reduces_to_accepted_projection(tmp_path: Path) -> None:
    from boardroom_os.proving.v2_100_resettable_fixture import build_accepted_round_input
    from boardroom_os.proving.v2_100_rework_loop import run_v2_100_rework_round

    round_build = build_accepted_round_input(tmp_path)

    result = run_v2_100_rework_round(round_build)

    assert result.outcome.status is ReworkOutcomeStatus.ACCEPTED
    assert result.projection.terminal_status is ReworkTerminalStatus.ACCEPTED
    assert result.remaining_blocker_refs == ()
    assert result.accepted_blocker_refs == result.recheck_result.accepted_blocker_refs


def test_multi_round_loop_rechecks_after_initial_failure(tmp_path: Path) -> None:
    from boardroom_os.proving.v2_100_resettable_fixture import (
        build_two_round_provider,
        build_v2_100_scenario_input,
    )
    from boardroom_os.proving.v2_100_rework_loop import (
        V2_100ScenarioTerminalStatus,
        run_v2_100_rework_loop_scenario,
    )

    scenario_input = build_v2_100_scenario_input(
        package_root=tmp_path / "package",
        require_real_provider=False,
        max_rounds=2,
    )

    result = run_v2_100_rework_loop_scenario(
        scenario_input,
        round_provider=build_two_round_provider(tmp_path),
    )

    all_events = tuple(event for round_result in result.rounds for event in round_result.events)
    manifest_refs = {entry.payload_ref for entry in result.payload_manifest_entries}
    event_payload_refs = {payload_ref for event in all_events for payload_ref in event.payload_refs}

    assert result.terminal_status is V2_100ScenarioTerminalStatus.ACCEPTED
    assert len(result.rounds) == 2
    assert result.rounds[0].remaining_blocker_refs
    assert result.rounds[0].projection.terminal_status is ReworkTerminalStatus.OPEN
    assert {
        event.event_type for event in result.rounds[0].events
    }.isdisjoint(
        {
            EventType.REWORK_ACCEPTED,
            EventType.REWORK_ESCALATED,
            EventType.REWORK_EXHAUSTED,
        }
    )
    assert event_payload_refs.issubset(manifest_refs)
    assert len(result.final_projection.committed_event_refs) == len(all_events)
    assert result.rounds[-1].remaining_blocker_refs == ()
    assert EventType.REWORK_ACCEPTED in {event.event_type for event in result.rounds[-1].events}


def test_v2_100_loop_can_start_from_verified_rework_request(tmp_path: Path) -> None:
    from boardroom_os.proving.v2_100_resettable_fixture import (
        build_two_round_provider,
        build_v2_100_scenario_input,
    )
    from boardroom_os.proving.v2_100_rework_loop import (
        project_snapshot_request,
        run_v2_100_rework_loop_for_request,
    )

    scenario_input = build_v2_100_scenario_input(
        package_root=tmp_path / "package",
        export_root=tmp_path / "audit-artifacts",
        require_real_provider=False,
        max_rounds=2,
    )
    request = project_snapshot_request(scenario_input)

    result = run_v2_100_rework_loop_for_request(
        scenario_input,
        request=request,
        round_provider=build_two_round_provider(tmp_path),
    )

    assert result.request == request
    assert result.rounds[-1].remaining_blocker_refs == ()
    assert result.final_projection.graph_version > scenario_input.initial_graph_version


def test_accepted_loop_includes_passed_closeout_gate_result(tmp_path: Path) -> None:
    from boardroom_os.proving.v2_100_resettable_fixture import (
        build_two_round_provider,
        build_v2_100_scenario_input,
    )
    from boardroom_os.proving.v2_100_rework_loop import (
        run_v2_100_rework_loop_scenario,
    )

    scenario_input = build_v2_100_scenario_input(
        package_root=tmp_path / "package",
        require_real_provider=False,
        max_rounds=2,
    )

    result = run_v2_100_rework_loop_scenario(
        scenario_input,
        round_provider=build_two_round_provider(tmp_path),
    )
    closeout_gate_result = result.rounds[-1].recheck_result.closeout_gate_result

    assert closeout_gate_result is not None
    assert closeout_gate_result.verdict is CloseoutGateVerdict.PASSED
    assert result.rounds[-1].outcome.closeout_gate_ref == closeout_gate_result.closeout_gate_result_id.value


def test_exhausted_loop_requires_auditable_termination(tmp_path: Path) -> None:
    from boardroom_os.proving.v2_100_resettable_fixture import (
        build_exhausted_round_provider,
        build_v2_100_scenario_input,
    )
    from boardroom_os.proving.v2_100_rework_loop import (
        V2_100ScenarioTerminalStatus,
        run_v2_100_rework_loop_scenario,
    )

    scenario_input = build_v2_100_scenario_input(
        package_root=tmp_path / "package",
        require_real_provider=False,
        max_rounds=1,
    )

    result = run_v2_100_rework_loop_scenario(
        scenario_input,
        round_provider=build_exhausted_round_provider(tmp_path),
    )

    assert result.terminal_status is V2_100ScenarioTerminalStatus.EXHAUSTED
    assert result.termination_decision is not None
    assert result.termination_decision.reason is ReworkTerminationReason.EXHAUSTED_BUDGET


def test_audit_export_contains_events_provider_attempts_and_evidence_refs(tmp_path: Path) -> None:
    from boardroom_os.proving.v2_100_resettable_fixture import (
        build_two_round_provider,
        build_v2_100_scenario_input,
    )
    from boardroom_os.proving.v2_100_rework_loop import (
        export_v2_100_rework_audit,
        run_v2_100_rework_loop_scenario,
    )

    scenario_input = build_v2_100_scenario_input(
        package_root=tmp_path / "package",
        export_root=tmp_path / "audit-artifacts",
        require_real_provider=False,
        max_rounds=2,
    )
    result = run_v2_100_rework_loop_scenario(
        scenario_input,
        round_provider=build_two_round_provider(tmp_path),
    )

    export = export_v2_100_rework_audit(result, tmp_path / "audit")

    assert export.summary_path.exists()
    assert export.event_log_path.exists()
    assert export.provider_attempts_path.exists()
    assert export.evidence_summary_path.exists()
    assert export.process_timeline_path.exists()
    assert export.checked_refs

    payload_manifest_text = export.payload_manifest_path.read_text(encoding="utf-8")
    provider_attempt_text = export.provider_attempts_path.read_text(encoding="utf-8")

    assert "canonical_json" in payload_manifest_text
    assert "sha256:" in payload_manifest_text
    assert "raw_output_ref" in provider_attempt_text
    assert "parsed_output_ref" in provider_attempt_text
    assert "raw_output_sha256" in provider_attempt_text
    assert "parsed_output_sha256" in provider_attempt_text


def test_audit_export_source_inventory_hashes_match_package_files(tmp_path: Path) -> None:
    from boardroom_os.proving.v2_100_resettable_fixture import (
        build_two_round_provider,
        build_v2_100_scenario_input,
    )
    from boardroom_os.proving.v2_100_rework_loop import (
        export_v2_100_rework_audit,
        run_v2_100_rework_loop_scenario,
    )

    package_root = tmp_path / "package-two-round"
    scenario_input = build_v2_100_scenario_input(
        package_root=tmp_path / "package",
        export_root=tmp_path / "audit-artifacts",
        require_real_provider=False,
        max_rounds=2,
    )
    result = run_v2_100_rework_loop_scenario(
        scenario_input,
        round_provider=build_two_round_provider(tmp_path),
    )

    export = export_v2_100_rework_audit(result, tmp_path / "audit")
    evidence_summary = json.loads(export.evidence_summary_path.read_text(encoding="utf-8"))
    final_round = evidence_summary[-1]

    for entry in final_round["source_inventory_entries"]:
        source_path = package_root / entry["path"]
        expected_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
        assert entry["sha256"] == expected_sha


def test_resettable_package_writes_non_empty_contract_and_run_manifest(tmp_path: Path) -> None:
    from boardroom_os.proving.v2_100_resettable_fixture import build_v2_100_resettable_fixture

    package_root = tmp_path / "package"

    build_v2_100_resettable_fixture(package_root=package_root)

    package_contract = json.loads((package_root / "package-contract.json").read_text(encoding="utf-8"))
    run_manifest = json.loads((package_root / "run-manifest.json").read_text(encoding="utf-8"))

    assert package_contract["package_contract_id"]["value"] == "package.v2-100e"
    assert package_contract["run_commands"]
    assert package_contract["test_commands"]
    assert run_manifest["run_manifest_id"]["value"].startswith("run-manifest.")
    assert run_manifest["commands"]
    assert run_manifest["service_contracts"]
