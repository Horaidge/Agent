from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo import MongoClient

from core.config.settings import get_settings

_CLIENT: MongoClient | None = None


def _coll() -> Any | None:
    global _CLIENT
    s = get_settings()
    try:
        if _CLIENT is None:
            _CLIENT = MongoClient(s.mongodb_uri)
        c = _CLIENT[s.mongodb_db]["dream_lite_generation_metrics"]
        c.create_index([("user_id", 1), ("lite_run_id", 1), ("created_at", -1)], name="user_run_created")
        c.create_index([("model_id", 1), ("created_at", -1)], name="model_created")
        c.create_index([("stage", 1), ("created_at", -1)], name="stage_created")
        return c
    except Exception:
        return None


def record_metric(doc: dict[str, Any]) -> None:
    c = _coll()
    if c is None:
        return
    payload = dict(doc or {})
    payload["created_at"] = datetime.now(timezone.utc)
    try:
        c.insert_one(payload)
    except Exception:
        return

