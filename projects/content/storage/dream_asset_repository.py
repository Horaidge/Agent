"""MongoDB: коллекция dream_assets (визуальные материалы пользователя)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo.collection import Collection


class DreamAssetRepository:
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

    async def find_by_id(self, asset_id: Any) -> dict[str, Any] | None:
        from bson import ObjectId

        try:
            oid = ObjectId(asset_id)
        except Exception:  # noqa: BLE001
            return None
        doc = await self._async.find_one({"_id": oid})
        if not doc:
            return None
        out = dict(doc)
        out["_id"] = str(out["_id"])
        return out

    async def update_classification(
        self,
        asset_id: Any,
        *,
        owner_user_id: int,
        asset_type: str,
        status: str,
    ) -> bool:
        from bson import ObjectId

        try:
            oid = ObjectId(asset_id)
        except Exception:  # noqa: BLE001
            return False
        now = datetime.now(timezone.utc)
        r = await self._async.update_one(
            {"_id": oid, "owner_user_id": owner_user_id},
            {
                "$set": {
                    "asset_type": asset_type,
                    "status": status,
                    "updated_at": now,
                }
            },
        )
        return r.matched_count > 0

    async def has_classified_face_asset(self, owner_user_id: int) -> bool:
        """Есть ли у пользователя классифицированный face-asset."""
        doc = await self._async.find_one(
            {
                "owner_user_id": owner_user_id,
                "asset_type": "face",
                "status": "classified",
            }
        )
        return doc is not None

    async def list_by_owner(self, owner_user_id: int, *, limit: int = 200) -> list[dict[str, Any]]:
        lim = max(1, min(limit, 500))
        cur = (
            self._async.find({"owner_user_id": owner_user_id})
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

    async def count_by_owner(self, owner_user_id: int, query: dict[str, Any] | None = None) -> int:
        q = {"owner_user_id": owner_user_id}
        if query:
            q.update(query)
        return await self._async.count_documents(q)

    async def delete_by_owner(self, owner_user_id: int, query: dict[str, Any] | None = None) -> int:
        q = {"owner_user_id": owner_user_id}
        if query:
            q.update(query)
        r = await self._async.delete_many(q)
        return int(getattr(r, "deleted_count", 0) or 0)

    def list_distinct_owner_ids_sync(self) -> list[int]:
        """Пользователи, у которых есть хотя бы один asset (для dev UI)."""
        return sorted(
            self._sync.distinct("owner_user_id"),
            reverse=True,
        )

    def find_by_id_sync(self, asset_id: str) -> dict[str, Any] | None:
        """Синхронное чтение одного asset по Mongo _id (строка)."""
        from bson import ObjectId

        try:
            oid = ObjectId(asset_id)
        except Exception:  # noqa: BLE001
            return None
        doc = self._sync.find_one({"_id": oid})
        if not doc:
            return None
        d = dict(doc)
        oid2 = d.pop("_id", None)
        d["_id"] = str(oid2) if oid2 is not None else None
        ca = d.get("created_at")
        ua = d.get("updated_at")
        if hasattr(ca, "isoformat"):
            d["created_at"] = ca.isoformat()
        if hasattr(ua, "isoformat"):
            d["updated_at"] = ua.isoformat()
        return d

    def list_by_owner_sync(
        self,
        owner_user_id: int,
        *,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        lim = max(1, min(limit, 500))
        cur = (
            self._sync.find({"owner_user_id": owner_user_id})
            .sort("created_at", -1)
            .limit(lim)
        )
        out: list[dict[str, Any]] = []
        for doc in cur:
            d = dict(doc)
            oid = d.pop("_id", None)
            d["_id"] = str(oid) if oid is not None else None
            ca = d.get("created_at")
            ua = d.get("updated_at")
            if hasattr(ca, "isoformat"):
                d["created_at"] = ca.isoformat()
            if hasattr(ua, "isoformat"):
                d["updated_at"] = ua.isoformat()
            out.append(d)
        return out


async def ensure_dream_asset_indexes(collection: AsyncIOMotorCollection) -> None:
    await collection.create_index([("owner_user_id", 1), ("created_at", -1)])
    await collection.create_index("status")
