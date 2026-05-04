from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.contracts.replay import ReplayCaseResult, ReplayImportManifest
from app.core.replay_audit_report import build_replay_audit_report


def _load_manifest(path: Path) -> ReplayImportManifest:
    return ReplayImportManifest.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _load_case_result(path: Path) -> ReplayCaseResult:
    return ReplayCaseResult.model_validate(json.loads(path.read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a replay audit report from replay case results.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--case-result", action="append", default=[])
    parser.add_argument("--report-out", required=True)
    args = parser.parse_args(argv)

    manifest = _load_manifest(Path(args.manifest))
    case_results = [_load_case_result(Path(path)) for path in list(args.case_result or [])]
    report = build_replay_audit_report(manifest=manifest, case_results=case_results)
    report_out = Path(args.report_out)
    report_out.parent.mkdir(parents=True, exist_ok=True)
    payload = report.model_dump(mode="json")
    report_out.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if report.status == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
