"""Сервис входящих сообщений: связывает Telegram, хранилище и чат-агента."""
from __future__ import annotations

import logging
from typing import Any

from aiogram.types import Message

from core.observability.context import current_trace_id
from core.observability.service import ObservabilityService
from services.chat.chat_orchestrator import ChatOrchestrator
from services.dreams.dream_orchestrator import DreamPipelineService
from services.telegram_reply_keyboards import main_reply_keyboard
from storage.repository import MessageRepository

logger = logging.getLogger(__name__)


class MessageService:
    """Точка входа для обработки сообщений пользователя (Mongo + оркестратор LLM)."""

    def __init__(
        self,
        repository: MessageRepository,
        observability: ObservabilityService | None = None,
        *,
        chat_orchestrator: ChatOrchestrator | None = None,
        dream_pipeline: DreamPipelineService | None = None,
    ) -> None:
        self._repo = repository
        self._obs = observability
        self._chat = chat_orchestrator
        self._dream = dream_pipeline

    async def handle_inbound_video_or_document(
        self,
        message: Message,
        *,
        media: dict[str, Any],
    ) -> None:
        """Сохранить метаданные видео в inbound_messages (без LLM)."""
        user = message.from_user
        uid = user.id if user else 0
        uname = user.username if user else None
        trace_id = current_trace_id.get()
        caption = (message.caption or "").strip() or None
        mt = str(media.get("kind") or "video")

        raw_update = {
            "message_id": message.message_id,
            "date": message.date.isoformat() if message.date else None,
            "content_type": mt,
        }

        tid = trace_id or "unknown"
        if self._obs:
            await self._obs.record_message_normalized(
                trace_id=tid,
                telegram_user_id=uid,
                telegram_chat_id=message.chat.id,
                text=caption,
                message_type=mt,
                status="processing",
            )

        doc_id = await self._repo.save_text_message(
            telegram_user_id=uid,
            telegram_chat_id=message.chat.id,
            telegram_message_id=message.message_id,
            username=uname,
            text=caption,
            raw_update=raw_update,
            trace_id=trace_id,
            message_type=mt,
            media=media,
        )

        if self._obs and trace_id:
            await self._obs.record_message_persisted(
                trace_id=trace_id,
                telegram_user_id=uid,
                telegram_chat_id=message.chat.id,
                mongo_document_id=doc_id,
                collection_name="inbound_messages",
            )
            preview = (caption or "")[:500]
            if media.get("file_name"):
                preview = f"{media.get('file_name')}|{preview}"
            await self._obs.record_mongo_write(
                trace_id=trace_id,
                collection="inbound_messages",
                operation="insert_one",
                document_id=doc_id,
                preview={
                    "telegram_user_id": uid,
                    "telegram_chat_id": message.chat.id,
                    "text": preview,
                    "message_type": mt,
                },
            )
            await self._obs.record_pipeline_stage(
                trace_id=trace_id,
                stage="inbound_media_saved",
                status="ok",
                detail={"kind": mt},
            )

    async def handle_inbound_message(self, message: Message) -> None:
        user = message.from_user
        uid = user.id if user else 0
        uname = user.username if user else None
        trace_id = current_trace_id.get()

        raw_update = {
            "message_id": message.message_id,
            "date": message.date.isoformat() if message.date else None,
        }

        tid = trace_id or "unknown"
        if self._obs:
            await self._obs.record_message_normalized(
                trace_id=tid,
                telegram_user_id=uid,
                telegram_chat_id=message.chat.id,
                text=message.text,
                message_type="text",
                status="processing",
            )

        doc_id = await self._repo.save_text_message(
            telegram_user_id=uid,
            telegram_chat_id=message.chat.id,
            telegram_message_id=message.message_id,
            username=uname,
            text=message.text,
            raw_update=raw_update,
            trace_id=trace_id,
        )

        if self._obs and trace_id:
            await self._obs.record_message_persisted(
                trace_id=trace_id,
                telegram_user_id=uid,
                telegram_chat_id=message.chat.id,
                mongo_document_id=doc_id,
                collection_name="inbound_messages",
            )
            await self._obs.record_mongo_write(
                trace_id=trace_id,
                collection="inbound_messages",
                operation="insert_one",
                document_id=doc_id,
                preview={
                    "telegram_user_id": uid,
                    "telegram_chat_id": message.chat.id,
                    "text": (message.text or "")[:500],
                },
            )
            await self._obs.record_pipeline_stage(
                trace_id=trace_id,
                stage="inbound_saved",
                status="ok",
                detail={"note": "chat orchestrator"},
            )

        if self._dream:
            try:
                if await self._dream.detect_intent_and_maybe_start(message):
                    return
            except Exception:
                logger.exception("DreamPipeline intent detection/launch failed")
                if self._obs and trace_id:
                    await self._obs.record_error(
                        trace_id=trace_id,
                        where="MessageService.dream_pipeline",
                        message="Ошибка dream pipeline",
                    )
                try:
                    await message.answer(
                        "Не удалось обработать запрос визуализации сна. Попробуйте позже.",
                        reply_markup=main_reply_keyboard(),
                    )
                except Exception:
                    logger.exception("Не удалось отправить сообщение об ошибке dream")
                return

        if self._chat:
            try:
                await self._chat.handle_user_message(message, trace_id=trace_id)
            except Exception:
                logger.exception("ChatOrchestrator failed")
                if self._obs and trace_id:
                    await self._obs.record_error(
                        trace_id=trace_id,
                        where="MessageService.chat_orchestrator",
                        message="Ошибка оркестратора чата",
                    )
                try:
                    await message.answer(
                        "Не удалось обработать сообщение (внутренняя ошибка). "
                        "Попробуйте ещё раз или проверьте логи сервера.",
                        reply_markup=main_reply_keyboard(),
                    )
                except Exception:
                    logger.exception("Не удалось отправить сообщение об ошибке в Telegram")
