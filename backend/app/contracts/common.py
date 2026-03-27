from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectionEnvelopeBase(StrictModel):
    schema_version: str
    generated_at: datetime
    projection_version: int
    cursor: str | None


JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None
