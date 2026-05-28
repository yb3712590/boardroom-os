from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ValidationError

from boardroom_os.contracts.hashes import Sha256Hex

_T = TypeVar("_T")
_NAMESPACE_SEGMENT_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?$")


class NamespacedRefError(ValueError):
    pass


def assert_namespace_segment(value: str, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise NamespacedRefError(f"{field_name} must be str")
    normalized = value.strip()
    if not normalized:
        raise NamespacedRefError(f"{field_name} must not be empty")
    if normalized != value:
        raise NamespacedRefError(f"{field_name} must not contain surrounding whitespace")
    if _NAMESPACE_SEGMENT_PATTERN.fullmatch(normalized) is None:
        raise NamespacedRefError(f"{field_name} must match {_NAMESPACE_SEGMENT_PATTERN.pattern}: {normalized!r}")
    return normalized


def _sha256_digest(value: str | Sha256Hex) -> str:
    if isinstance(value, Sha256Hex):
        return value.value
    try:
        return Sha256Hex(value=value).value
    except (TypeError, ValidationError, ValueError) as error:
        raise NamespacedRefError("content_hash must be a valid sha256") from error


def namespaced_ref(
    *,
    kind: str,
    project_ref: str,
    content_hash: str | Sha256Hex,
    run_id: str | None = None,
    extra_suffix: str | None = None,
) -> str:
    parts = [
        assert_namespace_segment(kind, field_name="kind"),
        assert_namespace_segment(project_ref, field_name="project_ref"),
        _sha256_digest(content_hash)[:12],
    ]
    if run_id is not None:
        parts.append(assert_namespace_segment(run_id, field_name="run_id"))
    if extra_suffix is not None:
        if run_id is None:
            raise NamespacedRefError("extra_suffix requires run_id")
        parts.append(assert_namespace_segment(extra_suffix, field_name="extra_suffix"))
    return ".".join(parts)


def assert_namespaced_ref_binding(
    value: str,
    *,
    kind: str,
    project_ref: str,
    content_hash: str | Sha256Hex,
    run_id: str | None = None,
    extra_suffix: str | None = None,
    field_name: str = "namespaced_ref",
) -> str:
    expected = namespaced_ref(
        kind=kind,
        project_ref=project_ref,
        content_hash=content_hash,
        run_id=run_id,
        extra_suffix=extra_suffix,
    )
    if value != expected:
        raise NamespacedRefError(f"{field_name} namespace binding mismatch")
    return value


def canonical_sort_for_hash(values: Iterable[_T], *, key: Callable[[_T], str]) -> tuple[_T, ...]:
    keyed: list[tuple[str, _T]] = []
    seen: set[str] = set()
    for value in values:
        sort_key = key(value)
        if not isinstance(sort_key, str):
            raise NamespacedRefError(f"canonical_sort_for_hash key must return str, got {type(sort_key).__name__}")
        if sort_key in seen:
            raise NamespacedRefError(f"canonical_sort_for_hash detected duplicate key: {sort_key!r}")
        seen.add(sort_key)
        keyed.append((sort_key, value))
    return tuple(value for _, value in sorted(keyed, key=lambda item: item[0]))


def _canonical_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        field_names = tuple(type(value).model_fields)
        if field_names == ("value",):
            return value.value
        return _canonical_jsonable(value.model_dump(mode="json"))
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, tuple | list):
        return [_canonical_jsonable(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _canonical_jsonable(item) for key, item in value.items()}
    return value


def hash_namespaced_payload(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        raise NamespacedRefError("payload must be dict")
    try:
        encoded = json.dumps(
            _canonical_jsonable(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise NamespacedRefError("payload must be canonical JSON serializable") from error
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "NamespacedRefError",
    "assert_namespaced_ref_binding",
    "assert_namespace_segment",
    "canonical_sort_for_hash",
    "hash_namespaced_payload",
    "namespaced_ref",
]
