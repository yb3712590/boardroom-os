from __future__ import annotations

from app.config import get_settings


def test_default_max_context_tokens_defaults_to_270k(monkeypatch) -> None:
    monkeypatch.delenv("BOARDROOM_OS_DEFAULT_MAX_CONTEXT_TOKENS", raising=False)

    settings = get_settings()

    assert settings.default_max_context_tokens == 270_000


def test_default_max_context_tokens_can_be_overridden(monkeypatch) -> None:
    monkeypatch.setenv("BOARDROOM_OS_DEFAULT_MAX_CONTEXT_TOKENS", "131072")

    settings = get_settings()

    assert settings.default_max_context_tokens == 131_072
