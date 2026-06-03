from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from tests.proving.fixtures.tiny_closeout import (
    TinyCloseoutSampleManifest,
    _locked_provider_fixture_from_sample,
    materialize_tiny_closeout_sample,
)
from tests.proving.fixtures.tiny_provider_attempts import openai_settings_from_test_env


DEFAULT_OUTPUT_ROOT = Path("examples/generated-workspaces/tiny-fullstack")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the V2-090F tiny live blackbox closeout golden sample."
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Repository-relative sample output root.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate the existing sample against a fresh locked-provider replay.",
    )
    parser.add_argument(
        "--provider-deadline-seconds",
        type=float,
        default=None,
        help=(
            "Maximum wall-clock seconds for provider-backed sample generation "
            "when no valid provider lock is available. Defaults to "
            "BOARDROOM_OPENAI_TIMEOUT_SECONDS from .env.test/.env."
        ),
    )
    parser.add_argument(
        "--_materialize-only",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)

    try:
        if args._materialize_only:
            manifest = materialize_tiny_closeout_sample(
                args.output_root,
                clean=True,
                allow_absolute_output_root=True,
            )
        elif args.check:
            return _check_sample(args.output_root)
        else:
            manifest = _build_sample(
                args.output_root,
                provider_deadline_seconds=args.provider_deadline_seconds,
            )
    except Exception as error:  # pragma: no cover - CLI boundary only.
        print(f"tiny closeout sample build failed: {error}", file=sys.stderr)
        return 1

    print(
        "tiny closeout sample built: "
        f"{manifest.sample_root} "
        f"files={manifest.file_count} "
        f"bytes={manifest.total_bytes} "
        f"sha256={manifest.sha256}"
    )
    return 0


def _check_sample(output_root: Path) -> int:
    with tempfile.TemporaryDirectory(prefix="boardroom-os-v2090f-sample-") as temp_dir:
        generated_root = Path(temp_dir) / "tiny-fullstack"
        try:
            _copy_required_provider_lock(output_root, generated_root)
            expected = materialize_tiny_closeout_sample(
                generated_root,
                clean=True,
                allow_absolute_output_root=True,
            )
        except Exception as error:
            print(f"tiny closeout sample check failed: {error}", file=sys.stderr)
            return 1

        if not output_root.exists():
            print(f"sample output missing: {output_root.as_posix()}", file=sys.stderr)
            return 1
        actual_files = _read_tree(output_root)
        expected_files = _read_tree(generated_root)
        if actual_files != expected_files:
            actual_paths = set(actual_files)
            expected_paths = set(expected_files)
            missing = sorted(expected_paths - actual_paths)
            extra = sorted(actual_paths - expected_paths)
            changed = sorted(
                path
                for path in actual_paths & expected_paths
                if actual_files[path] != expected_files[path]
            )
            print("tiny closeout sample is not current", file=sys.stderr)
            if missing:
                print(f"missing: {missing}", file=sys.stderr)
            if extra:
                print(f"extra: {extra}", file=sys.stderr)
            if changed:
                print(f"changed: {changed}", file=sys.stderr)
            return 1

    print(
        "tiny closeout sample check passed: "
        f"{output_root.as_posix()} "
        f"files={expected.file_count} "
        f"bytes={expected.total_bytes} "
        f"sha256={expected.sha256}"
    )
    return 0


def _build_sample(
    output_root: Path,
    *,
    provider_deadline_seconds: float | None = None,
):
    with tempfile.TemporaryDirectory(prefix="boardroom-os-v2090f-sample-") as temp_dir:
        generated_root = Path(temp_dir) / "tiny-fullstack"
        lock_copied = _copy_valid_provider_lock_if_available(output_root, generated_root)
        if lock_copied:
            manifest = materialize_tiny_closeout_sample(
                generated_root,
                clean=True,
                allow_absolute_output_root=True,
            )
        else:
            manifest = _materialize_provider_backed_sample_with_deadline(
                generated_root,
                timeout_seconds=_provider_deadline_seconds(provider_deadline_seconds),
            )
        _replace_output_root(source_root=generated_root, output_root=output_root)
    return manifest


def _provider_deadline_seconds(explicit_seconds: float | None) -> float:
    if explicit_seconds is not None:
        return explicit_seconds
    return openai_settings_from_test_env().timeout_seconds


def _materialize_provider_backed_sample_with_deadline(
    generated_root: Path,
    *,
    timeout_seconds: float,
) -> TinyCloseoutSampleManifest:
    command = (
        sys.executable,
        str(Path(__file__).resolve()),
        "--output-root",
        str(generated_root),
        "--_materialize-only",
    )
    result = _run_subprocess_with_deadline(
        command,
        timeout_seconds=timeout_seconds,
        error_context="provider-backed sample generation",
    )
    if result.returncode != 0:
        details = (result.stderr or result.stdout).strip()
        raise RuntimeError(
            "provider-backed sample generation failed"
            + (f": {details}" if details else "")
        )
    manifest_path = generated_root / "sample-manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("provider-backed sample generation did not write manifest")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return TinyCloseoutSampleManifest(
        sample_root=payload["sample_root"],
        generated_at=payload["generated_at"],
        run_id=payload["run_id"],
        file_count=payload["file_count"],
        total_bytes=payload["total_bytes"],
        sha256=payload["sha256"],
        files=tuple(payload["files"]),
    )


def _run_subprocess_with_deadline(
    command: tuple[str, ...],
    *,
    timeout_seconds: float,
    error_context: str,
) -> subprocess.CompletedProcess[str]:
    if timeout_seconds <= 0:
        raise ValueError("provider deadline seconds must be positive")
    process = subprocess.Popen(
        command,
        cwd=Path.cwd(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as error:
        _terminate_process_tree(process)
        raise TimeoutError(
            f"{error_context} exceeded deadline of {timeout_seconds:g} seconds"
        ) from error
    return subprocess.CompletedProcess(
        args=command,
        returncode=process.returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if os.name == "nt":
        subprocess.run(
            ("taskkill", "/PID", str(process.pid), "/T", "/F"),
            capture_output=True,
            text=True,
            check=False,
        )
    else:
        process.kill()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _copy_valid_provider_lock_if_available(source_root: Path, target_root: Path) -> bool:
    if not source_root.exists():
        return False
    if _is_v2_080_failure_package(source_root):
        return False
    try:
        provider_fixture = _locked_provider_fixture_from_sample(source_root)
    except ValueError as error:
        raise ValueError(f"provider lock is invalid: {error}") from error
    if provider_fixture is None:
        return False
    _copy_provider_lock(source_root, target_root)
    return True


def _is_v2_080_failure_package(source_root: Path) -> bool:
    run_manifest_path = source_root / "20-evidence/tests/run-manifest.json"
    verification_runs_path = source_root / "20-evidence/tests/verification-runs.json"
    service_runs_path = source_root / "20-evidence/tests/service-runs.json"
    if not run_manifest_path.exists() or not verification_runs_path.exists():
        return False
    try:
        run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
        verification_runs = json.loads(
            verification_runs_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return False
    declared_command_ids = {
        item.get("command_id", {}).get("value")
        for item in run_manifest.get("commands", ())
        if isinstance(item, dict)
    }
    verified_command_ids = {
        item.get("command_id", {}).get("value")
        for item in verification_runs
        if isinstance(item, dict)
    }
    service_command_ids = _service_run_command_ids(service_runs_path)
    if {"run-backend", "run-frontend"}.issubset(service_command_ids):
        return False
    return {"run-backend", "run-frontend"}.issubset(
        declared_command_ids - verified_command_ids
    )


def _service_run_command_ids(service_runs_path: Path) -> set[object]:
    if not service_runs_path.exists():
        return set()
    try:
        service_runs = json.loads(service_runs_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(service_runs, list):
        return set()
    return {
        item.get("command_id", {}).get("value")
        for item in service_runs
        if isinstance(item, dict)
    }


def _copy_required_provider_lock(source_root: Path, target_root: Path) -> None:
    if not source_root.exists():
        raise ValueError(f"provider lock source is missing: {source_root.as_posix()}")
    try:
        provider_fixture = _locked_provider_fixture_from_sample(source_root)
    except Exception as error:
        raise ValueError(f"provider lock is invalid: {error}") from error
    if provider_fixture is None:
        raise ValueError("provider lock is required for --check replay")
    _copy_provider_lock(source_root, target_root)


def _copy_provider_lock(source_root: Path, target_root: Path) -> None:
    lock_paths = (
        Path("20-evidence/provider-attempts"),
        Path("20-evidence/provider-artifacts"),
        Path("30-audit/agent-context-index.json"),
    )
    for relative_path in lock_paths:
        source = source_root / relative_path
        if not source.exists():
            continue
        target = target_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)


def _replace_output_root(*, source_root: Path, output_root: Path) -> None:
    if output_root.exists():
        if not output_root.is_dir():
            raise RuntimeError("sample output root must be a directory")
        shutil.rmtree(output_root)
    output_root.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_root, output_root)


def _read_tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


if __name__ == "__main__":
    raise SystemExit(main())
