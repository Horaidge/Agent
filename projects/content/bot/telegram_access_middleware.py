"""Middleware ограничения доступа к Telegram-боту по allowlist."""
from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

from core.config.settings import Settings
from storage.telegram_access_repository import TelegramAccessRepository


class TelegramAccessMiddleware(BaseMiddleware):
    def __init__(
        self,
        settings: Settings,
        *,
        access_repo: TelegramAccessRepository | None = None,
        cache_ttl_sec: float = 3.0,
    ) -> None:
        super().__init__()
        self._settings = settings
        self._repo = access_repo
        self._cache_ttl_sec = max(0.5, float(cache_ttl_sec))
        self._cache_until = 0.0
        self._cached_enabled = bool(settings.telegram_access_allowlist_enabled)
        self._cached_ids = set(settings.telegram_allowed_user_ids_set())

    def _refresh_policy_if_needed(self) -> None:
        now = time.time()
        if now < self._cache_until:
            return
        enabled = bool(self._settings.telegram_access_allowlist_enabled)
        ids = set(self._settings.telegram_allowed_user_ids_set())
        if self._repo is not None:
            try:
                p = self._repo.get_policy_sync()
                enabled = bool(p.get("enabled", enabled))
                ids = set(int(x) for x in list(p.get("user_ids") or []))
            except Exception:
                pass
        self._cached_enabled = enabled
        self._cached_ids = ids
        self._cache_until = now + self._cache_ttl_sec

    def _user_allowed(self, user_id: int) -> bool:
        self._refresh_policy_if_needed()
        if not self._cached_enabled:
            return True
        if not self._cached_ids:
            return False
        return int(user_id) in self._cached_ids

    @staticmethod
    def _extract_user_id(event: TelegramObject) -> int | None:
        if isinstance(event, Message) and event.from_user:
            return int(event.from_user.id)
        if isinstance(event, CallbackQuery) and event.from_user:
            return int(event.from_user.id)
        if isinstance(event, Update):
            if event.message and event.message.from_user:
                return int(event.message.from_user.id)
            if event.callback_query and event.callback_query.from_user:
                return int(event.callback_query.from_user.id)
            if event.edited_message and event.edited_message.from_user:
                return int(event.edited_message.from_user.id)
            if event.inline_query and event.inline_query.from_user:
                return int(event.inline_query.from_user.id)
            if event.chosen_inline_result and event.chosen_inline_result.from_user:
                return int(event.chosen_inline_result.from_user.id)
        if getattr(event, "from_user", None) is not None:
            try:
                return int(getattr(event, "from_user").id)
            except Exception:
                return None
        return None

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        uid = self._extract_user_id(event)
        if uid is None or uid <= 0:
            return await handler(event, data)
        if self._user_allowed(uid):
            return await handler(event, data)
        denial_text = "Доступ к боту закрыт: вы не в allowlist."
        if isinstance(event, Message):
            try:
                await event.answer(denial_text)
            except Exception:
                pass
            return None
        if isinstance(event, CallbackQuery):
            try:
                await event.answer(denial_text, show_alert=True)
            except Exception:
                pass
            return None
        return None
