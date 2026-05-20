"""Dev-only snapshot шага 3 для быстрого ретеста шагов 4/5."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo.collection import Collection


class DreamLiteStep3SnapshotRepository:
    def __init__(self, sync_coll: Collection) -> None:
        self._sync = sync_coll

    def upsert_latest_sync(
        self,
        *,
        user_id: int,
        payload: dict[str, Any],
        updated_by: str = "dev_console",
    ) -> bool:
        doc_id = f"user:{int(user_id)}"
        now = datetime.now(timezone.utc)
        res = self._sync.update_one(
            {"_id": doc_id},
            {
                "$set": {
                    "user_id": int(user_id),
                    "payload": dict(payload or {}),
                    "updated_at": now,
                    "updated_by": str(updated_by or "dev_console").strip() or "dev_console",
                }
            },
            upsert=True,
        )
        if getattr(res, "acknowledged", False):
            return True
        # Fallback для окружений, где write concern не помечает acknowledged
        return res.upserted_id is not None or int(getattr(res, "matched_count", 0) or 0) > 0

    def get_latest_sync(self, *, user_id: int) -> dict[str, Any] | None:
        doc_id = f"user:{int(user_id)}"
        doc = self._sync.find_one({"_id": doc_id}) or {}
        payload = doc.get("payload")
        if not isinstance(payload, dict):
            return None
        out = dict(payload)
        out["updated_at"] = doc.get("updated_at")
        out["updated_by"] = str(doc.get("updated_by") or "").strip()
        return out


def ensure_dream_lite_step3_snapshot_indexes(sync_coll: Collection) -> None:
    try:
        sync_coll.create_index([("user_id", 1)], name="user_id")
        sync_coll.create_index([("updated_at", -1)], name="updated_at_desc")
    except Exception:
        pass
