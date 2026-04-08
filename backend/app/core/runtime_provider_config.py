from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import Field

from app.contracts.commands import (
    CommandAckEnvelope,
    CommandAckStatus,
    RuntimeProviderCapabilityTag,
    RuntimeProviderCostTier,
    RuntimeProviderMode,
    RuntimeProviderParticipationPolicy,
    RuntimeSelectionPreference,
    RuntimeProviderUpsertCommand,
)
from app.contracts.common import StrictModel
from app.config import get_settings
from app.core.execution_targets import (
    EXECUTION_TARGET_ARCHITECT_GOVERNANCE_DOCUMENT,
    EXECUTION_TARGET_BACKEND_BUILD,
    EXECUTION_TARGET_CHECKER_DELIVERY_CHECK,
    EXECUTION_TARGET_CTO_GOVERNANCE_DOCUMENT,
    EXECUTION_TARGET_DATABASE_BUILD,
    EXECUTION_TARGET_FRONTEND_BUILD,
    EXECUTION_TARGET_FRONTEND_CLOSEOUT,
    EXECUTION_TARGET_FRONTEND_GOVERNANCE_DOCUMENT,
    EXECUTION_TARGET_FRONTEND_REVIEW,
    EXECUTION_TARGET_PLATFORM_BUILD,
    EXECUTION_TARGET_SCOPE_CONSENSUS,
    EXECUTION_TARGET_SCOPE_GOVERNANCE_DOCUMENT,
    legacy_target_refs_for_execution_target,
)
from app.core.governance_templates import list_runtime_provider_future_binding_slots
from app.core.ids import new_prefixed_id
from app.core.time import now_local
from app.db.repository import ControlPlaneRepository

OPENAI_COMPAT_PROVIDER_ID = "prov_openai_compat"
CLAUDE_CODE_PROVIDER_ID = "prov_claude_code"

ROLE_BINDING_CEO_SHADOW = "ceo_shadow"
ROLE_BINDING_UI_DESIGNER = "role_profile:ui_designer_primary"
ROLE_BINDING_FRONTEND_ENGINEER = "role_profile:frontend_engineer_primary"
ROLE_BINDING_CHECKER = "role_profile:checker_primary"
ROLE_BINDING_BACKEND_ENGINEER = "role_profile:backend_engineer_primary"
ROLE_BINDING_DATABASE_ENGINEER = "role_profile:database_engineer_primary"
ROLE_BINDING_PLATFORM_SRE = "role_profile:platform_sre_primary"
ROLE_BINDING_ARCHITECT = "role_profile:architect_primary"
ROLE_BINDING_CTO = "role_profile:cto_primary"

CURRENT_RUNTIME_ROLE_TARGET_REFS = (
    ROLE_BINDING_CEO_SHADOW,
    ROLE_BINDING_UI_DESIGNER,
    ROLE_BINDING_FRONTEND_ENGINEER,
    ROLE_BINDING_CHECKER,
    ROLE_BINDING_BACKEND_ENGINEER,
    ROLE_BINDING_DATABASE_ENGINEER,
    ROLE_BINDING_PLATFORM_SRE,
    ROLE_BINDING_ARCHITECT,
    ROLE_BINDING_CTO,
)

RUNTIME_TARGET_LABELS = {
    ROLE_BINDING_CEO_SHADOW: "CEO Shadow",
    ROLE_BINDING_UI_DESIGNER: "Scope Consensus",
    ROLE_BINDING_FRONTEND_ENGINEER: "Frontend Engineer",
    ROLE_BINDING_CHECKER: "Checker",
    ROLE_BINDING_BACKEND_ENGINEER: "Backend Engineer / 服务交付",
    ROLE_BINDING_DATABASE_ENGINEER: "Database Engineer / 数据可靠性",
    ROLE_BINDING_PLATFORM_SRE: "Platform / SRE",
    ROLE_BINDING_ARCHITECT: "架构师 / 设计评审",
    ROLE_BINDING_CTO: "CTO / 架构治理",
    EXECUTION_TARGET_SCOPE_CONSENSUS: "Scope Consensus",
    EXECUTION_TARGET_SCOPE_GOVERNANCE_DOCUMENT: "Scope Governance Document",
    EXECUTION_TARGET_FRONTEND_BUILD: "Frontend Build",
    EXECUTION_TARGET_BACKEND_BUILD: "Backend Build",
    EXECUTION_TARGET_DATABASE_BUILD: "Database Build",
    EXECUTION_TARGET_PLATFORM_BUILD: "Platform Build",
    EXECUTION_TARGET_FRONTEND_GOVERNANCE_DOCUMENT: "Frontend Governance Document",
    EXECUTION_TARGET_ARCHITECT_GOVERNANCE_DOCUMENT: "Architect Governance Document",
    EXECUTION_TARGET_CTO_GOVERNANCE_DOCUMENT: "CTO Governance Document",
    EXECUTION_TARGET_CHECKER_DELIVERY_CHECK: "Checker Delivery Check",
    EXECUTION_TARGET_FRONTEND_REVIEW: "Frontend Review",
    EXECUTION_TARGET_FRONTEND_CLOSEOUT: "Frontend Closeout",
}

FUTURE_ROLE_BINDING_SLOTS = tuple(list_runtime_provider_future_binding_slots())


class RuntimeProviderAdapterKind(StrEnum):
    OPENAI_COMPAT = "openai_compat"
    CLAUDE_CODE_CLI = "claude_code_cli"


class RuntimeProviderConfigEntry(StrictModel):
    provider_id: str = Field(min_length=1)
    adapter_kind: RuntimeProviderAdapterKind
    label: str = Field(min_length=1)
    enabled: bool = False
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    timeout_sec: float = Field(default=30.0, gt=0)
    reasoning_effort: str | None = None
    command_path: str | None = None
    capability_tags: list[RuntimeProviderCapabilityTag] = Field(default_factory=list)
    cost_tier: RuntimeProviderCostTier = RuntimeProviderCostTier.STANDARD
    participation_policy: RuntimeProviderParticipationPolicy = RuntimeProviderParticipationPolicy.ALWAYS_ALLOWED
    fallback_provider_ids: list[str] = Field(default_factory=list)


class RuntimeProviderRoleBinding(StrictModel):
    target_ref: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    model: str | None = None


class RuntimeProviderStoredConfig(StrictModel):
    default_provider_id: str | None = None
    providers: list[RuntimeProviderConfigEntry] = Field(default_factory=list)
    role_bindings: list[RuntimeProviderRoleBinding] = Field(default_factory=list)


@dataclass(frozen=True)
class RuntimeProviderSelection:
    provider: RuntimeProviderConfigEntry
    preferred_provider_id: str
    preferred_model: str | None
    actual_model: str | None
    binding_target_ref: str | None = None
    selection_reason: str | None = None
    policy_reason: str | None = None


DEFAULT_PROVIDER_CAPABILITY_TAGS = (
    RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
    RuntimeProviderCapabilityTag.PLANNING,
    RuntimeProviderCapabilityTag.IMPLEMENTATION,
    RuntimeProviderCapabilityTag.REVIEW,
)

LOW_FREQUENCY_HIGH_LEVERAGE_TARGET_REFS = frozenset(
    {
        ROLE_BINDING_CEO_SHADOW,
        ROLE_BINDING_UI_DESIGNER,
        ROLE_BINDING_ARCHITECT,
        ROLE_BINDING_CTO,
        EXECUTION_TARGET_SCOPE_CONSENSUS,
        EXECUTION_TARGET_SCOPE_GOVERNANCE_DOCUMENT,
        EXECUTION_TARGET_FRONTEND_GOVERNANCE_DOCUMENT,
        EXECUTION_TARGET_ARCHITECT_GOVERNANCE_DOCUMENT,
        EXECUTION_TARGET_CTO_GOVERNANCE_DOCUMENT,
    }
)

RUNTIME_TARGET_CAPABILITY_FLOORS: dict[str, tuple[RuntimeProviderCapabilityTag, ...]] = {
    ROLE_BINDING_CEO_SHADOW: (
        RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
        RuntimeProviderCapabilityTag.PLANNING,
    ),
    ROLE_BINDING_UI_DESIGNER: (
        RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
        RuntimeProviderCapabilityTag.PLANNING,
    ),
    EXECUTION_TARGET_SCOPE_CONSENSUS: (
        RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
        RuntimeProviderCapabilityTag.PLANNING,
    ),
    ROLE_BINDING_FRONTEND_ENGINEER: (
        RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
        RuntimeProviderCapabilityTag.IMPLEMENTATION,
    ),
    ROLE_BINDING_BACKEND_ENGINEER: (
        RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
        RuntimeProviderCapabilityTag.IMPLEMENTATION,
    ),
    ROLE_BINDING_DATABASE_ENGINEER: (
        RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
        RuntimeProviderCapabilityTag.IMPLEMENTATION,
    ),
    ROLE_BINDING_PLATFORM_SRE: (
        RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
        RuntimeProviderCapabilityTag.IMPLEMENTATION,
    ),
    ROLE_BINDING_ARCHITECT: (
        RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
        RuntimeProviderCapabilityTag.PLANNING,
    ),
    ROLE_BINDING_CTO: (
        RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
        RuntimeProviderCapabilityTag.PLANNING,
    ),
    EXECUTION_TARGET_FRONTEND_BUILD: (
        RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
        RuntimeProviderCapabilityTag.IMPLEMENTATION,
    ),
    EXECUTION_TARGET_BACKEND_BUILD: (
        RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
        RuntimeProviderCapabilityTag.IMPLEMENTATION,
    ),
    EXECUTION_TARGET_DATABASE_BUILD: (
        RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
        RuntimeProviderCapabilityTag.IMPLEMENTATION,
    ),
    EXECUTION_TARGET_PLATFORM_BUILD: (
        RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
        RuntimeProviderCapabilityTag.IMPLEMENTATION,
    ),
    EXECUTION_TARGET_SCOPE_GOVERNANCE_DOCUMENT: (
        RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
        RuntimeProviderCapabilityTag.PLANNING,
    ),
    EXECUTION_TARGET_FRONTEND_GOVERNANCE_DOCUMENT: (
        RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
        RuntimeProviderCapabilityTag.PLANNING,
    ),
    EXECUTION_TARGET_ARCHITECT_GOVERNANCE_DOCUMENT: (
        RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
        RuntimeProviderCapabilityTag.PLANNING,
    ),
    EXECUTION_TARGET_CTO_GOVERNANCE_DOCUMENT: (
        RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
        RuntimeProviderCapabilityTag.PLANNING,
    ),
    EXECUTION_TARGET_FRONTEND_REVIEW: (
        RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
        RuntimeProviderCapabilityTag.IMPLEMENTATION,
    ),
    EXECUTION_TARGET_FRONTEND_CLOSEOUT: (
        RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
        RuntimeProviderCapabilityTag.IMPLEMENTATION,
    ),
    ROLE_BINDING_CHECKER: (
        RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
        RuntimeProviderCapabilityTag.REVIEW,
    ),
    EXECUTION_TARGET_CHECKER_DELIVERY_CHECK: (
        RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
        RuntimeProviderCapabilityTag.REVIEW,
    ),
}


class RuntimeProviderConfigStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load_saved_config(self) -> RuntimeProviderStoredConfig | None:
        if not self.path.exists():
            return None
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return RuntimeProviderStoredConfig.model_validate(_normalize_provider_store_payload(payload))

    def save_config(self, payload: RuntimeProviderStoredConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(payload.model_dump(mode="json"), ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )


def _default_provider_entries(
    *,
    openai_enabled: bool = False,
    openai_base_url: str | None = None,
    openai_api_key: str | None = None,
    openai_model: str | None = None,
    openai_timeout_sec: float = 30.0,
    openai_reasoning_effort: str | None = None,
) -> list[RuntimeProviderConfigEntry]:
    return [
        RuntimeProviderConfigEntry(
            provider_id=OPENAI_COMPAT_PROVIDER_ID,
            adapter_kind=RuntimeProviderAdapterKind.OPENAI_COMPAT,
            label="OpenAI Compat",
            enabled=openai_enabled,
            base_url=openai_base_url,
            api_key=openai_api_key,
            model=openai_model,
            timeout_sec=openai_timeout_sec,
            reasoning_effort=openai_reasoning_effort,
            capability_tags=list(DEFAULT_PROVIDER_CAPABILITY_TAGS),
            cost_tier=RuntimeProviderCostTier.STANDARD,
            participation_policy=RuntimeProviderParticipationPolicy.ALWAYS_ALLOWED,
            fallback_provider_ids=[],
        ),
        RuntimeProviderConfigEntry(
            provider_id=CLAUDE_CODE_PROVIDER_ID,
            adapter_kind=RuntimeProviderAdapterKind.CLAUDE_CODE_CLI,
            label="Claude Code CLI",
            enabled=False,
            command_path=None,
            model=None,
            timeout_sec=30.0,
            capability_tags=list(DEFAULT_PROVIDER_CAPABILITY_TAGS),
            cost_tier=RuntimeProviderCostTier.PREMIUM,
            participation_policy=RuntimeProviderParticipationPolicy.LOW_FREQUENCY_ONLY,
            fallback_provider_ids=[],
        ),
    ]


def _build_env_backed_provider_config() -> RuntimeProviderStoredConfig:
    settings = get_settings()
    has_openai_values = any(
        (
            settings.provider_openai_compat_base_url,
            settings.provider_openai_compat_api_key,
            settings.provider_openai_compat_model,
        )
    )
    return RuntimeProviderStoredConfig(
        default_provider_id=OPENAI_COMPAT_PROVIDER_ID if has_openai_values else None,
        providers=_default_provider_entries(
            openai_enabled=has_openai_values,
            openai_base_url=settings.provider_openai_compat_base_url,
            openai_api_key=settings.provider_openai_compat_api_key,
            openai_model=settings.provider_openai_compat_model,
            openai_timeout_sec=settings.provider_openai_compat_timeout_sec,
            openai_reasoning_effort=settings.provider_openai_compat_reasoning_effort,
        ),
        role_bindings=[],
    )


def _migrate_legacy_provider_payload(payload: dict) -> dict:
    mode = str(payload.get("mode") or RuntimeProviderMode.DETERMINISTIC)
    openai_enabled = mode == RuntimeProviderMode.OPENAI_COMPAT
    return {
        "default_provider_id": OPENAI_COMPAT_PROVIDER_ID if openai_enabled else None,
        "providers": [
            {
                "provider_id": OPENAI_COMPAT_PROVIDER_ID,
                "adapter_kind": RuntimeProviderAdapterKind.OPENAI_COMPAT,
                "label": "OpenAI Compat",
                "enabled": openai_enabled,
                "base_url": payload.get("base_url"),
                "api_key": payload.get("api_key"),
                "model": payload.get("model"),
                "timeout_sec": payload.get("timeout_sec") or 30.0,
                "reasoning_effort": payload.get("reasoning_effort"),
                "capability_tags": [tag.value for tag in DEFAULT_PROVIDER_CAPABILITY_TAGS],
                "cost_tier": RuntimeProviderCostTier.STANDARD,
                "participation_policy": RuntimeProviderParticipationPolicy.ALWAYS_ALLOWED,
                "fallback_provider_ids": [],
            },
            {
                "provider_id": CLAUDE_CODE_PROVIDER_ID,
                "adapter_kind": RuntimeProviderAdapterKind.CLAUDE_CODE_CLI,
                "label": "Claude Code CLI",
                "enabled": False,
                "command_path": None,
                "model": None,
                "timeout_sec": 30.0,
                "capability_tags": [tag.value for tag in DEFAULT_PROVIDER_CAPABILITY_TAGS],
                "cost_tier": RuntimeProviderCostTier.PREMIUM,
                "participation_policy": RuntimeProviderParticipationPolicy.LOW_FREQUENCY_ONLY,
                "fallback_provider_ids": [],
            },
        ],
        "role_bindings": [],
    }


def _normalize_provider_store_payload(payload: dict) -> dict:
    if "providers" not in payload and "role_bindings" not in payload and "default_provider_id" not in payload:
        payload = _migrate_legacy_provider_payload(payload)

    providers = []
    for raw_provider in list(payload.get("providers") or []):
        if not isinstance(raw_provider, dict):
            providers.append(raw_provider)
            continue
        normalized_provider = dict(raw_provider)
        normalized_provider.setdefault(
            "capability_tags",
            [tag.value for tag in DEFAULT_PROVIDER_CAPABILITY_TAGS],
        )
        normalized_provider.setdefault("cost_tier", RuntimeProviderCostTier.STANDARD)
        normalized_provider.setdefault(
            "participation_policy",
            RuntimeProviderParticipationPolicy.ALWAYS_ALLOWED,
        )
        normalized_provider.setdefault("fallback_provider_ids", [])
        providers.append(normalized_provider)

    return {
        **payload,
        "providers": providers,
        "role_bindings": list(payload.get("role_bindings") or []),
    }


def build_runtime_provider_store() -> RuntimeProviderConfigStore:
    return RuntimeProviderConfigStore(get_settings().runtime_provider_config_path)


def resolve_runtime_provider_config(
    store: RuntimeProviderConfigStore | None = None,
) -> RuntimeProviderStoredConfig:
    resolved_store = store or build_runtime_provider_store()
    saved = resolved_store.load_saved_config()
    if saved is not None:
        return _ensure_provider_defaults(saved)
    return _build_env_backed_provider_config()


def _ensure_provider_defaults(config: RuntimeProviderStoredConfig) -> RuntimeProviderStoredConfig:
    provider_by_id = {provider.provider_id: provider for provider in config.providers}
    providers = [_normalized_provider_entry(provider) for provider in config.providers]
    defaults = _default_provider_entries()
    for provider in defaults:
        if provider.provider_id not in provider_by_id:
            providers.append(provider)
    return RuntimeProviderStoredConfig(
        default_provider_id=config.default_provider_id,
        providers=providers,
        role_bindings=list(config.role_bindings),
    )


def find_provider_entry(
    config: RuntimeProviderStoredConfig,
    provider_id: str | None,
) -> RuntimeProviderConfigEntry | None:
    if not provider_id:
        return None
    normalized = str(provider_id).strip()
    if not normalized:
        return None
    for provider in config.providers:
        if provider.provider_id == normalized:
            return _normalized_provider_entry(provider)
    return None


def _normalized_provider_entry(provider: RuntimeProviderConfigEntry) -> RuntimeProviderConfigEntry:
    if (
        provider.capability_tags
        and provider.cost_tier is not None
        and provider.participation_policy is not None
    ):
        return provider
    return provider.model_copy(
        update={
            "capability_tags": list(provider.capability_tags or DEFAULT_PROVIDER_CAPABILITY_TAGS),
            "cost_tier": provider.cost_tier or RuntimeProviderCostTier.STANDARD,
            "participation_policy": (
                provider.participation_policy or RuntimeProviderParticipationPolicy.ALWAYS_ALLOWED
            ),
        }
    )


def _provider_capability_tag_values(provider: RuntimeProviderConfigEntry) -> set[str]:
    normalized_provider = _normalized_provider_entry(provider)
    return {tag.value for tag in normalized_provider.capability_tags}


def provider_meets_target_capability_floor(provider: RuntimeProviderConfigEntry, target_ref: str) -> bool:
    required_tags = RUNTIME_TARGET_CAPABILITY_FLOORS.get(target_ref)
    if not required_tags:
        return True
    capability_values = _provider_capability_tag_values(provider)
    return all(required_tag.value in capability_values for required_tag in required_tags)


def target_is_low_frequency_high_leverage(target_ref: str) -> bool:
    return target_ref in LOW_FREQUENCY_HIGH_LEVERAGE_TARGET_REFS


def provider_allows_target_participation(provider: RuntimeProviderConfigEntry, target_ref: str) -> bool:
    normalized_provider = _normalized_provider_entry(provider)
    if normalized_provider.participation_policy == RuntimeProviderParticipationPolicy.ALWAYS_ALLOWED:
        return True
    return target_is_low_frequency_high_leverage(target_ref)


def _preferred_provider_policy_reason(provider: RuntimeProviderConfigEntry, target_ref: str) -> str | None:
    if provider_allows_target_participation(provider, target_ref):
        return None
    if provider.participation_policy == RuntimeProviderParticipationPolicy.LOW_FREQUENCY_ONLY:
        return "preferred_provider_low_frequency_only_for_high_frequency_target"
    return "preferred_provider_participation_policy_rejected"


def _normalize_runtime_preference(
    runtime_preference: RuntimeSelectionPreference | dict[str, Any] | None,
) -> RuntimeSelectionPreference | None:
    if runtime_preference is None:
        return None
    if isinstance(runtime_preference, RuntimeSelectionPreference):
        return runtime_preference
    if isinstance(runtime_preference, dict):
        preferred_provider_id = str(runtime_preference.get("preferred_provider_id") or "").strip()
        if not preferred_provider_id:
            return None
        preferred_model = runtime_preference.get("preferred_model")
        return RuntimeSelectionPreference(
            preferred_provider_id=preferred_provider_id,
            preferred_model=(str(preferred_model).strip() or None) if preferred_model is not None else None,
        )
    return None


def _build_runtime_provider_selection(
    *,
    provider: RuntimeProviderConfigEntry,
    preferred_provider_id: str,
    preferred_model: str | None,
    actual_model: str | None,
    binding_target_ref: str | None,
    selection_reason: str,
    policy_reason: str | None = None,
) -> RuntimeProviderSelection:
    return RuntimeProviderSelection(
        provider=provider,
        preferred_provider_id=preferred_provider_id,
        preferred_model=preferred_model,
        actual_model=actual_model,
        binding_target_ref=binding_target_ref,
        selection_reason=selection_reason,
        policy_reason=policy_reason,
    )


def _binding_target_ref_candidates(target_ref: str) -> tuple[str, ...]:
    normalized_target_ref = str(target_ref or "").strip()
    if not normalized_target_ref:
        return ()

    candidates = [normalized_target_ref]
    for legacy_target_ref in legacy_target_refs_for_execution_target(normalized_target_ref):
        if legacy_target_ref not in candidates:
            candidates.append(legacy_target_ref)
    return tuple(candidates)


def resolve_provider_selection(
    config: RuntimeProviderStoredConfig,
    *,
    target_ref: str,
    employee_provider_id: str | None,
    runtime_preference: RuntimeSelectionPreference | dict[str, Any] | None = None,
) -> RuntimeProviderSelection | None:
    normalized_preference = _normalize_runtime_preference(runtime_preference)
    preferred_provider_id = (
        normalized_preference.preferred_provider_id if normalized_preference is not None else None
    )
    preferred_model = normalized_preference.preferred_model if normalized_preference is not None else None
    preferred_policy_reason: str | None = None
    if normalized_preference is not None:
        preferred_provider = find_provider_entry(config, normalized_preference.preferred_provider_id)
        if (
            preferred_provider is not None
            and preferred_provider.enabled
            and provider_meets_target_capability_floor(preferred_provider, target_ref)
            and provider_allows_target_participation(preferred_provider, target_ref)
        ):
            resolved_preferred_model = normalized_preference.preferred_model or preferred_provider.model
            return _build_runtime_provider_selection(
                provider=preferred_provider,
                preferred_provider_id=normalized_preference.preferred_provider_id,
                preferred_model=resolved_preferred_model,
                actual_model=resolved_preferred_model,
                binding_target_ref=target_ref,
                selection_reason="ticket_runtime_preference",
            )
        if preferred_provider is not None:
            preferred_policy_reason = _preferred_provider_policy_reason(preferred_provider, target_ref)

    for binding_target_ref in _binding_target_ref_candidates(target_ref):
        for binding in config.role_bindings:
            if binding.target_ref != binding_target_ref:
                continue
            provider = find_provider_entry(config, binding.provider_id)
            if (
                provider is None
                or not provider.enabled
                or not provider_meets_target_capability_floor(provider, target_ref)
                or not provider_allows_target_participation(provider, target_ref)
            ):
                continue
            resolved_preferred_provider_id = preferred_provider_id or provider.provider_id
            resolved_preferred_model = preferred_model or binding.model or provider.model
            return _build_runtime_provider_selection(
                provider=provider,
                preferred_provider_id=resolved_preferred_provider_id,
                preferred_model=resolved_preferred_model,
                actual_model=binding.model or provider.model,
                binding_target_ref=target_ref,
                selection_reason=(
                    "role_binding_fallback_after_ticket_runtime_preference"
                    if normalized_preference is not None
                    else "role_binding"
                ),
                policy_reason=preferred_policy_reason,
            )

    employee_provider = find_provider_entry(config, employee_provider_id)
    if (
        employee_provider is not None
        and employee_provider.enabled
        and provider_meets_target_capability_floor(employee_provider, target_ref)
        and provider_allows_target_participation(employee_provider, target_ref)
    ):
        return _build_runtime_provider_selection(
            provider=employee_provider,
            preferred_provider_id=preferred_provider_id or employee_provider.provider_id,
            preferred_model=preferred_model or employee_provider.model,
            actual_model=employee_provider.model,
            binding_target_ref=None,
            selection_reason=(
                "employee_provider_fallback_after_ticket_runtime_preference"
                if normalized_preference is not None
                else "employee_provider"
            ),
            policy_reason=preferred_policy_reason,
        )

    default_provider = find_provider_entry(config, config.default_provider_id)
    if (
        default_provider is not None
        and default_provider.enabled
        and provider_meets_target_capability_floor(default_provider, target_ref)
        and provider_allows_target_participation(default_provider, target_ref)
    ):
        return _build_runtime_provider_selection(
            provider=default_provider,
            preferred_provider_id=preferred_provider_id or default_provider.provider_id,
            preferred_model=preferred_model or default_provider.model,
            actual_model=default_provider.model,
            binding_target_ref=None,
            selection_reason=(
                "default_provider_fallback_after_ticket_runtime_preference"
                if normalized_preference is not None
                else "default_provider"
            ),
            policy_reason=preferred_policy_reason,
        )
    return None


def resolve_provider_failover_selections(
    config: RuntimeProviderStoredConfig,
    repository: ControlPlaneRepository,
    *,
    target_ref: str,
    primary_selection: RuntimeProviderSelection,
) -> list[RuntimeProviderSelection]:
    selections: list[RuntimeProviderSelection] = []
    attempted_provider_ids = {primary_selection.provider.provider_id}
    for fallback_provider_id in primary_selection.provider.fallback_provider_ids:
        fallback_provider = find_provider_entry(config, fallback_provider_id)
        if fallback_provider is None:
            continue
        if fallback_provider.provider_id in attempted_provider_ids:
            continue
        if not fallback_provider.enabled or not provider_meets_target_capability_floor(fallback_provider, target_ref):
            continue
        health_status, _ = runtime_provider_health_details(fallback_provider, repository)
        if health_status != "HEALTHY":
            continue
        selections.append(
            _build_runtime_provider_selection(
                provider=fallback_provider,
                preferred_provider_id=primary_selection.preferred_provider_id,
                preferred_model=primary_selection.preferred_model,
                actual_model=fallback_provider.model,
                binding_target_ref=primary_selection.binding_target_ref,
                selection_reason="provider_failover",
                policy_reason=primary_selection.policy_reason,
            )
        )
        attempted_provider_ids.add(fallback_provider.provider_id)
    return selections


def provider_is_configured(provider: RuntimeProviderConfigEntry) -> bool:
    provider = _normalized_provider_entry(provider)
    if provider.adapter_kind == RuntimeProviderAdapterKind.OPENAI_COMPAT:
        return bool(provider.base_url and provider.api_key and provider.model)
    if provider.adapter_kind == RuntimeProviderAdapterKind.CLAUDE_CODE_CLI:
        return bool(provider.command_path and provider.model)
    return False


def _resolve_claude_command_path(command_path: str | None) -> str | None:
    normalized_command = str(command_path or "").strip()
    if not normalized_command:
        return None
    resolved = shutil.which(normalized_command)
    if resolved:
        return resolved
    candidate = Path(normalized_command).expanduser()
    if candidate.is_file():
        return str(candidate)
    return None


def runtime_provider_health_details(
    provider: RuntimeProviderConfigEntry,
    repository: ControlPlaneRepository,
) -> tuple[str, str]:
    normalized_provider = _normalized_provider_entry(provider)
    if normalized_provider.adapter_kind == RuntimeProviderAdapterKind.OPENAI_COMPAT:
        provider_label = "OpenAI-compatible provider"
    else:
        provider_label = "Claude Code CLI provider"

    if not normalized_provider.enabled:
        return ("DISABLED", f"{provider_label} is disabled.")
    if not provider_is_configured(normalized_provider):
        return ("INCOMPLETE", f"{provider_label} configuration is incomplete.")
    if (
        normalized_provider.adapter_kind == RuntimeProviderAdapterKind.CLAUDE_CODE_CLI
        and _resolve_claude_command_path(normalized_provider.command_path) is None
    ):
        return (
            "COMMAND_NOT_FOUND",
            f"{provider_label} command path could not be resolved on this machine.",
        )
    if repository.has_open_circuit_breaker_for_provider(normalized_provider.provider_id):
        return (
            "PAUSED",
            f"{provider_label} is paused by an open provider incident.",
        )
    if normalized_provider.adapter_kind == RuntimeProviderAdapterKind.OPENAI_COMPAT:
        return ("HEALTHY", "Runtime is using the saved OpenAI-compatible provider config.")
    return ("HEALTHY", "Runtime is using the saved Claude Code CLI provider config.")


def provider_effective_mode(
    provider: RuntimeProviderConfigEntry,
    repository: ControlPlaneRepository,
) -> tuple[str, str]:
    provider = _normalized_provider_entry(provider)
    if provider.adapter_kind == RuntimeProviderAdapterKind.OPENAI_COMPAT:
        prefix = "OPENAI_COMPAT"
    else:
        prefix = "CLAUDE_CODE_CLI"
    health_status, health_reason = runtime_provider_health_details(provider, repository)

    if health_status == "DISABLED":
        return ("LOCAL_DETERMINISTIC", f"{health_reason} Runtime falls back to the local deterministic path.")
    if health_status in {"INCOMPLETE", "COMMAND_NOT_FOUND"}:
        return (f"{prefix}_INCOMPLETE", f"{health_reason} Runtime falls back to the local deterministic path.")
    if health_status == "PAUSED":
        return (f"{prefix}_PAUSED", f"{health_reason} Runtime falls back to the local deterministic path.")
    return (f"{prefix}_LIVE", health_reason)


def runtime_provider_effective_mode(
    config: RuntimeProviderStoredConfig,
    repository: ControlPlaneRepository,
) -> tuple[str, str]:
    default_provider = find_provider_entry(config, config.default_provider_id)
    if default_provider is None:
        return ("LOCAL_DETERMINISTIC", "Runtime is using the local deterministic path.")
    return provider_effective_mode(default_provider, repository)


def runtime_provider_health_summary(
    config: RuntimeProviderStoredConfig,
    repository: ControlPlaneRepository,
) -> str:
    effective_mode, _ = runtime_provider_effective_mode(config, repository)
    if effective_mode == "LOCAL_DETERMINISTIC":
        return "LOCAL_ONLY"
    if effective_mode.endswith("_INCOMPLETE"):
        return "INCOMPLETE"
    if effective_mode.endswith("_PAUSED"):
        return "PAUSED"
    return "HEALTHY"


def mask_api_key(api_key: str | None) -> str | None:
    if not api_key:
        return None
    if len(api_key) <= 4:
        return "*" * len(api_key)
    return f"{api_key[:3]}***{api_key[-4:]}"


def count_configured_workers(
    repository: ControlPlaneRepository,
    *,
    provider_id: str,
) -> int:
    return sum(
        1
        for employee in repository.list_employee_projections(board_approved_only=True)
        if str(employee.get("provider_id") or "") == provider_id
    )


def runtime_target_label(target_ref: str) -> str:
    return RUNTIME_TARGET_LABELS.get(target_ref, target_ref)


def save_runtime_provider_command(
    store: RuntimeProviderConfigStore,
    payload: RuntimeProviderUpsertCommand,
) -> CommandAckEnvelope:
    existing_config = resolve_runtime_provider_config(store)
    existing_provider_by_id = {
        provider.provider_id: provider for provider in existing_config.providers
    }

    providers: list[RuntimeProviderConfigEntry] = []
    for item in payload.providers:
        provider_payload = item.model_dump(mode="json")
        if provider_payload.get("adapter_kind") == RuntimeProviderAdapterKind.OPENAI_COMPAT.value:
            existing_provider = existing_provider_by_id.get(str(provider_payload.get("provider_id") or ""))
            if (
                provider_payload.get("api_key") is None
                and existing_provider is not None
                and existing_provider.api_key
            ):
                provider_payload["api_key"] = existing_provider.api_key
        providers.append(RuntimeProviderConfigEntry.model_validate(provider_payload))

    store.save_config(
        RuntimeProviderStoredConfig(
            default_provider_id=payload.default_provider_id,
            providers=providers,
            role_bindings=[
                RuntimeProviderRoleBinding.model_validate(item.model_dump(mode="json"))
                for item in payload.role_bindings
            ],
        )
    )
    causation_provider_id = payload.default_provider_id or "local_deterministic"
    return CommandAckEnvelope(
        command_id=new_prefixed_id("cmd"),
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=now_local(),
        reason=None,
        causation_hint=f"runtime-provider:{causation_provider_id}",
    )
