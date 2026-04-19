"""MongoDB: коллекция story_videos (финальный ролик dream pipeline)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo.collection import Collection


class StoryVideoRepository:
    def __init__(
        self,
        async_coll: AsyncIOMotorCollection,
        sync_coll: Collection,
    ) -> None:
        self._async = async_coll
        self._sync = sync_coll

    async def insert_one(self, doc: dict[str, Any]) -> str:
        d = {**doc}
        now = datetime.now(timezone.utc)
        if "created_at" not in d:
            d["created_at"] = now
        if "updated_at" not in d:
            d["updated_at"] = now
        r = await self._async.insert_one(d)
        return str(r.inserted_id)

    async def update(self, doc_id: str, patch: dict[str, Any]) -> None:
        from bson import ObjectId

        try:
            oid = ObjectId(doc_id)
        except Exception:  # noqa: BLE001
            return
        p = {**patch, "updated_at": datetime.now(timezone.utc)}
        await self._async.update_one({"_id": oid}, {"$set": p})

    async def find_by_trace(self, trace_id: str) -> dict[str, Any] | None:
        doc = await self._async.find_one({"trace_id": trace_id})
        if not doc:
            return None
        d = dict(doc)
        d["_id"] = str(d.pop("_id"))
        return d

    async def list_recent(self, *, limit: int = 50) -> list[dict[str, Any]]:
        lim = max(1, min(limit, 200))
        cur = self._async.find().sort("created_at", -1).limit(lim)
        out: list[dict[str, Any]] = []
        async for doc in cur:
            d = dict(doc)
            d["_id"] = str(d.pop("_id"))
            out.append(d)
        return out


async def ensure_story_video_indexes(collection: AsyncIOMotorCollection) -> None:
    await collection.create_index("trace_id", unique=True)
    await collection.create_index([("user_id", 1), ("created_at", -1)])
