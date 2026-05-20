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

    async def count_conversation_for_internal_user(self, internal_user_id: str) -> int:
        return await self._conv_a.count_documents({"internal_user_id": internal_user_id})

    def aggregate_tool_stats_global_sync(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Группировка по tool_name: total, success count, last_used (для Dev Tools UI)."""
        m: dict[str, Any] = {}
        if since is not None or until is not None:
            r: dict[str, Any] = {}
            if since is not None:
                r["$gte"] = since
            if until is not None:
                r["$lte"] = until
            m["created_at"] = r
        pipeline: list[dict[str, Any]] = [
            {"$match": m},
            {
                "$group": {
                    "_id": "$tool_name",
                    "total": {"$sum": 1},
                    "ok": {"$sum": {"$cond": ["$success", 1, 0]}},
                    "last_used": {"$max": "$created_at"},
                }
            },
        ]
        out: list[dict[str, Any]] = []
        for row in self._tool_s.aggregate(pipeline):
            lu = row.get("last_used")
            ok = int(row.get("ok") or 0)
            tot = int(row.get("total") or 0)
            out.append(
                {
                    "tool_name": row.get("_id") or "unknown",
                    "total": tot,
                    "success": ok,
                    "last_used": lu,
                }
            )
        return out

    def aggregate_model_token_usage_global_sync(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> dict[str, Any]:
        """Сумма токенов по model_calls (поле usage.*), глобально за период."""
        m: dict[str, Any] = {}
        if since is not None or until is not None:
            r: dict[str, Any] = {}
            if since is not None:
                r["$gte"] = since
            if until is not None:
                r["$lte"] = until
            m["created_at"] = r
        pipeline: list[dict[str, Any]] = [
            {"$match": m},
            {
                "$group": {
                    "_id": None,
                    "calls": {"$sum": 1},
                    "prompt_tokens": {"$sum": {"$ifNull": ["$usage.prompt_tokens", 0]}},
                    "completion_tokens": {
                        "$sum": {"$ifNull": ["$usage.completion_tokens", 0]}
                    },
                    "total_tokens": {"$sum": {"$ifNull": ["$usage.total_tokens", 0]}},
                }
            },
        ]
        rows = list(self._model_s.aggregate(pipeline))
        if not rows:
            return {
                "calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }
        row = rows[0]
        return {
            "calls": int(row.get("calls") or 0),
            "prompt_tokens": int(row.get("prompt_tokens") or 0),
            "completion_tokens": int(row.get("completion_tokens") or 0),
            "total_tokens": int(row.get("total_tokens") or 0),
        }

    def list_tool_calls_global_sync(
        self,
        *,
        limit: int = 80,
        since: datetime | None = None,
        until: datetime | None = None,
        tool_name: str | None = None,
        internal_user_id: str | None = None,
        only_failed: bool = False,
    ) -> list[dict[str, Any]]:
        q: dict[str, Any] = {}
        if since is not None or until is not None:
            r: dict[str, Any] = {}
            if since is not None:
                r["$gte"] = since
            if until is not None:
                r["$lte"] = until
            q["created_at"] = r
        if tool_name:
            q["tool_name"] = tool_name
        if internal_user_id:
            q["internal_user_id"] = internal_user_id
        if only_failed:
            q["success"] = False
        lim = max(1, min(limit, 300))
        cur = self._tool_s.find(q).sort("created_at", -1).limit(lim)
        return self._docs_list(cur)

    def get_tool_call_by_id_sync(self, doc_id: str) -> dict[str, Any] | None:
        """Один документ tool_calls по строковому _id."""
        from bson import ObjectId
        from bson.errors import InvalidId

        try:
            oid = ObjectId(doc_id)
        except (InvalidId, TypeError):
            return None
        doc = self._tool_s.find_one({"_id": oid})
        if not doc:
            return None
        return self._docs_list([doc])[0]

    def tool_calls_timeseries_sync(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        bucket: str = "day",
    ) -> list[dict[str, Any]]:
        """Подсчёт вызовов по дате (для простого графика в Dev UI)."""
        m: dict[str, Any] = {}
        if since is not None or until is not None:
            r: dict[str, Any] = {}
            if since is not None:
                r["$gte"] = since
            if until is not None:
                r["$lte"] = until
            m["created_at"] = r
        fmt = "%Y-%m-%d" if bucket == "day" else "%Y-%m-%d"
        pipeline: list[dict[str, Any]] = [
            {"$match": m},
            {
                "$group": {
                    "_id": {
                        "d": {
                            "$dateToString": {
                                "format": fmt,
                                "date": "$created_at",
                            }
                        }
                    },
                    "calls": {"$sum": 1},
                    "failed": {
                        "$sum": {"$cond": [{"$eq": ["$success", False]}, 1, 0]}
                    },
                }
            },
            {"$sort": {"_id.d": 1}},
        ]
        out: list[dict[str, Any]] = []
        for row in self._tool_s.aggregate(pipeline):
            _id = row.get("_id") or {}
            day = _id.get("d") if isinstance(_id, dict) else None
            out.append(
                {
                    "date": day or "",
                    "calls": int(row.get("calls") or 0),
                    "failed": int(row.get("failed") or 0),
                }
            )
        return out


async def ensure_chat_indexes(
    conv: AsyncIOMotorCollection,
    model: AsyncIOMotorCollection,
    tool: AsyncIOMotorCollection,
) -> None:
    await conv.create_index([("internal_user_id", 1), ("created_at", 1)])
    await model.create_index([("internal_user_id", 1), ("created_at", -1)])
    await tool.create_index([("internal_user_id", 1), ("created_at", -1)])
