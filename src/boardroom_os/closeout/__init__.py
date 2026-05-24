from boardroom_os.closeout.gate import (
    CloseoutCommandEvidenceBinding,
    CloseoutGate,
    CloseoutGateBlocker,
    CloseoutGateBlockerCode,
    CloseoutGateBlockerRef,
    CloseoutGateError,
    CloseoutGateInput,
    CloseoutGateResult,
    CloseoutGateResultRef,
    CloseoutGateVerdict,
    EventRangeRef,
    GitAuditReadiness,
    GitCommitSha,
    ProcessAuditArtifactPath,
    ProcessAuditReadiness,
    ProjectionVersionRef,
    ReplayBundleReadiness,
    ReplaySummaryHash,
    SourceInventoryHash,
)

_CLOSEOUT_PACKAGE_EXPORTS = {
    "CloseoutPackage",
    "CloseoutPackageBuilderInput",
    "CloseoutPackageCheckedRef",
    "CloseoutPackageError",
    "CloseoutPackageRef",
    "CloseoutPackageVerdict",
    "build_closeout_package",
}


def __getattr__(name: str) -> object:
    if name in _CLOSEOUT_PACKAGE_EXPORTS:
        from boardroom_os.closeout import package as closeout_package

        return getattr(closeout_package, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "CloseoutCommandEvidenceBinding",
    "CloseoutGate",
    "CloseoutGateBlocker",
    "CloseoutGateBlockerCode",
    "CloseoutGateBlockerRef",
    "CloseoutGateError",
    "CloseoutGateInput",
    "CloseoutGateResult",
    "CloseoutGateResultRef",
    "CloseoutGateVerdict",
    "EventRangeRef",
    "GitAuditReadiness",
    "GitCommitSha",
    "ProcessAuditArtifactPath",
    "ProcessAuditReadiness",
    "ProjectionVersionRef",
    "ReplayBundleReadiness",
    "ReplaySummaryHash",
    "SourceInventoryHash",
    "CloseoutPackage",
    "CloseoutPackageBuilderInput",
    "CloseoutPackageCheckedRef",
    "CloseoutPackageError",
    "CloseoutPackageRef",
    "CloseoutPackageVerdict",
    "build_closeout_package",
]
