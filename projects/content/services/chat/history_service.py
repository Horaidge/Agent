"""Сохранение и сборка истории сообщений для OpenAI."""
from __future__ import annotations

import json
import logging
from typing import Any

from storage.chat_repository import ChatStoreRepository

logger = logging.getLogger(__name__)


async def save_user_message(
    store: ChatStoreRepository,
    *,
    internal_user_id: str,
    telegram_user_id: int,
    chat_id: int,
    text: str,
    trace_id: str | None,
    message_type: str = "text",
    metadata: dict[str, Any] | None = None,
) -> str:
    doc = {
        "internal_user_id": internal_user_id,
        "telegram_user_id": telegram_user_id,
        "chat_id": chat_id,
        "role": "user",
        "text": text,
        "message_type": message_type,
        "metadata": metadata or {},
        "trace_id": trace_id,
    }
    return await store.insert_conversation_message(doc)


async def save_assistant_message(
    store: ChatStoreRepository,
    *,
    internal_user_id: str,
    telegram_user_id: int,
    chat_id: int,
    text: str | None,
    trace_id: str | None,
    message_type: str = "text",
    metadata: dict[str, Any] | None = None,
) -> str:
    doc = {
        "internal_user_id": internal_user_id,
        "telegram_user_id": telegram_user_id,
        "chat_id": chat_id,
        "role": "assistant",
        "text": text,
        "message_type": message_type,
        "metadata": metadata or {},
        "trace_id": trace_id,
    }
    return await store.insert_conversation_message(doc)


async def save_tool_message(
    store: ChatStoreRepository,
    *,
    internal_user_id: str,
    telegram_user_id: int,
    chat_id: int,
    tool_call_id: str,
    content: str,
    trace_id: str | None,
) -> str:
    doc = {
        "internal_user_id": internal_user_id,
        "telegram_user_id": telegram_user_id,
        "chat_id": chat_id,
        "role": "tool",
        "text": content,
        "message_type": "tool_result",
        "metadata": {"tool_call_id": tool_call_id},
        "trace_id": trace_id,
    }
    return await store.insert_conversation_message(doc)


def build_model_messages(
    system_prompt: str,
    history_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Собирает список сообщений для OpenAI Chat Completions.
    `history_rows` — документы из conversation_messages (хронологический порядок).
    """
    out: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for row in history_rows:
        role = row.get("role")
        if role == "user":
            out.append({"role": "user", "content": row.get("text") or ""})
        elif role == "assistant":
            meta = row.get("metadata") or {}
            tc = meta.get("tool_calls")
            if tc:
                item = {"role": "assistant", "tool_calls": tc}
                txt = row.get("text")
                item["content"] = txt if txt else None
                out.append(item)
            else:
                out.append(
                    {"role": "assistant", "content": row.get("text") or ""}
                )
        elif role == "tool":
            meta = row.get("metadata") or {}
            tid = meta.get("tool_call_id") or ""
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": tid,
                    "content": row.get("text") or "",
                }
            )
        else:
            logger.warning("Пропуск неизвестной роли в истории: %s", role)
    return out


def tool_calls_to_storage_format(tool_calls: list[Any]) -> list[dict[str, Any]]:
    """Преобразует объекты tool_calls ответа OpenAI в JSON-serializable список."""
    result: list[dict[str, Any]] = []
    for tc in tool_calls:
        if hasattr(tc, "model_dump"):
            result.append(tc.model_dump())
        elif isinstance(tc, dict):
            result.append(tc)
        else:
            result.append(json.loads(json.dumps(tc, default=str)))
    return result
