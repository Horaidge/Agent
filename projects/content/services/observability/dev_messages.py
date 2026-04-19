"""
Чтение сообщений и трейсов для локальной dev-консоли.

UI не обращается к Mongo напрямую — только через эти функции.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.observability.repository import ObservabilityRepository
from services.llm.system_prompt_loader import system_prompt_preview
from services.observability.chat_trace_service import (
    get_model_calls_for_user,
    get_tool_calls_for_user,
    get_user_dialog_trace,
)
from storage.chat_repository import ChatStoreRepository
from storage.models import InboundMessageRecord
from storage.repository import MessageRepository

_PREVIEW_LEN = 120


def _json_pretty(data: Any) -> str:
    try:
        return json.dumps(data, ensure_ascii=False, indent=2, default=str)
    except TypeError:
        return str(data)


def _infer_message_type(doc: dict[str, Any]) -> str:
    ru = doc.get("raw_update")
    if isinstance(ru, dict):
        if ru.get("photo"):
            return "photo"
        if ru.get("document"):
            return "document"
        if ru.get("voice"):
            return "voice"
    if doc.get("text"):
        return "text"
    return "unknown"


def _resolve_status(trace_id: str | None, obs_repo: ObservabilityRepository) -> str:
    """
    Упрощённая модель: received → processed/error по событиям с тем же trace_id.
    """
    if not trace_id:
        return "received"
    events = obs_repo.list_events_sync(limit=400, trace_id=trace_id)
    for e in events:
        if e.get("event_type") == "error":
            return "error"
        pl = e.get("payload") or {}
        if (
            e.get("event_type") == "pipeline.stage"
            and str(pl.get("status", "")).lower() == "error"
        ):
            return "error"
    for e in events:
        if e.get("event_type") in ("message.persisted", "model.call"):
            return "processed"
        if e.get("event_type") == "pipeline.stage" and (
            e.get("payload") or {}
        ).get("status") in ("ok", "done", "success"):
            return "processed"
    if any(e.get("event_type") == "message.persisted" for e in events):
        return "processed"
    return "received"


@dataclass
class MessageListItemDTO:
    id: str
    created_at_iso: str
    user_id: int
    chat_id: int
    text_preview: str
    message_type: str
    status: str


@dataclass
class MessageDetailDTO:
    id: str
    created_at_iso: str
    telegram_user_id: int
    telegram_chat_id: int
    internal_user_id: Any
    full_text: str | None
    message_type: str
    status: str
    trace_id: str | None
    raw_telegram_json: str
    extracted: dict[str, Any]
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    model_calls: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    # Агент: отдельные коллекции Mongo (conversation_messages, model_calls, tool_calls)
    agent_dialog: list[dict[str, Any]] = field(default_factory=list)
    agent_model_calls: list[dict[str, Any]] = field(default_factory=list)
    agent_tool_calls: list[dict[str, Any]] = field(default_factory=list)
    system_prompt_preview: str = ""


def _infer_message_type_from_record(r: InboundMessageRecord) -> str:
    if r.message_type and r.message_type != "text":
        return r.message_type
    doc = {"text": r.text, "raw_update": r.raw_update}
    return _infer_message_type(doc)


def get_recent_messages(
    message_repo: MessageRepository,
    obs_repo: ObservabilityRepository,
    *,
    limit: int = 100,
) -> list[MessageListItemDTO]:
    rows = message_repo.list_messages_debug_sync(limit=limit)
    out: list[MessageListItemDTO] = []
    for r in rows:
        doc_id = r.id or ""
        text = r.text or ""
        if r.media and r.media.get("file_name"):
            prefix = str(r.media.get("file_name")) + " · "
            text = prefix + text
        preview = text if len(text) <= _PREVIEW_LEN else text[:_PREVIEW_LEN] + "…"
        mt = _infer_message_type_from_record(r)
        st = _resolve_status(r.trace_id, obs_repo)
        out.append(
            MessageListItemDTO(
                id=doc_id,
                created_at_iso=r.created_at.isoformat(),
                user_id=r.telegram_user_id,
                chat_id=r.telegram_chat_id,
                text_preview=preview,
                message_type=mt,
                status=st,
            )
        )
    return out


def get_message_detail(
    message_id: str,
    message_repo: MessageRepository,
    obs_repo: ObservabilityRepository,
    chat_store: ChatStoreRepository | None = None,
) -> MessageDetailDTO | None:
    doc = message_repo.get_message_by_id_sync(message_id)
    if not doc:
        return None

    tid = doc.get("trace_id")
    status = _resolve_status(tid, obs_repo)
    raw = doc.get("raw_update")
    raw_str = _json_pretty(raw if raw is not None else {})

    events = (
        obs_repo.list_events_sync(limit=500, trace_id=tid) if tid else []
    )

    tools: list[dict[str, Any]] = []
    models: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for e in events:
        et = e.get("event_type")
        payload = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        created = e.get("created_at")
        ts = (
            created.isoformat()
            if isinstance(created, datetime)
            else str(created or "")
        )
        base_ev = {"created_at": ts, "event_type": et}
        if et == "tool.call":
            tools.append({**base_ev, **payload})
        elif et == "model.call":
            models.append({**base_ev, **payload})
        elif et == "error":
            errors.append({**base_ev, **(payload or {})})

    tg_uid = int(doc.get("telegram_user_id", 0))
    internal_uid = str(tg_uid)

    agent_dialog: list[dict[str, Any]] = []
    agent_m: list[dict[str, Any]] = []
    agent_t: list[dict[str, Any]] = []
    sp_preview = ""
    if chat_store is not None:
        agent_dialog = get_user_dialog_trace(
            chat_store, internal_uid, conv_limit=60
        )
        agent_m = get_model_calls_for_user(chat_store, internal_uid, limit=25)
        agent_t = get_tool_calls_for_user(chat_store, internal_uid, limit=25)
        if agent_m:
            sp_preview = str(agent_m[0].get("system_prompt_preview") or "")
        if not sp_preview:
            sp_preview = system_prompt_preview(300)

    extracted = {
        "username": doc.get("username"),
        "telegram_message_id": doc.get("telegram_message_id"),
        "mongo_id": doc.get("_id"),
        "trace_id": tid,
        "internal_user_id": internal_uid,
    }

    created = doc.get("created_at")
    if isinstance(created, str):
        created_iso = created
    elif isinstance(created, datetime):
        created_iso = created.isoformat()
    else:
        created_iso = ""

    return MessageDetailDTO(
        id=str(doc.get("_id", message_id)),
        created_at_iso=created_iso,
        telegram_user_id=tg_uid,
        telegram_chat_id=int(doc.get("telegram_chat_id", 0)),
        internal_user_id=doc.get("internal_user_id") or internal_uid,
        full_text=doc.get("text"),
        message_type=_infer_message_type(doc),
        status=status,
        trace_id=tid,
        raw_telegram_json=raw_str,
        extracted=extracted,
        tool_calls=tools,
        model_calls=models,
        errors=errors,
        agent_dialog=agent_dialog,
        agent_model_calls=agent_m,
        agent_tool_calls=agent_t,
        system_prompt_preview=sp_preview,
    )
