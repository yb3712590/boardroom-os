from __future__ import annotations

import json

import pytest

from app.core.runtime_provider_config import (
    OPENAI_COMPAT_PROVIDER_ID,
    RuntimeProviderConfigEntry,
    RuntimeProviderStoredConfig,
)


def _project_init(client, goal: str) -> str:
    response = client.post(
        "/api/v1/commands/project-init",
        json={
            "north_star_goal": goal,
            "hard_constraints": [
                "Keep governance explicit.",
                "Do not move workflow truth into the browser.",
            ],
            "budget_cap": 500000,
            "deadline_at": None,
        },
    )
    assert response.status_code == 200
    return response.json()["causation_hint"].split(":", 1)[1]


def _configure_live_openai_provider(client, *, model: str = "gpt-5.4") -> None:
    client.app.state.runtime_provider_store.save_config(
        RuntimeProviderStoredConfig(
            default_provider_id=OPENAI_COMPAT_PROVIDER_ID,
            providers=[
                RuntimeProviderConfigEntry(
                    provider_id=OPENAI_COMPAT_PROVIDER_ID,
                    adapter_kind="openai_compat",
                    label="OpenAI Compat",
                    enabled=True,
                    base_url="https://api-hk.codex-for.me/v1",
                    api_key="test-key",
                    model=model,
                    timeout_sec=30.0,
                    reasoning_effort="high",
                    capability_tags=["structured_output", "planning", "implementation", "review"],
                    fallback_provider_ids=[],
                )
            ],
            role_bindings=[],
        )
    )


def test_run_board_riddle_drill_generates_chinese_parallel_report_archive_and_board_review(
    client,
    set_ticket_time,
    monkeypatch,
):
    from app.core.board_riddle_drill import run_board_riddle_drill

    set_ticket_time("2026-04-08T10:00:00+08:00")
    workflow_id = _project_init(client, "Board riddle drill")
    _configure_live_openai_provider(client)

    def _fake_provider(config, rendered_payload):
        ticket_id = rendered_payload.meta.ticket_id
        if ticket_id.endswith("ceo_assignments"):
            accepted_employees = rendered_payload.messages[1].content_payload["accepted_employees"]
            assignments = [
                {
                    "employee_id": employee["employee_id"],
                    "question": f"第{index}题：一个会议室里有三盏灯，关掉一盏后还剩几盏亮着？",
                    "expected_answer": "两盏亮着。",
                }
                for index, employee in enumerate(accepted_employees, start=1)
            ]
            return type(
                "ProviderResult",
                (),
                {
                    "response_id": "resp_ceo_assignments",
                    "output_text": '{"bad":"shape"}'
                    + json.dumps(
                        {
                            "summary": "已为每位录用员工生成一题中文脑筋急转弯，并附上中文标准答案。",
                            "assignments": assignments,
                        }
                    ),
                    "selected_payload": {
                        "summary": "已为每位录用员工生成一题中文脑筋急转弯，并附上中文标准答案。",
                        "assignments": assignments,
                    },
                },
            )()

        employee_id = rendered_payload.messages[1].content_payload["employee"]["employee_id"]
        return type(
            "ProviderResult",
            (),
            {
                "response_id": f"resp_{employee_id}",
                "output_text": '{"bad":"shape"}'
                + json.dumps(
                    {
                        "employee_id": employee_id,
                        "answer": "两盏亮着。",
                        "confidence": 0.82,
                    }
                ),
                "selected_payload": {
                    "employee_id": employee_id,
                    "answer": "两盏亮着。",
                    "confidence": 0.82,
                },
            },
        )()

    import app.core.board_riddle_drill as board_riddle_drill_module

    original_selection = board_riddle_drill_module._require_live_openai_selection
    selection_target_refs: list[str] = []

    def _capture_selection_target_ref(repository, store, **kwargs):
        selection_target_refs.append(str(kwargs["target_ref"]))
        return original_selection(repository, store, **kwargs)

    monkeypatch.setattr(board_riddle_drill_module, "invoke_openai_compat_response", _fake_provider)
    monkeypatch.setattr(board_riddle_drill_module, "_require_live_openai_selection", _capture_selection_target_ref)

    report = run_board_riddle_drill(
        client.app.state.repository,
        client.app.state.runtime_provider_store,
        workflow_id=workflow_id,
        requested_headcount=20,
        random_seed=7,
        preferred_provider_id=OPENAI_COMPAT_PROVIDER_ID,
        preferred_model="gpt-5.4",
    )

    assert report["workflow_id"] == workflow_id
    assert report["requested_headcount"] == 20
    assert report["accepted_headcount"] == 20
    assert report["rejected_headcount"] == 4
    assert report["recruitment_attempt_count"] == 24
    assert report["deterministic_fallback_used"] is False
    assert report["board_report"]["status"] == "COMPLETED"
    assert report["board_report"]["completed_answer_count"] == 20
    assert report["board_review"]["status"] == "COMPLETED"
    assert report["board_review"]["review_materials"][0]["archived_only"] is True
    assert report["board_review"]["review_materials"][0]["process_asset_ref"] is None
    assert report["board_review"]["review_materials"][0]["artifact_ref"] == report["process_archive_artifact_ref"]
    assert report["artifact_ref"] == f"art://board-riddle-drill/{workflow_id}/board-report.json"
    assert client.app.state.repository.get_artifact_by_ref(report["artifact_ref"]) is not None
    assert client.app.state.repository.get_artifact_by_ref(report["process_archive_artifact_ref"]) is not None
    assert report["roster"]["accepted"][0]["role_name_zh"]
    assert "中文脑筋急转弯" in report["ceo_assignment_batch"]["summary"]
    assert "前端" in report["roster"]["accepted"][0]["role_name_zh"] or "工程师" in report["roster"]["accepted"][0]["role_name_zh"]
    assert "第1题" in report["employee_runs"][0]["question"]
    assert report["employee_runs"][0]["submitted_answer"] == "两盏亮着。"
    assert report["employee_runs"][0]["dispatch_context"]["employee"]["role_name_zh"]
    assert report["employee_runs"][0]["dispatch_context"]["assignment"]["question"].startswith("第")
    assert not any(target_ref.startswith("role_profile:") for target_ref in selection_target_refs)


def test_run_board_riddle_drill_rejects_local_deterministic_fallback(client, set_ticket_time):
    from app.core.board_riddle_drill import BoardRiddleDrillError, run_board_riddle_drill

    set_ticket_time("2026-04-08T10:00:00+08:00")
    workflow_id = _project_init(client, "Board riddle drill without live provider")

    with pytest.raises(BoardRiddleDrillError) as exc_info:
        run_board_riddle_drill(
            client.app.state.repository,
            client.app.state.runtime_provider_store,
            workflow_id=workflow_id,
            requested_headcount=20,
            random_seed=7,
            preferred_provider_id=OPENAI_COMPAT_PROVIDER_ID,
            preferred_model="gpt-5.4",
        )

    assert exc_info.value.failure_kind == "DETERMINISTIC_FALLBACK_FORBIDDEN"
