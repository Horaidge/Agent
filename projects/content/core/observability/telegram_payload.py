"""Извлечение полей из тела Telegram Update (dict)."""
from __future__ import annotations

from typing import Any


def classify_update_type(body: dict[str, Any]) -> str:
    keys = (
        "message",
        "edited_message",
        "channel_post",
        "edited_channel_post",
        "inline_query",
        "chosen_inline_result",
        "callback_query",
        "shipping_query",
        "pre_checkout_query",
        "poll",
        "poll_answer",
        "my_chat_member",
        "chat_member",
        "chat_join_request",
    )
    for k in keys:
        if k in body and body[k] is not None:
            return k
    return "unknown"


def extract_user_chat_ids(body: dict[str, Any]) -> tuple[int | None, int | None]:
    """telegram_user_id, telegram_chat_id из произвольного update."""
    for key in (
        "message",
        "edited_message",
        "channel_post",
        "edited_channel_post",
        "callback_query",
    ):
        node = body.get(key)
        if not isinstance(node, dict):
            continue
        uid: int | None = None
        cid: int | None = None
        if "from" in node and isinstance(node["from"], dict):
            uid = node["from"].get("id")
        ch = node.get("chat") or {}
        if isinstance(ch, dict):
            cid = ch.get("id")
        if uid is not None or cid is not None:
            return (int(uid) if uid is not None else None, int(cid) if cid is not None else None)
    return (None, None)
