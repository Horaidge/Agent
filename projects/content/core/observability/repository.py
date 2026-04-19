"""MongoDB: append-only observability_events + синхронное чтение для debug UI."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo.collection import Collection


class ObservabilityRepository:
    def __init__(
        self,
        async_coll: AsyncIOMotorCollection,
        sync_coll: Collection,
    ) -> None:
        self._async = async_coll
        self._sync = sync_coll

    async def insert_event(self, doc: dict[str, Any]) -> str:
        doc = {**doc, "created_at": datetime.now(timezone.utc)}
        r = await self._async.insert_one(doc)
        return str(r.inserted_id)

    def list_events_sync(
        self,
        *,
        limit: int = 100,
        trace_id: str | None = None,
        event_type: str | None = None,
        telegram_user_id: int | None = None,
        telegram_chat_id: int | None = None,
        since_iso: str | None = None,
    ) -> list[dict[str, Any]]:
        q: dict[str, Any] = {}
        if trace_id:
            q["trace_id"] = trace_id
        if event_type:
            q["event_type"] = event_type
        if telegram_user_id is not None:
            q["telegram_user_id"] = telegram_user_id
        if telegram_chat_id is not None:
            q["telegram_chat_id"] = telegram_chat_id
        if since_iso:
            try:
                dt = datetime.fromisoformat(since_iso.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                q["created_at"] = {"$gte": dt}
            except ValueError:
                pass

        cur = self._sync.find(q).sort("created_at", -1).limit(max(1, min(limit, 500)))
        out: list[dict[str, Any]] = []
        for doc in cur:
            oid = doc.pop("_id", None)
            doc["_id"] = str(oid) if oid is not None else None
            out.append(doc)
        return out

    async def delete_all_events(self) -> int:
        """Удалить все события observability (dev «очистить всё»)."""
        r = await self._async.delete_many({})
        return int(getattr(r, "deleted_count", 0) or 0)

    async def delete_by_telegram_user_id(self, telegram_user_id: int) -> int:
        """События observability, привязанные к пользователю Telegram."""
        r = await self._async.delete_many({"telegram_user_id": telegram_user_id})
        return int(getattr(r, "deleted_count", 0) or 0)

    def list_trace_ids_sync(self, *, limit: int = 80) -> list[str]:
        """Последние уникальные trace_id (без тяжёлого aggregate)."""
        seen: list[str] = []
        for doc in self._sync.find({}, {"trace_id": 1, "created_at": 1}).sort(
            "created_at", -1
        ).limit(3000):
            tid = doc.get("trace_id")
            if tid and tid not in seen:
                seen.append(str(tid))
            if len(seen) >= max(1, min(limit, 200)):
                break
        return seen

    def get_message_docs_for_user_sync(
        self,
        collection: Collection,
        *,
        telegram_user_id: int,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        cur = (
            collection.find({"telegram_user_id": telegram_user_id})
            .sort("created_at", -1)
            .limit(max(1, min(limit, 300)))
        )
        out: list[dict[str, Any]] = []
        for doc in cur:
            oid = doc.pop("_id", None)
            doc["_id"] = str(oid) if oid is not None else None
            out.append(doc)
        return out


async def ensure_observability_indexes(collection: AsyncIOMotorCollection) -> None:
    await collection.create_index([("trace_id", 1), ("created_at", -1)])
    await collection.create_index([("telegram_user_id", 1), ("created_at", -1)])
    await collection.create_index([("event_type", 1), ("created_at", -1)])
