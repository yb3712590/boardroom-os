from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.contracts.replay import ReplayImportManifest
from app.core.replay_closeout import (
    REPLAY_IMPORT_ISSUE_CLASSIFICATION,
    failed_closeout_case_result,
    replay_closeout_case,
)


def _load_manifest(path: Path) -> ReplayImportManifest:
    return ReplayImportManifest.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _diagnostic(reason_code: str, message: str, **details) -> dict:
    return {
        "reason_code": reason_code,
        "classification": REPLAY_IMPORT_ISSUE_CLASSIFICATION,
        "message": message,
        **details,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay a closeout case from an imported replay DB.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--replay-db", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--case-out", required=True)
    args = parser.parse_args(argv)

    case_id = str(args.case_id)
    manifest_path = Path(args.manifest)
    replay_db_path = Path(args.replay_db)
    manifest: ReplayImportManifest | None = None
    diagnostics: list[dict] = []
    if not manifest_path.is_file():
        diagnostics.append(
            _diagnostic(
                "manifest_missing",
                "Replay closeout requires an existing ReplayImportManifest JSON file.",
                manifest_path=str(manifest_path),
            )
        )
    else:
        manifest = _load_manifest(manifest_path)
    if not replay_db_path.is_file():
        diagnostics.append(
            _diagnostic(
                "replay_db_missing",
                "Replay closeout requires an imported replay DB.",
                replay_db_path=str(replay_db_path),
            )
        )
    if diagnostics:
        result = failed_closeout_case_result(
            case_id=case_id,
            manifest=manifest,
            diagnostics=diagnostics,
        )
    else:
        result = replay_closeout_case(
            manifest=manifest,
            replay_db_path=replay_db_path,
            case_id=case_id,
        )
    case_out = Path(args.case_out)
    case_out.parent.mkdir(parents=True, exist_ok=True)
    payload = result.model_dump(mode="json")
    case_out.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result.status == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
