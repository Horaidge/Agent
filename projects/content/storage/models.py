"""Модели данных для хранения входящих сообщений."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class InboundMessageRecord(BaseModel):
    """Запись о входящем сообщении из Telegram (для MongoDB и Gradio)."""

    id: str | None = Field(default=None, description="MongoDB _id как строка")
    created_at: datetime
    telegram_user_id: int
    telegram_chat_id: int
    telegram_message_id: int
    username: str | None = None
    text: str | None = None
    raw_update: dict[str, Any] | None = Field(
        default=None,
        description="Сырой update (опционально, для отладки / будущего pipeline)",
    )
    trace_id: str | None = Field(
        default=None,
        description="Связка с observability (webhook → обработка)",
    )
    message_type: str | None = Field(
        default="text",
        description="text | video | document_video и т.п.",
    )
    media: dict[str, Any] | None = Field(
        default=None,
        description="Метаданные вложения (имя файла, file_id, без бинарника)",
    )
