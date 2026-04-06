from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

from app.contracts.runtime import RenderedExecutionPayload


@dataclass(frozen=True)
class ClaudeCodeProviderConfig:
    command_path: str
    model: str
    timeout_sec: float


@dataclass(frozen=True)
class ClaudeCodeProviderResult:
    output_text: str
    response_id: str | None = None


class ClaudeCodeProviderError(RuntimeError):
    def __init__(self, *, failure_kind: str, message: str, failure_detail: dict[str, object]) -> None:
        super().__init__(message)
        self.failure_kind = failure_kind
        self.failure_detail = failure_detail


def _render_payload_as_prompt(rendered_payload: RenderedExecutionPayload) -> str:
    lines: list[str] = []
    for message in rendered_payload.messages:
        lines.append(
            json.dumps(
                {
                    "role": message.role,
                    "channel": message.channel,
                    "content_type": message.content_type,
                    "content_payload": message.content_payload,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    return "\n".join(lines)


def invoke_claude_code_response(
    config: ClaudeCodeProviderConfig,
    rendered_payload: RenderedExecutionPayload,
) -> ClaudeCodeProviderResult:
    command = [
        config.command_path,
        "--print",
        "--output-format",
        "text",
        "--permission-mode",
        "bypassPermissions",
        "--model",
        config.model,
        "--json-schema",
        '{"type":"object"}',
        _render_payload_as_prompt(rendered_payload),
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=config.timeout_sec,
        )
    except FileNotFoundError as exc:
        raise ClaudeCodeProviderError(
            failure_kind="UPSTREAM_UNAVAILABLE",
            message=f"Claude Code command was not found: {config.command_path}",
            failure_detail={"command_path": config.command_path},
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ClaudeCodeProviderError(
            failure_kind="UPSTREAM_UNAVAILABLE",
            message=f"Claude Code command timed out: {exc}",
            failure_detail={"command_path": config.command_path, "provider_transport_error": "TimeoutExpired"},
        ) from exc
    if completed.returncode != 0:
        raise ClaudeCodeProviderError(
            failure_kind="PROVIDER_BAD_RESPONSE",
            message="Claude Code command failed.",
            failure_detail={
                "command_path": config.command_path,
                "provider_exit_code": completed.returncode,
                "provider_stderr": completed.stderr.strip(),
            },
        )
    output_text = completed.stdout.strip()
    if not output_text:
        raise ClaudeCodeProviderError(
            failure_kind="PROVIDER_BAD_RESPONSE",
            message="Claude Code command returned an empty response.",
            failure_detail={"command_path": config.command_path, "provider_exit_code": completed.returncode},
        )
    return ClaudeCodeProviderResult(output_text=output_text)

