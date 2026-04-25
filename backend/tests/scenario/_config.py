from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any


def _ensure_tuple(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    if not isinstance(values, list):
        raise ValueError("Expected a TOML array.")
    return tuple(str(item).strip() for item in values if str(item).strip())


def _ensure_path(value: Any, *, field_name: str) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(f"`{field_name}` must not be empty.")
    return Path(raw)


def _resolve_relative_path(raw_path: Path, *, base_dir: Path) -> Path:
    return raw_path if raw_path.is_absolute() else (base_dir / raw_path)


def _normalize_workflow_token(pattern: str, workflow_id: str) -> str:
    if "wf_{workflow_id}" in pattern and workflow_id.startswith("wf_"):
        return workflow_id.removeprefix("wf_")
    return workflow_id


@dataclass(frozen=True)
class ScenarioInputConfig:
    north_star_goal: str
    hard_constraints: tuple[str, ...]
    read_only_context_refs: tuple[str, ...]
    workflow_profile: str
    force_requirement_elicitation: bool


@dataclass(frozen=True)
class ScenarioRuntimeConfig:
    seed: int
    max_ticks: int
    timeout_sec: int
    maintenance_interval_sec: int
    scheduler_max_dispatches: int
    resume_enabled: bool


@dataclass(frozen=True)
class ScenarioProviderRoleBinding:
    target_ref: str
    provider_model_entry_refs: tuple[str, ...]
    max_context_window_override: int | None = None
    reasoning_effort_override: str | None = None


@dataclass(frozen=True)
class ScenarioProviderConfig:
    provider_id: str
    base_url: str
    api_key: str | None
    api_key_env: str | None
    preferred_model: str
    max_context_window: int | None
    reasoning_effort: str | None
    timeout_sec: float | None
    connect_timeout_sec: float | None
    write_timeout_sec: float | None
    first_token_timeout_sec: float | None
    stream_idle_timeout_sec: float | None
    request_total_timeout_sec: float | None
    retry_backoff_schedule_sec: tuple[float, ...]
    fallback_provider_ids: tuple[str, ...]


@dataclass(frozen=True)
class ScenarioLayoutConfig:
    runtime_db: Path
    events_log: Path
    runtime_blobs_dir: Path
    audit_records_dir: Path
    audit_views_dir: Path
    audit_stage_views_dir: Path
    workspace_dir_pattern: Path
    workspace_metadata_dir: Path
    debug_compile_dir: Path
    debug_logs_dir: Path
    runtime_provider_config: Path
    artifact_uploads_dir: Path
    ticket_context_archive_dir: Path

    def _resolve_pattern(self, pattern: Path, workflow_id: str) -> Path:
        raw_pattern = str(pattern)
        token = _normalize_workflow_token(raw_pattern, workflow_id)
        return Path(raw_pattern.replace("{workflow_id}", token))

    def resolve_workspace_dir(self, scenario_root: Path, workflow_id: str) -> Path:
        return scenario_root / self._resolve_pattern(self.workspace_dir_pattern, workflow_id)

    def resolve_workspace_metadata_dir(self, scenario_root: Path, workflow_id: str) -> Path:
        return scenario_root / self._resolve_pattern(self.workspace_metadata_dir, workflow_id)

    def resolve_project_workspace_root(self, scenario_root: Path) -> Path:
        parts: list[str] = []
        for part in self.workspace_dir_pattern.parts:
            if "{workflow_id}" in part:
                break
            parts.append(part)
        return scenario_root / Path(*parts) if parts else scenario_root


@dataclass(frozen=True)
class ScenarioSeedConfig:
    seed_id: str
    path: Path
    description: str = ""
    workflow_id: str | None = None
    requires_prepared_state: bool = False


@dataclass(frozen=True)
class ScenarioStageSpec:
    stage_id: str
    test_file: str
    seed_ref: str
    start_mode: str
    checkpoint_kind: str
    expected_stage: str | None
    expected_outputs: tuple[str, ...]
    required_schema_refs: tuple[str, ...] = ()
    forbidden_schema_refs: tuple[str, ...] = ()
    required_role_types: tuple[str, ...] = ()
    required_node_ids: tuple[str, ...] = ()
    required_summary_terms: tuple[str, ...] = ()

    def with_updates(self, **changes: Any) -> "ScenarioStageSpec":
        return replace(self, **changes)


@dataclass(frozen=True)
class ScenarioTestConfig:
    config_path: Path
    scenario_id: str
    display_name: str
    input_config: ScenarioInputConfig
    runtime: ScenarioRuntimeConfig
    layout: ScenarioLayoutConfig
    provider: ScenarioProviderConfig
    role_bindings: tuple[ScenarioProviderRoleBinding, ...]
    seeds: dict[str, ScenarioSeedConfig]
    stages: dict[str, ScenarioStageSpec]

    @property
    def config_dir(self) -> Path:
        return self.config_path.parent

    def default_run_root(self) -> Path:
        return self.config_dir / self.scenario_id / "runs"

    def build_project_init_payload(self) -> dict[str, Any]:
        return {
            "north_star_goal": self.input_config.north_star_goal,
            "hard_constraints": list(self.input_config.hard_constraints),
            "budget_cap": 1_500_000,
            "deadline_at": None,
            "workflow_profile": self.input_config.workflow_profile,
            "force_requirement_elicitation": self.input_config.force_requirement_elicitation,
        }

    def build_runtime_provider_payload(self) -> dict[str, Any]:
        entry_ref = f"{self.provider.provider_id}::{self.provider.preferred_model}"
        provider_model_entries: list[dict[str, str]] = []
        seen_entry_refs: set[str] = set()

        def add_provider_model_entry(raw_entry_ref: str) -> None:
            entry_ref_value = str(raw_entry_ref or "").strip()
            if not entry_ref_value or entry_ref_value in seen_entry_refs:
                return
            provider_id, separator, model_name = entry_ref_value.partition("::")
            if not separator or not provider_id.strip() or not model_name.strip():
                return
            seen_entry_refs.add(entry_ref_value)
            provider_model_entries.append(
                {
                    "provider_id": provider_id.strip(),
                    "model_name": model_name.strip(),
                }
            )

        add_provider_model_entry(entry_ref)
        for binding in self.role_bindings:
            for binding_entry_ref in binding.provider_model_entry_refs:
                add_provider_model_entry(binding_entry_ref)

        return {
            "providers": [
                {
                    "provider_id": self.provider.provider_id,
                    "type": "openai_responses_stream",
                    "enabled": True,
                    "base_url": self.provider.base_url,
                    "api_key": self.provider.api_key or "",
                    "alias": self.scenario_id,
                    "preferred_model": self.provider.preferred_model,
                    "max_context_window": self.provider.max_context_window,
                    "timeout_sec": self.provider.timeout_sec,
                    "connect_timeout_sec": self.provider.connect_timeout_sec,
                    "write_timeout_sec": self.provider.write_timeout_sec,
                    "first_token_timeout_sec": self.provider.first_token_timeout_sec,
                    "stream_idle_timeout_sec": self.provider.stream_idle_timeout_sec,
                    "request_total_timeout_sec": self.provider.request_total_timeout_sec,
                    "retry_backoff_schedule_sec": list(self.provider.retry_backoff_schedule_sec),
                    "reasoning_effort": self.provider.reasoning_effort,
                    "fallback_provider_ids": list(self.provider.fallback_provider_ids),
                }
            ],
            "provider_model_entries": provider_model_entries,
            "role_bindings": [
                {
                    "target_ref": binding.target_ref,
                    "provider_model_entry_refs": list(binding.provider_model_entry_refs or (entry_ref,)),
                    "max_context_window_override": binding.max_context_window_override,
                    "reasoning_effort_override": binding.reasoning_effort_override,
                }
                for binding in self.role_bindings
            ],
            "idempotency_key": f"runtime-provider-upsert:{self.scenario_id}",
        }


def _load_provider_config(payload: dict[str, Any]) -> ScenarioProviderConfig:
    api_key = str(payload.get("api_key") or "").strip() or None
    api_key_env = str(payload.get("api_key_env") or "").strip() or None
    if api_key is None and api_key_env is not None:
        api_key = str(os.environ.get(api_key_env) or "").strip() or None
    preferred_model = str(payload.get("preferred_model") or "").strip()
    if not preferred_model:
        raise ValueError("`provider.default.preferred_model` must not be empty.")
    return ScenarioProviderConfig(
        provider_id=str(payload.get("provider_id") or "").strip(),
        base_url=str(payload.get("base_url") or "").strip(),
        api_key=api_key,
        api_key_env=api_key_env,
        preferred_model=preferred_model,
        max_context_window=payload.get("max_context_window"),
        reasoning_effort=str(payload.get("reasoning_effort") or "").strip() or None,
        timeout_sec=payload.get("timeout_sec"),
        connect_timeout_sec=payload.get("connect_timeout_sec"),
        write_timeout_sec=payload.get("write_timeout_sec"),
        first_token_timeout_sec=payload.get("first_token_timeout_sec"),
        stream_idle_timeout_sec=payload.get("stream_idle_timeout_sec"),
        request_total_timeout_sec=payload.get("request_total_timeout_sec"),
        retry_backoff_schedule_sec=tuple(float(item) for item in list(payload.get("retry_backoff_schedule_sec") or [])),
        fallback_provider_ids=_ensure_tuple(payload.get("fallback_provider_ids")),
    )


def load_scenario_test_config(config_path: Path) -> ScenarioTestConfig:
    raw = tomllib.loads(config_path.read_text(encoding="utf-8"))

    scenario_payload = dict(raw.get("scenario") or {})
    input_payload = dict(raw.get("input") or {})
    runtime_payload = dict(raw.get("runtime") or {})
    layout_payload = dict(raw.get("layout") or {})
    provider_payload = dict(((raw.get("provider") or {}).get("default")) or {})
    role_bindings_payload = list(((raw.get("provider") or {}).get("role_bindings")) or [])
    seeds_payload = dict(raw.get("seeds") or {})
    stages_payload = list(raw.get("stages") or [])

    layout = ScenarioLayoutConfig(
        runtime_db=_ensure_path(layout_payload.get("runtime_db"), field_name="layout.runtime_db"),
        events_log=_ensure_path(layout_payload.get("events_log"), field_name="layout.events_log"),
        runtime_blobs_dir=_ensure_path(layout_payload.get("runtime_blobs_dir"), field_name="layout.runtime_blobs_dir"),
        audit_records_dir=_ensure_path(layout_payload.get("audit_records_dir"), field_name="layout.audit_records_dir"),
        audit_views_dir=_ensure_path(layout_payload.get("audit_views_dir"), field_name="layout.audit_views_dir"),
        audit_stage_views_dir=_ensure_path(
            layout_payload.get("audit_stage_views_dir"),
            field_name="layout.audit_stage_views_dir",
        ),
        workspace_dir_pattern=_ensure_path(
            layout_payload.get("workspace_dir_pattern"),
            field_name="layout.workspace_dir_pattern",
        ),
        workspace_metadata_dir=_ensure_path(
            layout_payload.get("workspace_metadata_dir"),
            field_name="layout.workspace_metadata_dir",
        ),
        debug_compile_dir=_ensure_path(layout_payload.get("debug_compile_dir"), field_name="layout.debug_compile_dir"),
        debug_logs_dir=_ensure_path(layout_payload.get("debug_logs_dir"), field_name="layout.debug_logs_dir"),
        runtime_provider_config=_ensure_path(
            layout_payload.get("runtime_provider_config"),
            field_name="layout.runtime_provider_config",
        ),
        artifact_uploads_dir=_ensure_path(
            layout_payload.get("artifact_uploads_dir"),
            field_name="layout.artifact_uploads_dir",
        ),
        ticket_context_archive_dir=_ensure_path(
            layout_payload.get("ticket_context_archive_dir"),
            field_name="layout.ticket_context_archive_dir",
        ),
    )

    provider = _load_provider_config(provider_payload)
    if not provider.provider_id:
        raise ValueError("`provider.default.provider_id` must not be empty.")
    if not provider.base_url:
        raise ValueError("`provider.default.base_url` must not be empty.")

    role_bindings = tuple(
        ScenarioProviderRoleBinding(
            target_ref=str(item.get("target_ref") or "").strip(),
            provider_model_entry_refs=_ensure_tuple(item.get("provider_model_entry_refs")),
            max_context_window_override=item.get("max_context_window_override"),
            reasoning_effort_override=str(item.get("reasoning_effort_override") or "").strip() or None,
        )
        for item in role_bindings_payload
    )

    seeds: dict[str, ScenarioSeedConfig] = {}
    for seed_id, payload in seeds_payload.items():
        resolved_path = _resolve_relative_path(
            _ensure_path(payload.get("path"), field_name=f"seeds.{seed_id}.path"),
            base_dir=config_path.parent,
        )
        seeds[seed_id] = ScenarioSeedConfig(
            seed_id=seed_id,
            path=resolved_path,
            description=str(payload.get("description") or "").strip(),
            workflow_id=str(payload.get("workflow_id") or "").strip() or None,
            requires_prepared_state=bool(payload.get("requires_prepared_state", False)),
        )

    stages: dict[str, ScenarioStageSpec] = {}
    for item in stages_payload:
        stage = ScenarioStageSpec(
            stage_id=str(item.get("stage_id") or "").strip(),
            test_file=str(item.get("test_file") or "").strip(),
            seed_ref=str(item.get("seed_ref") or "").strip(),
            start_mode=str(item.get("start_mode") or "").strip() or "copy_seed",
            checkpoint_kind=str(item.get("checkpoint_kind") or "").strip(),
            expected_stage=str(item.get("expected_stage") or "").strip() or None,
            expected_outputs=_ensure_tuple(item.get("expected_outputs")),
            required_schema_refs=_ensure_tuple(item.get("required_schema_refs")),
            forbidden_schema_refs=_ensure_tuple(item.get("forbidden_schema_refs")),
            required_role_types=_ensure_tuple(item.get("required_role_types")),
            required_node_ids=_ensure_tuple(item.get("required_node_ids")),
            required_summary_terms=_ensure_tuple(item.get("required_summary_terms")),
        )
        if stage.seed_ref not in seeds:
            raise ValueError(f"Stage `{stage.stage_id}` references unknown seed `{stage.seed_ref}`.")
        stages[stage.stage_id] = stage

    return ScenarioTestConfig(
        config_path=config_path,
        scenario_id=str(scenario_payload.get("scenario_id") or "").strip(),
        display_name=str(scenario_payload.get("display_name") or "").strip(),
        input_config=ScenarioInputConfig(
            north_star_goal=str(input_payload.get("north_star_goal") or "").strip(),
            hard_constraints=_ensure_tuple(input_payload.get("hard_constraints")),
            read_only_context_refs=_ensure_tuple(input_payload.get("read_only_context_refs")),
            workflow_profile=str(input_payload.get("workflow_profile") or "").strip() or "STANDARD",
            force_requirement_elicitation=bool(input_payload.get("force_requirement_elicitation", False)),
        ),
        runtime=ScenarioRuntimeConfig(
            seed=int(runtime_payload.get("seed", 17)),
            max_ticks=int(runtime_payload.get("max_ticks", 30)),
            timeout_sec=int(runtime_payload.get("timeout_sec", 600)),
            maintenance_interval_sec=int(runtime_payload.get("maintenance_interval_sec", 1)),
            scheduler_max_dispatches=int(runtime_payload.get("scheduler_max_dispatches", 10)),
            resume_enabled=bool(runtime_payload.get("resume_enabled", True)),
        ),
        layout=layout,
        provider=provider,
        role_bindings=role_bindings,
        seeds=seeds,
        stages=stages,
    )
