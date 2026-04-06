from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pydantic import Field

from app.contracts.commands import (
    CommandAckEnvelope,
    CommandAckStatus,
    RuntimeProviderCapabilityTag,
    RuntimeProviderMode,
    RuntimeProviderUpsertCommand,
)
from app.contracts.common import StrictModel
from app.config import get_settings
from app.core.ids import new_prefixed_id
from app.core.time import now_local
from app.db.repository import ControlPlaneRepository

OPENAI_COMPAT_PROVIDER_ID = "prov_openai_compat"
CLAUDE_CODE_PROVIDER_ID = "prov_claude_code"

ROLE_BINDING_CEO_SHADOW = "ceo_shadow"
ROLE_BINDING_UI_DESIGNER = "role_profile:ui_designer_primary"
ROLE_BINDING_FRONTEND_ENGINEER = "role_profile:frontend_engineer_primary"
ROLE_BINDING_CHECKER = "role_profile:checker_primary"

CURRENT_RUNTIME_ROLE_TARGET_REFS = (
    ROLE_BINDING_CEO_SHADOW,
    ROLE_BINDING_UI_DESIGNER,
    ROLE_BINDING_FRONTEND_ENGINEER,
    ROLE_BINDING_CHECKER,
)

RUNTIME_TARGET_LABELS = {
    ROLE_BINDING_CEO_SHADOW: "CEO Shadow",
    ROLE_BINDING_UI_DESIGNER: "Scope Consensus",
    ROLE_BINDING_FRONTEND_ENGINEER: "Frontend Engineer",
    ROLE_BINDING_CHECKER: "Checker",
}

FUTURE_ROLE_BINDING_SLOTS = (
    {
        "target_ref": "role_profile:cto_primary",
        "label": "CTO / 架构治理",
        "status": "NOT_ENABLED",
        "reason": "治理模板角色尚未纳入当前主线。",
    },
    {
        "target_ref": "role_profile:architect_primary",
        "label": "架构师 / 设计评审",
        "status": "NOT_ENABLED",
        "reason": "治理模板角色尚未纳入当前主线。",
    },
)


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


DEFAULT_PROVIDER_CAPABILITY_TAGS = (
    RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
    RuntimeProviderCapabilityTag.PLANNING,
    RuntimeProviderCapabilityTag.IMPLEMENTATION,
    RuntimeProviderCapabilityTag.REVIEW,
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
    ROLE_BINDING_FRONTEND_ENGINEER: (
        RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
        RuntimeProviderCapabilityTag.IMPLEMENTATION,
    ),
    ROLE_BINDING_CHECKER: (
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
    if provider.capability_tags:
        return provider
    return provider.model_copy(update={"capability_tags": list(DEFAULT_PROVIDER_CAPABILITY_TAGS)})


def _provider_capability_tag_values(provider: RuntimeProviderConfigEntry) -> set[str]:
    normalized_provider = _normalized_provider_entry(provider)
    return {tag.value for tag in normalized_provider.capability_tags}


def provider_meets_target_capability_floor(provider: RuntimeProviderConfigEntry, target_ref: str) -> bool:
    required_tags = RUNTIME_TARGET_CAPABILITY_FLOORS.get(target_ref)
    if not required_tags:
        return True
    capability_values = _provider_capability_tag_values(provider)
    return all(required_tag.value in capability_values for required_tag in required_tags)


def resolve_provider_selection(
    config: RuntimeProviderStoredConfig,
    *,
    target_ref: str,
    employee_provider_id: str | None,
) -> RuntimeProviderSelection | None:
    for binding in config.role_bindings:
        if binding.target_ref != target_ref:
            continue
        provider = find_provider_entry(config, binding.provider_id)
        if provider is None or not provider.enabled or not provider_meets_target_capability_floor(provider, target_ref):
            continue
        return RuntimeProviderSelection(
            provider=provider,
            preferred_provider_id=provider.provider_id,
            preferred_model=binding.model or provider.model,
            actual_model=binding.model or provider.model,
            binding_target_ref=binding.target_ref,
        )

    employee_provider = find_provider_entry(config, employee_provider_id)
    if (
        employee_provider is not None
        and employee_provider.enabled
        and provider_meets_target_capability_floor(employee_provider, target_ref)
    ):
        return RuntimeProviderSelection(
            provider=employee_provider,
            preferred_provider_id=employee_provider.provider_id,
            preferred_model=employee_provider.model,
            actual_model=employee_provider.model,
            binding_target_ref=None,
        )

    default_provider = find_provider_entry(config, config.default_provider_id)
    if default_provider is not None and default_provider.enabled and provider_meets_target_capability_floor(default_provider, target_ref):
        return RuntimeProviderSelection(
            provider=default_provider,
            preferred_provider_id=default_provider.provider_id,
            preferred_model=default_provider.model,
            actual_model=default_provider.model,
            binding_target_ref=None,
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
            RuntimeProviderSelection(
                provider=fallback_provider,
                preferred_provider_id=primary_selection.preferred_provider_id,
                preferred_model=primary_selection.preferred_model,
                actual_model=fallback_provider.model,
                binding_target_ref=primary_selection.binding_target_ref,
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
    store.save_config(
        RuntimeProviderStoredConfig(
            default_provider_id=payload.default_provider_id,
            providers=[
                RuntimeProviderConfigEntry.model_validate(item.model_dump(mode="json"))
                for item in payload.providers
            ],
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
