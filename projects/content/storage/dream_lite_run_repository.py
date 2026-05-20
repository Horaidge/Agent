"""MongoDB: коллекция dream_lite_runs (Dream Pipeline Lite, пошаговые job без смешивания пользователей)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo.collection import Collection
from core.config.settings import get_settings
from services.dreams.dream_lite_service import default_run_config


async def ensure_dream_lite_run_indexes(coll: AsyncIOMotorCollection) -> None:
    await coll.create_index(
        [("user_id", 1), ("lite_run_id", 1)],
        unique=True,
        name="user_lite_run_unique",
    )
    await coll.create_index(
        [("user_id", 1), ("created_at", -1)],
        name="user_created",
    )


async def ensure_dream_lite_profile_indexes(coll: AsyncIOMotorCollection) -> None:
    await coll.create_index(
        [("is_active", 1), ("updated_at", -1)],
        name="active_updated",
    )


class DreamLiteRunRepository:
    """Все выборки и обновления — строго по (user_id, lite_run_id)."""

    def __init__(
        self,
        async_coll: AsyncIOMotorCollection,
        sync_coll: Collection,
        profile_async_coll: AsyncIOMotorCollection | None = None,
        profile_sync_coll: Collection | None = None,
    ) -> None:
        self._async = async_coll
        self._sync = sync_coll
        self._profile_async = profile_async_coll
        self._profile_sync = profile_sync_coll

    @staticmethod
    def new_lite_run_id() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def _merge_run_config(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        out = dict(base)
        out.update(dict(incoming or {}))
        for key in ("image_policy", "video_policy", "fallback_policy", "steps"):
            b = base.get(key) if isinstance(base.get(key), dict) else {}
            i = incoming.get(key) if isinstance(incoming, dict) and isinstance(incoming.get(key), dict) else {}
            out[key] = {**b, **i}
        return out

    async def _resolve_run_config_from_active_profile(self) -> tuple[str, dict[str, Any], dict[str, Any]]:
        base = default_run_config()
        variant = str(base.get("pipeline_variant") or "pair_i2v_between_keyframes")
        meta: dict[str, Any] = {
            "profile_name": "default_fallback",
            "profile_revision": 0,
            "profile_updated_at": None,
        }
        if self._profile_async is None:
            return variant, base, meta
        prof = await self._profile_async.find_one(
            {"is_active": True},
            sort=[("updated_at", -1)],
        )
        if not prof:
            return variant, base, meta
        cfg = prof.get("run_config")
        if not isinstance(cfg, dict) or not cfg:
            return variant, base, meta
        cfg_copy = self._merge_run_config(base, dict(cfg))
        cfg_variant = str(cfg_copy.get("pipeline_variant") or "").strip()
        if not cfg_variant:
            cfg_copy["pipeline_variant"] = variant
            cfg_variant = variant
        rev = int(prof.get("profile_revision") or 1)
        meta = {
            "profile_name": str(prof.get("profile_name") or "default").strip() or "default",
            "profile_revision": max(1, rev),
            "profile_updated_at": prof.get("updated_at"),
        }
        return cfg_variant, cfg_copy, meta

    async def create_run(self, *, user_id: int, dream_text: str) -> str:
        lite_run_id = self.new_lite_run_id()
        now = datetime.now(timezone.utc)
        retention_days = int(get_settings().dream_lite_retention_days or 30)
        retention_until = now + timedelta(days=max(1, retention_days))
        pipeline_variant, run_config, profile_meta = await self._resolve_run_config_from_active_profile()
        doc: dict[str, Any] = {
            "lite_run_id": lite_run_id,
            "user_id": int(user_id),
            "dream_text": (dream_text or "").strip(),
            "created_at": now,
            "updated_at": now,
            "run_status": "active",
            "step_phase": "text_step1",
            "last_error": None,
            "step1_raw": None,
            "step2_raw": None,
            "step2_prev_link_raw": None,
            "env_cards": [],
            "char_cards": [],
            "frame_cards": [],
            "generated_env": {},
            "generated_char": {},
            "generated_frames": [],
            "transition_plan_raw": None,
            "transition_plan": None,
            "generated_anim_clips": [],
            "gen_anim_i": 0,
            "anim_run_complete": False,
            "gen_env_i": 0,
            "gen_char_i": 0,
            "gen_frame_i": 0,
            "last_success_frame_url": None,
            "final_video_url": None,
            "final_assembly_error": None,
            "last_delivery_status": None,
            "pipeline_variant": pipeline_variant,
            "run_config": run_config,
            "config_profile_name": str(profile_meta.get("profile_name") or "default_fallback"),
            "config_profile_revision": int(profile_meta.get("profile_revision") or 0),
            "config_profile_updated_at": profile_meta.get("profile_updated_at"),
            "completed_at": None,
            "retention_until": retention_until,
            "archived_at": None,
            "purged_at": None,
            "has_frames": False,
            "has_final_video": False,
            "phase_revision": 0,
            "step_id": "text_step1:0",
            "execution_trace": [],
        }
        await self._async.insert_one(doc)
        return lite_run_id

    async def upsert_active_profile(
        self,
        *,
        run_config: dict[str, Any],
        pipeline_variant: str | None = None,
        updated_by_user_id: int | None = None,
        profile_name: str = "default",
    ) -> bool:
        if self._profile_async is None:
            return False
        prof_name = (profile_name or "default").strip() or "default"
        base = default_run_config()
        cfg = self._merge_run_config(base, dict(run_config or {}))
        variant = str(
            pipeline_variant or cfg.get("pipeline_variant") or "pair_i2v_between_keyframes"
        ).strip() or "pair_i2v_between_keyframes"
        cfg["pipeline_variant"] = variant
        now = datetime.now(timezone.utc)
        existing = await self._profile_async.find_one({"profile_name": prof_name})
        next_rev = int(existing.get("profile_revision") or 0) + 1 if isinstance(existing, dict) else 1
        # Держим один активный профиль, чтобы Telegram/Playground читали одинаковый эталон.
        await self._profile_async.update_many(
            {"is_active": True},
            {"$set": {"is_active": False, "status": "Archived", "updated_at": now}},
        )
        r = await self._profile_async.update_one(
            {"profile_name": prof_name},
            {
                "$set": {
                    "profile_name": prof_name,
                    "is_active": True,
                    "status": "Active",
                    "profile_revision": next_rev,
                    "pipeline_variant": variant,
                    "run_config": cfg,
                    "updated_at": now,
                    "updated_by_user_id": int(updated_by_user_id) if updated_by_user_id is not None else None,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        return bool(getattr(r, "acknowledged", False))

    def get_active_profile_sync(self) -> dict[str, Any] | None:
        if self._profile_sync is None:
            return None
        doc = self._profile_sync.find_one(
            {"is_active": True},
            sort=[("updated_at", -1)],
        )
        if not doc:
            return None
        d = dict(doc)
        if "_id" in d:
            d["_id"] = str(d.pop("_id"))
        return d

    async def save_draft_profile(
        self,
        *,
        run_config: dict[str, Any],
        pipeline_variant: str | None = None,
        updated_by_user_id: int | None = None,
        profile_name: str = "default",
    ) -> bool:
        if self._profile_async is None:
            return False
        base = default_run_config()
        cfg = self._merge_run_config(base, dict(run_config or {}))
        variant = str(
            pipeline_variant or cfg.get("pipeline_variant") or "pair_i2v_between_keyframes"
        ).strip() or "pair_i2v_between_keyframes"
        cfg["pipeline_variant"] = variant
        prof_name = (profile_name or "default").strip() or "default"
        now = datetime.now(timezone.utc)
        existing = await self._profile_async.find_one({"profile_name": prof_name, "status": "Draft"})
        draft_rev = int(existing.get("draft_revision") or 0) + 1 if isinstance(existing, dict) else 1
        r = await self._profile_async.update_one(
            {"profile_name": prof_name, "status": "Draft"},
            {
                "$set": {
                    "profile_name": prof_name,
                    "status": "Draft",
                    "is_active": False,
                    "draft_revision": draft_rev,
                    "pipeline_variant": variant,
                    "run_config": cfg,
                    "updated_at": now,
                    "updated_by_user_id": int(updated_by_user_id) if updated_by_user_id is not None else None,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        return bool(getattr(r, "acknowledged", False))

    def get_profile_sync(self, *, profile_name: str = "default", status: str = "Draft") -> dict[str, Any] | None:
        if self._profile_sync is None:
            return None
        doc = self._profile_sync.find_one(
            {"profile_name": (profile_name or "default").strip() or "default", "status": status},
            sort=[("updated_at", -1)],
        )
        if not doc:
            return None
        d = dict(doc)
        if "_id" in d:
            d["_id"] = str(d.pop("_id"))
        return d

    async def publish_draft_profile(self, *, profile_name: str = "default", updated_by_user_id: int | None = None) -> bool:
        if self._profile_async is None:
            return False
        prof_name = (profile_name or "default").strip() or "default"
        draft = await self._profile_async.find_one({"profile_name": prof_name, "status": "Draft"})
        if not draft:
            return False
        ok = await self.upsert_active_profile(
            run_config=dict(draft.get("run_config") or {}),
            pipeline_variant=str(draft.get("pipeline_variant") or "").strip() or None,
            updated_by_user_id=updated_by_user_id,
            profile_name=prof_name,
        )
        return bool(ok)

    async def rollback_active_profile(self, *, profile_name: str = "default", updated_by_user_id: int | None = None) -> bool:
        if self._profile_async is None:
            return False
        prof_name = (profile_name or "default").strip() or "default"
        archived = await self._profile_async.find_one(
            {"profile_name": prof_name, "status": "Archived"},
            sort=[("updated_at", -1)],
        )
        if not archived:
            return False
        ok = await self.upsert_active_profile(
            run_config=dict(archived.get("run_config") or {}),
            pipeline_variant=str(archived.get("pipeline_variant") or "").strip() or None,
            updated_by_user_id=updated_by_user_id,
            profile_name=prof_name,
        )
        return bool(ok)

    async def get_run(self, *, user_id: int, lite_run_id: str) -> dict[str, Any] | None:
        doc = await self._async.find_one(
            {"user_id": int(user_id), "lite_run_id": (lite_run_id or "").strip()},
        )
        if not doc:
            return None
        d = dict(doc)
        if "_id" in d:
            d["_id"] = str(d.pop("_id"))
        return d

    async def get_latest_run_for_user(self, *, user_id: int) -> dict[str, Any] | None:
        doc = await self._async.find_one(
            {"user_id": int(user_id)},
            sort=[("created_at", -1)],
        )
        if not doc:
            return None
        d = dict(doc)
        if "_id" in d:
            d["_id"] = str(d.pop("_id"))
        return d

    async def update_run(
        self,
        *,
        user_id: int,
        lite_run_id: str,
        patch: dict[str, Any],
    ) -> bool:
        lid = (lite_run_id or "").strip()
        if not lid:
            return False
        p = {**patch, "updated_at": datetime.now(timezone.utc)}
        r = await self._async.update_one(
            {"user_id": int(user_id), "lite_run_id": lid},
            {"$set": p},
        )
        return bool(getattr(r, "modified_count", 0))

    async def append_execution_trace(
        self,
        *,
        user_id: int,
        lite_run_id: str,
        event: dict[str, Any],
        max_items: int = 300,
    ) -> bool:
        lid = (lite_run_id or "").strip()
        if not lid:
            return False
        item = {**(event or {}), "ts": datetime.now(timezone.utc)}
        r = await self._async.update_one(
            {"user_id": int(user_id), "lite_run_id": lid},
            {
                "$set": {"updated_at": datetime.now(timezone.utc)},
                "$push": {"execution_trace": {"$each": [item], "$slice": -max(20, int(max_items))}},
            },
        )
        return bool(getattr(r, "modified_count", 0))

    async def fail_stale_active_runs(
        self,
        *,
        user_id: int,
        max_idle_seconds: int,
        reason: str,
    ) -> int:
        """Переводит зависшие active run в failed по таймауту updated_at."""
        idle = max(1, int(max_idle_seconds))
        threshold = datetime.now(timezone.utc).timestamp() - idle
        dt = datetime.fromtimestamp(threshold, tz=timezone.utc)
        patch = {
            "run_status": "failed",
            "step_phase": "failed",
            "last_error": reason,
            "updated_at": datetime.now(timezone.utc),
        }
        r = await self._async.update_many(
            {
                "user_id": int(user_id),
                "run_status": "active",
                "updated_at": {"$lt": dt},
            },
            {"$set": patch},
        )
        return int(getattr(r, "modified_count", 0) or 0)

    async def mark_expired_runs_archived(self, *, now: datetime | None = None) -> int:
        dt = now or datetime.now(timezone.utc)
        r = await self._async.update_many(
            {
                "retention_until": {"$ne": None, "$lt": dt},
                "archived_at": None,
            },
            {
                "$set": {
                    "archived_at": dt,
                    "updated_at": dt,
                }
            },
        )
        return int(getattr(r, "modified_count", 0) or 0)

    def list_recent_runs_sync(
        self,
        *,
        limit: int = 50,
        user_id: int | None = None,
    ) -> list[dict[str, Any]]:
        q: dict[str, Any] = {}
        if user_id is not None:
            q["user_id"] = int(user_id)
        lim = max(1, min(int(limit), 200))
        cur = self._sync.find(q).sort("updated_at", -1).limit(lim)
        out: list[dict[str, Any]] = []
        for doc in cur:
            d = dict(doc)
            if "_id" in d:
                d["_id"] = str(d.pop("_id"))
            out.append(d)
        return out

    def get_run_sync(self, *, user_id: int, lite_run_id: str) -> dict[str, Any] | None:
        doc = self._sync.find_one(
            {"user_id": int(user_id), "lite_run_id": (lite_run_id or "").strip()},
        )
        if not doc:
            return None
        d = dict(doc)
        if "_id" in d:
            d["_id"] = str(d.pop("_id"))
        return d
