"""Персистентный журнал расхода токенов / событий генерации для Dev UI (MongoDB)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING
from pymongo.collection import Collection


def ensure_dev_usage_ledger_indexes(sync_collection: Collection) -> None:
    sync_collection.create_index([("created_at", ASCENDING)])
    sync_collection.create_index([("category", ASCENDING), ("created_at", ASCENDING)])


class DevUsageLedgerRepository:
    def __init__(self, sync_collection: Collection) -> None:
        self._sync = sync_collection

    def insert_event_sync(self, doc: dict[str, Any]) -> str:
        d = {
            **doc,
            "created_at": datetime.now(timezone.utc),
        }
        r = self._sync.insert_one(d)
        return str(r.inserted_id)

    def aggregate_by_category_sync(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]:
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
                    "_id": "$category",
                    "events": {"$sum": 1},
                    "input_tokens": {"$sum": {"$ifNull": ["$input_tokens", 0]}},
                    "output_tokens": {"$sum": {"$ifNull": ["$output_tokens", 0]}},
                    "total_tokens": {"$sum": {"$ifNull": ["$total_tokens", 0]}},
                    "cost_usd": {"$sum": {"$ifNull": ["$cost_usd", 0.0]}},
                }
            },
            {"$sort": {"_id": ASCENDING}},
        ]
        out: list[dict[str, Any]] = []
        for row in self._sync.aggregate(pipeline):
            out.append(
                {
                    "category": row.get("_id") or "unknown",
                    "events": int(row.get("events") or 0),
                    "input_tokens": int(row.get("input_tokens") or 0),
                    "output_tokens": int(row.get("output_tokens") or 0),
                    "total_tokens": int(row.get("total_tokens") or 0),
                    "cost_usd": float(row.get("cost_usd") or 0.0),
                }
            )
        return out
