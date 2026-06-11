from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
from typing import Any, Literal, Self

from atomic_agent.providers.openai_compatible import OpenAICompatibleProviderOptions
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
import yaml


class BoardroomConfigError(ValueError):
    pass


_STALE_OPENAI_PREFIX = "BOARDROOM_OPENAI_"
_STALE_ATOMIC_BUDGET_PREFIX = "BOARDROOM_ATOMIC_"
_ALLOWED_ATOMIC_ENV_KEYS = {"BOARDROOM_ATOMIC_AGENT_PATH"}


@dataclass(frozen=True)
class BoardroomConfigPaths:
    runtime_config: Path
    providers_config: Path
    roles_config: Path


@dataclass(frozen=True)
class BoardroomConfigHashes:
    runtime_config_hash: str
    providers_config_hash: str
    roles_config_hash: str


class AtomicExecutionModeConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    implementation_executor: Literal["atomic_agent"]
    reject_provider_executor_for_implementation: bool

    @model_validator(mode="before")
    @classmethod
    def _map_executor_error(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("implementation_executor") != "atomic_agent":
            raise ValueError("implementation_executor must be atomic_agent")
        return data

    @model_validator(mode="after")
    def _require_atomic_executor(self) -> Self:
        if self.implementation_executor != "atomic_agent":
            raise ValueError("implementation_executor must be atomic_agent")
        if self.reject_provider_executor_for_implementation is not True:
            raise ValueError("reject_provider_executor_for_implementation must be true")
        return self


class AgentExecutionBudgetConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_steps: int = Field(gt=0)
    max_parse_failures: int = Field(ge=0)
    max_observation_chars: int = Field(gt=0)
    max_wall_seconds: float = Field(gt=0)
    max_actions_per_turn: int = Field(gt=0)


class BudgetCapsConfig(AgentExecutionBudgetConfig):
    pass


class AtomicRequiredOutputCheckpointConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_auto_runs: int = Field(gt=0)


class AtomicCheckpointConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    required_output: AtomicRequiredOutputCheckpointConfig


class AtomicDependencyConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    atomic_agent_path_env: str
    default_atomic_agent_path: str
    contract_lock_ref: str
    require_contract_hash_match: bool

    @field_validator("atomic_agent_path_env", "default_atomic_agent_path", "contract_lock_ref")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("atomic dependency text fields must not be empty")
        return normalized


class AtomicExecutionPolicyConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    wall_time_seconds: float = Field(gt=0)
    retry_on_provider_timeout: bool
    retry_on_runtime_crash: bool
    max_retries: int = Field(ge=0)
    interrupt_grace_period_seconds: float = Field(gt=0)
    retry_requires_no_workspace_mutation: bool

    @model_validator(mode="after")
    def _reject_provider_timeout_retry_without_policy(self) -> Self:
        if self.retry_on_provider_timeout:
            raise ValueError("retry_on_provider_timeout requires explicit idempotency policy")
        return self


class AtomicConcurrencyConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Literal["serial_per_workspace"]
    workspace_lock_root: str
    require_run_scoped_event_artifact_roots: bool

    @field_validator("workspace_lock_root")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("workspace_lock_root must not be empty")
        return normalized


class AtomicFilesystemConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    default_read_limit: int = Field(gt=0)
    max_read_limit: int = Field(gt=0)
    default_max_entries: int = Field(gt=0)
    max_entries_limit: int = Field(gt=0)
    default_max_matches: int = Field(gt=0)
    max_matches_limit: int = Field(gt=0)
    allow_apply_patch: bool = False

    @model_validator(mode="after")
    def _validate_limits(self) -> Self:
        if self.default_read_limit > self.max_read_limit:
            raise ValueError("default_read_limit must not exceed max_read_limit")
        if self.default_max_entries > self.max_entries_limit:
            raise ValueError("default_max_entries must not exceed max_entries_limit")
        if self.default_max_matches > self.max_matches_limit:
            raise ValueError("default_max_matches must not exceed max_matches_limit")
        return self


class AtomicCommandConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    default_timeout_seconds: float = Field(gt=0)
    max_timeout_seconds: float = Field(gt=0)
    max_output_bytes: int = Field(gt=0)

    @model_validator(mode="after")
    def _validate_timeouts(self) -> Self:
        if self.default_timeout_seconds > self.max_timeout_seconds:
            raise ValueError("default_timeout_seconds must not exceed max_timeout_seconds")
        return self


class NetworkAllowRuleConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: str
    scheme: Literal["http", "https"]
    host: str
    port: int | None = Field(default=None, ge=1, le=65535)
    path_prefix: str

    @field_validator("rule_id", "host", "path_prefix")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("network allow rule text fields must not be empty")
        return normalized


class AtomicNetworkConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    default: Literal["deny"]
    allow_rules: tuple[NetworkAllowRuleConfig, ...] = ()


class AtomicAgentRuntimeConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    package_name: str
    import_name: str
    runtime_port_contract_ref: str
    event_stream_root: str
    artifact_root: str
    run_id_prefix: str
    dependency: AtomicDependencyConfig
    execution_policy: AtomicExecutionPolicyConfig
    concurrency: AtomicConcurrencyConfig
    default_tools: tuple[str, ...]
    required_tools: tuple[str, ...]
    tool_permission_map: dict[str, tuple[str, ...]]
    budget_profiles: dict[str, AgentExecutionBudgetConfig]
    budget_caps: BudgetCapsConfig
    checkpoints: AtomicCheckpointConfig
    filesystem: AtomicFilesystemConfig
    commands: AtomicCommandConfig
    network: AtomicNetworkConfig

    @field_validator("package_name", "import_name", "runtime_port_contract_ref", "event_stream_root", "artifact_root", "run_id_prefix")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("atomic_agent text fields must not be empty")
        return normalized

    @field_validator("default_tools", "required_tools")
    @classmethod
    def _reject_empty_tools(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("atomic_agent tools must not be empty")
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("atomic_agent tools must not contain empty values")
        return normalized

    @model_validator(mode="after")
    def _validate_tools_and_budgets(self) -> Self:
        if "submit_result" not in self.default_tools:
            raise ValueError("atomic_agent.default_tools must include submit_result")
        for tool in self.required_tools:
            if tool not in self.default_tools:
                raise ValueError("atomic_agent.required_tools must be present in default_tools")
        if not self.budget_profiles:
            raise ValueError("atomic_agent.budget_profiles must not be empty")
        return self


class BoardroomRuntimeConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1]
    runtime_id: str
    execution: AtomicExecutionModeConfig
    atomic_agent: AtomicAgentRuntimeConfig


class ProviderProfileConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_profile_id: str
    provider_type: Literal["openai_compatible"]
    provider_label: str | None = None
    base_url: str
    api_key_env: str
    model: str
    context_window_tokens: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)
    stream_idle_timeout_seconds: float = Field(gt=0)
    total_timeout_seconds: float = Field(gt=0)
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh"] | None = None
    temperature: float | None = None
    top_p: float | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    seed: int | None = None
    stop: tuple[str, ...] | None = None
    response_format: dict[str, Any] | None = None
    stream_options: dict[str, Any] | None = None
    service_tier: str | None = None
    user: str | None = None

    @field_validator("provider_profile_id", "base_url", "api_key_env", "model")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("provider text fields must not be empty")
        return normalized

    @model_validator(mode="before")
    @classmethod
    def _map_provider_type_error(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("provider_type") != "openai_compatible":
            raise ValueError("provider_type must be openai_compatible")
        return data

    @model_validator(mode="after")
    def _validate_provider(self) -> Self:
        if self.stream_idle_timeout_seconds > self.total_timeout_seconds:
            raise ValueError("stream_idle_timeout_seconds must not exceed total_timeout_seconds")
        return self

    def to_openai_options(self, *, api_key: str) -> OpenAICompatibleProviderOptions:
        if not api_key.strip():
            raise ValueError("provider api key env is required")
        return OpenAICompatibleProviderOptions(
            base_url=self.base_url,
            api_key=api_key,
            model=self.model,
            context_window_tokens=self.context_window_tokens,
            max_output_tokens=self.max_output_tokens,
            stream_idle_timeout_seconds=self.stream_idle_timeout_seconds,
            total_timeout_seconds=self.total_timeout_seconds,
            temperature=self.temperature,
            provider_label=self.provider_label,
            reasoning_effort=self.reasoning_effort,
            top_p=self.top_p,
            presence_penalty=self.presence_penalty,
            frequency_penalty=self.frequency_penalty,
            seed=self.seed,
            stop=self.stop,
            response_format=self.response_format,
            stream_options=self.stream_options,
            service_tier=self.service_tier,
            user=self.user,
        )


class BoardroomProvidersConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1]
    providers: tuple[ProviderProfileConfig, ...]

    @model_validator(mode="after")
    def _require_unique_providers(self) -> Self:
        if not self.providers:
            raise ValueError("providers must not be empty")
        seen: set[str] = set()
        for provider in self.providers:
            if provider.provider_profile_id in seen:
                raise ValueError("provider_profile_id values must be unique")
            seen.add(provider.provider_profile_id)
        return self


class RoleSlotConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    seat_ref: str
    role_profile_ref: str
    role_category: str
    model_execution_profile_id: str
    provider_profile_ref: str
    budget_profile_ref: str
    skill_refs: tuple[str, ...]
    default_tools: tuple[str, ...]
    budgets_override: dict[str, int | float] = Field(default_factory=dict)

    @field_validator("seat_ref", "role_profile_ref", "role_category", "model_execution_profile_id", "provider_profile_ref", "budget_profile_ref")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("role slot text fields must not be empty")
        return normalized

    @field_validator("skill_refs", "default_tools")
    @classmethod
    def _reject_empty_tuple(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("role slot tuples must not be empty")
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("role slot tuples must not contain empty values")
        return normalized


class BoardroomRolesConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1]
    role_slots: tuple[RoleSlotConfig, ...]

    @model_validator(mode="after")
    def _require_unique_seats(self) -> Self:
        if not self.role_slots:
            raise ValueError("role_slots must not be empty")
        seen: set[str] = set()
        for slot in self.role_slots:
            if slot.seat_ref in seen:
                raise ValueError("seat_ref values must be unique")
            seen.add(slot.seat_ref)
        return self


class BoardroomSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    runtime: BoardroomRuntimeConfig
    providers: BoardroomProvidersConfig
    roles: BoardroomRolesConfig
    config_hashes: BoardroomConfigHashes

    @model_validator(mode="after")
    def _validate_cross_refs(self) -> Self:
        provider_ids = {provider.provider_profile_id for provider in self.providers.providers}
        allowed_budget_keys = set(AgentExecutionBudgetConfig.model_fields)
        for slot in self.roles.role_slots:
            if slot.provider_profile_ref not in provider_ids:
                raise ValueError("unknown provider_profile_ref")
            if slot.budget_profile_ref not in self.runtime.atomic_agent.budget_profiles:
                raise ValueError("unknown budget_profile_ref")
            unknown_budget_keys = set(slot.budgets_override) - allowed_budget_keys
            if unknown_budget_keys:
                raise ValueError("unknown budget override keys: " + ", ".join(sorted(unknown_budget_keys)))
            if slot.role_category == "worker" and "submit_result" not in slot.default_tools:
                raise ValueError("worker role slot tools must include submit_result")
            if slot.role_category == "worker" and "run_command" not in slot.default_tools:
                raise ValueError("worker role slot tools must include run_command")
            if slot.role_category == "worker" and not {"write_file", "apply_patch"}.intersection(slot.default_tools):
                raise ValueError("worker role slot tools must include write_file or apply_patch")
        return self

    def provider_by_id(self, provider_profile_id: str) -> ProviderProfileConfig:
        for provider in self.providers.providers:
            if provider.provider_profile_id == provider_profile_id:
                return provider
        raise ValueError("unknown provider_profile_id")

    def role_slot_by_seat(self, seat_ref: str) -> RoleSlotConfig:
        for slot in self.roles.role_slots:
            if slot.seat_ref == seat_ref:
                return slot
        raise ValueError("unknown seat_ref")

    def budgets_for_seat(self, seat_ref: str) -> dict[str, int | float | str]:
        slot = self.role_slot_by_seat(seat_ref)
        profile = self.runtime.atomic_agent.budget_profiles.get(slot.budget_profile_ref)
        if profile is None:
            raise ValueError("unknown budget_profile_ref")
        merged = profile.model_dump()
        merged.update(slot.budgets_override)
        for key, value in merged.items():
            cap = getattr(self.runtime.atomic_agent.budget_caps, key)
            if value > cap:
                raise ValueError(f"resolved budget {key} exceeds budget_caps")
        merged["budget_profile_ref"] = slot.budget_profile_ref
        return merged

    def openai_compatible_options(self, provider_profile_id: str) -> OpenAICompatibleProviderOptions:
        provider = self.provider_by_id(provider_profile_id)
        api_key = os.environ.get(provider.api_key_env, "")
        if not api_key:
            raise ValueError("provider api key env is required")
        return provider.to_openai_options(api_key=api_key)


def load_boardroom_settings(paths: BoardroomConfigPaths, *, env_values: dict[str, str] | None = None) -> BoardroomSettings:
    env_values = env_values or {}
    _reject_stale_env_keys(env_values)
    runtime = _validate_config_model(BoardroomRuntimeConfig, _load_yaml_mapping(paths.runtime_config))
    _load_atomic_agent_contract_lock(runtime.atomic_agent.dependency.contract_lock_ref)
    providers = _validate_config_model(BoardroomProvidersConfig, _load_yaml_mapping(paths.providers_config))
    roles = _validate_config_model(BoardroomRolesConfig, _load_yaml_mapping(paths.roles_config))
    settings = _validate_config_model(
        BoardroomSettings,
        {
            "runtime": runtime,
            "providers": providers,
            "roles": roles,
            "config_hashes": BoardroomConfigHashes(
                runtime_config_hash=_sha256_file(paths.runtime_config),
                providers_config_hash=_sha256_file(paths.providers_config),
                roles_config_hash=_sha256_file(paths.roles_config),
            ),
        },
    )
    for provider in settings.providers.providers:
        if not os.environ.get(provider.api_key_env, ""):
            raise ValueError("provider api key env is required")
    return settings


def resolve_atomic_agent_path(*, default_path: str) -> Path:
    path = Path(os.environ.get("BOARDROOM_ATOMIC_AGENT_PATH", default_path)).expanduser().resolve()
    if ".worktrees" in path.parts:
        raise ValueError("BOARDROOM_ATOMIC_AGENT_PATH must not point at .worktrees")
    if not path.is_dir():
        raise ValueError(f"BOARDROOM_ATOMIC_AGENT_PATH does not exist: {path}")
    return path


def _reject_stale_env_keys(env_values: dict[str, str]) -> None:
    stale = sorted(key for key, value in env_values.items() if key.startswith(_STALE_OPENAI_PREFIX) and value.strip())
    stale.extend(
        sorted(
            key
            for key, value in env_values.items()
            if key.startswith(_STALE_ATOMIC_BUDGET_PREFIX)
            and key not in _ALLOWED_ATOMIC_ENV_KEYS
            and value.strip()
        )
    )
    if stale:
        raise ValueError("stale env execution config keys are not allowed: " + ", ".join(stale))


def _validate_config_model(model_type: type[BaseModel], data: Any) -> Any:
    try:
        return model_type.model_validate(data)
    except ValidationError as exc:
        message = str(exc)
        if "Extra inputs are not permitted" in message:
            raise ValueError(message.replace("Extra inputs are not permitted", "extra inputs are not permitted")) from exc
        raise ValueError(message) from exc


def _load_atomic_agent_contract_lock(contract_lock_ref: str) -> str:
    path = Path(contract_lock_ref)
    if not path.exists():
        raise ValueError(f"atomic-agent contract lock is required: {contract_lock_ref}")
    text = path.read_text(encoding="utf-8")
    if "AgentInvocation" not in text or "AgentRunResult" not in text:
        raise ValueError("atomic-agent contract lock is missing active model fields")
    return text


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"config file is required: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"config file must contain a YAML mapping: {path}")
    return data


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
