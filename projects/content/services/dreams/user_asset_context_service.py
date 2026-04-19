"""Сбор нормализованного контекста ассетов пользователя для dream pipeline."""
from __future__ import annotations

from typing import Any

from services.assets.dream_asset_service import ASSET_TYPE_FACE, STATUS_CLASSIFIED
from storage.dream_asset_repository import DreamAssetRepository
from storage.generated_frame_repository import GeneratedFrameRepository
from storage.generated_image_repository import GeneratedImageRepository
from storage.user_profile_repository import UserProfileRepository
from storage.video_job_repository import VideoJobRepository


class UserAssetContextService:
    def __init__(
        self,
        dream_assets: DreamAssetRepository,
        user_profiles: UserProfileRepository,
        generated_frames: GeneratedFrameRepository,
        generated_images: GeneratedImageRepository,
        video_jobs: VideoJobRepository,
    ) -> None:
        self._dream = dream_assets
        self._profiles = user_profiles
        self._frames = generated_frames
        self._genimg = generated_images
        self._video = video_jobs

    async def build(self, user_id: int) -> dict[str, Any]:
        prof = await self._profiles.get_by_user_id(user_id)
        assets = await self._dream.list_by_owner(user_id, limit=300)

        face_assets = [
            a
            for a in assets
            if (a.get("asset_type") or "").lower() == ASSET_TYPE_FACE
            and (a.get("status") or "") == STATUS_CLASSIFIED
        ]
        env_assets = [
            a
            for a in assets
            if (a.get("asset_type") or "").lower() == "environment"
            and (a.get("status") or "") == STATUS_CLASSIFIED
        ]
        dream_obj = [
            a
            for a in assets
            if (a.get("asset_type") or "").lower() in ("dream_object", "character", "other")
            and (a.get("status") or "") == STATUS_CLASSIFIED
        ]

        has_face = len(face_assets) > 0
        base_id = (prof or {}).get("base_character_asset_id")
        has_base = bool(base_id)

        missing: list[str] = []
        if not has_face and not has_base:
            missing.append("identity")
        if not env_assets:
            missing.append("environment")

        n_frames = await self._frames.count_for_user(user_id)
        n_genimg = await self._genimg.count_for_user(user_id)

        owner = str(user_id)
        all_vj = self._video.list_recent_sync(limit=80)
        video_snippets = []
        for doc in all_vj:
            if str(doc.get("owner_user_id")) != owner:
                continue
            video_snippets.append(
                {
                    "_id": doc.get("_id"),
                    "status": doc.get("status"),
                    "dream_trace_id": doc.get("dream_trace_id"),
                }
            )
            if len(video_snippets) >= 15:
                break

        return {
            "user_id": user_id,
            "has_face": has_face,
            "has_base_character": has_base,
            "base_character_asset_id": base_id,
            "face_assets": face_assets,
            "environment_assets": env_assets,
            "dream_assets": dream_obj,
            "all_classified_assets": [
                a for a in assets if (a.get("status") or "") == STATUS_CLASSIFIED
            ],
            "generated_frames_count": n_frames,
            "generated_images_count": n_genimg,
            "recent_video_jobs": video_snippets,
            "missing": missing,
            "user_profile": prof or {},
        }

    async def build_storage_snapshot(self, user_id: int) -> dict[str, Any]:
        """Компактный снимок для `dream_runs.asset_context_snapshot` и dev UI."""
        ctx = await self.build(user_id)
        face_ids = [a.get("_id") for a in (ctx.get("face_assets") or []) if a.get("_id")]
        env_ids = [
            a.get("_id") for a in (ctx.get("environment_assets") or []) if a.get("_id")
        ]
        base_id = ctx.get("base_character_asset_id")
        selected = base_id
        role = "none"
        if base_id:
            role = "base_character"
        elif face_ids:
            selected = face_ids[0]
            role = "face_asset"

        base_preview: str | None = None
        if base_id:
            asset = await self._dream.find_by_id(base_id)
            if asset:
                base_preview = asset.get("source_image_url")

        return {
            "has_face": ctx.get("has_face"),
            "has_base_character": ctx.get("has_base_character"),
            "base_character_asset_id": base_id,
            "base_character_preview_url": base_preview,
            "face_asset_ids": face_ids,
            "environment_asset_ids": env_ids,
            "missing": list(ctx.get("missing") or []),
            "selected_character_asset_id": selected,
            "selected_reference_role": role,
        }
