"""MongoDB: коллекция user_profiles (базовый персонаж и флаги онбординга)."""
from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo.collection import Collection


class UserProfileRepository:
    def __init__(
        self,
        async_coll: AsyncIOMotorCollection,
        sync_coll: Collection,
    ) -> None:
        self._async = async_coll
        self._sync = sync_coll

    async def get_by_user_id(self, user_id: int) -> dict[str, Any] | None:
        doc = await self._async.find_one({"user_id": user_id})
        if not doc:
            return None
        out = dict(doc)
        oid = out.pop("_id", None)
        out["_id"] = str(oid) if oid is not None else None
        return out

    async def set_awaiting_character_description(
        self,
        user_id: int,
        *,
        awaiting: bool,
    ) -> None:
        await self._async.update_one(
            {"user_id": user_id},
            {
                "$set": {"awaiting_character_description": awaiting},
                "$setOnInsert": {"user_id": user_id},
            },
            upsert=True,
        )

    async def set_base_character_asset(
        self,
        user_id: int,
        *,
        asset_id: str,
    ) -> None:
        await self._async.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "base_character_asset_id": asset_id,
                    "awaiting_character_description": False,
                },
                "$setOnInsert": {"user_id": user_id},
            },
            upsert=True,
        )


async def ensure_user_profile_indexes(collection: AsyncIOMotorCollection) -> None:
    await collection.create_index("user_id", unique=True)
