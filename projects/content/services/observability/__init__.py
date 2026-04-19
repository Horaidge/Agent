"""Слой для dev-консоли и наблюдаемости (агрегация без прямого доступа UI к Mongo)."""

from services.observability.dev_messages import (
    MessageDetailDTO,
    MessageListItemDTO,
    get_message_detail,
    get_recent_messages,
)

__all__ = [
    "MessageDetailDTO",
    "MessageListItemDTO",
    "get_message_detail",
    "get_recent_messages",
]
