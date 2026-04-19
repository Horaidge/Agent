"""MongoDB: коллекция `video_jobs` для асинхронных задач image-to-video."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo.collection import Collection


def _oid(job_id: str) -> ObjectId:
    try:
        return ObjectId(job_id)
    except (InvalidId, TypeError) as e:
        raise ValueError(f"Некорректный job_id: {job_id!r}") from e


class VideoJobRepository:
    """Sync + async доступ к `video_jobs` (polling в потоке использует sync)."""

    def __init__(
        self,
        async_collection: AsyncIOMotorCollection | None,
        sync_collection: Collection,
    ) -> None:
        self._async = async_collection
        self._sync = sync_collection

    def insert_job_sync(self, doc: dict[str, Any]) -> str:
        d = {
            **doc,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        r = self._sync.insert_one(d)
        return str(r.inserted_id)

    def update_job_sync(self, job_id: str, patch: dict[str, Any]) -> None:
        oid = _oid(job_id)
        update = {**patch, "updated_at": datetime.now(timezone.utc)}
        self._sync.update_one({"_id": oid}, {"$set": update})

    def get_job_sync(self, job_id: str) -> dict[str, Any] | None:
        oid = _oid(job_id)
        doc = self._sync.find_one({"_id": oid})
        if not doc:
            return None
        return _serialize_doc(doc)

    def list_recent_sync(self, *, limit: int = 50) -> list[dict[str, Any]]:
        lim = max(1, min(limit, 200))
        cur = self._sync.find().sort("created_at", -1).limit(lim)
        return [_serialize_doc(dict(doc)) for doc in cur]

    async def insert_job(self, doc: dict[str, Any]) -> str:
        if self._async is None:
            raise RuntimeError("Async collection not configured for VideoJobRepository")
        d = {
            **doc,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        r = await self._async.insert_one(d)
        return str(r.inserted_id)

    async def update_job(self, job_id: str, patch: dict[str, Any]) -> None:
        if self._async is None:
            raise RuntimeError("Async collection not configured for VideoJobRepository")
        oid = _oid(job_id)
        update = {**patch, "updated_at": datetime.now(timezone.utc)}
        await self._async.update_one({"_id": oid}, {"$set": update})

    async def get_job(self, job_id: str) -> dict[str, Any] | None:
        if self._async is None:
            raise RuntimeError("Async collection not configured for VideoJobRepository")
        oid = _oid(job_id)
        doc = await self._async.find_one({"_id": oid})
        if not doc:
            return None
        return _serialize_doc(doc)


def _serialize_doc(doc: dict[str, Any]) -> dict[str, Any]:
    out = dict(doc)
    oid = out.pop("_id", None)
    out["_id"] = str(oid) if oid is not None else None
    for key in ("created_at", "updated_at"):
        v = out.get(key)
        if hasattr(v, "isoformat"):
            out[key] = v.isoformat()
    return out


async def ensure_video_job_indexes(collection: AsyncIOMotorCollection) -> None:
    await collection.create_index([("owner_user_id", 1), ("created_at", -1)])
    await collection.create_index("provider_task_id", sparse=True)
    await collection.create_index("dream_trace_id", sparse=True)


def ensure_video_job_indexes_sync(collection: Collection) -> None:
    collection.create_index([("owner_user_id", 1), ("created_at", -1)])
    collection.create_index("provider_task_id", sparse=True)
    collection.create_index("dream_trace_id", sparse=True)
