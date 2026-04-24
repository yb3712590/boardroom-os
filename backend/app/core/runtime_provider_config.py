from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from tempfile import mkdtemp
from typing import Any
from urllib.parse import urlparse

from pydantic import Field, model_validator

from app.contracts.commands import (
    CommandAckEnvelope,
    CommandAckStatus,
    RuntimeProviderCapabilityTag,
    RuntimeProviderCostTier,
    RuntimeProviderParticipationPolicy,
    RuntimeProviderReasoningEffort,
    RuntimeProviderType,
    RuntimeSelectionPreference,
    RuntimeProviderUpsertCommand,
)
from app.contracts.common import StrictModel
from app.config import get_settings
from app.core.execution_targets import legacy_target_refs_for_execution_target
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
    ROLE_BINDING_BACKEND_ENGINEER: "Backend Engineer / Service Delivery",
    ROLE_BINDING_DATABASE_ENGINEER: "Database Engineer / Data Reliability",
    ROLE_BINDING_PLATFORM_SRE: "Platform / SRE",
    ROLE_BINDING_ARCHITECT: "Architect / Design Review",
    ROLE_BINDING_CTO: "CTO / Architecture Governance",
}

FUTURE_ROLE_BINDING_SLOTS: tuple[dict[str, object], ...] = ()
DEFAULT_MAX_CONTEXT_WINDOW = 1_000_000
DEFAULT_TIMEOUT_SEC = 300.0
DEFAULT_CONNECT_TIMEOUT_SEC = 10.0
DEFAULT_WRITE_TIMEOUT_SEC = 20.0
DEFAULT_FIRST_TOKEN_TIMEOUT_SEC = 300.0
DEFAULT_STREAM_IDLE_TIMEOUT_SEC = 300.0
DEFAULT_RETRY_BACKOFF_SCHEDULE_SEC: tuple[float, ...] = (1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0, 60.0)
DEFAULT_REASONING_EFFORT: RuntimeProviderReasoningEffort = "high"
DEFAULT_PROVIDER_CAPABILITY_TAGS = (
    RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
    RuntimeProviderCapabilityTag.PLANNING,
    RuntimeProviderCapabilityTag.IMPLEMENTATION,
    RuntimeProviderCapabilityTag.REVIEW,
)


class RuntimeProviderAdapterKind(StrEnum):
    OPENAI_COMPAT = "openai_compat"
    CLAUDE_CODE_CLI = "claude_code_cli"


class RuntimeProviderConfigEntry(StrictModel):
    provider_id: str = Field(min_length=1)
    type: RuntimeProviderType = RuntimeProviderType.OPENAI_RESPONSES_STREAM
    adapter_kind: RuntimeProviderAdapterKind = RuntimeProviderAdapterKind.OPENAI_COMPAT
    label: str = Field(min_length=1)
    enabled: bool = False
    base_url: str | None = None
    api_key: str | None = None
    alias: str | None = None
    preferred_model: str | None = None
    model: str | None = None
    max_context_window: int = Field(default=DEFAULT_MAX_CONTEXT_WINDOW, ge=1)
    timeout_sec: float | None = Field(default=None, gt=0)
    connect_timeout_sec: float | None = Field(default=None, gt=0)
    write_timeout_sec: float | None = Field(default=None, gt=0)
    first_token_timeout_sec: float | None = Field(default=None, gt=0)
    stream_idle_timeout_sec: float | None = Field(default=None, gt=0)
    request_total_timeout_sec: float | None = Field(default=None, gt=0)
    retry_backoff_schedule_sec: list[float] = Field(default_factory=list)
    reasoning_effort: RuntimeProviderReasoningEffort = DEFAULT_REASONING_EFFORT
    command_path: str | None = None
    capability_tags: list[RuntimeProviderCapabilityTag] = Field(default_factory=list)
    cost_tier: RuntimeProviderCostTier = RuntimeProviderCostTier.STANDARD
    participation_policy: RuntimeProviderParticipationPolicy = RuntimeProviderParticipationPolicy.ALWAYS_ALLOWED
    fallback_provider_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_legacy_fields(self) -> "RuntimeProviderConfigEntry":
        provider_type = self.type
        if self.adapter_kind == RuntimeProviderAdapterKind.CLAUDE_CODE_CLI:
            provider_type = RuntimeProviderType.CLAUDE_STREAM
        alias = _derive_alias(str(self.base_url or ""), self.alias or self.label)
        legacy_timeout_sec = float(self.timeout_sec or DEFAULT_TIMEOUT_SEC)
        timeout_was_explicit = self.timeout_sec is not None
        request_total_timeout_sec = (
            float(self.request_total_timeout_sec) if self.request_total_timeout_sec is not None else None
        )
        fallback_timeout_sec = float(request_total_timeout_sec or legacy_timeout_sec)
        connect_timeout_sec = float(
            self.connect_timeout_sec or min(fallback_timeout_sec, DEFAULT_CONNECT_TIMEOUT_SEC)
        )
        write_timeout_sec = float(
            self.write_timeout_sec or min(fallback_timeout_sec, DEFAULT_WRITE_TIMEOUT_SEC)
        )
        first_token_timeout_sec = float(
            self.first_token_timeout_sec
            or (
                min(legacy_timeout_sec, DEFAULT_FIRST_TOKEN_TIMEOUT_SEC)
                if timeout_was_explicit and self.request_total_timeout_sec is None
                else DEFAULT_FIRST_TOKEN_TIMEOUT_SEC
            )
        )
        stream_idle_timeout_sec = float(
            self.stream_idle_timeout_sec
            or (
                min(legacy_timeout_sec, DEFAULT_STREAM_IDLE_TIMEOUT_SEC)
                if timeout_was_explicit and self.request_total_timeout_sec is None
                else DEFAULT_STREAM_IDLE_TIMEOUT_SEC
            )
        )
        retry_backoff_schedule_sec = [
            float(item) for item in (self.retry_backoff_schedule_sec or DEFAULT_RETRY_BACKOFF_SCHEDULE_SEC)
        ]
        object.__setattr__(self, "type", provider_type)
        object.__setattr__(self, "adapter_kind", _normalize_provider_type(provider_type))
        object.__setattr__(self, "alias", alias)
        object.__setattr__(self, "label", alias)
        object.__setattr__(self, "model", self.preferred_model or self.model)
        object.__setattr__(self, "preferred_model", self.preferred_model or self.model)
        object.__setattr__(self, "max_context_window", self.max_context_window or DEFAULT_MAX_CONTEXT_WINDOW)
        object.__setattr__(self, "timeout_sec", fallback_timeout_sec)
        object.__setattr__(self, "connect_timeout_sec", connect_timeout_sec)
        object.__setattr__(self, "write_timeout_sec", write_timeout_sec)
        object.__setattr__(self, "first_token_timeout_sec", first_token_timeout_sec)
        object.__setattr__(self, "stream_idle_timeout_sec", stream_idle_timeout_sec)
        object.__setattr__(self, "request_total_timeout_sec", request_total_timeout_sec)
        object.__setattr__(self, "retry_backoff_schedule_sec", retry_backoff_schedule_sec)
        object.__setattr__(self, "reasoning_effort", _normalize_reasoning_effort(self.reasoning_effort))
        return self


class RuntimeProviderModelEntry(StrictModel):
    entry_ref: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    model_name: str = Field(min_length=1)


class RuntimeProviderRoleBinding(StrictModel):
    target_ref: str = Field(min_length=1)
    provider_model_entry_refs: list[str] = Field(default_factory=list)
    max_context_window_override: int | None = Field(default=None, ge=1)
    reasoning_effort_override: RuntimeProviderReasoningEffort | None = None
    provider_id: str | None = None
    model: str | None = None

    @model_validator(mode="after")
    def normalize_legacy_fields(self) -> "RuntimeProviderRoleBinding":
        if (not self.provider_model_entry_refs) and self.provider_id and self.model:
            object.__setattr__(
                self,
                "provider_model_entry_refs",
                [build_provider_model_entry_ref(self.provider_id, self.model)],
            )
        return self


class RuntimeProviderStoredConfig(StrictModel):
    default_provider_id: str | None = None
    providers: list[RuntimeProviderConfigEntry] = Field(default_factory=list)
    provider_model_entries: list[RuntimeProviderModelEntry] = Field(default_factory=list)
    role_bindings: list[RuntimeProviderRoleBinding] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_legacy_entries(self) -> "RuntimeProviderStoredConfig":
        if self.provider_model_entries:
            return self
        derived_entries: list[RuntimeProviderModelEntry] = []
        seen_refs: set[str] = set()
        for provider in self.providers:
            if provider.preferred_model or provider.model:
                model_name = str(provider.preferred_model or provider.model or "").strip()
                if model_name:
                    entry_ref = build_provider_model_entry_ref(provider.provider_id, model_name)
                    if entry_ref not in seen_refs:
                        derived_entries.append(
                            RuntimeProviderModelEntry(
                                entry_ref=entry_ref,
                                provider_id=provider.provider_id,
                                model_name=model_name,
                            )
                        )
                        seen_refs.add(entry_ref)
        for binding in self.role_bindings:
            for entry_ref in binding.provider_model_entry_refs:
                if entry_ref in seen_refs:
                    continue
                provider_id, _, model_name = entry_ref.partition("::")
                if provider_id and model_name:
                    derived_entries.append(
                        RuntimeProviderModelEntry(
                            entry_ref=entry_ref,
                            provider_id=provider_id,
                            model_name=model_name,
                        )
                    )
                    seen_refs.add(entry_ref)
        object.__setattr__(self, "provider_model_entries", derived_entries)
        if self.default_provider_id is None:
            object.__setattr__(
                self,
                "default_provider_id",
                _derive_default_provider_id_from_bindings(self.role_bindings, derived_entries),
            )
        return self


@dataclass(frozen=True)
class RuntimeProviderSelection:
    provider: RuntimeProviderConfigEntry
    provider_model_entry_ref: str
    preferred_provider_id: str
    preferred_model: str | None
    actual_model: str | None
    binding_target_ref: str | None = None
    selection_reason: str | None = None
    policy_reason: str | None = None
    effective_max_context_window: int = DEFAULT_MAX_CONTEXT_WINDOW
    effective_reasoning_effort: RuntimeProviderReasoningEffort = DEFAULT_REASONING_EFFORT


class RuntimeProviderConfigStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.shard_dir = Path(f"{self.path}.d")

    def load_saved_config(self) -> RuntimeProviderStoredConfig | None:
        if self.shard_dir.is_dir():
            return self._load_sharded_config()
        if not self.path.exists():
            return None
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return RuntimeProviderStoredConfig.model_validate(_normalize_provider_store_payload(payload))

    def save_config(self, payload: RuntimeProviderStoredConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        normalized_payload = RuntimeProviderStoredConfig.model_validate(payload.model_dump(mode="json"))
        temp_dir = Path(mkdtemp(prefix=f"{self.path.name}.", suffix=".tmp", dir=self.path.parent))
        try:
            self._write_sharded_config(temp_dir, normalized_payload)
            self._replace_shard_dir(temp_dir)
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise
        self.path.write_text(
            json.dumps(normalized_payload.model_dump(mode="json"), ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _load_sharded_config(self) -> RuntimeProviderStoredConfig:
        routing_path = self.shard_dir / "routing.json"
        routing_payload = {}
        if routing_path.exists():
            routing_payload = json.loads(routing_path.read_text(encoding="utf-8"))
        providers = [
            json.loads(provider_path.read_text(encoding="utf-8"))
            for provider_path in self.shard_dir.glob("provider.*.json")
            if provider_path.is_file()
        ]
        providers.sort(key=lambda item: str(item.get("provider_id") or "").strip())
        payload = {
            "default_provider_id": routing_payload.get("default_provider_id"),
            "providers": providers,
            "provider_model_entries": routing_payload.get("provider_model_entries", []),
            "role_bindings": routing_payload.get("role_bindings", []),
        }
        return RuntimeProviderStoredConfig.model_validate(_normalize_provider_store_payload(payload))

    def _write_sharded_config(self, target_dir: Path, payload: RuntimeProviderStoredConfig) -> None:
        target_dir.mkdir(parents=True, exist_ok=True)
        providers = sorted(payload.providers, key=lambda item: item.provider_id)
        for provider in providers:
            provider_payload = provider.model_dump(
                mode="json",
                exclude={"adapter_kind", "label", "model"},
            )
            provider_path = target_dir / f"provider.{provider.provider_id}.json"
            provider_path.write_text(
                json.dumps(provider_payload, ensure_ascii=True, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        routing_payload = {
            "default_provider_id": payload.default_provider_id,
            "provider_model_entries": [
                {
                    "provider_id": entry.provider_id,
                    "model_name": entry.model_name,
                }
                for entry in payload.provider_model_entries
            ],
            "role_bindings": [binding.model_dump(mode="json") for binding in payload.role_bindings],
        }
        (target_dir / "routing.json").write_text(
            json.dumps(routing_payload, ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _replace_shard_dir(self, source_dir: Path) -> None:
        backup_dir = Path(f"{self.shard_dir}.bak")
        if backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)
        if self.shard_dir.exists():
            self.shard_dir.replace(backup_dir)
        try:
            source_dir.replace(self.shard_dir)
        except Exception:
            if backup_dir.exists() and not self.shard_dir.exists():
                backup_dir.replace(self.shard_dir)
            raise
        shutil.rmtree(backup_dir, ignore_errors=True)


def build_provider_model_entry_ref(provider_id: str, model_name: str) -> str:
    return f"{str(provider_id).strip()}::{str(model_name).strip()}"


def _empty_runtime_provider_config() -> RuntimeProviderStoredConfig:
    return RuntimeProviderStoredConfig(
        default_provider_id=None,
        providers=[],
        provider_model_entries=[],
        role_bindings=[],
    )


def _build_env_backed_provider_config() -> RuntimeProviderStoredConfig:
    settings = get_settings()
    base_url = str(settings.provider_openai_compat_base_url or "").strip()
    api_key = str(settings.provider_openai_compat_api_key or "").strip()
    model = str(settings.provider_openai_compat_model or "").strip()
    if not (base_url and api_key and model):
        return _empty_runtime_provider_config()
    provider = _normalize_provider_entry(
        {
            "provider_id": OPENAI_COMPAT_PROVIDER_ID,
            "type": RuntimeProviderType.OPENAI_RESPONSES_STREAM,
            "base_url": base_url,
            "api_key": api_key,
            "alias": "env",
            "preferred_model": model,
            "max_context_window": DEFAULT_MAX_CONTEXT_WINDOW,
            "enabled": True,
            "timeout_sec": settings.provider_openai_compat_timeout_sec,
            "reasoning_effort": settings.provider_openai_compat_reasoning_effort,
        }
    )
    entry = RuntimeProviderModelEntry(
        entry_ref=build_provider_model_entry_ref(provider.provider_id, model),
        provider_id=provider.provider_id,
        model_name=model,
    )
    return RuntimeProviderStoredConfig(
        default_provider_id=provider.provider_id,
        providers=[provider],
        provider_model_entries=[entry],
        role_bindings=[],
    )


def _derive_alias(base_url: str, alias: str | None) -> str:
    normalized_alias = str(alias or "").strip()
    if normalized_alias:
        return normalized_alias
    parsed = urlparse(base_url)
    host = str(parsed.hostname or "").strip().lower()
    if not host:
        return "provider"
    parts = [part for part in host.split(".") if part]
    if len(parts) >= 2:
        return parts[-2]
    return parts[0]


def _provider_label(provider: RuntimeProviderConfigEntry) -> str:
    return provider.alias or provider.label or provider.provider_id


def _normalize_reasoning_effort(
    reasoning_effort: RuntimeProviderReasoningEffort | str | None,
) -> RuntimeProviderReasoningEffort:
    normalized = str(reasoning_effort or "").strip().lower()
    if normalized in {"low", "medium", "high", "xhigh"}:
        return normalized  # type: ignore[return-value]
    return DEFAULT_REASONING_EFFORT


def _normalize_provider_type(provider_type: RuntimeProviderType) -> RuntimeProviderAdapterKind:
    if provider_type in {
        RuntimeProviderType.OPENAI_RESPONSES_STREAM,
        RuntimeProviderType.OPENAI_RESPONSES_NON_STREAM,
    }:
        return RuntimeProviderAdapterKind.OPENAI_COMPAT
    return RuntimeProviderAdapterKind.CLAUDE_CODE_CLI


def _normalize_provider_entry(provider: RuntimeProviderConfigEntry | dict[str, Any]) -> RuntimeProviderConfigEntry:
    if isinstance(provider, dict):
        payload = dict(provider)
        provider_id = str(payload.get("provider_id") or "").strip()
        provider_type = payload.get("type") or RuntimeProviderType.OPENAI_RESPONSES_STREAM
        adapter_kind = payload.get("adapter_kind")
        if adapter_kind == RuntimeProviderAdapterKind.CLAUDE_CODE_CLI.value:
            provider_type = RuntimeProviderType.CLAUDE_STREAM
        if not isinstance(provider_type, RuntimeProviderType):
            provider_type = RuntimeProviderType(str(provider_type))
        base_url = str(payload.get("base_url") or "").strip() or None
        alias = _derive_alias(base_url or "", payload.get("alias"))
        preferred_model = str(payload.get("preferred_model") or payload.get("model") or "").strip() or None
        return RuntimeProviderConfigEntry(
            provider_id=provider_id,
            type=provider_type,
            adapter_kind=_normalize_provider_type(provider_type),
            label=alias,
            enabled=bool(payload.get("enabled", False)),
            base_url=base_url,
            api_key=str(payload.get("api_key") or "").strip() or None,
            alias=alias,
            preferred_model=preferred_model,
            model=preferred_model,
            max_context_window=int(payload.get("max_context_window") or DEFAULT_MAX_CONTEXT_WINDOW),
            timeout_sec=float(payload.get("timeout_sec") or DEFAULT_TIMEOUT_SEC),
            connect_timeout_sec=payload.get("connect_timeout_sec"),
            write_timeout_sec=payload.get("write_timeout_sec"),
            first_token_timeout_sec=payload.get("first_token_timeout_sec"),
            stream_idle_timeout_sec=payload.get("stream_idle_timeout_sec"),
            request_total_timeout_sec=payload.get("request_total_timeout_sec"),
            retry_backoff_schedule_sec=[float(item) for item in list(payload.get("retry_backoff_schedule_sec") or [])],
            reasoning_effort=_normalize_reasoning_effort(payload.get("reasoning_effort")),
            command_path=(str(payload.get("command_path") or "").strip() or None),
            capability_tags=list(payload.get("capability_tags") or DEFAULT_PROVIDER_CAPABILITY_TAGS),
            cost_tier=payload.get("cost_tier") or RuntimeProviderCostTier.STANDARD,
            participation_policy=(
                payload.get("participation_policy") or RuntimeProviderParticipationPolicy.ALWAYS_ALLOWED
            ),
            fallback_provider_ids=list(payload.get("fallback_provider_ids") or []),
        )
    return provider.model_copy(
        update={
            "adapter_kind": _normalize_provider_type(provider.type),
            "alias": _derive_alias(str(provider.base_url or ""), provider.alias),
            "label": _derive_alias(str(provider.base_url or ""), provider.alias),
            "model": provider.preferred_model,
            "max_context_window": provider.max_context_window or DEFAULT_MAX_CONTEXT_WINDOW,
            "timeout_sec": provider.timeout_sec or DEFAULT_TIMEOUT_SEC,
            "connect_timeout_sec": provider.connect_timeout_sec,
            "write_timeout_sec": provider.write_timeout_sec,
            "first_token_timeout_sec": provider.first_token_timeout_sec,
            "stream_idle_timeout_sec": provider.stream_idle_timeout_sec,
            "request_total_timeout_sec": provider.request_total_timeout_sec,
            "retry_backoff_schedule_sec": list(
                provider.retry_backoff_schedule_sec or DEFAULT_RETRY_BACKOFF_SCHEDULE_SEC
            ),
            "reasoning_effort": _normalize_reasoning_effort(provider.reasoning_effort),
            "capability_tags": list(provider.capability_tags or DEFAULT_PROVIDER_CAPABILITY_TAGS),
            "cost_tier": provider.cost_tier or RuntimeProviderCostTier.STANDARD,
            "participation_policy": (
                provider.participation_policy or RuntimeProviderParticipationPolicy.ALWAYS_ALLOWED
            ),
        }
    )


def _normalize_provider_store_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if "provider_model_entries" not in payload:
        return _empty_runtime_provider_config().model_dump(mode="json")

    providers = [_normalize_provider_entry(item).model_dump(mode="json") for item in payload.get("providers", [])]
    provider_model_entries = []
    for raw_entry in payload.get("provider_model_entries", []) or []:
        if not isinstance(raw_entry, dict):
            continue
        provider_id = str(raw_entry.get("provider_id") or "").strip()
        model_name = str(raw_entry.get("model_name") or "").strip()
        if not provider_id or not model_name:
            continue
        provider_model_entries.append(
            RuntimeProviderModelEntry(
                entry_ref=build_provider_model_entry_ref(provider_id, model_name),
                provider_id=provider_id,
                model_name=model_name,
            ).model_dump(mode="json")
        )
    role_bindings = [
        RuntimeProviderRoleBinding.model_validate(item).model_dump(mode="json")
        for item in payload.get("role_bindings", []) or []
    ]
    default_provider_id = str(payload.get("default_provider_id") or "").strip() or None
    if default_provider_id is None:
        default_provider_id = _derive_default_provider_id_from_bindings(
            [RuntimeProviderRoleBinding.model_validate(item) for item in role_bindings],
            [RuntimeProviderModelEntry.model_validate(item) for item in provider_model_entries],
        )
    return {
        "default_provider_id": default_provider_id,
        "providers": providers,
        "provider_model_entries": provider_model_entries,
        "role_bindings": role_bindings,
    }


def build_runtime_provider_store() -> RuntimeProviderConfigStore:
    return RuntimeProviderConfigStore(get_settings().runtime_provider_config_path)


def resolve_runtime_provider_config(
    store: RuntimeProviderConfigStore | None = None,
) -> RuntimeProviderStoredConfig:
    resolved_store = store or build_runtime_provider_store()
    saved = resolved_store.load_saved_config()
    if saved is not None:
        return saved
    return _build_env_backed_provider_config()


def _derive_default_provider_id_from_bindings(
    role_bindings: list[RuntimeProviderRoleBinding],
    provider_model_entries: list[RuntimeProviderModelEntry],
) -> str | None:
    binding = next((item for item in role_bindings if item.target_ref == ROLE_BINDING_CEO_SHADOW), None)
    if binding is None or not binding.provider_model_entry_refs:
        return None
    first_ref = binding.provider_model_entry_refs[0]
    entry = next((item for item in provider_model_entries if item.entry_ref == first_ref), None)
    return entry.provider_id if entry is not None else None


def find_provider_entry(
    config: RuntimeProviderStoredConfig,
    provider_id: str | None,
) -> RuntimeProviderConfigEntry | None:
    normalized = str(provider_id or "").strip()
    if not normalized:
        return None
    for provider in config.providers:
        if provider.provider_id == normalized:
            return _normalize_provider_entry(provider)
    return None


def find_provider_model_entry(
    config: RuntimeProviderStoredConfig,
    entry_ref: str | None,
) -> RuntimeProviderModelEntry | None:
    normalized = str(entry_ref or "").strip()
    if not normalized:
        return None
    for entry in config.provider_model_entries:
        if entry.entry_ref == normalized:
            return entry
    return None


def provider_meets_target_capability_floor(provider: RuntimeProviderConfigEntry, target_ref: str) -> bool:
    capability_values = {tag.value for tag in provider.capability_tags}
    if not capability_values:
        return True
    if target_ref.endswith("checker_primary") or "checker" in target_ref:
        return "review" in capability_values
    if target_ref == ROLE_BINDING_CEO_SHADOW or "governance" in target_ref or "scope" in target_ref:
        return "planning" in capability_values and "structured_output" in capability_values
    return "implementation" in capability_values and "structured_output" in capability_values


def provider_is_configured(provider: RuntimeProviderConfigEntry) -> bool:
    normalized_provider = _normalize_provider_entry(provider)
    if normalized_provider.adapter_kind == RuntimeProviderAdapterKind.CLAUDE_CODE_CLI:
        return bool(
            normalized_provider.command_path
            and (normalized_provider.preferred_model or normalized_provider.model)
        )
    return bool(
        normalized_provider.base_url
        and normalized_provider.api_key
        and (normalized_provider.preferred_model or normalized_provider.model)
    )


def runtime_provider_health_details(
    provider: RuntimeProviderConfigEntry,
    repository: ControlPlaneRepository,
) -> tuple[str, str]:
    normalized_provider = _normalize_provider_entry(provider)
    provider_label = _provider_label(normalized_provider)
    if not normalized_provider.enabled:
        return ("DISABLED", f"{provider_label} is disabled.")
    if not provider_is_configured(normalized_provider):
        return ("INCOMPLETE", f"{provider_label} configuration is incomplete.")
    if repository.has_open_circuit_breaker_for_provider(normalized_provider.provider_id):
        return ("PAUSED", f"{provider_label} is paused by an open provider incident.")
    if normalized_provider.adapter_kind == RuntimeProviderAdapterKind.CLAUDE_CODE_CLI:
        return ("HEALTHY", f"{provider_label} is ready with Claude Code CLI.")
    if normalized_provider.type == RuntimeProviderType.OPENAI_RESPONSES_STREAM:
        return ("HEALTHY", f"{provider_label} is ready with streaming Responses.")
    return ("HEALTHY", f"{provider_label} is ready with non-streaming Responses.")


def provider_effective_mode(
    provider: RuntimeProviderConfigEntry,
    repository: ControlPlaneRepository,
) -> tuple[str, str]:
    health_status, health_reason = runtime_provider_health_details(provider, repository)
    mode_prefix = "CLAUDE_CODE_CLI"
    if provider.adapter_kind != RuntimeProviderAdapterKind.CLAUDE_CODE_CLI:
        mode_prefix = (
            "OPENAI_RESPONSES_STREAM"
            if provider.type == RuntimeProviderType.OPENAI_RESPONSES_STREAM
            else "OPENAI_RESPONSES_NON_STREAM"
        )
    if health_status == "DISABLED":
        return ("PROVIDER_REQUIRED_UNAVAILABLE", health_reason)
    if health_status == "INCOMPLETE":
        return (f"{mode_prefix}_INCOMPLETE", health_reason)
    if health_status == "PAUSED":
        return (f"{mode_prefix}_PAUSED", health_reason)
    return (f"{mode_prefix}_LIVE", health_reason)


def runtime_provider_effective_mode(
    config: RuntimeProviderStoredConfig,
    repository: ControlPlaneRepository,
) -> tuple[str, str]:
    selection = resolve_provider_selection(
        config,
        target_ref=ROLE_BINDING_CEO_SHADOW,
        employee_provider_id=None,
    )
    if selection is None:
        return ("PROVIDER_REQUIRED_UNAVAILABLE", "No live provider is configured for runtime execution.")
    return provider_effective_mode(selection.provider, repository)


def runtime_provider_health_summary(
    config: RuntimeProviderStoredConfig,
    repository: ControlPlaneRepository,
) -> str:
    effective_mode, _ = runtime_provider_effective_mode(config, repository)
    if effective_mode == "PROVIDER_REQUIRED_UNAVAILABLE":
        return "UNAVAILABLE"
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


def _binding_target_ref_candidates(target_ref: str) -> tuple[str, ...]:
    normalized_target_ref = str(target_ref or "").strip()
    if not normalized_target_ref:
        return ()
    candidates = [normalized_target_ref]
    for legacy_target_ref in legacy_target_refs_for_execution_target(normalized_target_ref):
        if legacy_target_ref not in candidates:
            candidates.append(legacy_target_ref)
    return tuple(candidates)


def _get_binding(config: RuntimeProviderStoredConfig, target_ref: str) -> RuntimeProviderRoleBinding | None:
    for binding in config.role_bindings:
        if binding.target_ref == target_ref:
            return binding
    return None


def _selection_from_entry(
    config: RuntimeProviderStoredConfig,
    *,
    entry_ref: str,
    binding_target_ref: str | None,
    selection_reason: str,
    max_context_window_override: int | None = None,
    reasoning_effort_override: RuntimeProviderReasoningEffort | None = None,
) -> RuntimeProviderSelection | None:
    entry = find_provider_model_entry(config, entry_ref)
    if entry is None:
        return None
    provider = find_provider_entry(config, entry.provider_id)
    if provider is None or not provider.enabled:
        return None
    actual_model = entry.model_name
    return RuntimeProviderSelection(
        provider=provider,
        provider_model_entry_ref=entry.entry_ref,
        preferred_provider_id=provider.provider_id,
        preferred_model=actual_model,
        actual_model=actual_model,
        binding_target_ref=binding_target_ref,
        selection_reason=selection_reason,
        policy_reason=None,
        effective_max_context_window=max_context_window_override or provider.max_context_window,
        effective_reasoning_effort=reasoning_effort_override or provider.reasoning_effort,
    )


def _selection_from_binding(
    config: RuntimeProviderStoredConfig,
    *,
    binding: RuntimeProviderRoleBinding,
    binding_target_ref: str,
    selection_reason: str,
) -> RuntimeProviderSelection | None:
    selections = _selections_from_binding(
        config,
        binding=binding,
        binding_target_ref=binding_target_ref,
        selection_reason=selection_reason,
    )
    return selections[0] if selections else None


def _selections_from_binding(
    config: RuntimeProviderStoredConfig,
    *,
    binding: RuntimeProviderRoleBinding,
    binding_target_ref: str,
    selection_reason: str,
) -> list[RuntimeProviderSelection]:
    if not binding.provider_model_entry_refs:
        return []
    selections: list[RuntimeProviderSelection] = []
    for entry_ref in binding.provider_model_entry_refs:
        selection = _selection_from_entry(
            config,
            entry_ref=entry_ref,
            binding_target_ref=binding_target_ref,
            selection_reason=selection_reason,
            max_context_window_override=binding.max_context_window_override,
            reasoning_effort_override=binding.reasoning_effort_override,
        )
        if selection is not None:
            selections.append(selection)
    return selections


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
        preferred_model = str(runtime_preference.get("preferred_model") or "").strip() or None
        return RuntimeSelectionPreference(
            preferred_provider_id=preferred_provider_id,
            preferred_model=preferred_model,
        )
    return None


def resolve_provider_selection(
    config: RuntimeProviderStoredConfig,
    *,
    target_ref: str,
    employee_provider_id: str | None,
    runtime_preference: RuntimeSelectionPreference | dict[str, Any] | None = None,
) -> RuntimeProviderSelection | None:
    normalized_preference = _normalize_runtime_preference(runtime_preference)
    if normalized_preference is not None:
        preferred_provider = find_provider_entry(config, normalized_preference.preferred_provider_id)
        if preferred_provider is None or not preferred_provider.enabled:
            return None
        preferred_model = normalized_preference.preferred_model or preferred_provider.preferred_model
        if not preferred_model:
            return None
        return RuntimeProviderSelection(
            provider=preferred_provider,
            provider_model_entry_ref=build_provider_model_entry_ref(
                preferred_provider.provider_id,
                preferred_model,
            ),
            preferred_provider_id=preferred_provider.provider_id,
            preferred_model=preferred_model,
            actual_model=preferred_model,
            binding_target_ref=target_ref,
            selection_reason="ticket_runtime_preference",
            policy_reason=None,
            effective_max_context_window=preferred_provider.max_context_window,
            effective_reasoning_effort=preferred_provider.reasoning_effort,
        )

    for candidate_ref in _binding_target_ref_candidates(target_ref):
        binding = _get_binding(config, candidate_ref)
        if binding is None:
            continue
        selection = _selection_from_binding(
            config,
            binding=binding,
            binding_target_ref=candidate_ref,
            selection_reason="role_binding",
        )
        if selection is not None:
            return selection
        break

    ceo_binding = _get_binding(config, ROLE_BINDING_CEO_SHADOW)
    if ceo_binding is not None:
        selection = _selection_from_binding(
            config,
            binding=ceo_binding,
            binding_target_ref=ROLE_BINDING_CEO_SHADOW,
            selection_reason="ceo_binding_inheritance",
        )
        if selection is not None:
            return selection

    employee_provider = find_provider_entry(config, employee_provider_id)
    if employee_provider is not None and employee_provider.enabled and employee_provider.preferred_model:
        return RuntimeProviderSelection(
            provider=employee_provider,
            provider_model_entry_ref=build_provider_model_entry_ref(
                employee_provider.provider_id,
                employee_provider.preferred_model,
            ),
            preferred_provider_id=employee_provider.provider_id,
            preferred_model=employee_provider.preferred_model,
            actual_model=employee_provider.preferred_model,
            binding_target_ref=None,
            selection_reason="employee_provider",
            policy_reason=None,
            effective_max_context_window=employee_provider.max_context_window,
            effective_reasoning_effort=employee_provider.reasoning_effort,
        )
    default_provider = find_provider_entry(config, config.default_provider_id)
    if default_provider is not None and default_provider.enabled and (default_provider.preferred_model or default_provider.model):
        model_name = str(default_provider.preferred_model or default_provider.model or "").strip()
        return RuntimeProviderSelection(
            provider=default_provider,
            provider_model_entry_ref=build_provider_model_entry_ref(default_provider.provider_id, model_name),
            preferred_provider_id=default_provider.provider_id,
            preferred_model=model_name,
            actual_model=model_name,
            binding_target_ref=None,
            selection_reason="default_provider",
            policy_reason=None,
            effective_max_context_window=default_provider.max_context_window,
            effective_reasoning_effort=default_provider.reasoning_effort,
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
    if (
        primary_selection.binding_target_ref is not None
        and primary_selection.selection_reason != "ticket_runtime_preference"
    ):
        binding = _get_binding(config, primary_selection.binding_target_ref)
        if binding is not None:
            binding_selections = _selections_from_binding(
                config,
                binding=binding,
                binding_target_ref=primary_selection.binding_target_ref,
                selection_reason="provider_failover",
            )
            binding_refs = [item.provider_model_entry_ref for item in binding_selections]
            try:
                start_index = binding_refs.index(primary_selection.provider_model_entry_ref) + 1
            except ValueError:
                start_index = 0
            for failover_selection in binding_selections[start_index:]:
                provider_id = failover_selection.provider.provider_id
                if provider_id in attempted_provider_ids:
                    continue
                if not provider_meets_target_capability_floor(failover_selection.provider, target_ref):
                    continue
                health_status, _ = runtime_provider_health_details(failover_selection.provider, repository)
                if health_status != "HEALTHY":
                    continue
                selections.append(failover_selection)
                attempted_provider_ids.add(provider_id)
    for fallback_provider_id in primary_selection.provider.fallback_provider_ids:
        fallback_provider = find_provider_entry(config, fallback_provider_id)
        if fallback_provider is None or fallback_provider.provider_id in attempted_provider_ids:
            continue
        if not fallback_provider.enabled or not provider_meets_target_capability_floor(fallback_provider, target_ref):
            continue
        health_status, _ = runtime_provider_health_details(fallback_provider, repository)
        if health_status != "HEALTHY":
            continue
        model_name = str(fallback_provider.preferred_model or fallback_provider.model or "").strip()
        if not model_name:
            continue
        selections.append(
            RuntimeProviderSelection(
                provider=fallback_provider,
                provider_model_entry_ref=build_provider_model_entry_ref(fallback_provider.provider_id, model_name),
                preferred_provider_id=primary_selection.preferred_provider_id,
                preferred_model=primary_selection.preferred_model,
                actual_model=model_name,
                binding_target_ref=primary_selection.binding_target_ref,
                selection_reason="provider_failover",
                policy_reason=primary_selection.policy_reason,
                effective_max_context_window=fallback_provider.max_context_window,
                effective_reasoning_effort=fallback_provider.reasoning_effort,
            )
        )
        attempted_provider_ids.add(fallback_provider.provider_id)
    return selections


def save_runtime_provider_command(
    store: RuntimeProviderConfigStore,
    payload: RuntimeProviderUpsertCommand,
) -> CommandAckEnvelope:
    providers = [
        _normalize_provider_entry(
            {
                "provider_id": item.provider_id,
                "type": item.type,
                "base_url": item.base_url,
                "api_key": item.api_key,
                "alias": item.alias,
                "preferred_model": item.preferred_model,
                "max_context_window": item.max_context_window or DEFAULT_MAX_CONTEXT_WINDOW,
                "timeout_sec": item.timeout_sec,
                "connect_timeout_sec": item.connect_timeout_sec,
                "write_timeout_sec": item.write_timeout_sec,
                "first_token_timeout_sec": item.first_token_timeout_sec,
                "stream_idle_timeout_sec": item.stream_idle_timeout_sec,
                "request_total_timeout_sec": item.request_total_timeout_sec,
                "retry_backoff_schedule_sec": list(item.retry_backoff_schedule_sec),
                "reasoning_effort": item.reasoning_effort,
                "enabled": item.enabled,
                "fallback_provider_ids": list(item.fallback_provider_ids),
            }
        )
        for item in payload.providers
    ]
    provider_model_entries = [
        RuntimeProviderModelEntry(
            entry_ref=build_provider_model_entry_ref(item.provider_id, item.model_name),
            provider_id=item.provider_id,
            model_name=item.model_name,
        )
        for item in payload.provider_model_entries
    ]
    role_bindings = [
        RuntimeProviderRoleBinding(
            target_ref=item.target_ref,
            provider_model_entry_refs=list(item.provider_model_entry_refs),
            max_context_window_override=item.max_context_window_override,
            reasoning_effort_override=item.reasoning_effort_override,
        )
        for item in payload.role_bindings
    ]
    default_provider_id = _derive_default_provider_id_from_bindings(role_bindings, provider_model_entries)
    store.save_config(
        RuntimeProviderStoredConfig(
            default_provider_id=default_provider_id,
            providers=providers,
            provider_model_entries=provider_model_entries,
            role_bindings=role_bindings,
        )
    )
    causation_provider_id = default_provider_id or "local_deterministic"
    return CommandAckEnvelope(
        command_id=new_prefixed_id("cmd"),
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=now_local(),
        reason=None,
        causation_hint=f"runtime-provider:{causation_provider_id}",
    )
