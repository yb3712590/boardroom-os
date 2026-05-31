from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from boardroom_os.providers.adapter import ProviderRequest
from boardroom_os.providers.attempt import (
    ProviderArtifactRef,
    ProviderAttempt,
    ProviderAttemptOutcome,
    ProviderAttemptStatus,
)


class OpenAIProviderConfigError(ValueError):
    pass


class ProviderOutputContentHash(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    value: str

    @field_validator("value")
    @classmethod
    def _require_sha256(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
            raise ValueError("content_hash must be a 64-character lowercase sha256")
        return normalized


class ProviderOutputArtifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_ref: ProviderArtifactRef
    content_hash: ProviderOutputContentHash
    path: Path
    content_type: Literal["raw_provider_response", "parsed_provider_text"]


class FileProviderOutputStore:
    def __init__(self, *, root: Path) -> None:
        self._root = root

    def write_text(
        self,
        *,
        response_id: str,
        artifact_kind: Literal["raw", "parsed"],
        text: str,
    ) -> ProviderOutputArtifact:
        if not text.strip():
            raise OpenAIProviderConfigError("provider artifact text is required")
        encoded = text.encode("utf-8")
        content_hash = hashlib.sha256(encoded).hexdigest()
        artifact_ref = ProviderArtifactRef(
            value=f"provider-artifact.openai.{artifact_kind}.{response_id}.{content_hash}"
        )
        path = self._path_for_ref(artifact_ref)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(encoded)
        if hashlib.sha256(path.read_bytes()).hexdigest() != content_hash:
            raise OpenAIProviderConfigError("provider artifact hash mismatch after write")
        content_type: Literal["raw_provider_response", "parsed_provider_text"]
        if artifact_kind == "raw":
            content_type = "raw_provider_response"
        else:
            content_type = "parsed_provider_text"
        return ProviderOutputArtifact(
            artifact_ref=artifact_ref,
            content_hash=ProviderOutputContentHash(value=content_hash),
            path=path,
            content_type=content_type,
        )

    def get(self, artifact_ref: ProviderArtifactRef) -> ProviderOutputArtifact:
        path = self._path_for_ref(artifact_ref)
        if not path.exists():
            raise OpenAIProviderConfigError(f"provider artifact is missing: {artifact_ref.value}")
        content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        ref_hash = artifact_ref.value.rsplit(".", 1)[-1]
        if ref_hash != content_hash:
            raise OpenAIProviderConfigError("provider artifact hash does not match ref")
        content_type: Literal["raw_provider_response", "parsed_provider_text"]
        if ".raw." in artifact_ref.value:
            content_type = "raw_provider_response"
        elif ".parsed." in artifact_ref.value:
            content_type = "parsed_provider_text"
        else:
            raise OpenAIProviderConfigError("provider artifact ref kind is invalid")
        return ProviderOutputArtifact(
            artifact_ref=artifact_ref,
            content_hash=ProviderOutputContentHash(value=content_hash),
            path=path,
            content_type=content_type,
        )

    def read_text(self, artifact_ref: ProviderArtifactRef) -> str:
        artifact = self.get(artifact_ref)
        return artifact.path.read_text(encoding="utf-8")

    def _path_for_ref(self, artifact_ref: ProviderArtifactRef) -> Path:
        safe_name = artifact_ref.value.replace("/", "_").replace("\\", "_").replace(":", "_")
        return self._root / f"{safe_name}.txt"


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        raise OpenAIProviderConfigError(f"provider env file is required: {path}")

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


class OpenAIProviderSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    api_key: SecretStr = Field(exclude=True, repr=False)
    base_url: str
    model: str
    api_protocol: Literal["responses", "chat_completions"]
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh"] = "high"
    text_verbosity: Literal["low", "medium", "high"] = "low"
    response_format: Literal["text", "json_object"] = "text"
    max_output_tokens: int = Field(default=1024, gt=0)
    timeout_seconds: float = Field(default=60.0, gt=0)
    max_retries: int = Field(default=0, ge=0)
    system_instructions: str = ""
    artifact_store_root: Path | None = None

    @classmethod
    def from_env_file(cls, path: Path) -> Self:
        values = _load_env_file(path)
        return cls.from_env_values(values)

    @classmethod
    def from_env_files(cls, paths: tuple[Path, ...]) -> Self:
        missing_paths: list[str] = []
        for path in paths:
            if path.exists():
                return cls.from_env_file(path)
            missing_paths.append(str(path))
        raise OpenAIProviderConfigError(
            "provider env file is required: " + ", ".join(missing_paths)
        )

    @classmethod
    def from_env_values(cls, values: dict[str, str]) -> Self:
        api_key = values.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise OpenAIProviderConfigError("OPENAI_API_KEY is required")
        required_names = (
            "OPENAI_BASE_URL",
            "BOARDROOM_OPENAI_MODEL",
            "BOARDROOM_OPENAI_API_PROTOCOL",
        )
        missing_names = tuple(name for name in required_names if not values.get(name, "").strip())
        if missing_names:
            raise OpenAIProviderConfigError(
                "required provider config is missing: " + ", ".join(missing_names)
            )
        return cls(
            api_key=api_key,
            base_url=values["OPENAI_BASE_URL"],
            model=values["BOARDROOM_OPENAI_MODEL"],
            api_protocol=values["BOARDROOM_OPENAI_API_PROTOCOL"],
            reasoning_effort=values.get("BOARDROOM_OPENAI_REASONING_EFFORT", "high"),
            text_verbosity=values.get("BOARDROOM_OPENAI_TEXT_VERBOSITY", "low"),
            response_format=values.get("BOARDROOM_OPENAI_RESPONSE_FORMAT", "text"),
            max_output_tokens=values.get("BOARDROOM_OPENAI_MAX_OUTPUT_TOKENS", "1024"),
            timeout_seconds=values.get("BOARDROOM_OPENAI_TIMEOUT_SECONDS", "60"),
            max_retries=values.get("BOARDROOM_OPENAI_MAX_RETRIES", "0"),
            system_instructions=values.get("BOARDROOM_OPENAI_SYSTEM_INSTRUCTIONS", ""),
            artifact_store_root=values.get("BOARDROOM_OPENAI_ARTIFACT_STORE_ROOT") or None,
        )

    @field_validator("base_url", "model")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text fields must not be empty")
        return normalized

    @field_validator("system_instructions")
    @classmethod
    def _normalize_system_instructions(cls, value: str) -> str:
        return value.strip()


class OpenAIProviderTransport:
    def __init__(
        self,
        *,
        settings: OpenAIProviderSettings,
        client: Any | None = None,
        artifact_store: FileProviderOutputStore | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        store_root = settings.artifact_store_root or Path("20-evidence/provider-artifacts")
        self._artifact_store = artifact_store or FileProviderOutputStore(root=store_root)

    def invoke(self, request: ProviderRequest) -> ProviderAttempt:
        started_at = datetime.now(UTC)
        last_error: Exception | None = None
        for _attempt_index in range(self._settings.max_retries + 1):
            try:
                client = self._client_or_default()
                if self._settings.api_protocol == "responses":
                    response = self._invoke_responses_api(client, request)
                else:
                    response = self._invoke_chat_completions(client, request)

                response_id = self._response_id(response)
                response_text = self._response_text(response)
                raw_artifact = self._artifact_store.write_text(
                    response_id=response_id,
                    artifact_kind="raw",
                    text=self._raw_response_text(response=response, response_text=response_text),
                )
                parsed_artifact = self._artifact_store.write_text(
                    response_id=response_id,
                    artifact_kind="parsed",
                    text=response_text,
                )
                return self._succeeded_attempt(
                    request=request,
                    response_id=response_id,
                    started_at=started_at,
                    raw_output_ref=raw_artifact.artifact_ref,
                    parsed_output_ref=parsed_artifact.artifact_ref,
                )
            except Exception as error:
                last_error = error

        assert last_error is not None
        return ProviderAttempt(
            provider_attempt_id=(
                "provider-attempt.openai.failed."
                f"{request.execution_package_ref.value}.{int(started_at.timestamp() * 1_000_000)}"
            ),
            provider=request.model_execution_profile.provider,
            model=request.model_execution_profile.model,
            reasoning_effort=request.model_execution_profile.reasoning_effort,
            input_package_ref=request.execution_package_ref,
            seat_ref=request.seat_ref,
            role_prompt_hook_ref=request.role_prompt_hook_ref,
            role_prompt_hook_version=request.role_prompt_hook_version,
            role_prompt_hook_sha256=request.role_prompt_hook_sha256,
            status=ProviderAttemptStatus.FAILED,
            outcome=ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            failure_kind=f"provider_error.{type(last_error).__name__}",
        )

    def _invoke_responses_api(self, client: Any, request: ProviderRequest) -> Any:
        return client.responses.create(
            model=request.model_execution_profile.model,
            input=request.prompt,
            instructions=self._settings.system_instructions or None,
            reasoning={"effort": request.model_execution_profile.reasoning_effort},
            text={"verbosity": self._settings.text_verbosity},
            max_output_tokens=self._settings.max_output_tokens,
            timeout=self._settings.timeout_seconds,
        )

    def _invoke_chat_completions(self, client: Any, request: ProviderRequest) -> Any:
        messages = [{"role": "user", "content": request.prompt}]
        if self._settings.system_instructions:
            messages = [
                {"role": "system", "content": self._settings.system_instructions},
                *messages,
            ]
        kwargs = {
            "model": request.model_execution_profile.model,
            "messages": messages,
            "reasoning_effort": request.model_execution_profile.reasoning_effort,
            "max_completion_tokens": self._settings.max_output_tokens,
            "verbosity": self._settings.text_verbosity,
            "timeout": self._settings.timeout_seconds,
        }
        if self._settings.response_format == "json_object":
            kwargs["response_format"] = {"type": "json_object"}
        return client.chat.completions.create(**kwargs)

    @staticmethod
    def _has_chat_completions(client: Any) -> bool:
        chat = getattr(client, "chat", None)
        completions = getattr(chat, "completions", None)
        return callable(getattr(completions, "create", None))

    @staticmethod
    def _succeeded_attempt(
        *,
        request: ProviderRequest,
        response_id: str,
        started_at: datetime,
        raw_output_ref: ProviderArtifactRef,
        parsed_output_ref: ProviderArtifactRef,
    ) -> ProviderAttempt:
        return ProviderAttempt(
            provider_attempt_id=f"provider-attempt.openai.{response_id}",
            provider=request.model_execution_profile.provider,
            model=request.model_execution_profile.model,
            reasoning_effort=request.model_execution_profile.reasoning_effort,
            input_package_ref=request.execution_package_ref,
            seat_ref=request.seat_ref,
            role_prompt_hook_ref=request.role_prompt_hook_ref,
            role_prompt_hook_version=request.role_prompt_hook_version,
            role_prompt_hook_sha256=request.role_prompt_hook_sha256,
            status=ProviderAttemptStatus.SUCCEEDED,
            outcome=ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            raw_output_ref=raw_output_ref,
            parsed_output_ref=parsed_output_ref,
        )

    def _client_or_default(self) -> Any:
        if self._client is not None:
            return self._client

        from openai import OpenAI

        self._client = OpenAI(
            api_key=self._settings.api_key.get_secret_value(),
            base_url=self._settings.base_url,
            max_retries=self._settings.max_retries,
        )
        return self._client

    @staticmethod
    def _response_id(response: Any) -> str:
        response_id = str(getattr(response, "id", "")).strip()
        if not response_id:
            raise OpenAIProviderConfigError("OpenAI response id is required")
        return response_id.replace("/", "_").replace(":", "_")

    @staticmethod
    def _response_text(response: Any) -> str:
        raw_output_text = getattr(response, "output_text", "")
        output_text = "" if raw_output_text is None else str(raw_output_text).strip()
        if not output_text and getattr(response, "choices", None):
            first_choice = response.choices[0]
            message = getattr(first_choice, "message", None)
            raw_message_content = getattr(message, "content", "")
            output_text = (
                ""
                if raw_message_content is None
                else str(raw_message_content).strip()
            )
        if not output_text:
            raise OpenAIProviderConfigError("OpenAI response output_text is required")
        return output_text

    @staticmethod
    def _raw_response_text(*, response: Any, response_text: str) -> str:
        model_dump_json = getattr(response, "model_dump_json", None)
        if callable(model_dump_json):
            dumped = str(model_dump_json()).strip()
            if dumped:
                return dumped
        response_id = str(getattr(response, "id", "")).strip()
        return json.dumps(
            {
                "id": response_id,
                "output_text": response_text,
            },
            ensure_ascii=False,
            sort_keys=True,
        )


__all__ = [
    "FileProviderOutputStore",
    "OpenAIProviderConfigError",
    "OpenAIProviderSettings",
    "OpenAIProviderTransport",
    "ProviderOutputArtifact",
    "ProviderOutputContentHash",
]
