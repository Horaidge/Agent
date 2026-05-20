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
    i = 0
    n = len(history_rows)
    while i < n:
        row = history_rows[i]
        role = row.get("role")
        if role == "user":
            out.append({"role": "user", "content": row.get("text") or ""})
            i += 1
            continue
        if role == "assistant":
            meta = row.get("metadata") or {}
            tc = meta.get("tool_calls")
            if not tc:
                out.append({"role": "assistant", "content": row.get("text") or ""})
                i += 1
                continue

            # OpenAI требует, чтобы assistant.tool_calls сразу сопровождался tool-сообщениями
            # с каждым tool_call_id. Если история битая (обрыв записи), пропускаем этот блок.
            ids_required = {
                str((x or {}).get("id") or "").strip()
                for x in tc
                if isinstance(x, dict) and str((x or {}).get("id") or "").strip()
            }
            if not ids_required:
                logger.warning("Пропуск tool-блока: assistant.tool_calls без валидных id")
                i += 1
                continue
            j = i + 1
            tool_rows: list[dict[str, Any]] = []
            ids_seen: set[str] = set()
            has_bad_tool_row = False
            while j < n:
                rj = history_rows[j]
                if rj.get("role") != "tool":
                    break
                mj = rj.get("metadata") or {}
                tid = str(mj.get("tool_call_id") or "").strip()
                if not tid or tid not in ids_required:
                    has_bad_tool_row = True
                    j += 1
                    continue
                ids_seen.add(tid)
                tool_rows.append(rj)
                j += 1

            if has_bad_tool_row or not ids_required.issubset(ids_seen):
                logger.warning(
                    "Пропуск битого tool-блока: missing=%s bad_tool_rows=%s",
                    sorted(ids_required - ids_seen),
                    has_bad_tool_row,
                )
                i = j
                continue

            item = {"role": "assistant", "tool_calls": tc}
            txt = row.get("text")
            item["content"] = txt if txt else None
            out.append(item)
            for tr in tool_rows:
                tm = tr.get("metadata") or {}
                tid = str(tm.get("tool_call_id") or "").strip()
                out.append(
                    {
                        "role": "tool",
                        "tool_call_id": tid,
                        "content": tr.get("text") or "",
                    }
                )
            i = j
            continue
        if role == "tool":
            # orphan tool (без предшествующего assistant.tool_calls) не отправляем в модель
            i += 1
            continue

        logger.warning("Пропуск неизвестной роли в истории: %s", role)
        i += 1
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
