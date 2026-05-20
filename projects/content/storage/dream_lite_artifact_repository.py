"""MongoDB: dream_lite_artifacts — учёт путей /dev/static/ для кадров Lite, TTL по expires_at."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo.collection import Collection

ARTIFACT_TTL_DAYS = 2


async def ensure_dream_lite_artifact_indexes(coll: AsyncIOMotorCollection) -> None:
    await coll.create_index(
        [("user_id", 1), ("artifact_id", 1)],
        unique=True,
        name="user_artifact_unique",
    )
    await coll.create_index(
        [("user_id", 1), ("lite_run_id", 1)],
        name="user_lite_run",
    )
    await coll.create_index(
        [("expires_at", 1)],
        expireAfterSeconds=0,
        name="ttl_expires_at",
    )


class DreamLiteArtifactRepository:
    """Метаданные файлов; физическое удаление с диска TTL не делает — только документы."""

    def __init__(
        self,
        async_coll: AsyncIOMotorCollection,
        sync_coll: Collection,
    ) -> None:
        self._async = async_coll
        self._sync = sync_coll

    async def record_frame_artifacts(
        self,
        *,
        user_id: int,
        lite_run_id: str,
        frame_results: list[dict[str, Any]],
    ) -> None:
        now = datetime.now(timezone.utc)
        exp = now + timedelta(days=ARTIFACT_TTL_DAYS)
        lid = (lite_run_id or "").strip()
        docs: list[dict[str, Any]] = []
        for row in frame_results or []:
            if not isinstance(row, dict):
                continue
            ix = row.get("index")
            if ix is None:
                continue
            ix = int(ix)
            for u in list(row.get("urls") or []):
                su = str(u or "").strip()
                if not su.startswith("/dev/static/"):
                    continue
                docs.append(
                    {
                        "artifact_id": str(uuid.uuid4()),
                        "user_id": int(user_id),
                        "lite_run_id": lid,
                        "frame_index": ix,
                        "kind": "frame_output",
                        "dev_static_url": su,
                        "created_at": now,
                        "expires_at": exp,
                    }
                )
        if docs:
            await self._async.insert_many(docs)
