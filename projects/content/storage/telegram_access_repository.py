"""Хранилище allowlist-доступа к Telegram-боту."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo.collection import Collection


_DOC_ID = "telegram_allowlist_policy_v1"


class TelegramAccessRepository:
    def __init__(self, sync_coll: Collection) -> None:
        self._sync = sync_coll

    def get_policy_sync(self) -> dict[str, Any]:
        doc = self._sync.find_one({"_id": _DOC_ID}) or {}
        ids_raw = list(doc.get("user_ids") or [])
        ids: list[int] = []
        for x in ids_raw:
            try:
                ids.append(int(x))
            except Exception:
                continue
        ids = sorted(set(ids))
        return {
            "enabled": bool(doc.get("enabled", False)),
            "user_ids": ids,
            "updated_at": doc.get("updated_at"),
            "updated_by": str(doc.get("updated_by") or "").strip(),
        }

    def upsert_policy_sync(
        self,
        *,
        enabled: bool,
        user_ids: list[int],
        updated_by: str = "dev_console",
    ) -> bool:
        clean = sorted(set(int(x) for x in (user_ids or [])))
        res = self._sync.update_one(
            {"_id": _DOC_ID},
            {
                "$set": {
                    "enabled": bool(enabled),
                    "user_ids": clean,
                    "updated_at": datetime.now(timezone.utc),
                    "updated_by": str(updated_by or "dev_console").strip() or "dev_console",
                }
            },
            upsert=True,
        )
        return bool(getattr(res, "acknowledged", False))
