from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest
from pydantic import BaseModel

from boardroom_os.audit.replay_bundle import (
    ReplayBundleError,
    ReplayContentHash,
    ReplayManifestEntry,
    replay_bundle_readiness,
)
from tests.closeout.test_replay_bundle import (
    _builder_input,
    _payload_manifest_entries,
    _ticket_created_event,
    _ticket_payload,
    _seat_assigned_event,
    _seat_assignment_payload,
    build_replay_bundle,
)


def _canonical_sha256(value: Any) -> str:
    if isinstance(value, bytes):
        data = value
    elif isinstance(value, str):
        data = value.encode("utf-8")
    else:
        if isinstance(value, BaseModel):
            value = value.model_dump(mode="json")
        data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


class PayloadResolver:
    def __init__(self, payloads: dict[str, Any]) -> None:
        self._payloads = payloads

    def resolve_payload(self, content_ref):
        return self._payloads[content_ref.value]


class FailingPayloadResolver:
    def resolve_payload(self, content_ref):
        raise RuntimeError(f"resolver exploded for {content_ref.value}")


class NonCanonicalPayload:
    pass


def _payloads() -> dict[str, Any]:
    return {
        "payload:ticket-backend-api-created": _ticket_payload(),
        "payload:ticket-backend-api-seat-assigned": _seat_assignment_payload(),
    }


def _entries_for_payloads(payloads: dict[str, Any]) -> tuple[ReplayManifestEntry, ...]:
    events = (_ticket_created_event(), _seat_assigned_event())
    return tuple(
        ReplayManifestEntry(
            manifest_ref=entry.manifest_ref,
            kind=entry.kind,
            content_ref=entry.content_ref,
            sha256=_canonical_sha256(payloads[entry.content_ref.value]),
        )
        for entry in _payload_manifest_entries(events)
    )


def _bundle_with_payload_hashes(payloads: dict[str, Any] | None = None):
    payloads = payloads or _payloads()
    return build_replay_bundle(
        _builder_input(payload_manifest_entries=_entries_for_payloads(payloads))
    )


def test_replay_bundle_readiness_requires_payload_resolver() -> None:
    bundle = build_replay_bundle(_builder_input())

    with pytest.raises(ReplayBundleError, match="payload resolver is required"):
        replay_bundle_readiness(bundle)


def test_replay_bundle_readiness_rejects_missing_payload_content() -> None:
    payloads = _payloads()
    bundle = _bundle_with_payload_hashes(payloads)
    payloads.pop("payload:ticket-backend-api-seat-assigned")

    with pytest.raises(
        ReplayBundleError,
        match="payload content missing for replay manifest entry",
    ):
        replay_bundle_readiness(bundle, payload_resolver=PayloadResolver(payloads))


def test_replay_bundle_readiness_reports_payload_resolver_failures_separately() -> None:
    bundle = _bundle_with_payload_hashes(_payloads())

    with pytest.raises(
        ReplayBundleError,
        match="payload resolver failed for replay manifest entry",
    ):
        replay_bundle_readiness(bundle, payload_resolver=FailingPayloadResolver())


def test_replay_bundle_readiness_preserves_non_canonical_payload_error() -> None:
    payloads = _payloads()
    payloads["payload:ticket-backend-api-created"] = NonCanonicalPayload()
    bundle = build_replay_bundle(_builder_input())

    with pytest.raises(
        ReplayBundleError,
        match="payload content must be canonical JSON serializable",
    ):
        replay_bundle_readiness(bundle, payload_resolver=PayloadResolver(payloads))


def test_replay_bundle_readiness_rejects_payload_sha256_tampering() -> None:
    payloads = _payloads()
    bundle = _bundle_with_payload_hashes(payloads)
    tampered_entries = tuple(
        entry.model_copy(update={"sha256": ReplayContentHash(value=_canonical_sha256("tampered"))})
        if index == 0
        else entry
        for index, entry in enumerate(bundle.payload_manifest.entries)
    )
    tampered_payload_manifest = bundle.payload_manifest.model_copy(
        update={"entries": tampered_entries}
    )
    tampered_hash_manifest = bundle.hash_manifest.model_copy(
        update={
            "payload_manifest_hash": ReplayContentHash(
                value=tampered_payload_manifest.payload_manifest_hash
            )
        }
    )
    tampered_bundle = bundle.model_copy(
        update={
            "payload_manifest": tampered_payload_manifest,
            "hash_manifest": tampered_hash_manifest,
        }
    )

    with pytest.raises(ReplayBundleError, match="payload manifest sha256 mismatch"):
        replay_bundle_readiness(tampered_bundle, payload_resolver=PayloadResolver(payloads))


def test_replay_bundle_readiness_hashes_canonical_json_payload() -> None:
    payloads = {
        "payload:ticket-backend-api-created": {"b": 2, "a": 1},
        "payload:ticket-backend-api-seat-assigned": {"ticket_id": "ticket-backend-api", "seat_ref": "seat-worker-backend"},
    }
    bundle = _bundle_with_payload_hashes(payloads)

    readiness = replay_bundle_readiness(bundle, payload_resolver=PayloadResolver(payloads))

    assert readiness.payload_sha256_verified is True
