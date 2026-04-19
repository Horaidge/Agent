"""Фасад: запись событий наблюдаемости (вызывается из webhook, сервисов, будущего pipeline)."""
from __future__ import annotations

from typing import Any

from core.observability.repository import ObservabilityRepository
from core.observability.sanitize import sanitize_for_debug


class ObservabilityService:
    def __init__(self, repo: ObservabilityRepository) -> None:
        self._repo = repo

    async def record_telegram_update(
        self,
        *,
        trace_id: str,
        raw_body: dict[str, Any],
        update_id: int | None,
        telegram_user_id: int | None,
        telegram_chat_id: int | None,
        update_type: str,
    ) -> None:
        payload = {
            "raw": sanitize_for_debug(raw_body),
            "update_type": update_type,
        }
        await self._repo.insert_event(
            {
                "trace_id": trace_id,
                "event_type": "telegram.update",
                "telegram_update_id": update_id,
                "telegram_user_id": telegram_user_id,
                "telegram_chat_id": telegram_chat_id,
                "payload": payload,
            }
        )

    async def record_message_normalized(
        self,
        *,
        trace_id: str,
        telegram_user_id: int,
        telegram_chat_id: int,
        text: str | None,
        message_type: str,
        status: str = "received",
    ) -> None:
        await self._repo.insert_event(
            {
                "trace_id": trace_id,
                "event_type": "message.normalized",
                "telegram_user_id": telegram_user_id,
                "telegram_chat_id": telegram_chat_id,
                "payload": {
                    "text": (text or "")[:8000],
                    "message_type": message_type,
                    "processing_status": status,
                },
            }
        )

    async def record_message_persisted(
        self,
        *,
        trace_id: str,
        telegram_user_id: int,
        telegram_chat_id: int,
        mongo_document_id: str,
        collection_name: str,
    ) -> None:
        await self._repo.insert_event(
            {
                "trace_id": trace_id,
                "event_type": "message.persisted",
                "telegram_user_id": telegram_user_id,
                "telegram_chat_id": telegram_chat_id,
                "payload": {
                    "mongo_document_id": mongo_document_id,
                    "collection": collection_name,
                },
            }
        )

    async def record_pipeline_stage(
        self,
        *,
        trace_id: str,
        stage: str,
        status: str,
        detail: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        pl: dict[str, Any] = {
            "stage": stage,
            "status": status,
        }
        if detail:
            pl["detail"] = sanitize_for_debug(detail)
        if error:
            pl["error"] = error[:4000]
        await self._repo.insert_event(
            {
                "trace_id": trace_id,
                "event_type": "pipeline.stage",
                "payload": pl,
            }
        )

    async def record_model_call(
        self,
        *,
        trace_id: str,
        system_prompt: str | None,
        user_message: str | None,
        context_excerpt: str | None,
        tools_available: list[str] | None,
        response_text: str | None,
        structured: dict[str, Any] | None = None,
    ) -> None:
        await self._repo.insert_event(
            {
                "trace_id": trace_id,
                "event_type": "model.call",
                "payload": {
                    "system_prompt": (system_prompt or "")[:12000],
                    "user_message": (user_message or "")[:12000],
                    "context_excerpt": (context_excerpt or "")[:12000],
                    "tools_available": tools_available or [],
                    "response_text": (response_text or "")[:12000],
                    "structured": sanitize_for_debug(structured) if structured else None,
                },
            }
        )

    async def record_tool_call(
        self,
        *,
        trace_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None,
        result_excerpt: str | None,
        error: str | None = None,
    ) -> None:
        await self._repo.insert_event(
            {
                "trace_id": trace_id,
                "event_type": "tool.call",
                "payload": {
                    "tool_name": tool_name,
                    "arguments": sanitize_for_debug(arguments or {}),
                    "result_excerpt": (result_excerpt or "")[:8000],
                    "error": (error or "")[:2000] if error else None,
                },
            }
        )

    async def record_mongo_write(
        self,
        *,
        trace_id: str,
        collection: str,
        operation: str,
        document_id: str | None,
        preview: dict[str, Any] | None = None,
    ) -> None:
        await self._repo.insert_event(
            {
                "trace_id": trace_id,
                "event_type": "mongo.write",
                "payload": {
                    "collection": collection,
                    "operation": operation,
                    "document_id": document_id,
                    "preview": sanitize_for_debug(preview) if preview else None,
                },
            }
        )

    async def record_dream_pipeline_event(
        self,
        *,
        trace_id: str,
        event_type: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        """События пайплайна сон→видео (dream.pipeline.*, dream.frame.*, …)."""
        await self._repo.insert_event(
            {
                "trace_id": trace_id,
                "event_type": event_type,
                "payload": sanitize_for_debug(detail or {}),
            }
        )

    async def record_error(
        self,
        *,
        trace_id: str | None,
        where: str,
        message: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        await self._repo.insert_event(
            {
                "trace_id": trace_id or "unknown",
                "event_type": "error",
                "payload": {
                    "where": where,
                    "message": message[:4000],
                    "extra": sanitize_for_debug(extra) if extra else None,
                },
            }
        )
