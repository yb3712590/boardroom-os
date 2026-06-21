from __future__ import annotations

from boardroom_os.proving.v2_090f_prd_agent_team import _load_v2_090k_run_manifest_artifact
from boardroom_os.workspace.run_manifest_ingestion import ingest_run_manifest_artifact


def _manifest_with_assertion(assertion: dict[str, object]) -> dict[str, object]:
    return {
        "run_manifest_id": "runmanifest.tolerant",
        "workspace_manifest_ref": "workspacemanifest.tolerant",
        "package_contract_ref": "packagecontract.tolerant",
        "package_root": "10-project",
        "commands": [
            {
                "command_id": "cmd.run.backend",
                "kind": "run",
                "label": "Run backend",
                "command": ["python", "-m", "app"],
                "cwd": ".",
            },
            {
                "command_id": "cmd.test.backend",
                "kind": "test",
                "label": "Run tests",
                "command": ["python", "-m", "pytest"],
                "cwd": ".",
            },
        ],
        "service_contracts": [
            {
                "command_id": "cmd.run.backend",
                "role": "backend",
                "env_bindings": {
                    "HOST": {"value_source": "runtime_host"},
                    "PORT": {"value_source": "runtime_port"},
                },
                "readiness_probe": {
                    "method": "GET",
                    "path": "/health",
                    "expect_status": 200,
                },
            }
        ],
        "behavioral_probes": [
            {
                "probe_id": "probe.books",
                "service_command_id": "cmd.run.backend",
                "acceptance_refs": ["AC-BOOKS-LIST"],
                "steps": [
                    {
                        "step_id": "list-books",
                        "method": "GET",
                        "path": "/books",
                        "expect_status": 200,
                        "assertions": [assertion],
                    }
                ],
            }
        ],
    }


def test_unknown_assertion_is_preserved_without_raw_crash() -> None:
    context = ingest_run_manifest_artifact(
        artifact=_manifest_with_assertion(
            {"type": "json_array_contains_field", "path": "$", "field": "title"}
        ),
        source_ref="00-boardroom/generated-run-manifest.json",
        raw_manifest_ref="artifact.run_manifest.generated",
    )

    assert context.ingestion_status == "context_only"
    assert context.raw_assertions[0].raw_type == "json_array_contains_field"
    assert context.raw_assertions[0].raw_payload["field"] == "title"
    assert context.raw_assertions[0].source_ref == (
        "00-boardroom/generated-run-manifest.json#probe.books/list-books/assertions/0"
    )
    assert context.skeleton_summary.behavioral_probe_ids == ("probe.books",)
    assert context.skeleton_summary.step_ids == ("list-books",)


def test_090f_run_manifest_loader_keeps_novel_assertion_as_context_not_crash() -> None:
    manifest, context = _load_v2_090k_run_manifest_artifact(
        _manifest_with_assertion(
            {"type": "json_array_contains_field", "path": "$", "field": "title"}
        ),
        include_ingestion_context=True,
    )

    assert manifest.behavioral_probes[0].steps[0].assertions == ()
    assert context.raw_assertions[0].raw_type == "json_array_contains_field"
    assert context.skeleton_summary.unknown_assertion_count == 1


def test_non_object_assertion_is_preserved_as_raw_context() -> None:
    context = ingest_run_manifest_artifact(
        artifact=_manifest_with_assertion("response includes title"),
        source_ref="00-boardroom/generated-run-manifest.json",
        raw_manifest_ref="artifact.run_manifest.generated",
    )

    assert context.raw_assertions[0].raw_type == "unknown"
    assert context.raw_assertions[0].raw_payload == {"value": "response includes title"}
