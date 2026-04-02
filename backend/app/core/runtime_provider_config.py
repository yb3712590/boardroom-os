from __future__ import annotations

import json
from pathlib import Path

from pydantic import Field

from app.contracts.commands import (
    CommandAckEnvelope,
    CommandAckStatus,
    RuntimeProviderMode,
    RuntimeProviderUpsertCommand,
)
from app.config import get_settings
from app.contracts.common import StrictModel
from app.core.ids import new_prefixed_id
from app.core.time import now_local
from app.db.repository import ControlPlaneRepository

OPENAI_COMPAT_PROVIDER_ID = "prov_openai_compat"


class RuntimeProviderStoredConfig(StrictModel):
    mode: RuntimeProviderMode = RuntimeProviderMode.DETERMINISTIC
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    timeout_sec: float = Field(default=30.0, gt=0)
    reasoning_effort: str | None = None


class RuntimeProviderResolvedConfig(StrictModel):
    mode: RuntimeProviderMode
    provider_id: str
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    timeout_sec: float = Field(default=30.0, gt=0)
    reasoning_effort: str | None = None


class RuntimeProviderConfigStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load_saved_config(self) -> RuntimeProviderStoredConfig | None:
        if not self.path.exists():
            return None
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return RuntimeProviderStoredConfig.model_validate(payload)

    def save_config(self, payload: RuntimeProviderStoredConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(payload.model_dump(mode="json"), ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )


def build_runtime_provider_store() -> RuntimeProviderConfigStore:
    return RuntimeProviderConfigStore(get_settings().runtime_provider_config_path)


def resolve_runtime_provider_config(
    store: RuntimeProviderConfigStore | None = None,
) -> RuntimeProviderResolvedConfig:
    settings = get_settings()
    resolved_store = store or build_runtime_provider_store()
    saved = resolved_store.load_saved_config()
    if saved is not None:
        return RuntimeProviderResolvedConfig(
            mode=saved.mode,
            provider_id=OPENAI_COMPAT_PROVIDER_ID,
            base_url=saved.base_url,
            api_key=saved.api_key,
            model=saved.model,
            timeout_sec=saved.timeout_sec,
            reasoning_effort=saved.reasoning_effort,
        )

    env_mode = (
        RuntimeProviderMode.OPENAI_COMPAT
        if any(
            (
                settings.provider_openai_compat_base_url,
                settings.provider_openai_compat_api_key,
                settings.provider_openai_compat_model,
            )
        )
        else RuntimeProviderMode.DETERMINISTIC
    )
    return RuntimeProviderResolvedConfig(
        mode=env_mode,
        provider_id=OPENAI_COMPAT_PROVIDER_ID,
        base_url=settings.provider_openai_compat_base_url,
        api_key=settings.provider_openai_compat_api_key,
        model=settings.provider_openai_compat_model,
        timeout_sec=settings.provider_openai_compat_timeout_sec,
        reasoning_effort=settings.provider_openai_compat_reasoning_effort,
    )


def runtime_provider_effective_mode(
    config: RuntimeProviderResolvedConfig,
    repository: ControlPlaneRepository,
) -> tuple[str, str]:
    if config.mode != RuntimeProviderMode.OPENAI_COMPAT:
        return ("LOCAL_DETERMINISTIC", "Runtime is using the local deterministic path.")
    if not all((config.base_url, config.api_key, config.model)):
        return (
            "OPENAI_COMPAT_INCOMPLETE",
            "OpenAI-compatible provider mode is selected but configuration is incomplete.",
        )
    open_incidents = repository.list_open_provider_incidents()
    if open_incidents:
        pause_reason = str((open_incidents[0].get("payload") or {}).get("pause_reason") or "provider pause")
        return (
            "OPENAI_COMPAT_PAUSED",
            f"OpenAI-compatible provider execution is paused because of {pause_reason}.",
        )
    return (
        "OPENAI_COMPAT_LIVE",
        "Runtime is using the saved OpenAI-compatible provider config.",
    )


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


def save_runtime_provider_command(
    store: RuntimeProviderConfigStore,
    payload: RuntimeProviderUpsertCommand,
) -> CommandAckEnvelope:
    store.save_config(
        RuntimeProviderStoredConfig(
            mode=payload.mode,
            base_url=payload.base_url if payload.mode == RuntimeProviderMode.OPENAI_COMPAT else None,
            api_key=payload.api_key if payload.mode == RuntimeProviderMode.OPENAI_COMPAT else None,
            model=payload.model if payload.mode == RuntimeProviderMode.OPENAI_COMPAT else None,
            timeout_sec=payload.timeout_sec,
            reasoning_effort=(
                payload.reasoning_effort if payload.mode == RuntimeProviderMode.OPENAI_COMPAT else None
            ),
        )
    )
    return CommandAckEnvelope(
        command_id=new_prefixed_id("cmd"),
        idempotency_key=payload.idempotency_key,
        status=CommandAckStatus.ACCEPTED,
        received_at=now_local(),
        reason=None,
        causation_hint=f"runtime-provider:{OPENAI_COMPAT_PROVIDER_ID}",
    )
