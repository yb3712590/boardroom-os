from __future__ import annotations

from app.contracts.common import StrictModel
from app.core.constants import (
    EVENT_BOARD_REVIEW_REQUIRED,
    EVENT_GRAPH_PATCH_APPLIED,
    EVENT_INCIDENT_CLOSED,
    EVENT_INCIDENT_OPENED,
    EVENT_TICKET_EXECUTION_PRECONDITION_BLOCKED,
    EVENT_TICKET_EXECUTION_PRECONDITION_CLEARED,
)


class GraphHealthPolicy(StrictModel):
    bottleneck_multiplier: int
    fanout_too_wide_threshold: int
    critical_path_too_deep_threshold: int
    freeze_spread_ratio_threshold: float
    graph_thrashing_threshold: int
    graph_thrashing_window: int
    persistent_failure_zone_threshold: int
    persistent_failure_zone_window: int
    queue_starvation_multiplier: int
    ready_blocked_thrashing_threshold: int
    ready_blocked_thrashing_window: int
    ready_node_stale_multiplier: int
    cross_version_sla_multiplier: int
    cross_version_sla_version_delta_threshold: int
    ready_blocked_event_types: tuple[str, ...]
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
    queue_starvation_multiplier=3,
    ready_blocked_thrashing_threshold=3,
    ready_blocked_thrashing_window=24,
    ready_node_stale_multiplier=2,
    cross_version_sla_multiplier=2,
    cross_version_sla_version_delta_threshold=3,
    ready_blocked_event_types=(
        EVENT_TICKET_EXECUTION_PRECONDITION_BLOCKED,
        EVENT_TICKET_EXECUTION_PRECONDITION_CLEARED,
        EVENT_BOARD_REVIEW_REQUIRED,
        EVENT_INCIDENT_OPENED,
        EVENT_INCIDENT_CLOSED,
        EVENT_GRAPH_PATCH_APPLIED,
    ),
    finding_severities={
        "FANOUT_TOO_WIDE": "WARNING",
        "BOTTLENECK_DETECTED": "WARNING",
        "CRITICAL_PATH_TOO_DEEP": "WARNING",
        "ORPHAN_SUBGRAPH": "CRITICAL",
        "PERSISTENT_FAILURE_ZONE": "CRITICAL",
        "FREEZE_SPREAD_TOO_WIDE": "WARNING",
        "GRAPH_THRASHING": "CRITICAL",
        "QUEUE_STARVATION": "CRITICAL",
        "READY_BLOCKED_THRASHING": "WARNING",
        "READY_NODE_STALE": "WARNING",
        "CROSS_VERSION_SLA_BREACH": "CRITICAL",
    },
)
