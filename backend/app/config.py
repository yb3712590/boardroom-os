from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


RuntimeExecutionMode = Literal["INPROCESS", "EXTERNAL"]
ProviderOpenAICompatReasoningEffort = Literal["low", "medium", "high", "xhigh"]


@dataclass(frozen=True)
class Settings:
    db_path: Path
    developer_inspector_root: Path
    artifact_store_root: Path
    artifact_upload_staging_root: Path
    runtime_provider_config_path: Path
    runtime_execution_mode: RuntimeExecutionMode
    artifact_object_store_enabled: bool
    artifact_object_store_endpoint: str | None
    artifact_object_store_bucket: str | None
    artifact_object_store_access_key: str | None
    artifact_object_store_secret_key: str | None
    artifact_object_store_region: str | None
    provider_openai_compat_base_url: str | None
    provider_openai_compat_api_key: str | None
    provider_openai_compat_model: str | None
    provider_openai_compat_timeout_sec: float
    provider_openai_compat_reasoning_effort: ProviderOpenAICompatReasoningEffort | None
    worker_bootstrap_signing_secret: str | None
    worker_admin_signing_secret: str | None
    worker_shared_secret: str | None
    public_base_url: str | None
    worker_session_ttl_sec: int
    worker_delivery_token_ttl_sec: int
    worker_delivery_signing_secret: str | None
    worker_bootstrap_default_ttl_sec: int
    worker_bootstrap_max_ttl_sec: int
    worker_admin_default_ttl_sec: int
    worker_admin_max_ttl_sec: int
    worker_admin_trusted_proxy_ids: tuple[str, ...]
    worker_bootstrap_allowed_tenant_ids: tuple[str, ...]
    busy_timeout_ms: int = 5000
    recent_event_limit: int = 10
    scheduler_poll_interval_sec: float = 5.0
    scheduler_max_dispatches: int = 10
    enable_inprocess_scheduler: bool = False
    artifact_cleanup_interval_sec: int = 300
    artifact_cleanup_operator_id: str = "system:artifact-cleanup"
    artifact_ephemeral_default_ttl_sec: int = 604800
    artifact_operational_evidence_default_ttl_sec: int = 1209600
    artifact_review_evidence_default_ttl_sec: int = 2592000
    artifact_upload_part_size_limit_bytes: int = 5 * 1024 * 1024
    artifact_upload_max_size_bytes: int = 100 * 1024 * 1024
    artifact_upload_max_part_count: int = 10_000


def _read_bool_env(name: str, default: bool = False) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _read_runtime_execution_mode() -> RuntimeExecutionMode:
    raw_value = os.environ.get("BOARDROOM_OS_RUNTIME_EXECUTION_MODE", "INPROCESS")
    normalized = raw_value.strip().upper()
    if normalized not in {"INPROCESS", "EXTERNAL"}:
        raise ValueError(
            "BOARDROOM_OS_RUNTIME_EXECUTION_MODE must be INPROCESS or EXTERNAL."
        )
    return normalized


def get_settings() -> Settings:
    repo_root = Path(__file__).resolve().parents[2]
    db_path = Path(
        os.environ.get(
            "BOARDROOM_OS_DB_PATH",
            repo_root / "backend" / "data" / "boardroom_os.db",
        )
    )
    developer_inspector_root = Path(
        os.environ.get(
            "BOARDROOM_OS_DEVELOPER_INSPECTOR_ROOT",
            repo_root / "backend" / "data" / "developer_inspector",
        )
    )
    artifact_store_root = Path(
        os.environ.get(
            "BOARDROOM_OS_ARTIFACT_STORE_ROOT",
            repo_root / "backend" / "data" / "artifacts",
        )
    )
    artifact_upload_staging_root = Path(
        os.environ.get(
            "BOARDROOM_OS_ARTIFACT_UPLOAD_STAGING_ROOT",
            repo_root / "backend" / "data" / "artifact_uploads",
        )
    )
    runtime_provider_config_path = Path(
        os.environ.get(
            "BOARDROOM_OS_RUNTIME_PROVIDER_CONFIG_PATH",
            repo_root / "backend" / "data" / "runtime-provider-config.json",
        )
    )
    artifact_object_store_enabled = _read_bool_env(
        "BOARDROOM_OS_ARTIFACT_OBJECT_STORE_ENABLED",
        default=False,
    )
    artifact_object_store_endpoint = os.environ.get("BOARDROOM_OS_ARTIFACT_OBJECT_STORE_ENDPOINT")
    artifact_object_store_bucket = os.environ.get("BOARDROOM_OS_ARTIFACT_OBJECT_STORE_BUCKET")
    artifact_object_store_access_key = os.environ.get("BOARDROOM_OS_ARTIFACT_OBJECT_STORE_ACCESS_KEY")
    artifact_object_store_secret_key = os.environ.get("BOARDROOM_OS_ARTIFACT_OBJECT_STORE_SECRET_KEY")
    artifact_object_store_region = os.environ.get("BOARDROOM_OS_ARTIFACT_OBJECT_STORE_REGION")
    provider_openai_compat_base_url = os.environ.get("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_BASE_URL")
    if provider_openai_compat_base_url is not None:
        provider_openai_compat_base_url = provider_openai_compat_base_url.strip().rstrip("/") or None
    provider_openai_compat_api_key = os.environ.get("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_API_KEY")
    if provider_openai_compat_api_key is not None:
        provider_openai_compat_api_key = provider_openai_compat_api_key.strip() or None
    provider_openai_compat_model = os.environ.get("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_MODEL")
    if provider_openai_compat_model is not None:
        provider_openai_compat_model = provider_openai_compat_model.strip() or None
    provider_openai_compat_reasoning_effort = os.environ.get(
        "BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_REASONING_EFFORT"
    )
    if provider_openai_compat_reasoning_effort is not None:
        provider_openai_compat_reasoning_effort = (
            provider_openai_compat_reasoning_effort.strip().lower() or None
        )
    if provider_openai_compat_reasoning_effort not in {None, "low", "medium", "high", "xhigh"}:
        raise ValueError(
            "BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_REASONING_EFFORT must be one of: "
            "low, medium, high, xhigh."
        )
    provider_openai_compat_timeout_sec = float(
        os.environ.get("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_TIMEOUT_SEC", "30")
    )
    if provider_openai_compat_timeout_sec <= 0:
        raise ValueError("BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_TIMEOUT_SEC must be greater than 0.")
    busy_timeout_ms = int(os.environ.get("BOARDROOM_OS_BUSY_TIMEOUT_MS", "5000"))
    recent_event_limit = int(os.environ.get("BOARDROOM_OS_RECENT_EVENT_LIMIT", "10"))
    scheduler_poll_interval_sec = float(
        os.environ.get("BOARDROOM_OS_SCHEDULER_POLL_INTERVAL_SEC", "5.0")
    )
    scheduler_max_dispatches = int(
        os.environ.get("BOARDROOM_OS_SCHEDULER_MAX_DISPATCHES", "10")
    )
    runtime_execution_mode = _read_runtime_execution_mode()
    worker_bootstrap_signing_secret = os.environ.get(
        "BOARDROOM_OS_WORKER_BOOTSTRAP_SIGNING_SECRET"
    )
    worker_admin_signing_secret = os.environ.get("BOARDROOM_OS_WORKER_ADMIN_SIGNING_SECRET")
    worker_shared_secret = os.environ.get("BOARDROOM_OS_WORKER_SHARED_SECRET")
    public_base_url = os.environ.get("BOARDROOM_OS_PUBLIC_BASE_URL")
    if public_base_url is not None:
        normalized_public_base_url = public_base_url.strip().rstrip("/")
        public_base_url = normalized_public_base_url or None
    worker_session_ttl_sec = int(
        os.environ.get("BOARDROOM_OS_WORKER_SESSION_TTL_SEC", "86400")
    )
    worker_delivery_token_ttl_sec = int(
        os.environ.get("BOARDROOM_OS_WORKER_DELIVERY_TOKEN_TTL_SEC", "3600")
    )
    worker_delivery_signing_secret = os.environ.get(
        "BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET"
    )
    worker_bootstrap_default_ttl_sec = int(
        os.environ.get("BOARDROOM_OS_WORKER_BOOTSTRAP_DEFAULT_TTL_SEC", "86400")
    )
    worker_bootstrap_max_ttl_sec = int(
        os.environ.get("BOARDROOM_OS_WORKER_BOOTSTRAP_MAX_TTL_SEC", "604800")
    )
    worker_admin_default_ttl_sec = int(
        os.environ.get("BOARDROOM_OS_WORKER_ADMIN_DEFAULT_TTL_SEC", "900")
    )
    worker_admin_max_ttl_sec = int(
        os.environ.get("BOARDROOM_OS_WORKER_ADMIN_MAX_TTL_SEC", "3600")
    )
    raw_worker_admin_trusted_proxy_ids = os.environ.get("BOARDROOM_OS_WORKER_ADMIN_TRUSTED_PROXY_IDS")
    if raw_worker_admin_trusted_proxy_ids:
        worker_admin_trusted_proxy_ids = tuple(
            proxy_id
            for proxy_id in (item.strip() for item in raw_worker_admin_trusted_proxy_ids.split(","))
            if proxy_id
        )
    else:
        worker_admin_trusted_proxy_ids = ()
    raw_allowed_tenants = os.environ.get("BOARDROOM_OS_WORKER_BOOTSTRAP_ALLOWED_TENANT_IDS")
    if raw_allowed_tenants:
        worker_bootstrap_allowed_tenant_ids = tuple(
            tenant_id
            for tenant_id in (item.strip() for item in raw_allowed_tenants.split(","))
            if tenant_id
        )
    else:
        worker_bootstrap_allowed_tenant_ids = ()
    enable_inprocess_scheduler = _read_bool_env(
        "BOARDROOM_OS_ENABLE_INPROCESS_SCHEDULER",
        default=False,
    )
    artifact_cleanup_interval_sec = int(
        os.environ.get("BOARDROOM_OS_ARTIFACT_CLEANUP_INTERVAL_SEC", "300")
    )
    artifact_cleanup_operator_id = os.environ.get(
        "BOARDROOM_OS_ARTIFACT_CLEANUP_OPERATOR_ID",
        "system:artifact-cleanup",
    ).strip() or "system:artifact-cleanup"
    artifact_ephemeral_default_ttl_sec = int(
        os.environ.get("BOARDROOM_OS_ARTIFACT_EPHEMERAL_DEFAULT_TTL_SEC", "604800")
    )
    if artifact_ephemeral_default_ttl_sec <= 0:
        raise ValueError(
            "BOARDROOM_OS_ARTIFACT_EPHEMERAL_DEFAULT_TTL_SEC must be greater than 0."
        )
    artifact_operational_evidence_default_ttl_sec = int(
        os.environ.get("BOARDROOM_OS_ARTIFACT_OPERATIONAL_EVIDENCE_DEFAULT_TTL_SEC", "1209600")
    )
    if artifact_operational_evidence_default_ttl_sec <= 0:
        raise ValueError(
            "BOARDROOM_OS_ARTIFACT_OPERATIONAL_EVIDENCE_DEFAULT_TTL_SEC must be greater than 0."
        )
    artifact_review_evidence_default_ttl_sec = int(
        os.environ.get("BOARDROOM_OS_ARTIFACT_REVIEW_EVIDENCE_DEFAULT_TTL_SEC", "2592000")
    )
    if artifact_review_evidence_default_ttl_sec <= 0:
        raise ValueError(
            "BOARDROOM_OS_ARTIFACT_REVIEW_EVIDENCE_DEFAULT_TTL_SEC must be greater than 0."
        )
    artifact_upload_part_size_limit_bytes = int(
        os.environ.get("BOARDROOM_OS_ARTIFACT_UPLOAD_PART_SIZE_LIMIT_BYTES", str(5 * 1024 * 1024))
    )
    artifact_upload_max_size_bytes = int(
        os.environ.get("BOARDROOM_OS_ARTIFACT_UPLOAD_MAX_SIZE_BYTES", str(100 * 1024 * 1024))
    )
    artifact_upload_max_part_count = int(
        os.environ.get("BOARDROOM_OS_ARTIFACT_UPLOAD_MAX_PART_COUNT", "10000")
    )
    if artifact_upload_part_size_limit_bytes <= 0:
        raise ValueError(
            "BOARDROOM_OS_ARTIFACT_UPLOAD_PART_SIZE_LIMIT_BYTES must be greater than 0."
        )
    if artifact_upload_max_size_bytes <= 0:
        raise ValueError(
            "BOARDROOM_OS_ARTIFACT_UPLOAD_MAX_SIZE_BYTES must be greater than 0."
        )
    if artifact_upload_max_part_count <= 0:
        raise ValueError(
            "BOARDROOM_OS_ARTIFACT_UPLOAD_MAX_PART_COUNT must be greater than 0."
        )
    return Settings(
        db_path=db_path,
        developer_inspector_root=developer_inspector_root,
        artifact_store_root=artifact_store_root,
        artifact_upload_staging_root=artifact_upload_staging_root,
        runtime_provider_config_path=runtime_provider_config_path,
        runtime_execution_mode=runtime_execution_mode,
        artifact_object_store_enabled=artifact_object_store_enabled,
        artifact_object_store_endpoint=artifact_object_store_endpoint,
        artifact_object_store_bucket=artifact_object_store_bucket,
        artifact_object_store_access_key=artifact_object_store_access_key,
        artifact_object_store_secret_key=artifact_object_store_secret_key,
        artifact_object_store_region=artifact_object_store_region,
        provider_openai_compat_base_url=provider_openai_compat_base_url,
        provider_openai_compat_api_key=provider_openai_compat_api_key,
        provider_openai_compat_model=provider_openai_compat_model,
        provider_openai_compat_timeout_sec=provider_openai_compat_timeout_sec,
        provider_openai_compat_reasoning_effort=provider_openai_compat_reasoning_effort,
        worker_bootstrap_signing_secret=worker_bootstrap_signing_secret,
        worker_admin_signing_secret=worker_admin_signing_secret,
        worker_shared_secret=worker_shared_secret,
        public_base_url=public_base_url,
        worker_session_ttl_sec=worker_session_ttl_sec,
        worker_delivery_token_ttl_sec=worker_delivery_token_ttl_sec,
        worker_delivery_signing_secret=worker_delivery_signing_secret,
        worker_bootstrap_default_ttl_sec=worker_bootstrap_default_ttl_sec,
        worker_bootstrap_max_ttl_sec=worker_bootstrap_max_ttl_sec,
        worker_admin_default_ttl_sec=worker_admin_default_ttl_sec,
        worker_admin_max_ttl_sec=worker_admin_max_ttl_sec,
        worker_admin_trusted_proxy_ids=worker_admin_trusted_proxy_ids,
        worker_bootstrap_allowed_tenant_ids=worker_bootstrap_allowed_tenant_ids,
        busy_timeout_ms=busy_timeout_ms,
        recent_event_limit=recent_event_limit,
        scheduler_poll_interval_sec=scheduler_poll_interval_sec,
        scheduler_max_dispatches=scheduler_max_dispatches,
        enable_inprocess_scheduler=enable_inprocess_scheduler,
        artifact_cleanup_interval_sec=artifact_cleanup_interval_sec,
        artifact_cleanup_operator_id=artifact_cleanup_operator_id,
        artifact_ephemeral_default_ttl_sec=artifact_ephemeral_default_ttl_sec,
        artifact_operational_evidence_default_ttl_sec=artifact_operational_evidence_default_ttl_sec,
        artifact_review_evidence_default_ttl_sec=artifact_review_evidence_default_ttl_sec,
        artifact_upload_part_size_limit_bytes=artifact_upload_part_size_limit_bytes,
        artifact_upload_max_size_bytes=artifact_upload_max_size_bytes,
        artifact_upload_max_part_count=artifact_upload_max_part_count,
    )
