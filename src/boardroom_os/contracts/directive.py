from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, field_serializer

from boardroom_os.contracts.types import ContractId


class BoardDirectiveSourceType(StrEnum):
    NATURAL_LANGUAGE = "natural_language"
    PRD_FILE = "prd_file"
    HUMAN_REVIEW_UPDATE = "human_review_update"


class BoardDirective(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    board_directive_id: ContractId
    source_type: BoardDirectiveSourceType
    content_ref: ContractId
    received_at: AwareDatetime
    requester_ref: ContractId

    @field_serializer("received_at")
    def _serialize_received_at(self, received_at: datetime) -> str:
        return received_at.isoformat().replace("+00:00", "Z")


class DirectiveRegistry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    directives: tuple[BoardDirective, ...]

    @classmethod
    def from_directives(cls, *directives: BoardDirective) -> Self:
        return cls(directives=directives)

    def contains(self, board_directive_ref: ContractId) -> bool:
        return any(
            directive.board_directive_id == board_directive_ref
            for directive in self.directives
        )
