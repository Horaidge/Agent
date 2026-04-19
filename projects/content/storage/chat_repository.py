"""MongoDB: conversation_messages, model_calls, tool_calls (async запись, sync чтение для dev UI)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo.collection import Collection


class ChatStoreRepository:
    """Хранилище диалога и трейсов вызовов модели/tools."""

    def __init__(
        self,
        conv_async: AsyncIOMotorCollection,
        conv_sync: Collection,
        model_async: AsyncIOMotorCollection,
        model_sync: Collection,
        tool_async: AsyncIOMotorCollection,
        tool_sync: Collection,
    ) -> None:
        self._conv_a = conv_async
        self._conv_s = conv_sync
        self._model_a = model_async
        self._model_s = model_sync
        self._tool_a = tool_async
        self._tool_s = tool_sync

    async def insert_conversation_message(self, doc: dict[str, Any]) -> str:
        d = {**doc, "created_at": datetime.now(timezone.utc)}
        r = await self._conv_a.insert_one(d)
        return str(r.inserted_id)

    async def insert_model_call(self, doc: dict[str, Any]) -> str:
        d = {**doc, "created_at": datetime.now(timezone.utc)}
        r = await self._model_a.insert_one(d)
        return str(r.inserted_id)

    async def insert_tool_call_record(self, doc: dict[str, Any]) -> str:
        d = {**doc, "created_at": datetime.now(timezone.utc)}
        r = await self._tool_a.insert_one(d)
        return str(r.inserted_id)

    async def list_recent_conversation_for_model(
        self,
        internal_user_id: str,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Последние N сообщений в хронологическом порядке (старые → новые)."""
        lim = max(1, min(limit, 100))
        cur = self._conv_a.find({"internal_user_id": internal_user_id}).sort(
            "created_at", -1
        ).limit(lim)
        docs = await cur.to_list(length=lim)
        docs.reverse()
        return docs

    def list_conversation_sync(
        self,
        internal_user_id: str,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Последние N сообщений в хронологическом порядке (старые → новые)."""
        lim = max(1, min(limit, 200))
        cur = (
            self._conv_s.find({"internal_user_id": internal_user_id})
            .sort("created_at", -1)
            .limit(lim)
        )
        rows = list(cur)
        rows.reverse()
        return self._docs_list_from_rows(rows)

    def list_model_calls_sync(
        self,
        internal_user_id: str,
        *,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        cur = (
            self._model_s.find({"internal_user_id": internal_user_id})
            .sort("created_at", -1)
            .limit(max(1, min(limit, 100)))
        )
        return self._docs_list(cur)

    def list_tool_calls_sync(
        self,
        internal_user_id: str,
        *,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        cur = (
            self._tool_s.find({"internal_user_id": internal_user_id})
            .sort("created_at", -1)
            .limit(max(1, min(limit, 100)))
        )
        return self._docs_list(cur)

    @staticmethod
    def _docs_list_from_rows(rows: list[Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for doc in rows:
            d = dict(doc)
            oid = d.pop("_id", None)
            d["_id"] = str(oid) if oid is not None else None
            ca = d.get("created_at")
            if hasattr(ca, "isoformat"):
                d["created_at"] = ca.isoformat()
            out.append(d)
        return out

    @staticmethod
    def _docs_list(cur: Any) -> list[dict[str, Any]]:
        return ChatStoreRepository._docs_list_from_rows(list(cur))

    async def delete_all(self) -> tuple[int, int, int]:
        """Удалить все сообщения диалога, model_calls и tool_calls (dev «очистить всё»)."""
        r1 = await self._conv_a.delete_many({})
        r2 = await self._model_a.delete_many({})
        r3 = await self._tool_a.delete_many({})
        return (
            int(getattr(r1, "deleted_count", 0) or 0),
            int(getattr(r2, "deleted_count", 0) or 0),
            int(getattr(r3, "deleted_count", 0) or 0),
        )

    async def delete_for_internal_user(self, internal_user_id: str) -> tuple[int, int, int]:
        """Удалить переписку и трейсы агента для одного пользователя."""
        q = {"internal_user_id": internal_user_id}
        r1 = await self._conv_a.delete_many(q)
        r2 = await self._model_a.delete_many(q)
        r3 = await self._tool_a.delete_many(q)
        return (
            int(getattr(r1, "deleted_count", 0) or 0),
            int(getattr(r2, "deleted_count", 0) or 0),
            int(getattr(r3, "deleted_count", 0) or 0),
        )


async def ensure_chat_indexes(
    conv: AsyncIOMotorCollection,
    model: AsyncIOMotorCollection,
    tool: AsyncIOMotorCollection,
) -> None:
    await conv.create_index([("internal_user_id", 1), ("created_at", 1)])
    await model.create_index([("internal_user_id", 1), ("created_at", -1)])
    await tool.create_index([("internal_user_id", 1), ("created_at", -1)])
