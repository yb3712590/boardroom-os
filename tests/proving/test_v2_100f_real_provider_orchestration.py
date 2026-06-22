from __future__ import annotations

import os
from pathlib import Path

import pytest

from boardroom_os.proving.v2_100f_native_manifest_rework import (
    V2_100FNativeManifestReworkInput,
    V2_100FTerminalStatus,
    run_v2_100f_native_manifest_rework,
)
from tests.proving.test_v2_100f_native_orchestration import _manifest_with_novel_assertion


def _real_provider_env_ready() -> bool:
    return (
        os.environ.get("BOARDROOM_RUN_REAL_PROVIDER_TESTS") == "1"
        and os.environ.get("BOARDROOM_RUN_REAL_PROVIDER_PROVING") == "1"
        and bool(os.environ.get("OPENAI_API_KEY"))
        and os.environ.get("BOARDROOM_RUNTIME_CONFIG")
        == "config/boardroom-runtime.v2-090f.yaml"
        and os.environ.get("BOARDROOM_PROVIDERS_CONFIG")
        == "config/boardroom-providers.v2-090f.yaml"
        and os.environ.get("BOARDROOM_ROLES_CONFIG")
        == "config/boardroom-roles.v2-090f.yaml"
    )


@pytest.mark.skipif(
    not _real_provider_env_ready(),
    reason="V2-100F real provider proof requires explicit opt-in env",
)
def test_v2_100f_real_provider_orchestration_reaches_typed_terminal_status(
    tmp_path: Path,
) -> None:
    result = run_v2_100f_native_manifest_rework(
        V2_100FNativeManifestReworkInput(
            output_root=tmp_path / "output",
            workspace_root=tmp_path / "workspace",
            run_manifest_artifact=_manifest_with_novel_assertion(),
            require_real_provider=True,
            deterministic_provider_fixture=False,
            http_status=404,
            runtime_config_path=os.environ["BOARDROOM_RUNTIME_CONFIG"],
            providers_config_path=os.environ["BOARDROOM_PROVIDERS_CONFIG"],
            roles_config_path=os.environ["BOARDROOM_ROLES_CONFIG"],
        )
    )

    assert result.terminal_status in {
        V2_100FTerminalStatus.PASSED,
        V2_100FTerminalStatus.REWORK_REQUIRED,
        V2_100FTerminalStatus.BLOCKED_OR_ESCALATED,
    }
    assert "json_array_contains_field" in result.raw_assertion_types
    assert result.raw_error is None
