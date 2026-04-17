from __future__ import annotations

from app.contracts.common import StrictModel
class GraphHealthPolicy(StrictModel):
    bottleneck_multiplier: int
    fanout_too_wide_threshold: int
    critical_path_too_deep_threshold: int
    freeze_spread_ratio_threshold: float
    graph_thrashing_threshold: int
    graph_thrashing_window: int
    persistent_failure_zone_threshold: int
    persistent_failure_zone_window: int
    finding_severities: dict[str, str]


DEFAULT_GRAPH_HEALTH_POLICY = GraphHealthPolicy(
    bottleneck_multiplier=3,
    fanout_too_wide_threshold=10,
    critical_path_too_deep_threshold=15,
    freeze_spread_ratio_threshold=0.3,
    graph_thrashing_threshold=3,
    graph_thrashing_window=10,
    persistent_failure_zone_threshold=3,
    persistent_failure_zone_window=10,
    finding_severities={
        "FANOUT_TOO_WIDE": "WARNING",
        "BOTTLENECK_DETECTED": "WARNING",
        "CRITICAL_PATH_TOO_DEEP": "WARNING",
        "ORPHAN_SUBGRAPH": "CRITICAL",
        "PERSISTENT_FAILURE_ZONE": "CRITICAL",
        "FREEZE_SPREAD_TOO_WIDE": "WARNING",
        "GRAPH_THRASHING": "CRITICAL",
    },
)
