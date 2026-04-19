"""Внедряет UserDataService в обработчики меню."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from services.user_data_service import UserDataService


class UserDataServiceMiddleware(BaseMiddleware):
    def __init__(self, user_data_service: UserDataService) -> None:
        super().__init__()
        self._svc = user_data_service

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["user_data_service"] = self._svc
        return await handler(event, data)
