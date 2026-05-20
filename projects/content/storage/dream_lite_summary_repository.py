"""MongoDB: dream_lite_run_summaries — лёгкая проекция run для истории пользователя."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo.collection import Collection


async def ensure_dream_lite_summary_indexes(coll: AsyncIOMotorCollection) -> None:
    await coll.create_index(
        [("user_id", 1), ("lite_run_id", 1)],
        unique=True,
        name="user_lite_run_summary_unique",
    )
    await coll.create_index(
        [("user_id", 1), ("updated_at", -1)],
        name="user_summary_updated",
    )
    await coll.create_index(
        [("user_id", 1), ("created_at", -1)],
        name="user_summary_created",
    )


class DreamLiteSummaryRepository:
    def __init__(self, async_coll: AsyncIOMotorCollection, sync_coll: Collection) -> None:
        self._async = async_coll
        self._sync = sync_coll

    @staticmethod
    def _iso(v: Any) -> datetime | None:
        if isinstance(v, datetime):
            return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        return None

    @staticmethod
    def _excerpt(text: str, max_len: int = 180) -> str:
        t = " ".join((text or "").split())
        if len(t) <= max_len:
            return t
        return t[: max_len - 1] + "…"

    @staticmethod
    def _pick_thumb_url(doc: dict[str, Any]) -> str | None:
        for fr in list(doc.get("generated_frames") or []):
            if not isinstance(fr, dict):
                continue
            urls = list(fr.get("urls") or [])
            if urls:
                u = str(urls[0]).strip()
                if u:
                    return u
        return None

    def build_summary_doc(self, run_doc: dict[str, Any]) -> dict[str, Any]:
        user_id = int(run_doc.get("user_id") or 0)
        lite_run_id = str(run_doc.get("lite_run_id") or "").strip()
        dream_text = str(run_doc.get("dream_text") or "")
        frames = list(run_doc.get("generated_frames") or [])
        final_video_url = str(run_doc.get("final_video_url") or "").strip() or None
        now = datetime.now(timezone.utc)
        created_at = self._iso(run_doc.get("created_at")) or now
        updated_at = self._iso(run_doc.get("updated_at")) or now
        title = self._excerpt(dream_text, 72) or f"Сон {lite_run_id[:8]}"
        return {
            "user_id": user_id,
            "lite_run_id": lite_run_id,
            "title": title,
            "dream_excerpt": self._excerpt(dream_text, 180),
            "created_at": created_at,
            "updated_at": updated_at,
            "run_status": str(run_doc.get("run_status") or "").strip() or "unknown",
            "step_phase": str(run_doc.get("step_phase") or "").strip() or "unknown",
            "thumb_url": self._pick_thumb_url(run_doc),
            "final_video_url": final_video_url,
            "frames_count": len(frames),
            "has_frames": bool(frames),
            "has_final_video": bool(final_video_url),
            "retention_until": run_doc.get("retention_until"),
            "archived_at": run_doc.get("archived_at"),
            "purged_at": run_doc.get("purged_at"),
        }

    async def upsert_from_run_doc(self, run_doc: dict[str, Any]) -> bool:
        if not isinstance(run_doc, dict):
            return False
        user_id = int(run_doc.get("user_id") or 0)
        lite_run_id = str(run_doc.get("lite_run_id") or "").strip()
        if user_id <= 0 or not lite_run_id:
            return False
        payload = self.build_summary_doc(run_doc)
        r = await self._async.update_one(
            {"user_id": user_id, "lite_run_id": lite_run_id},
            {"$set": payload, "$setOnInsert": {"created_at": payload["created_at"]}},
            upsert=True,
        )
        return bool(getattr(r, "acknowledged", False))

    def list_user_summaries_sync(self, *, user_id: int, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        lim = max(1, min(int(limit), 100))
        skip = max(0, int(offset))
        cur = (
            self._sync.find({"user_id": int(user_id)})
            .sort("updated_at", -1)
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
