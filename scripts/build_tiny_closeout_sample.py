from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from tests.proving.fixtures.tiny_closeout import (
    materialize_tiny_closeout_sample,
)


DEFAULT_OUTPUT_ROOT = Path("examples/generated-workspaces/tiny-fullstack")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the V2-080F tiny closeout golden sample."
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
        help="Validate the existing sample against a fresh deterministic build.",
    )
    args = parser.parse_args(argv)

    try:
        _require_clean_repository_worktree()
        if args.check:
            return _check_sample(args.output_root)
        manifest = materialize_tiny_closeout_sample(args.output_root, clean=True)
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


def _require_clean_repository_worktree() -> None:
    result = subprocess.run(
        ("git", "status", "--porcelain=v1"),
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("git status failed before tiny closeout sample build")
    if result.stdout.strip():
        raise RuntimeError(
            "repository worktree is dirty; commit or clean changes before building "
            "the tiny closeout golden sample"
        )


def _check_sample(output_root: Path) -> int:
    with tempfile.TemporaryDirectory(prefix="boardroom-os-v2080f-sample-") as temp_dir:
        generated_root = Path(temp_dir) / "tiny-fullstack"
        try:
            if output_root.exists():
                _copy_provider_lock(output_root, generated_root)
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


def _copy_provider_lock(source_root: Path, target_root: Path) -> None:
    lock_paths = (
        Path("20-evidence/provider-attempts"),
        Path("20-evidence/provider-artifacts"),
    )
    for relative_path in lock_paths:
        source = source_root / relative_path
        if not source.exists():
            continue
        target = target_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)


def _read_tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


if __name__ == "__main__":
    raise SystemExit(main())
