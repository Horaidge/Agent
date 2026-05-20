"""MongoDB: dream_lite_assets — канонический реестр медиа артефактов Lite run."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo.collection import Collection


async def ensure_dream_lite_asset_indexes(coll: AsyncIOMotorCollection) -> None:
    await coll.create_index(
        [("user_id", 1), ("lite_run_id", 1), ("asset_kind", 1), ("asset_index", 1), ("public_url", 1)],
        unique=True,
        name="user_run_kind_idx_url_unique",
    )
    await coll.create_index(
        [("user_id", 1), ("lite_run_id", 1), ("asset_kind", 1), ("asset_index", 1)],
        name="user_run_kind_idx",
    )
    await coll.create_index(
        [("retention_until", 1)],
        name="retention_until_idx",
    )
    await coll.create_index(
        [("created_at", -1)],
        name="assets_created_desc",
    )


class DreamLiteAssetRepository:
    def __init__(self, async_coll: AsyncIOMotorCollection, sync_coll: Collection) -> None:
        self._async = async_coll
        self._sync = sync_coll

    @staticmethod
    def _norm_url(u: Any) -> str:
        return str(u or "").strip()

    @staticmethod
    def _sha(s: str) -> str:
        return hashlib.sha256(s.encode("utf-8")).hexdigest()

    async def upsert_asset(
        self,
        *,
        user_id: int,
        lite_run_id: str,
        asset_kind: str,
        asset_index: int,
        public_url: str,
        storage_backend: str = "local_dev_static",
        storage_key: str = "",
        retention_until: datetime | None = None,
        extra: dict[str, Any] | None = None,
    ) -> bool:
        lid = str(lite_run_id or "").strip()
        url = self._norm_url(public_url)
        kind = str(asset_kind or "").strip()
        if int(user_id) <= 0 or not lid or not kind or not url:
            return False
        now = datetime.now(timezone.utc)
        doc = {
            "user_id": int(user_id),
            "lite_run_id": lid,
            "asset_kind": kind,
            "asset_index": int(asset_index),
            "storage_backend": str(storage_backend or "local_dev_static").strip() or "local_dev_static",
            "storage_key": str(storage_key or url).strip() or url,
            "public_url": url,
            "sha256": self._sha(url),
            "size_bytes": None,
            "created_at": now,
            "updated_at": now,
            "retention_until": retention_until,
        }
        if extra:
            doc.update(dict(extra))
        r = await self._async.update_one(
            {
                "user_id": int(user_id),
                "lite_run_id": lid,
                "asset_kind": kind,
                "asset_index": int(asset_index),
                "public_url": url,
            },
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        return bool(getattr(r, "acknowledged", False))

    async def upsert_from_run_doc(self, run_doc: dict[str, Any]) -> int:
        if not isinstance(run_doc, dict):
            return 0
        user_id = int(run_doc.get("user_id") or 0)
        lid = str(run_doc.get("lite_run_id") or "").strip()
        if user_id <= 0 or not lid:
            return 0
        retention_until = run_doc.get("retention_until")
        inserted = 0

        gen_env = run_doc.get("generated_env") if isinstance(run_doc.get("generated_env"), dict) else {}
        for i, (title, payload) in enumerate(gen_env.items()):
            urls = list((payload or {}).get("urls") or []) if isinstance(payload, dict) else []
            for u in urls:
                ok = await self.upsert_asset(
                    user_id=user_id,
                    lite_run_id=lid,
                    asset_kind="env",
                    asset_index=int(i),
                    public_url=self._norm_url(u),
                    retention_until=retention_until,
                    extra={"title": str(title or "").strip()},
                )
                inserted += 1 if ok else 0

        gen_char = run_doc.get("generated_char") if isinstance(run_doc.get("generated_char"), dict) else {}
        for i, (title, payload) in enumerate(gen_char.items()):
            urls = list((payload or {}).get("urls") or []) if isinstance(payload, dict) else []
            for u in urls:
                ok = await self.upsert_asset(
                    user_id=user_id,
                    lite_run_id=lid,
                    asset_kind="char",
                    asset_index=int(i),
                    public_url=self._norm_url(u),
                    retention_until=retention_until,
                    extra={"title": str(title or "").strip()},
                )
                inserted += 1 if ok else 0

        frames = list(run_doc.get("generated_frames") or [])
        for f in frames:
            if not isinstance(f, dict):
                continue
            fi = int(f.get("index") or 0)
            for u in list(f.get("urls") or []):
                ok = await self.upsert_asset(
                    user_id=user_id,
                    lite_run_id=lid,
                    asset_kind="frame",
                    asset_index=fi,
                    public_url=self._norm_url(u),
                    retention_until=retention_until,
                    extra={"title": str(f.get("title") or "").strip()},
                )
                inserted += 1 if ok else 0

        clips = list(run_doc.get("generated_anim_clips") or [])
        for c in clips:
            if not isinstance(c, dict):
                continue
            ci = int(c.get("segment_index") or 0)
            vu = self._norm_url(c.get("video_url"))
            if vu:
                ok = await self.upsert_asset(
                    user_id=user_id,
                    lite_run_id=lid,
                    asset_kind="clip",
                    asset_index=ci,
                    public_url=vu,
                    storage_backend="remote_video_url",
                    retention_until=retention_until,
                )
                inserted += 1 if ok else 0

        final_video_url = self._norm_url(run_doc.get("final_video_url"))
        if final_video_url:
            ok = await self.upsert_asset(
                user_id=user_id,
                lite_run_id=lid,
                asset_kind="final_video",
                asset_index=0,
                public_url=final_video_url,
                retention_until=retention_until,
            )
            inserted += 1 if ok else 0

        return inserted

    def list_assets_sync(
        self,
        *,
        user_id: int,
        lite_run_id: str,
        asset_kind: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        lim = max(1, min(int(limit), 200))
        skip = max(0, int(offset))
        cur = (
            self._sync.find(
                {
                    "user_id": int(user_id),
                    "lite_run_id": str(lite_run_id or "").strip(),
                    "asset_kind": str(asset_kind or "").strip(),
                }
            )
            .sort([("asset_index", 1), ("created_at", 1)])
            .skip(skip)
            .limit(lim)
        )
        out: list[dict[str, Any]] = []
        for doc in cur:
            d = dict(doc)
            if "_id" in d:
                d["_id"] = str(d["_id"])
            out.append(d)
        return out

    async def purge_expired_assets(self, *, now: datetime | None = None) -> list[str]:
        dt = now or datetime.now(timezone.utc)
        expired = await self._async.find(
            {"retention_until": {"$ne": None, "$lt": dt}},
            {"public_url": 1},
        ).to_list(length=1000)
        urls = [self._norm_url(x.get("public_url")) for x in expired if self._norm_url(x.get("public_url"))]
        if urls:
            await self._async.delete_many({"retention_until": {"$ne": None, "$lt": dt}})
        return urls
