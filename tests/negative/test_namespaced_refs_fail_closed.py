from __future__ import annotations

from dataclasses import dataclass

import pytest

from boardroom_os.contracts.refs import (
    NamespacedRefError,
    assert_namespace_segment,
    canonical_sort_for_hash,
    hash_namespaced_payload,
    namespaced_ref,
)

_VALID_HASH = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"


@dataclass(frozen=True)
class _SortItem:
    key: object
    value: str


def test_namespaced_ref_rejects_empty_kind() -> None:
    with pytest.raises(NamespacedRefError, match="kind must not be empty"):
        namespaced_ref(kind="", project_ref="project-alpha", content_hash=_VALID_HASH)


def test_namespaced_ref_rejects_uppercase_kind() -> None:
    with pytest.raises(NamespacedRefError, match="kind must match"):
        namespaced_ref(kind="Replay-Bundle", project_ref="project-alpha", content_hash=_VALID_HASH)


def test_namespaced_ref_rejects_path_in_kind() -> None:
    with pytest.raises(NamespacedRefError, match="kind must match"):
        namespaced_ref(kind="replay/bundle", project_ref="project-alpha", content_hash=_VALID_HASH)


def test_namespaced_ref_rejects_short_content_hash() -> None:
    with pytest.raises(NamespacedRefError, match="content_hash must be a valid sha256"):
        namespaced_ref(kind="replay-bundle", project_ref="project-alpha", content_hash="abc")


def test_namespaced_ref_rejects_placeholder_content_hash() -> None:
    with pytest.raises(NamespacedRefError, match="content_hash must be a valid sha256"):
        namespaced_ref(kind="replay-bundle", project_ref="project-alpha", content_hash="a" * 64)


def test_namespaced_ref_rejects_uppercase_run_id() -> None:
    with pytest.raises(NamespacedRefError, match="run_id must match"):
        namespaced_ref(
            kind="replay-bundle",
            project_ref="project-alpha",
            content_hash=_VALID_HASH,
            run_id="RUN-001",
        )


def test_namespaced_ref_rejects_extra_suffix_without_run_id() -> None:
    with pytest.raises(NamespacedRefError, match="extra_suffix requires run_id"):
        namespaced_ref(
            kind="process-audit-artifact",
            project_ref="project-alpha",
            content_hash=_VALID_HASH,
            extra_suffix="timeline",
        )


def test_canonical_sort_rejects_duplicate_keys() -> None:
    values = (_SortItem(key="same", value="one"), _SortItem(key="same", value="two"))

    with pytest.raises(NamespacedRefError, match="duplicate key"):
        canonical_sort_for_hash(values, key=lambda item: item.key)  # type: ignore[return-value]


def test_canonical_sort_rejects_non_str_key_return() -> None:
    values = (_SortItem(key=1, value="one"),)

    with pytest.raises(NamespacedRefError, match="key must return str"):
        canonical_sort_for_hash(values, key=lambda item: item.key)  # type: ignore[return-value]


def test_assert_namespace_segment_rejects_leading_dash() -> None:
    with pytest.raises(NamespacedRefError, match="segment must match"):
        assert_namespace_segment("-foo", field_name="segment")


def test_assert_namespace_segment_rejects_trailing_dash() -> None:
    with pytest.raises(NamespacedRefError, match="segment must match"):
        assert_namespace_segment("foo-", field_name="segment")


def test_hash_namespaced_payload_rejects_non_dict_payload() -> None:
    with pytest.raises(NamespacedRefError, match="payload must be dict"):
        hash_namespaced_payload(["not", "a", "dict"])  # type: ignore[arg-type]


def test_hash_namespaced_payload_rejects_non_jsonable_payload() -> None:
    with pytest.raises(NamespacedRefError, match="payload must be canonical JSON serializable"):
        hash_namespaced_payload({"bad": object()})

