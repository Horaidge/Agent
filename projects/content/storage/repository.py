"""Репозиторий сообщений: async-запись (Motor), синхронное чтение для Gradio (PyMongo)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo.collection import Collection

from storage.models import InboundMessageRecord


class MessageRepository:
    """Доступ к коллекции входящих сообщений."""

    def __init__(
        self,
        async_collection: AsyncIOMotorCollection,
        sync_collection: Collection,
    ) -> None:
        self._async = async_collection
        self._sync = sync_collection

    async def save_text_message(
        self,
        *,
        telegram_user_id: int,
        telegram_chat_id: int,
        telegram_message_id: int,
        username: str | None,
        text: str | None,
        raw_update: dict[str, Any] | None = None,
        trace_id: str | None = None,
        message_type: str = "text",
        media: dict[str, Any] | None = None,
    ) -> str:
        doc: dict[str, Any] = {
            "created_at": datetime.now(timezone.utc),
            "telegram_user_id": telegram_user_id,
            "telegram_chat_id": telegram_chat_id,
            "telegram_message_id": telegram_message_id,
            "username": username,
            "text": text,
            "message_type": message_type,
        }
        if media is not None:
            doc["media"] = media
        if raw_update is not None:
            doc["raw_update"] = raw_update
        if trace_id:
            doc["trace_id"] = trace_id

        result = await self._async.insert_one(doc)
        return str(result.inserted_id)

    def list_recent_sync(self, limit: int = 200) -> list[InboundMessageRecord]:
        """Синхронное чтение для Gradio (в том же процессе, что и FastAPI)."""
        cursor = (
            self._sync.find()
            .sort("created_at", -1)
            .limit(max(1, min(limit, 500)))
        )
        out: list[InboundMessageRecord] = []
        for doc in cursor:
            oid = doc.get("_id")
            out.append(
                InboundMessageRecord(
                    id=str(oid) if oid is not None else None,
                    created_at=doc["created_at"],
                    telegram_user_id=doc["telegram_user_id"],
                    telegram_chat_id=doc["telegram_chat_id"],
                    telegram_message_id=doc["telegram_message_id"],
                    username=doc.get("username"),
                    text=doc.get("text"),
                    raw_update=doc.get("raw_update"),
                    trace_id=doc.get("trace_id"),
                    message_type=doc.get("message_type") or "text",
                    media=doc.get("media"),
                )
            )
        return out

    def list_messages_debug_sync(
        self,
        *,
        limit: int = 100,
        telegram_user_id: int | None = None,
        telegram_chat_id: int | None = None,
    ) -> list[InboundMessageRecord]:
        q: dict[str, Any] = {}
        if telegram_user_id is not None:
            q["telegram_user_id"] = telegram_user_id
        if telegram_chat_id is not None:
            q["telegram_chat_id"] = telegram_chat_id
        cur = (
            self._sync.find(q)
            .sort("created_at", -1)
            .limit(max(1, min(limit, 300)))
        )
        out: list[InboundMessageRecord] = []
        for doc in cur:
            oid = doc.get("_id")
            out.append(
                InboundMessageRecord(
                    id=str(oid) if oid is not None else None,
                    created_at=doc["created_at"],
                    telegram_user_id=doc["telegram_user_id"],
                    telegram_chat_id=doc["telegram_chat_id"],
                    telegram_message_id=doc["telegram_message_id"],
                    username=doc.get("username"),
                    text=doc.get("text"),
                    raw_update=doc.get("raw_update"),
                    trace_id=doc.get("trace_id"),
                    message_type=doc.get("message_type") or "text",
                    media=doc.get("media"),
                )
            )
        return out

    async def delete_all_messages(self) -> int:
        """Удалить все документы входящих сообщений (dev-очистка)."""
        r = await self._async.delete_many({})
        return int(getattr(r, "deleted_count", 0) or 0)

    async def delete_by_telegram_user_id(self, telegram_user_id: int) -> int:
        """Удалить все входящие сообщения пользователя (данные бота)."""
        r = await self._async.delete_many({"telegram_user_id": telegram_user_id})
        return int(getattr(r, "deleted_count", 0) or 0)

    def get_message_by_id_sync(self, doc_id: str) -> dict[str, Any] | None:
        """Один документ inbound по _id (строка ObjectId)."""
        try:
            from bson import ObjectId

            oid = ObjectId(doc_id)
        except Exception:  # noqa: BLE001
            return None
        doc = self._sync.find_one({"_id": oid})
        if not doc:
            return None
        out = dict(doc)
        out["_id"] = str(out["_id"])
        if "created_at" in out and hasattr(out["created_at"], "isoformat"):
            out["created_at"] = out["created_at"].isoformat()
        return out


async def ensure_indexes(collection: AsyncIOMotorCollection) -> None:
    """Индекс по времени для сортировки в Gradio (idempotent)."""
    await collection.create_index("created_at")
    await collection.create_index("trace_id")
