from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel
from boardroom_os.contracts.hashes import Sha256Hex
from boardroom_os.contracts.refs import canonical_sort_for_hash, hash_namespaced_payload, namespaced_ref

_HASH_A = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
_HASH_B = "123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0"


class _PayloadKind(StrEnum):
    AUDIT = "audit"


class _PayloadModel(BaseModel):
    ref: str
    kind: _PayloadKind


@dataclass(frozen=True)
class _SortItem:
    ref: str
    payload: str


def test_namespaced_ref_is_deterministic() -> None:
    first = namespaced_ref(kind="replay-bundle", project_ref="project-alpha", content_hash=_HASH_A)
    second = namespaced_ref(kind="replay-bundle", project_ref="project-alpha", content_hash=_HASH_A)
    different_hash = namespaced_ref(kind="replay-bundle", project_ref="project-alpha", content_hash=_HASH_B)

    assert first == second
    assert first == "replay-bundle.project-alpha.0123456789ab"
    assert different_hash == "replay-bundle.project-alpha.123456789abc"
    assert different_hash != first


def test_namespaced_ref_includes_run_id_when_provided() -> None:
    without_run = namespaced_ref(kind="process-audit", project_ref="project-alpha", content_hash=_HASH_A)
    with_run = namespaced_ref(
        kind="process-audit",
        project_ref="project-alpha",
        content_hash=_HASH_A,
        run_id="run-001",
    )

    assert without_run == "process-audit.project-alpha.0123456789ab"
    assert with_run == "process-audit.project-alpha.0123456789ab.run-001"
    assert with_run != without_run


def test_namespaced_ref_accepts_sha256_value_object() -> None:
    digest = Sha256Hex(value=_HASH_A)

    assert namespaced_ref(kind="git-audit", project_ref="project-alpha", content_hash=digest) == (
        "git-audit.project-alpha.0123456789ab"
    )


def test_namespaced_ref_includes_extra_suffix_after_run_id() -> None:
    ref = namespaced_ref(
        kind="process-audit-artifact",
        project_ref="project-alpha",
        content_hash=_HASH_A,
        run_id="run-001",
        extra_suffix="timeline",
    )

    assert ref == "process-audit-artifact.project-alpha.0123456789ab.run-001.timeline"


def test_canonical_sort_for_hash_is_stable_under_reordering() -> None:
    values = (
        _SortItem(ref="verified-evidence.c", payload="third"),
        _SortItem(ref="verified-evidence.a", payload="first"),
        _SortItem(ref="verified-evidence.b", payload="second"),
    )
    reordered = (values[1], values[2], values[0])

    assert canonical_sort_for_hash(values, key=lambda item: item.ref) == canonical_sort_for_hash(
        reordered,
        key=lambda item: item.ref,
    )
    assert [item.ref for item in canonical_sort_for_hash(values, key=lambda item: item.ref)] == [
        "verified-evidence.a",
        "verified-evidence.b",
        "verified-evidence.c",
    ]


def test_canonical_sort_for_hash_preserves_objects_not_keys() -> None:
    first = _SortItem(ref="b", payload="payload-b")
    second = _SortItem(ref="a", payload="payload-a")

    sorted_values = canonical_sort_for_hash((first, second), key=lambda item: item.ref)

    assert sorted_values == (second, first)
    assert sorted_values[0] is second
    assert sorted_values[1] is first
    assert all(isinstance(item, _SortItem) for item in sorted_values)


def test_hash_namespaced_payload_is_stable_under_field_reorder() -> None:
    left = {"a": 1, "b": {"x": "value", "y": [3, 2, 1]}}
    right = {"b": {"y": [3, 2, 1], "x": "value"}, "a": 1}

    assert hash_namespaced_payload(left) == hash_namespaced_payload(right)


def test_hash_namespaced_payload_canonicalizes_models_enums_and_sequences() -> None:
    payload = {
        "model": _PayloadModel(ref="artifact-a", kind=_PayloadKind.AUDIT),
        "tuple_values": (_PayloadKind.AUDIT, "done"),
        "nested": {"kind": _PayloadKind.AUDIT},
    }
    equivalent_payload = {
        "nested": {"kind": "audit"},
        "tuple_values": ["audit", "done"],
        "model": {"ref": "artifact-a", "kind": "audit"},
    }

    assert hash_namespaced_payload(payload) == hash_namespaced_payload(equivalent_payload)


def test_hash_namespaced_payload_round_trips_utf8() -> None:
    payload = {"summary": "事实链", "kind": "process-audit"}

    digest = hash_namespaced_payload(payload)

    assert digest == "321148213db4959473d8329cfadafa6eb2f0dbab16a18f713cea570b5e1070f4"
    assert len(digest) == 64
