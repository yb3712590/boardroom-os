from __future__ import annotations

import pytest
from pydantic import ValidationError

from boardroom_os.evidence.live_blackbox import build_live_blackbox_evidence_from_manifest_context
from boardroom_os.workspace.run_manifest_ingestion import (
    RunManifestIngestionContext,
    ingest_run_manifest_artifact,
)
from tests.workspace.test_run_manifest_tolerant_ingestion import _manifest_with_assertion


def test_unknown_assertion_context_is_not_evidence() -> None:
    context = ingest_run_manifest_artifact(
        artifact=_manifest_with_assertion({"type": "json_array_contains_field"}),
        source_ref="00-boardroom/generated-run-manifest.json",
        raw_manifest_ref="artifact.run_manifest.generated",
    )

    with pytest.raises(ValueError, match="raw manifest context is not verified evidence"):
        build_live_blackbox_evidence_from_manifest_context(context)


@pytest.mark.parametrize(
    "forbidden_field",
    ("passed", "verified", "satisfied", "evidence_ref", "closeout_ready"),
)
def test_run_manifest_ingestion_context_rejects_success_claim_fields(
    forbidden_field: str,
) -> None:
    context = ingest_run_manifest_artifact(
        artifact=_manifest_with_assertion({"type": "json_array_contains_field"}),
        source_ref="00-boardroom/generated-run-manifest.json",
        raw_manifest_ref="artifact.run_manifest.generated",
    )
    fields = context.model_dump(mode="json") | {forbidden_field: True}

    with pytest.raises(ValidationError):
        RunManifestIngestionContext.model_validate(fields)


def test_manifest_ingestion_requires_raw_manifest_ref() -> None:
    with pytest.raises(ValueError, match="raw_manifest_ref"):
        ingest_run_manifest_artifact(
            artifact=_manifest_with_assertion({"type": "json_array_contains_field"}),
            source_ref="00-boardroom/generated-run-manifest.json",
            raw_manifest_ref=" ",
        )
