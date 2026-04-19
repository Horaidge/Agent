"""Логирование видео/видео-документов в Mongo (inbound_messages) без запуска LLM."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import Message

from services.message_service import MessageService

logger = logging.getLogger(__name__)

router = Router(name="media_inbound_log")


def _video_payload(message: Message) -> dict:
    v = message.video
    if not v:
        return {}
    return {
        "kind": "video",
        "file_id": v.file_id,
        "file_unique_id": v.file_unique_id,
        "file_name": v.file_name,
        "duration_sec": v.duration,
        "width": v.width,
        "height": v.height,
        "mime_type": getattr(v, "mime_type", None) or "video/mp4",
    }


def _document_video_payload(message: Message) -> dict | None:
    d = message.document
    if not d:
        return None
    mime = (d.mime_type or "").lower()
    name = (d.file_name or "").lower()
    if not mime.startswith("video/") and not any(
        name.endswith(ext) for ext in (".mp4", ".mov", ".webm", ".mkv", ".avi")
    ):
        return None
    return {
        "kind": "document_video",
        "file_id": d.file_id,
        "file_unique_id": d.file_unique_id,
        "file_name": d.file_name,
        "mime_type": d.mime_type,
    }


@router.message(F.video)
async def on_video(message: Message, message_service: MessageService) -> None:
    await message_service.handle_inbound_video_or_document(message, media=_video_payload(message))


@router.message(F.document)
async def on_document_maybe_video(message: Message, message_service: MessageService) -> None:
    payload = _document_video_payload(message)
    if not payload:
        return
    await message_service.handle_inbound_video_or_document(message, media=payload)
