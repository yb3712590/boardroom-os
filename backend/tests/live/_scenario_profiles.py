from __future__ import annotations

import json
from typing import Any, Callable

from tests.live._config import DEFAULT_REQUIRED_CAPABILITIES, LiveAssertionConfig


MINIMALIST_BOOK_TRACKER_GOAL = (
    "实现一个完全匿名的、纯粹用于记录“实体书本当前是否在馆”的单机版终端系统。"
    "系统的唯一价值是回答两个问题：“馆里有什么书？”以及“这本书现在能拿走吗？”"
)
MINIMALIST_BOOK_TRACKER_CONSTRAINTS: tuple[str, ...] = (
    "绝对禁止权限系统，系统固定为单租户无头模式，不区分管理员和普通读者，没有登录注册模块。",
    "绝对禁止时间轴计算，借阅动作仅表现为状态切换，不记录时间戳。",
    "绝对禁止复杂分类，不设计分类表、标签表或馆藏位置表。",
    "绝对禁止用户借阅历史，不记录谁借了书，只记录书被借走。",
    "系统仅允许存在 books 一张表，字段固定为 id、title、author、status。",
    "status 只允许 IN_LIBRARY 和 CHECKED_OUT。",
    "核心状态机只允许 Add、Check Out、Return、Remove 四个动作。",
    "前端采用深色、单色文本、高信息密度 terminal/console 风格，不要动画、阴影或圆角。",
    "交互只保留一个新增输入框和一个纯文本列表。",
)
_REQUIRED_LIBRARY_CAPABILITY_TERMS = {
    "books": ("books", "books table", "book tracker", "books terminal"),
    "title": ("title", "书名"),
    "author": ("author", "作者"),
    "IN_LIBRARY": ("in_library",),
    "CHECKED_OUT": ("checked_out",),
    "add": (" add ", "add book", "新增图书", "入库"),
    "check out": ("check out", "checked out", "借出"),
    "return": (" return ", "归还"),
    "remove": ("remove", "下架", "删除图书"),
    "terminal": ("terminal", "终端", "hacker-console"),
    "console": ("console", "控制台", "单色文本", "monochrome"),
}


def _normalize_followup_key(value: Any) -> str:
    return str(value or "").strip().split(" ", 1)[0].upper()


def _followup_node_id(ticket_key: str) -> str:
    normalized = "".join(
        character.lower() if character.isalnum() else "_"
        for character in str(ticket_key or "").strip()
    ).strip("_")
    return f"node_backlog_followup_{normalized}" if normalized else "node_backlog_followup"


def _json_corpus(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).lower()
    except TypeError:
        return str(value).lower()


def _library_scope_corpus(common: dict[str, Any]) -> str:
    return "\n".join(
        [
            _json_corpus(common.get("created_specs") or {}),
            _json_corpus(common.get("terminals") or {}),
        ]
    )


def _missing_required_capabilities(common: dict[str, Any], required_capabilities: tuple[str, ...]) -> list[str]:
    corpus = f" {_library_scope_corpus(common)} "
    missing: list[str] = []
    for capability in required_capabilities:
        terms = _REQUIRED_LIBRARY_CAPABILITY_TERMS.get(capability, (capability,))
        if not any(term.lower() in corpus for term in terms):
            missing.append(capability)
    return missing


def _expected_model_for_role(config: LiveAssertionConfig, role_profile_ref: str) -> str:
    return config.expected_models_by_role_profile_ref.get(role_profile_ref) or config.expected_model


def _expected_reasoning_for_role(config: LiveAssertionConfig, role_profile_ref: str) -> str:
    return (
        config.expected_reasoning_by_role_profile_ref.get(role_profile_ref)
        or (
            config.architect_reasoning_effort
            if role_profile_ref == "architect_primary"
            else config.default_reasoning_effort
        )
    )


def _find_backlog_handoff(common: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    created_specs = dict(common.get("created_specs") or {})
    terminals = dict(common.get("terminals") or {})
    for ticket_id, created_spec in created_specs.items():
        if str(created_spec.get("output_schema_ref") or "").strip() != "backlog_recommendation":
            continue
        payload = (terminals.get(ticket_id) or {}).get("payload") or {}
        handoff = payload.get("implementation_handoff") if isinstance(payload, dict) else None
        if isinstance(handoff, dict):
            return str(ticket_id), handoff
    raise AssertionError("No backlog implementation_handoff evidence was recorded.")


def _required_followup_keys(handoff: dict[str, Any]) -> list[str]:
    sequence = [
        _normalize_followup_key(item)
        for item in list(handoff.get("recommended_sequence") or [])
        if _normalize_followup_key(item)
    ]
    if sequence:
        return sequence
    return [
        _normalize_followup_key(item.get("ticket_id"))
        for item in list(handoff.get("tickets") or [])
        if isinstance(item, dict) and _normalize_followup_key(item.get("ticket_id"))
    ]


def _ticket_status_by_id(common: dict[str, Any]) -> dict[str, str]:
    return {
        str(ticket.get("ticket_id") or ""): str(ticket.get("status") or "")
        for ticket in list(common.get("tickets") or [])
        if str(ticket.get("ticket_id") or "")
    }


def _materialized_followup_ticket_ids(
    common: dict[str, Any],
    *,
    backlog_ticket_id: str,
    required_followup_keys: list[str],
) -> dict[str, str]:
    created_specs = dict(common.get("created_specs") or {})
    ticket_statuses = _ticket_status_by_id(common)
    materialized: dict[str, str] = {}
    for ticket_key in required_followup_keys:
        expected_node_id = _followup_node_id(ticket_key)
        for ticket_id, created_spec in created_specs.items():
            if str(created_spec.get("output_schema_ref") or "").strip() != "source_code_delivery":
                continue
            if str(ticket_statuses.get(str(ticket_id)) or "").strip() != "COMPLETED":
                continue
            node_id = str(created_spec.get("node_id") or "").strip()
            parent_ticket_id = str(created_spec.get("parent_ticket_id") or "").strip()
            summary = _json_corpus(created_spec)
            if (
                node_id == expected_node_id
                or parent_ticket_id == backlog_ticket_id
                and ticket_key.lower() in summary
                or ticket_key.lower() in summary
            ):
                materialized[ticket_key] = str(ticket_id)
                break
    return materialized


def _approved_checker_handoff_ticket_ids(
    common: dict[str, Any],
    *,
    required_source_ticket_ids: set[str],
) -> list[str]:
    created_specs = dict(common.get("created_specs") or {})
    terminals = dict(common.get("terminals") or {})
    ticket_statuses = _ticket_status_by_id(common)
    approved_ticket_ids: list[str] = []
    for ticket_id, created_spec in created_specs.items():
        if str(created_spec.get("output_schema_ref") or "").strip() != "maker_checker_verdict":
            continue
        if str(ticket_statuses.get(str(ticket_id)) or "").strip() not in {"", "COMPLETED"}:
            continue
        maker_checker_context = created_spec.get("maker_checker_context") or {}
        maker_ticket_id = str(maker_checker_context.get("maker_ticket_id") or "").strip()
        if maker_ticket_id not in required_source_ticket_ids:
            continue
        terminal_event = terminals.get(ticket_id) or {}
        if str(terminal_event.get("event_type") or "TICKET_COMPLETED") != "TICKET_COMPLETED":
            continue
        payload = terminal_event.get("payload") or {}
        review_status = str(
            payload.get("maker_checker_summary", {}).get("review_status")
            or payload.get("review_status")
            or ""
        ).strip()
        if review_status in {"APPROVED", "APPROVED_WITH_NOTES"}:
            approved_ticket_ids.append(str(ticket_id))
    return approved_ticket_ids


def _assert_minimalist_book_tracker(
    paths,
    repository,
    workflow_id: str,
    common: dict[str, Any],
    *,
    config: LiveAssertionConfig,
) -> dict[str, Any]:
    employees = list(common.get("employees") or [])
    if not any(str(item.get("role_type") or "") == "governance_architect" for item in employees):
        raise AssertionError("No approved governance_architect employee was hired.")

    audits = list(common.get("audits") or [])
    architect_audits = [item for item in audits if item.get("role_profile_ref") == "architect_primary"]
    if not architect_audits:
        raise AssertionError("No architect_primary runtime ticket completed with recorded assumptions.")
    invalid_architect_audits = [
        item
        for item in architect_audits
        if item.get("assumptions", {}).get("actual_provider_id") != config.expected_provider_id
        or item.get("assumptions", {}).get("actual_model") != _expected_model_for_role(
            config,
            str(item.get("role_profile_ref") or ""),
        )
        or item.get("assumptions", {}).get("effective_reasoning_effort") != _expected_reasoning_for_role(
            config,
            str(item.get("role_profile_ref") or ""),
        )
    ]
    if invalid_architect_audits:
        raise AssertionError(f"Architect runtime audit deviated from expected provider/model profile: {invalid_architect_audits}")

    approved_architect_ticket_ids = list(common.get("architect_ticket_ids") or [])
    if not approved_architect_ticket_ids:
        raise AssertionError("No approved architect_primary governance document evidence was recorded.")

    non_architect_audits = [item for item in audits if item.get("role_profile_ref") != "architect_primary"]
    if not non_architect_audits:
        raise AssertionError("No non-architect runtime tickets completed.")
    invalid_non_architect = [
        item
        for item in non_architect_audits
        if item.get("assumptions", {}).get("actual_provider_id") != config.expected_provider_id
        or item.get("assumptions", {}).get("actual_model") != _expected_model_for_role(
            config,
            str(item.get("role_profile_ref") or ""),
        )
        or item.get("assumptions", {}).get("effective_reasoning_effort") != _expected_reasoning_for_role(
            config,
            str(item.get("role_profile_ref") or ""),
        )
    ]
    if invalid_non_architect:
        raise AssertionError(f"Non-architect runtime audits deviated from expected provider/model profile: {invalid_non_architect}")

    missing_capabilities = _missing_required_capabilities(common, config.required_capabilities)
    if missing_capabilities:
        raise AssertionError(f"Library delivery missed required capabilities: {missing_capabilities}")

    backlog_ticket_id, implementation_handoff = _find_backlog_handoff(common)
    required_followup_keys = _required_followup_keys(implementation_handoff)
    if not required_followup_keys:
        raise AssertionError("Library delivery backlog implementation_handoff has no required followups.")
    materialized_followup_ticket_ids = _materialized_followup_ticket_ids(
        common,
        backlog_ticket_id=backlog_ticket_id,
        required_followup_keys=required_followup_keys,
    )
    missing_followup_keys = [
        ticket_key
        for ticket_key in required_followup_keys
        if ticket_key not in materialized_followup_ticket_ids
    ]
    if missing_followup_keys:
        raise AssertionError(
            f"Library delivery missing followup materialization: {missing_followup_keys}"
        )
    checker_handoff_ticket_ids = _approved_checker_handoff_ticket_ids(
        common,
        required_source_ticket_ids=set(materialized_followup_ticket_ids.values()),
    )
    if not checker_handoff_ticket_ids:
        raise AssertionError("Library delivery is missing approved checker handoff evidence.")

    return {
        "approved_architect_governance_ticket_ids": approved_architect_ticket_ids,
        "scope_capabilities": list(config.required_capabilities),
        "required_followup_ticket_keys": required_followup_keys,
        "materialized_followup_ticket_ids": materialized_followup_ticket_ids,
        "checker_handoff_ticket_ids": checker_handoff_ticket_ids,
        "expected_provider_id": config.expected_provider_id,
        "expected_model": config.expected_model,
    }


def build_assert_outcome(config: LiveAssertionConfig) -> Callable[[Any, Any, str, dict[str, Any]], dict[str, Any]]:
    if config.profile == "minimalist_book_tracker":
        return lambda paths, repository, workflow_id, common: _assert_minimalist_book_tracker(
            paths,
            repository,
            workflow_id,
            common,
            config=config,
        )
    raise ValueError(f"Unknown live assertion profile: {config.profile}")


__all__ = [
    "DEFAULT_REQUIRED_CAPABILITIES",
    "MINIMALIST_BOOK_TRACKER_CONSTRAINTS",
    "MINIMALIST_BOOK_TRACKER_GOAL",
    "build_assert_outcome",
]
