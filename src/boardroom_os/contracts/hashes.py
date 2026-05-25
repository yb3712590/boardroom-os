from __future__ import annotations

import re
from typing import ClassVar

from pydantic import field_validator

from boardroom_os.contracts.types import NonEmptyTextValue

_SHA1_PATTERN = re.compile(r"[0-9a-f]{40}")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_DUMMY_DIGESTS = frozenset({"deadbeef" * 5, "deadbeef" * 8})


def is_placeholder_digest(value: str, *, length: int) -> bool:
    normalized = value.strip()
    if normalized != value:
        return True
    if len(normalized) != length:
        return True
    if re.fullmatch(r"[0-9a-f]+", normalized) is None:
        return True
    if len(set(normalized)) == 1:
        return True
    return normalized in _DUMMY_DIGESTS


class _HexDigest(NonEmptyTextValue):
    digest_length: ClassVar[int]
    digest_label: ClassVar[str]
    digest_pattern: ClassVar[re.Pattern[str]]

    @field_validator("value", mode="before")
    @classmethod
    def _reject_surrounding_whitespace(cls, value: str) -> str:
        if isinstance(value, str) and value.strip() != value:
            raise ValueError(f"{cls.digest_label} must not contain surrounding whitespace")
        return value

    @field_validator("value")
    @classmethod
    def _validate_hex_digest(cls, value: str) -> str:
        if cls.digest_pattern.fullmatch(value) is None:
            raise ValueError(f"{cls.digest_label} must be a lowercase hex digest")
        if is_placeholder_digest(value, length=cls.digest_length):
            raise ValueError(f"{cls.digest_label} must not be a placeholder or synthetic digest")
        return value


class Sha1Hex(_HexDigest):
    digest_length: ClassVar[int] = 40
    digest_label: ClassVar[str] = "sha1"
    digest_pattern: ClassVar[re.Pattern[str]] = _SHA1_PATTERN


class Sha256Hex(_HexDigest):
    digest_length: ClassVar[int] = 64
    digest_label: ClassVar[str] = "sha256"
    digest_pattern: ClassVar[re.Pattern[str]] = _SHA256_PATTERN
