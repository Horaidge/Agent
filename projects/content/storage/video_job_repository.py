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

    def list_active_sync(self, *, limit: int = 40) -> list[dict[str, Any]]:
        """Задачи image-to-video, которые ещё не завершены (Dev Tools → Live)."""
        lim = max(1, min(limit, 200))
        cur = (
            self._sync.find(
                {"status": {"$in": ["created", "running"]}},
            )
            .sort("updated_at", -1)
            .limit(lim)
        )
        return [_serialize_doc(dict(doc)) for doc in cur]

    def aggregate_period_stats_sync(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Счётчики по video_jobs за период без загрузки всех документов (Dev Tools / аналитика).
        """
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
                    "total": {"$sum": 1},
                    "succeeded": {
                        "$sum": {"$cond": [{"$eq": ["$status", "succeeded"]}, 1, 0]}
                    },
                    "failed": {
                        "$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}
                    },
                    "last_created": {"$max": "$created_at"},
                }
            },
        ]
        rows = list(self._sync.aggregate(pipeline))
        if not rows:
            return {
                "total": 0,
                "succeeded": 0,
                "failed": 0,
                "last_created": None,
            }
        row = rows[0]
        return {
            "total": int(row.get("total") or 0),
            "succeeded": int(row.get("succeeded") or 0),
            "failed": int(row.get("failed") or 0),
            "last_created": row.get("last_created"),
        }

    def list_filtered_sync(
        self,
        *,
        limit: int = 80,
        since: datetime | None = None,
        until: datetime | None = None,
        status_in: list[str] | None = None,
        owner_user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        q: dict[str, Any] = {}
        if since is not None or until is not None:
            r: dict[str, Any] = {}
            if since is not None:
                r["$gte"] = since
            if until is not None:
                r["$lte"] = until
            q["created_at"] = r
        if status_in:
            q["status"] = {"$in": status_in}
        if owner_user_id:
            q["owner_user_id"] = owner_user_id
        lim = max(1, min(limit, 300))
        cur = self._sync.find(q).sort("created_at", -1).limit(lim)
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

    async def count_for_owner(self, owner_user_id: str) -> int:
        if self._async is None:
            raise RuntimeError("Async collection not configured for VideoJobRepository")
        return await self._async.count_documents({"owner_user_id": owner_user_id})

    async def delete_for_owner(self, owner_user_id: str) -> int:
        if self._async is None:
            raise RuntimeError("Async collection not configured for VideoJobRepository")
        r = await self._async.delete_many({"owner_user_id": owner_user_id})
        return int(getattr(r, "deleted_count", 0) or 0)


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
