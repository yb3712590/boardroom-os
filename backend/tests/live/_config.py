from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_ROLE_TARGETS: tuple[str, ...] = (
    "ceo_shadow",
    "role_profile:ui_designer_primary",
    "role_profile:frontend_engineer_primary",
    "role_profile:checker_primary",
    "role_profile:backend_engineer_primary",
    "role_profile:database_engineer_primary",
    "role_profile:platform_sre_primary",
    "role_profile:cto_primary",
)
DEFAULT_REQUIRED_CAPABILITIES: tuple[str, ...] = (
    "books",
    "title",
    "author",
    "IN_LIBRARY",
    "CHECKED_OUT",
    "add",
    "check out",
    "return",
    "remove",
    "terminal",
    "console",
)


def _require_str(value: Any, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"`{field_name}` must not be empty.")
    return normalized


def _require_list_of_str(value: Any, *, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"`{field_name}` must be a TOML array.")
    return tuple(str(item).strip() for item in value if str(item).strip())


def _contains_forbidden_key(value: Any, *, forbidden_key: str) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key) == forbidden_key:
                return True
            if _contains_forbidden_key(child, forbidden_key=forbidden_key):
                return True
    if isinstance(value, list):
        return any(_contains_forbidden_key(item, forbidden_key=forbidden_key) for item in value)
    return False


@dataclass(frozen=True)
class LiveScenarioSection:
    slug: str
    description: str
    goal: str
    workflow_profile: str
    force_requirement_elicitation: bool
    budget_cap: int
    constraints: tuple[str, ...]


@dataclass(frozen=True)
class LiveRuntimeConfig:
    seed: int
    max_ticks: int
    timeout_sec: int


@dataclass(frozen=True)
class LiveProviderConfig:
    provider_id: str
    base_url: str
    api_key: str
    preferred_model: str
    max_context_window: int | None
    reasoning_effort: str | None
    connect_timeout_sec: float
    write_timeout_sec: float
    first_token_timeout_sec: float
    stream_idle_timeout_sec: float
    fallback_provider_ids: tuple[str, ...] = ()
    default_role_targets: tuple[str, ...] = DEFAULT_ROLE_TARGETS
    architect_reasoning_effort: str = "xhigh"
    default_role_reasoning_effort: str = "high"

    @property
    def compat_timeout_sec(self) -> float:
        return float(max(self.first_token_timeout_sec, self.stream_idle_timeout_sec))


@dataclass(frozen=True)
class LiveAssertionConfig:
    profile: str
    expected_provider_id: str | None = None
    expected_model: str = "gpt-5.4"
    architect_reasoning_effort: str = "xhigh"
    default_reasoning_effort: str = "high"
    required_capabilities: tuple[str, ...] = DEFAULT_REQUIRED_CAPABILITIES


@dataclass(frozen=True)
class LiveScenarioConfig:
    config_path: Path
    scenario: LiveScenarioSection
    runtime: LiveRuntimeConfig
    provider: LiveProviderConfig
    assertions: LiveAssertionConfig

    def build_project_init_payload(self) -> dict[str, Any]:
        return {
            "north_star_goal": self.scenario.goal,
            "hard_constraints": list(self.scenario.constraints),
            "budget_cap": self.scenario.budget_cap,
            "deadline_at": None,
            "workflow_profile": self.scenario.workflow_profile,
            "force_requirement_elicitation": self.scenario.force_requirement_elicitation,
        }

    def build_runtime_provider_payload(self) -> dict[str, Any]:
        entry_ref = f"{self.provider.provider_id}::{self.provider.preferred_model}"
        role_bindings = [
            {
                "target_ref": target_ref,
                "provider_model_entry_refs": [entry_ref],
                "max_context_window_override": self.provider.max_context_window,
                "reasoning_effort_override": self.provider.default_role_reasoning_effort,
            }
            for target_ref in self.provider.default_role_targets
        ]
        role_bindings.append(
            {
                "target_ref": "role_profile:architect_primary",
                "provider_model_entry_refs": [entry_ref],
                "max_context_window_override": self.provider.max_context_window,
                "reasoning_effort_override": self.provider.architect_reasoning_effort,
            }
        )
        compat_timeout_sec = self.provider.compat_timeout_sec
        return {
            "providers": [
                {
                    "provider_id": self.provider.provider_id,
                    "type": "openai_responses_stream",
                    "enabled": True,
                    "base_url": self.provider.base_url,
                    "api_key": self.provider.api_key,
                    "alias": self.scenario.slug,
                    "preferred_model": self.provider.preferred_model,
                    "max_context_window": self.provider.max_context_window,
                    "reasoning_effort": self.provider.reasoning_effort,
                    "timeout_sec": compat_timeout_sec,
                    "connect_timeout_sec": self.provider.connect_timeout_sec,
                    "write_timeout_sec": self.provider.write_timeout_sec,
                    "first_token_timeout_sec": self.provider.first_token_timeout_sec,
                    "stream_idle_timeout_sec": self.provider.stream_idle_timeout_sec,
                    "fallback_provider_ids": list(self.provider.fallback_provider_ids),
                }
            ],
            "provider_model_entries": [
                {
                    "provider_id": self.provider.provider_id,
                    "model_name": self.provider.preferred_model,
                }
            ],
            "role_bindings": role_bindings,
            "idempotency_key": f"runtime-provider-upsert:{self.scenario.slug}",
        }


def load_live_scenario_config(config_path: Path) -> LiveScenarioConfig:
    payload = tomllib.loads(config_path.read_text(encoding="utf-8"))

    forbidden_top_level = {"seeds", "stages"}
    offending = sorted(forbidden_top_level.intersection(payload))
    if offending:
        raise ValueError(
            "Live scenario config does not accept legacy stage fields: "
            + ", ".join(offending)
        )
    if _contains_forbidden_key(payload, forbidden_key="workflow_id"):
        raise ValueError("Live scenario config does not accept legacy `workflow_id` fields.")

    scenario_payload = dict(payload.get("scenario") or {})
    runtime_payload = dict(payload.get("runtime") or {})
    provider_payload = dict(payload.get("provider") or {})
    assertion_payload = dict(payload.get("assertions") or {})

    provider_id = _require_str(provider_payload.get("provider_id"), field_name="provider.provider_id")
    preferred_model = _require_str(
        provider_payload.get("preferred_model"),
        field_name="provider.preferred_model",
    )

    return LiveScenarioConfig(
        config_path=Path(config_path),
        scenario=LiveScenarioSection(
            slug=_require_str(scenario_payload.get("slug"), field_name="scenario.slug"),
            description=_require_str(
                scenario_payload.get("description"),
                field_name="scenario.description",
            ),
            goal=_require_str(scenario_payload.get("goal"), field_name="scenario.goal"),
            workflow_profile=_require_str(
                scenario_payload.get("workflow_profile"),
                field_name="scenario.workflow_profile",
            ),
            force_requirement_elicitation=bool(
                scenario_payload.get("force_requirement_elicitation", False)
            ),
            budget_cap=int(scenario_payload.get("budget_cap", 1_500_000)),
            constraints=_require_list_of_str(
                scenario_payload.get("constraints"),
                field_name="scenario.constraints",
            ),
        ),
        runtime=LiveRuntimeConfig(
            seed=int(runtime_payload.get("seed", 17)),
            max_ticks=int(runtime_payload.get("max_ticks", 180)),
            timeout_sec=int(runtime_payload.get("timeout_sec", 7200)),
        ),
        provider=LiveProviderConfig(
            provider_id=provider_id,
            base_url=_require_str(provider_payload.get("base_url"), field_name="provider.base_url"),
            api_key=_require_str(provider_payload.get("api_key"), field_name="provider.api_key"),
            preferred_model=preferred_model,
            max_context_window=(
                int(provider_payload["max_context_window"])
                if provider_payload.get("max_context_window") is not None
                else None
            ),
            reasoning_effort=str(provider_payload.get("reasoning_effort") or "").strip() or None,
            connect_timeout_sec=float(provider_payload.get("connect_timeout_sec", 10)),
            write_timeout_sec=float(provider_payload.get("write_timeout_sec", 20)),
            first_token_timeout_sec=float(provider_payload.get("first_token_timeout_sec", 300)),
            stream_idle_timeout_sec=float(provider_payload.get("stream_idle_timeout_sec", 300)),
            fallback_provider_ids=_require_list_of_str(
                provider_payload.get("fallback_provider_ids", []),
                field_name="provider.fallback_provider_ids",
            ),
        ),
        assertions=LiveAssertionConfig(
            profile=_require_str(assertion_payload.get("profile"), field_name="assertions.profile"),
            expected_provider_id=provider_id,
            expected_model=preferred_model,
            architect_reasoning_effort="xhigh",
            default_reasoning_effort=str(provider_payload.get("reasoning_effort") or "high").strip() or "high",
            required_capabilities=DEFAULT_REQUIRED_CAPABILITIES,
        ),
    )
