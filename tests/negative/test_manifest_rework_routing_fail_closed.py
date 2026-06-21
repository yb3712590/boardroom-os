from __future__ import annotations

from datetime import UTC, datetime

from boardroom_os.evidence.blackbox_plan import BlackboxPlanActionKind
from boardroom_os.execution.blackbox_plan_runner import BlackboxActionExecutionFact
from boardroom_os.rework.blocker_projection import (
    ManifestReworkRoutingStatus,
    route_manifest_blackbox_facts,
)
from tests.rework.test_manifest_rework_routing import _context, _failed_http_fact

NOW = datetime(2026, 6, 22, 9, 30, tzinfo=UTC)


def test_advisory_label_cannot_mark_failed_fact_passed() -> None:
    result = route_manifest_blackbox_facts(
        facts=(_failed_http_fact(status_text="probably acceptable"),),
        context=_context(),
        advisory_context={"labels": ("probably acceptable",), "agent_prose": "Looks fine to me."},
    )

    assert result.status is ManifestReworkRoutingStatus.REWORK_REQUIRED
    assert result.rework_request is not None
    assert result.blocked_reason_code is None
    assert result.rework_request.issues[0].advisory_context["labels"] == ("probably acceptable",)


def test_missing_plan_ref_routes_blocked_or_escalated() -> None:
    malformed_fact = BlackboxActionExecutionFact.model_construct(
        fact_id="blackbox-action-fact.missing-plan",
        plan_ref=None,
        action_id="action.http.books",
        action_kind=BlackboxPlanActionKind.HTTP,
        http_status=404,
        started_at=NOW,
        finished_at=NOW,
        acceptance_refs=(_context().active_acceptance_refs[0],),
        package_contract_ref="contract.package.tiny-fullstack",
    )

    result = route_manifest_blackbox_facts(facts=(malformed_fact,), context=_context())

    assert result.status is ManifestReworkRoutingStatus.BLOCKED_OR_ESCALATED
    assert result.rework_request is None
    assert result.blocked_reason_code == "missing_plan_ref"


def test_missing_facts_route_blocked_or_escalated() -> None:
    result = route_manifest_blackbox_facts(facts=(), context=_context())

    assert result.status is ManifestReworkRoutingStatus.BLOCKED_OR_ESCALATED
    assert result.rework_request is None
    assert result.blocked_reason_code == "missing_blackbox_facts"


def test_missing_active_refs_route_blocked_or_escalated() -> None:
    context = _context().model_copy(update={"active_acceptance_refs": ()})

    result = route_manifest_blackbox_facts(facts=(_failed_http_fact(),), context=context)

    assert result.status is ManifestReworkRoutingStatus.BLOCKED_OR_ESCALATED
    assert result.rework_request is None
    assert result.blocked_reason_code == "missing_active_acceptance_refs"


def test_missing_graph_version_routes_blocked_or_escalated() -> None:
    context = _context().model_copy(update={"active_graph_version": 0})

    result = route_manifest_blackbox_facts(facts=(_failed_http_fact(),), context=context)

    assert result.status is ManifestReworkRoutingStatus.BLOCKED_OR_ESCALATED
    assert result.rework_request is None
    assert result.blocked_reason_code == "missing_graph_linkage"


def test_raw_exception_alone_does_not_create_rework_request() -> None:
    result = route_manifest_blackbox_facts(
        facts=(),
        context=_context(),
        raw_exception=ValueError("unsupported RunManifest behavior assertion type"),
    )

    assert result.status is ManifestReworkRoutingStatus.BLOCKED_OR_ESCALATED
    assert result.rework_request is None
    assert result.blocked_reason_code == "raw_exception_without_facts"


def test_missing_package_contract_ref_routes_blocked_or_escalated() -> None:
    context = _context().model_copy(update={"package_contract_ref": None})

    result = route_manifest_blackbox_facts(facts=(_failed_http_fact(),), context=context)

    assert result.status is ManifestReworkRoutingStatus.BLOCKED_OR_ESCALATED
    assert result.rework_request is None
    assert result.blocked_reason_code == "missing_package_contract_ref"
