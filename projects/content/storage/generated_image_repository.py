"""MongoDB: коллекция generated_images (скрытый журнал кадров для video pipeline)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo.collection import Collection


class GeneratedImageRepository:
    def __init__(
        self,
        async_coll: AsyncIOMotorCollection,
        sync_coll: Collection,
    ) -> None:
        self._async = async_coll
        self._sync = sync_coll

    async def count_for_user(self, user_id: int) -> int:
        return await self._async.count_documents({"user_id": user_id})

    async def insert_one(
        self,
        *,
        user_id: int,
        image_url: str,
        prompt: str,
        related_character_id: str | None,
        created_at: datetime | None = None,
    ) -> str:
        now = created_at or datetime.now(timezone.utc)
        doc: dict[str, Any] = {
            "user_id": user_id,
            "image_url": image_url,
            "prompt": prompt,
            "related_character_id": related_character_id,
            "created_at": now,
        }
        r = await self._async.insert_one(doc)
        return str(r.inserted_id)

    async def list_for_user(
        self,
        user_id: int,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        lim = max(1, min(limit, 50))
        cur = (
            self._async.find({"user_id": user_id})
            .sort("created_at", -1)
            .limit(lim)
        )
        out: list[dict[str, Any]] = []
        async for doc in cur:
            d = dict(doc)
            oid = d.pop("_id", None)
            d["_id"] = str(oid) if oid is not None else None
            out.append(d)
        return out

    async def delete_all_for_user(self, user_id: int) -> int:
        r = await self._async.delete_many({"user_id": user_id})
        return int(getattr(r, "deleted_count", 0) or 0)


async def ensure_generated_image_indexes(collection: AsyncIOMotorCollection) -> None:
    await collection.create_index([("user_id", 1), ("created_at", -1)])
