from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.contracts.replay import ReplayImportManifest
from app.core.replay_import import import_replay_bundle


def _load_expected_manifest(path: Path | None) -> ReplayImportManifest | None:
    if path is None:
        return None
    return ReplayImportManifest.model_validate(json.loads(path.read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import a replay DB/artifact/log bundle and emit a stable manifest.")
    parser.add_argument("--source-db", required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--log-ref", action="append", default=[])
    parser.add_argument("--target-dir", required=True)
    parser.add_argument("--manifest-out", required=True)
    parser.add_argument("--expected-manifest")
    args = parser.parse_args(argv)

    target_dir = Path(args.target_dir)
    target_db_path = target_dir / "replay-import.db"
    expected_manifest_path = Path(args.expected_manifest) if args.expected_manifest else None
    manifest = import_replay_bundle(
        source_db_path=Path(args.source_db),
        artifact_root=Path(args.artifact_root),
        log_refs=[Path(path) for path in args.log_ref],
        target_db_path=target_db_path,
        expected_manifest=_load_expected_manifest(expected_manifest_path),
    )
    manifest_out = Path(args.manifest_out)
    manifest_out.parent.mkdir(parents=True, exist_ok=True)
    manifest_out.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if manifest.status == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
