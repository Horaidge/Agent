"""Операции «мои данные» в Telegram: очистка истории, список/удаление сгенерированных изображений."""
from __future__ import annotations

from typing import Any

from bson import ObjectId
from core.observability.repository import ObservabilityRepository
from storage.chat_repository import ChatStoreRepository
from storage.dream_asset_repository import DreamAssetRepository
from storage.dream_run_repository import DreamRunRepository
from storage.dream_scene_repository import DreamSceneRepository
from storage.generated_frame_repository import GeneratedFrameRepository
from storage.generated_image_repository import GeneratedImageRepository
from storage.scene_video_repository import SceneVideoRepository
from storage.story_video_repository import StoryVideoRepository
from storage.user_profile_repository import UserProfileRepository
from storage.repository import MessageRepository
from storage.video_job_repository import VideoJobRepository


class UserDataService:
    def __init__(
        self,
        message_repo: MessageRepository,
        chat_store: ChatStoreRepository,
        generated_image_repo: GeneratedImageRepository,
        generated_frame_repo: GeneratedFrameRepository,
        story_video_repo: StoryVideoRepository,
        dream_asset_repo: DreamAssetRepository,
        user_profile_repo: UserProfileRepository,
        dream_run_repo: DreamRunRepository,
        dream_scene_repo: DreamSceneRepository,
        scene_video_repo: SceneVideoRepository,
        video_job_repo: VideoJobRepository,
        *,
        observability_repo: ObservabilityRepository | None = None,
    ) -> None:
        self._messages = message_repo
        self._chat = chat_store
        self._images = generated_image_repo
        self._frames = generated_frame_repo
        self._story = story_video_repo
        self._assets = dream_asset_repo
        self._profiles = user_profile_repo
        self._runs = dream_run_repo
        self._scenes = dream_scene_repo
        self._scene_videos = scene_video_repo
        self._video_jobs = video_job_repo
        self._obs = observability_repo

    async def get_user_overview(self, telegram_user_id: int) -> dict[str, Any]:
        uid = telegram_user_id
        profile = await self._profiles.get_by_user_id(uid)
        avatar_asset_id = (profile or {}).get("base_character_asset_id")
        avatar_created_at = None
        if avatar_asset_id:
            asset = await self._assets.find_by_id(avatar_asset_id)
            avatar_created_at = (asset or {}).get("created_at")

        assets_total = await self._assets.count_by_owner(uid)
        actors_count = await self._assets.count_by_owner(
            uid, {"asset_type": "character", "is_secondary_actor": True}
        )
        env_count = await self._assets.count_by_owner(uid, {"asset_type": "environment"})
        images_count = await self._images.count_for_user(uid)
        frames_count = await self._frames.count_for_user(uid)
        videos_count = await self._story.count_for_user(uid)
        messages_count = await self._chat.count_conversation_for_internal_user(str(uid))
        runs_count = await self._runs.count_for_user(uid)
        inbound_count = await self._messages.count_by_telegram_user_id(uid)
        return {
            "avatar_exists": bool(avatar_asset_id),
            "avatar_created_at": avatar_created_at,
            "assets_total": int(assets_total),
            "actors_count": int(actors_count),
            "environments_count": int(env_count),
            "images_count": int(images_count + frames_count),
            "videos_count": int(videos_count),
            "messages_count": int(messages_count + inbound_count),
            "dream_runs_count": int(runs_count),
        }

    async def clear_bot_history(self, telegram_user_id: int) -> dict[str, int]:
        """Удалить сохранённые сообщения, диалог агента и (если есть) события observability."""
        n_msg = await self._messages.delete_by_telegram_user_id(telegram_user_id)
        conv, mod, tool = await self._chat.delete_for_internal_user(str(telegram_user_id))
        n_obs = 0
        if self._obs is not None:
            n_obs = await self._obs.delete_by_telegram_user_id(telegram_user_id)
        return {
            "inbound_messages": n_msg,
            "conversation_messages": conv,
            "model_calls": mod,
            "tool_calls": tool,
            "observability_events": n_obs,
        }

    async def list_generated_images(
        self,
        telegram_user_id: int,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        return await self._images.list_for_user(telegram_user_id, limit=limit)

    async def delete_all_generated_images(self, telegram_user_id: int) -> int:
        return await self._images.delete_all_for_user(telegram_user_id)

    async def delete_avatar(self, telegram_user_id: int) -> dict[str, int]:
        profile = await self._profiles.get_by_user_id(telegram_user_id)
        avatar_asset_id = (profile or {}).get("base_character_asset_id")
        n_assets = 0
        if avatar_asset_id:
            try:
                n_assets = await self._assets.delete_by_owner(
                    telegram_user_id,
                    {"_id": ObjectId(str(avatar_asset_id))},
                )
            except Exception:
                n_assets = 0
        await self._profiles.clear_base_character_asset(telegram_user_id)
        return {
            "avatar_assets_deleted": int(n_assets),
            "profile_updated": 1,
        }

    async def delete_videos(self, telegram_user_id: int) -> dict[str, int]:
        run_ids = await self._runs.list_ids_for_user(telegram_user_id, limit=5000)
        n_story = await self._story.delete_for_user(telegram_user_id)
        n_scene_videos = await self._scene_videos.delete_by_dream_run_ids(run_ids)
        n_video_jobs = await self._video_jobs.delete_for_owner(str(telegram_user_id))
        return {
            "story_videos": int(n_story),
            "scene_videos": int(n_scene_videos),
            "video_jobs": int(n_video_jobs),
        }

    async def clear_all_user_data(self, telegram_user_id: int) -> dict[str, int]:
        stats = await self.clear_bot_history(telegram_user_id)
        run_ids = await self._runs.list_ids_for_user(telegram_user_id, limit=5000)
        n_imgs = await self._images.delete_all_for_user(telegram_user_id)
        n_frames = await self._frames.delete_for_user(telegram_user_id)
        n_story = await self._story.delete_for_user(telegram_user_id)
        n_scene = await self._scenes.delete_by_dream_run_ids(run_ids)
        n_scene_vid = await self._scene_videos.delete_by_dream_run_ids(run_ids)
        n_runs = await self._runs.delete_for_user(telegram_user_id)
        n_assets = await self._assets.delete_by_owner(telegram_user_id)
        n_prof = await self._profiles.delete_for_user(telegram_user_id)
        n_vjobs = await self._video_jobs.delete_for_owner(str(telegram_user_id))
        stats.update(
            {
                "generated_images": int(n_imgs),
                "generated_frames": int(n_frames),
                "story_videos": int(n_story),
                "dream_scenes": int(n_scene),
                "scene_videos": int(n_scene_vid),
                "dream_runs": int(n_runs),
                "dream_assets": int(n_assets),
                "user_profiles": int(n_prof),
                "video_jobs": int(n_vjobs),
            }
        )
        return stats
