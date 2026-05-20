"""MongoDB: коллекция dream_runs (оркестрация сон→видео)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo.collection import Collection


class DreamRunRepository:
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

    async def update(self, run_id: str, patch: dict[str, Any]) -> None:
        from bson import ObjectId

        try:
            oid = ObjectId(run_id)
        except Exception:  # noqa: BLE001
            return
        p = {**patch, "updated_at": datetime.now(timezone.utc)}
        await self._async.update_one({"_id": oid}, {"$set": p})

    async def find_by_id(self, run_id: str) -> dict[str, Any] | None:
        from bson import ObjectId

        try:
            oid = ObjectId(run_id)
        except Exception:  # noqa: BLE001
            return None
        doc = await self._async.find_one({"_id": oid})
        if not doc:
            return None
        d = dict(doc)
        d["_id"] = str(d.pop("_id"))
        return d

    async def find_awaiting_character(self, user_id: int) -> dict[str, Any] | None:
        lst = (
            await self._async.find({"user_id": user_id, "status": "awaiting_character"})
            .sort("updated_at", -1)
            .limit(1)
            .to_list(1)
        )
        doc = lst[0] if lst else None
        if not doc:
            return None
        d = dict(doc)
        d["_id"] = str(d.pop("_id"))
        return d

    async def find_pending_input(self, user_id: int) -> dict[str, Any] | None:
        lst = (
            await self._async.find(
                {
                    "user_id": user_id,
                    "status": {
                        "$in": [
                            "awaiting_style",
                            "awaiting_character",
                            "awaiting_actors",
                        ]
                    },
                }
            )
            .sort("updated_at", -1)
            .limit(1)
            .to_list(1)
        )
        doc = lst[0] if lst else None
        if not doc:
            return None
        d = dict(doc)
        d["_id"] = str(d.pop("_id"))
        return d

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

    async def count_for_user(self, user_id: int) -> int:
        return await self._async.count_documents({"user_id": user_id})

    async def delete_for_user(self, user_id: int) -> int:
        r = await self._async.delete_many({"user_id": user_id})
        return int(getattr(r, "deleted_count", 0) or 0)

    async def list_ids_for_user(self, user_id: int, *, limit: int = 1000) -> list[str]:
        cur = self._async.find({"user_id": user_id}, {"_id": 1}).limit(max(1, min(limit, 5000)))
        out: list[str] = []
        async for doc in cur:
            oid = doc.get("_id")
            if oid is not None:
                out.append(str(oid))
        return out

    def find_by_id_sync(self, run_id: str) -> dict[str, Any] | None:
        from bson import ObjectId

        try:
            oid = ObjectId(run_id)
        except Exception:  # noqa: BLE001
            return None
        doc = self._sync.find_one({"_id": oid})
        if not doc:
            return None
        d = dict(doc)
        d["_id"] = str(d.pop("_id"))
        return d

    def list_recent_sync(self, *, limit: int = 50) -> list[dict[str, Any]]:
        lim = max(1, min(limit, 200))
        cur = self._sync.find().sort("created_at", -1).limit(lim)
        out: list[dict[str, Any]] = []
        for doc in cur:
            d = dict(doc)
            d["_id"] = str(d.pop("_id"))
            out.append(d)
        return out


async def ensure_dream_run_indexes(collection: AsyncIOMotorCollection) -> None:
    await collection.create_index([("user_id", 1), ("status", 1)])
    await collection.create_index("trace_id", unique=True)
    await collection.create_index([("created_at", -1)])
