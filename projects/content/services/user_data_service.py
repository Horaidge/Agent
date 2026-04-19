"""Операции «мои данные» в Telegram: очистка истории, список/удаление сгенерированных изображений."""
from __future__ import annotations

from typing import Any

from core.observability.repository import ObservabilityRepository
from storage.chat_repository import ChatStoreRepository
from storage.generated_image_repository import GeneratedImageRepository
from storage.repository import MessageRepository


class UserDataService:
    def __init__(
        self,
        message_repo: MessageRepository,
        chat_store: ChatStoreRepository,
        generated_image_repo: GeneratedImageRepository,
        *,
        observability_repo: ObservabilityRepository | None = None,
    ) -> None:
        self._messages = message_repo
        self._chat = chat_store
        self._images = generated_image_repo
        self._obs = observability_repo

    async def clear_bot_history(self, telegram_user_id: int) -> dict[str, int]:
        """Удалить сохранённые сообщения, диалог агента и (если есть) события observability."""
        n_msg = await self._messages.delete_by_telegram_user_id(telegram_user_id)
        conv, mod, tool = await self._chat.delete_for_internal_user(str(telegram_user_id))
        n_obs = 0
        if self._obs is not None:
            n_obs = await self._obs.delete_by_telegram_user_id(telegram_user_id)
        return {
            "inbound_messages": n_msg,
            "conversation_messages": conv,
            "model_calls": mod,
            "tool_calls": tool,
            "observability_events": n_obs,
        }

    async def list_generated_images(
        self,
        telegram_user_id: int,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        return await self._images.list_for_user(telegram_user_id, limit=limit)

    async def delete_all_generated_images(self, telegram_user_id: int) -> int:
        return await self._images.delete_all_for_user(telegram_user_id)
