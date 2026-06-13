from __future__ import annotations

import inspect


def _runner_source() -> str:
    from boardroom_os.proving import v2_090f_prd_agent_team as runner

    return inspect.getsource(runner)


def test_planning_prompt_does_not_hardcode_backend_layout_or_env() -> None:
    from boardroom_os.proving import v2_090f_prd_agent_team as runner

    prompt = runner._direct_planning_prompt("Objective mentions ticket-graph")

    forbidden = (
        "app/server.py",
        "python -m app.server",
        "LIBRARY_API_HOST",
        "LIBRARY_API_PORT",
        "LIBRARY_DB_PATH",
        "backend API, SQLite persistence, static frontend",
    )
    for value in forbidden:
        assert value not in prompt


def test_runner_source_does_not_contain_hard_backend_validator() -> None:
    source = _runner_source()

    assert "_validate_v2_090f_hard_backend_entrypoint" not in source
    assert "hard backend runtime environment" not in source


def test_runner_source_does_not_contain_library_domain_probe() -> None:
    source = _runner_source()

    forbidden = (
        "_probe_v2_090f_crud_workflow",
        "\"/books\"",
        "\"Dune\"",
        "\"Frank Herbert\"",
        "\"checked_out\"",
        "{\"books\": []}",
    )
    for value in forbidden:
        assert value not in source


def test_runner_source_does_not_contain_static_acceptance_or_path_surface_mapping() -> None:
    source = _runner_source()

    forbidden = (
        "_v2_090f_acceptance_refs",
        "_statement_for_acceptance_ref",
        "_acceptance_refs_for_project_path",
        "_source_surface_for_project_path",
        "AC-V2-090F-BACKEND-CRUD",
        "relative.startswith(\"app/\")",
        "relative.startswith(\"static/\")",
    )
    for value in forbidden:
        assert value not in source
