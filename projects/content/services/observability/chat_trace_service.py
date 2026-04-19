"""
Агрегированное чтение трейса чата для dev UI (sync Mongo, без логики Telegram).

UI не импортирует коллекции напрямую — только этот модуль.
"""
from __future__ import annotations

from typing import Any

from storage.chat_repository import ChatStoreRepository


def get_user_dialog_trace(
    store: ChatStoreRepository,
    internal_user_id: str,
    *,
    conv_limit: int = 50,
) -> list[dict[str, Any]]:
    """Сообщения диалога (хронологически)."""
    return store.list_conversation_sync(internal_user_id, limit=conv_limit)


def get_model_calls_for_user(
    store: ChatStoreRepository,
    internal_user_id: str,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    return store.list_model_calls_sync(internal_user_id, limit=limit)


def get_tool_calls_for_user(
    store: ChatStoreRepository,
    internal_user_id: str,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    return store.list_tool_calls_sync(internal_user_id, limit=limit)
