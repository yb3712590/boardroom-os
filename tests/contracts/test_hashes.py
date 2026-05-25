from __future__ import annotations

import pytest
from pydantic import ValidationError

from boardroom_os.contracts.hashes import (
    Sha1Hex,
    Sha256Hex,
    is_placeholder_digest,
)


VALID_SHA1 = "0123456789abcdef0123456789abcdef01234567"
VALID_SHA256 = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"


@pytest.mark.parametrize(
    ("value_object", "digest"),
    [
        (Sha1Hex, VALID_SHA1),
        (Sha256Hex, VALID_SHA256),
    ],
)
def test_sha_hex_value_objects_accept_valid_lowercase_digests(
    value_object: type[Sha1Hex] | type[Sha256Hex], digest: str
) -> None:
    assert value_object(value=digest).value == digest


@pytest.mark.parametrize(
    ("value_object", "digest"),
    [
        (Sha1Hex, VALID_SHA1.upper()),
        (Sha1Hex, VALID_SHA1[:-1]),
        (Sha1Hex, f" {VALID_SHA1}"),
        (Sha1Hex, f"{VALID_SHA1} "),
        (Sha1Hex, "0" * 40),
        (Sha1Hex, "f" * 40),
        (Sha1Hex, "deadbeef" * 5),
        (Sha256Hex, VALID_SHA256.upper()),
        (Sha256Hex, VALID_SHA256[:-1]),
        (Sha256Hex, f" {VALID_SHA256}"),
        (Sha256Hex, f"{VALID_SHA256} "),
        (Sha256Hex, "0" * 64),
        (Sha256Hex, "f" * 64),
        (Sha256Hex, "deadbeef" * 8),
    ],
)
def test_sha_hex_value_objects_reject_invalid_and_placeholder_digests(
    value_object: type[Sha1Hex] | type[Sha256Hex], digest: str
) -> None:
    with pytest.raises(ValidationError):
        value_object(value=digest)


@pytest.mark.parametrize(
    ("digest", "length"),
    [
        ("abc", 40),
        (VALID_SHA1.upper(), 40),
        (f" {VALID_SHA1}", 40),
        ("0" * 40, 40),
        ("f" * 40, 40),
        ("deadbeef" * 5, 40),
        (VALID_SHA256[:-1], 64),
        (VALID_SHA256.upper(), 64),
        (f"{VALID_SHA256} ", 64),
        ("0" * 64, 64),
        ("f" * 64, 64),
        ("deadbeef" * 8, 64),
    ],
)
def test_is_placeholder_digest_returns_true_for_malformed_and_placeholder_digests(
    digest: str, length: int
) -> None:
    assert is_placeholder_digest(digest, length=length) is True


@pytest.mark.parametrize(
    ("digest", "length"),
    [
        (VALID_SHA1, 40),
        (VALID_SHA256, 64),
    ],
)
def test_is_placeholder_digest_returns_false_for_realistic_lowercase_hex_digests(
    digest: str, length: int
) -> None:
    assert is_placeholder_digest(digest, length=length) is False
