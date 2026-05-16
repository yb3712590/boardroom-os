"""Agent role, skill, seat, and execution profile models."""

from boardroom_os.agents.policy import (
    BootstrapGovernanceAuthority,
    GovernanceAuthorityProjection,
    GovernanceAuthorityProjector,
    RoleProfileChange,
    RoleProfileChangeAction,
    RoleProfileProjection,
    SeatPolicy,
    SeatPolicyError,
    SeatPolicyMatch,
)
from boardroom_os.agents.profiles import (
    ModelExecutionProfile,
    ModelExecutionProfileId,
    ModelExecutionProfileRegistry,
    RoleProfile,
    RoleProfileRegistry,
)
from boardroom_os.agents.seat import (
    AgentSeat,
    AgentSeatRef,
    RoleCategory,
    SeatDemand,
    SeatLifecycleAction,
    SeatLifecycleEvent,
    SeatLifecycleProjection,
    SeatLifecycleProjectionError,
    SeatLifecycleProjector,
    SeatLifecycleStatus,
)

__all__ = [
    "AgentSeat",
    "AgentSeatRef",
    "BootstrapGovernanceAuthority",
    "GovernanceAuthorityProjection",
    "GovernanceAuthorityProjector",
    "ModelExecutionProfile",
    "ModelExecutionProfileId",
    "ModelExecutionProfileRegistry",
    "RoleCategory",
    "RoleProfile",
    "RoleProfileChange",
    "RoleProfileChangeAction",
    "RoleProfileProjection",
    "RoleProfileRegistry",
    "SeatDemand",
    "SeatLifecycleAction",
    "SeatLifecycleEvent",
    "SeatLifecycleProjection",
    "SeatLifecycleProjectionError",
    "SeatLifecycleProjector",
    "SeatLifecycleStatus",
    "SeatPolicy",
    "SeatPolicyError",
    "SeatPolicyMatch",
]
