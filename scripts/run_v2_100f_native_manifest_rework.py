from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from boardroom_os.proving.v2_100f_native_manifest_rework import (
    EXPECTED_PROVIDERS_CONFIG,
    EXPECTED_ROLES_CONFIG,
    EXPECTED_RUNTIME_CONFIG,
    V2_100FNativeManifestReworkInput,
    V2_100FTerminalStatus,
    run_v2_100f_native_manifest_rework,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run V2-100F native manifest rework proof."
    )
    parser.add_argument("--prd", required=True)
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--env", required=True)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args(argv)

    env_path = Path(args.env)
    env_values = _load_env_file(env_path)
    os.environ.update(env_values)
    _require_expected_config_paths(env_values)

    workspace_root = Path(args.workspace_root)
    output_root = Path(args.output_root)
    if args.reset and workspace_root.exists():
        _clear_directory(workspace_root)
    workspace_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)

    run_manifest_path = output_root / "00-boardroom" / "generated-run-manifest.json"
    if not run_manifest_path.is_file():
        raise SystemExit(
            "generated RunManifest is required at "
            f"{run_manifest_path.as_posix()}"
        )

    result = run_v2_100f_native_manifest_rework(
        V2_100FNativeManifestReworkInput(
            output_root=output_root,
            workspace_root=workspace_root,
            run_manifest_path=run_manifest_path,
            require_real_provider=True,
            deterministic_provider_fixture=False,
            runtime_config_path=env_values["BOARDROOM_RUNTIME_CONFIG"],
            providers_config_path=env_values["BOARDROOM_PROVIDERS_CONFIG"],
            roles_config_path=env_values["BOARDROOM_ROLES_CONFIG"],
        )
    )

    print(f"runtime_config={env_values['BOARDROOM_RUNTIME_CONFIG']}")
    print(f"providers_config={env_values['BOARDROOM_PROVIDERS_CONFIG']}")
    print(f"roles_config={env_values['BOARDROOM_ROLES_CONFIG']}")
    print(f"terminal_status={result.terminal_status.value}")
    print(
        json.dumps(
            result.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    if result.terminal_status is V2_100FTerminalStatus.PASSED:
        return 0
    if result.terminal_status is V2_100FTerminalStatus.REWORK_REQUIRED:
        return 4
    return 5


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise SystemExit(f"env file does not exist: {path.as_posix()}")
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise SystemExit(f"invalid env line: {raw_line}")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            raise SystemExit(f"invalid env key: {raw_line}")
        values[key] = value
    return values


def _require_expected_config_paths(values: dict[str, str]) -> None:
    expected = {
        "BOARDROOM_RUNTIME_CONFIG": EXPECTED_RUNTIME_CONFIG,
        "BOARDROOM_PROVIDERS_CONFIG": EXPECTED_PROVIDERS_CONFIG,
        "BOARDROOM_ROLES_CONFIG": EXPECTED_ROLES_CONFIG,
    }
    for key, expected_value in expected.items():
        actual = values.get(key)
        if actual != expected_value:
            raise SystemExit(
                f"{key} must be {expected_value}, got {actual or '<missing>'}"
            )


def _clear_directory(path: Path) -> None:
    resolved = path.resolve()
    if resolved == Path.cwd().resolve():
        raise SystemExit("refusing to reset current working directory")
    for child in path.iterdir():
        if child.is_dir():
            _clear_directory(child)
            child.rmdir()
        else:
            child.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
