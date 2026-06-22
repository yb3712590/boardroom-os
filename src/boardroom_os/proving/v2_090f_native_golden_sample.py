from __future__ import annotations

from pathlib import Path
from typing import Callable

from pydantic import BaseModel, ConfigDict

from boardroom_os.orchestration.prd_delivery import (
    PrdDeliveryInput,
    PrdDeliveryResult,
    PrdDeliveryTerminalStatus,
    run_prd_delivery,
)


V2_090F_NATIVE_PRD_PATH = Path("examples/directives/tiny-fullstack-prd.md")
V2_090F_RUNTIME_CONFIG_PATH = Path("config/boardroom-runtime.v2-090f.yaml")
V2_090F_PROVIDERS_CONFIG_PATH = Path("config/boardroom-providers.v2-090f.yaml")
V2_090F_ROLES_CONFIG_PATH = Path("config/boardroom-roles.v2-090f.yaml")
V2_090F_DEFAULT_WORKSPACE_ROOT = Path(
    ".evidence/atomic-agent/v2-090f-native-golden-sample-workspace"
)
V2_090F_DEFAULT_OUTPUT_ROOT = Path("examples/generated-workspaces/tiny-fullstack")


class V2_090FNativeGoldenSampleInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    workspace_root: Path = V2_090F_DEFAULT_WORKSPACE_ROOT
    output_root: Path = V2_090F_DEFAULT_OUTPUT_ROOT
    require_real_provider: bool = True
    reset: bool = False
    publish: bool = False


class V2_090FNativeGoldenSampleResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    delivery_result: PrdDeliveryResult
    done_candidate: bool


V2_090FDeliveryRunner = Callable[[PrdDeliveryInput], PrdDeliveryResult]


def run_v2_090f_native_golden_sample(
    input: V2_090FNativeGoldenSampleInput | None = None,
    *,
    delivery_runner: V2_090FDeliveryRunner = run_prd_delivery,
) -> V2_090FNativeGoldenSampleResult:
    native_input = V2_090FNativeGoldenSampleInput.model_validate(
        input or V2_090FNativeGoldenSampleInput()
    )
    delivery_result = PrdDeliveryResult.model_validate(
        delivery_runner(
            PrdDeliveryInput(
                prd_path=V2_090F_NATIVE_PRD_PATH,
                workspace_root=native_input.workspace_root,
                output_root=native_input.output_root,
                runtime_config_path=V2_090F_RUNTIME_CONFIG_PATH,
                providers_config_path=V2_090F_PROVIDERS_CONFIG_PATH,
                roles_config_path=V2_090F_ROLES_CONFIG_PATH,
                require_real_provider=native_input.require_real_provider,
                reset=native_input.reset,
                publish=native_input.publish,
            )
        )
    )
    return V2_090FNativeGoldenSampleResult(
        delivery_result=delivery_result,
        done_candidate=delivery_result.terminal_status
        in {
            PrdDeliveryTerminalStatus.PASSED_WITHOUT_REWORK,
            PrdDeliveryTerminalStatus.PASSED_AFTER_REWORK,
        },
    )
