"""Middleware для внедрения зависимостей в хендлеры."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from services.message_service import MessageService


class MessageServiceMiddleware(BaseMiddleware):
    """Прокидывает MessageService в data хендлера."""

    def __init__(self, message_service: MessageService) -> None:
        super().__init__()
        self._message_service = message_service

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["message_service"] = self._message_service
        return await handler(event, data)
