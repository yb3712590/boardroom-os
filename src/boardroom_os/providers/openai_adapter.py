from __future__ import annotations

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
    base_url: str = "https://api.truerealbill.com/v1"
    model: str = "gpt-5.5"
    api_protocol: Literal["auto", "responses", "chat_completions"] = "auto"
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh"] = "high"
    text_verbosity: Literal["low", "medium", "high"] = "low"
    max_output_tokens: int = Field(default=1024, gt=0)
    timeout_seconds: float = Field(default=60.0, gt=0)
    max_retries: int = Field(default=0, ge=0)
    system_instructions: str = ""

    @classmethod
    def from_env_file(cls, path: Path) -> Self:
        values = _load_env_file(path)
        api_key = values.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise OpenAIProviderConfigError("OPENAI_API_KEY is required")
        return cls(
            api_key=api_key,
            base_url=values.get("OPENAI_BASE_URL", "https://api.truerealbill.com/v1"),
            model=values.get("BOARDROOM_OPENAI_MODEL", "gpt-5.5"),
            api_protocol=values.get("BOARDROOM_OPENAI_API_PROTOCOL", "auto"),
            reasoning_effort=values.get("BOARDROOM_OPENAI_REASONING_EFFORT", "high"),
            text_verbosity=values.get("BOARDROOM_OPENAI_TEXT_VERBOSITY", "low"),
            max_output_tokens=values.get("BOARDROOM_OPENAI_MAX_OUTPUT_TOKENS", "1024"),
            timeout_seconds=values.get("BOARDROOM_OPENAI_TIMEOUT_SECONDS", "60"),
            max_retries=values.get("BOARDROOM_OPENAI_MAX_RETRIES", "0"),
            system_instructions=values.get("BOARDROOM_OPENAI_SYSTEM_INSTRUCTIONS", ""),
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
    ) -> None:
        self._settings = settings
        self._client = client
        self._use_chat_completions = settings.api_protocol == "chat_completions"

    def invoke(self, request: ProviderRequest) -> ProviderAttempt:
        started_at = datetime.now(UTC)
        try:
            client = self._client_or_default()
            if self._settings.api_protocol == "responses":
                response = self._invoke_responses_api(client, request)
            elif self._use_chat_completions:
                response = self._invoke_chat_completions(client, request)
            else:
                try:
                    response = self._invoke_responses_api(client, request)
                except Exception as responses_error:
                    if not self._has_chat_completions(client):
                        raise responses_error
                    response = self._invoke_chat_completions(client, request)
                    self._use_chat_completions = True

            response_id = self._response_id(response)
            _ = self._response_text(response)
            return self._succeeded_attempt(
                request=request,
                response_id=response_id,
                started_at=started_at,
            )
        except Exception as error:
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
                status=ProviderAttemptStatus.FAILED,
                outcome=ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                failure_kind=f"provider_error.{type(error).__name__}",
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
        return client.chat.completions.create(
            model=request.model_execution_profile.model,
            messages=messages,
            reasoning_effort=request.model_execution_profile.reasoning_effort,
            max_completion_tokens=self._settings.max_output_tokens,
            verbosity=self._settings.text_verbosity,
            timeout=self._settings.timeout_seconds,
        )

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
    ) -> ProviderAttempt:
        return ProviderAttempt(
            provider_attempt_id=f"provider-attempt.openai.{response_id}",
            provider=request.model_execution_profile.provider,
            model=request.model_execution_profile.model,
            reasoning_effort=request.model_execution_profile.reasoning_effort,
            input_package_ref=request.execution_package_ref,
            seat_ref=request.seat_ref,
            status=ProviderAttemptStatus.SUCCEEDED,
            outcome=ProviderAttemptOutcome.PRIMARY_PROVIDER_OUTPUT,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            raw_output_ref=ProviderArtifactRef(
                value=f"provider-artifact.openai.raw.{response_id}",
            ),
            parsed_output_ref=ProviderArtifactRef(
                value=f"provider-artifact.openai.text.{response_id}",
            ),
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
        output_text = str(getattr(response, "output_text", "")).strip()
        if not output_text and getattr(response, "choices", None):
            first_choice = response.choices[0]
            message = getattr(first_choice, "message", None)
            output_text = str(getattr(message, "content", "")).strip()
        if not output_text:
            raise OpenAIProviderConfigError("OpenAI response output_text is required")
        return output_text


__all__ = [
    "OpenAIProviderConfigError",
    "OpenAIProviderSettings",
    "OpenAIProviderTransport",
]
