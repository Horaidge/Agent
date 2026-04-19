"""События observability (payload хранится как dict в MongoDB)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ObservabilityEventType = Literal[
    "telegram.update",
    "message.normalized",
    "message.persisted",
    "pipeline.stage",
    "model.call",
    "tool.call",
    "mongo.write",
    "error",
]


class ObservabilityEventDoc(BaseModel):
    """Документ в коллекции observability_events."""

    trace_id: str
    created_at: datetime
    event_type: str
    telegram_update_id: int | None = None
    telegram_user_id: int | None = None
    telegram_chat_id: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
