"""MongoDB: коллекция dream_scenes (план сцен для dream pipeline UI)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo.collection import Collection


class DreamSceneRepository:
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

    async def update_by_run_and_index(
        self,
        dream_run_id: str,
        scene_index: int,
        patch: dict[str, Any],
    ) -> None:
        p = {**patch, "updated_at": datetime.now(timezone.utc)}
        await self._async.update_one(
            {"dream_run_id": dream_run_id, "scene_index": scene_index},
            {"$set": p},
        )

    async def list_by_dream_run(self, dream_run_id: str) -> list[dict[str, Any]]:
        cur = (
            self._async.find({"dream_run_id": dream_run_id})
            .sort("scene_index", 1)
        )
        out: list[dict[str, Any]] = []
        async for doc in cur:
            d = dict(doc)
            oid = d.pop("_id", None)
            d["_id"] = str(oid) if oid is not None else None
            out.append(d)
        return out

    async def delete_by_dream_run_ids(self, run_ids: list[str]) -> int:
        if not run_ids:
            return 0
        r = await self._async.delete_many({"dream_run_id": {"$in": run_ids}})
        return int(getattr(r, "deleted_count", 0) or 0)

    def list_by_dream_run_sync(self, dream_run_id: str) -> list[dict[str, Any]]:
        cur = self._sync.find({"dream_run_id": dream_run_id}).sort("scene_index", 1)
        out: list[dict[str, Any]] = []
        for doc in cur:
            d = dict(doc)
            oid = d.pop("_id", None)
            d["_id"] = str(oid) if oid is not None else None
            out.append(d)
        return out


async def ensure_dream_scene_indexes(collection: AsyncIOMotorCollection) -> None:
    await collection.create_index([("dream_run_id", 1), ("scene_index", 1)])
    await collection.create_index("trace_id")
