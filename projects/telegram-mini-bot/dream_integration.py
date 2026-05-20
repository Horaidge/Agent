"""Опциональная интеграция Dream Lite из projects/content (Mongo + пайплайн)."""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from config import Settings, get_settings as get_mini_settings

logger = logging.getLogger(__name__)

_CONTENT_ROOT = Path(__file__).resolve().parent.parent / "content"


@dataclass
class DreamLiteContext:
    dream_lite_run_repo: Any
    dream_lite_summary_repo: Any | None
    dream_lite_asset_repo: Any | None
    dream_pipeline_service: Any
    openai: Any
    reply_keyboard: Any


def dream_lite_enabled(mini: Settings) -> bool:
    if not mini.dream_lite_enabled:
        return False
    return bool((mini.mongodb_uri or "").strip())


def _bootstrap_content_env(mini: Settings, content_root: Path) -> None:
    """Подмешать env content без перезаписи токена мини-бота."""
    preserved = {
        "TELEGRAM_BOT_TOKEN": os.environ.get("TELEGRAM_BOT_TOKEN"),
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY"),
        "OPENAI_MODEL": os.environ.get("OPENAI_MODEL"),
        "OPENAI_PROXY_URL": os.environ.get("OPENAI_PROXY_URL"),
    }
    for name in ("ENV", "env", ".env"):
        path = content_root / name
        if path.is_file():
            load_dotenv(path, override=False)
    if mini.mongodb_uri:
        os.environ["MONGODB_URI"] = mini.mongodb_uri
    if mini.mongodb_db:
        os.environ["MONGODB_DB"] = mini.mongodb_db
    if mini.public_base_url:
        os.environ["PUBLIC_BASE_URL"] = mini.public_base_url
    if mini.openai_api_key:
        os.environ.setdefault("OPENAI_API_KEY", mini.openai_api_key)
    if mini.openai_model:
        os.environ.setdefault("OPENAI_MODEL", mini.openai_model)
    if mini.openai_proxy_url:
        os.environ.setdefault("OPENAI_PROXY_URL", mini.openai_proxy_url)
    for key, val in preserved.items():
        if val:
            os.environ[key] = val


@lru_cache
def get_dream_context() -> DreamLiteContext | None:
    mini = get_mini_settings()
    if not dream_lite_enabled(mini):
        return None

    content_root = Path(mini.content_project_root).resolve()
    if not content_root.is_dir():
        logger.error("Dream Lite: каталог content не найден: %s", content_root)
        return None

    root_str = str(content_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    _bootstrap_content_env(mini, content_root)

    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        from pymongo import MongoClient

        from core.config.settings import get_settings as get_content_settings
        from services.dreams.dream_orchestrator import DreamPipelineService
        from services.dreams.user_asset_context_service import UserAssetContextService
        from services.llm.openai_chat_service import OpenAIChatService
        from services.telegram_reply_keyboards import main_reply_keyboard
        from services.video.video_job_service import VideoJobService
        from storage.mongo import (
            build_dream_asset_repository,
            build_dream_lite_asset_repository,
            build_dream_lite_run_repository,
            build_dream_lite_summary_repository,
            build_dream_run_repository,
            build_dream_scene_repository,
            build_generated_frame_repository,
            build_generated_image_repository,
            build_scene_video_repository,
            build_story_video_repository,
            build_user_profile_repository,
            build_video_job_repository,
        )
    except Exception:
        logger.exception("Dream Lite: не удалось импортировать модули content")
        return None

    try:
        settings = get_content_settings()
        os.environ["TELEGRAM_BOT_TOKEN"] = mini.telegram_bot_token

        motor_client = AsyncIOMotorClient(settings.mongodb_uri)
        sync_client = MongoClient(settings.mongodb_uri)

        dream_lite_run_repo = build_dream_lite_run_repository(
            settings, motor_client, sync_client
        )
        dream_lite_summary_repo = build_dream_lite_summary_repository(
            settings, motor_client, sync_client
        )
        dream_lite_asset_repo = build_dream_lite_asset_repository(
            settings, motor_client, sync_client
        )
        dream_run_repo = build_dream_run_repository(settings, motor_client, sync_client)
        dream_scene_repo = build_dream_scene_repository(settings, motor_client, sync_client)
        generated_frame_repo = build_generated_frame_repository(
            settings, motor_client, sync_client
        )
        scene_video_repo = build_scene_video_repository(
            settings, motor_client, sync_client
        )
        story_video_repo = build_story_video_repository(
            settings, motor_client, sync_client
        )
        dream_asset_repo = build_dream_asset_repository(
            settings, motor_client, sync_client
        )
        user_profile_repo = build_user_profile_repository(
            settings, motor_client, sync_client
        )
        generated_image_repo = build_generated_image_repository(
            settings, motor_client, sync_client
        )
        video_job_repo = build_video_job_repository(settings, motor_client, sync_client)

        openai_chat = OpenAIChatService(
            settings.openai_api_key,
            settings.openai_model,
            proxy_url=settings.openai_proxy_url,
        )
        video_job_service = VideoJobService(video_job_repo, settings)
        user_asset_context = UserAssetContextService(
            dream_asset_repo,
            user_profile_repo,
            generated_frame_repo,
            generated_image_repo,
            video_job_repo,
        )
        dream_pipeline = DreamPipelineService(
            settings,
            dream_run_repo=dream_run_repo,
            dream_scene_repo=dream_scene_repo,
            frame_repo=generated_frame_repo,
            scene_video_repo=scene_video_repo,
            story_repo=story_video_repo,
            dream_asset_repo=dream_asset_repo,
            user_profile_repo=user_profile_repo,
            user_context=user_asset_context,
            video_jobs=video_job_service,
            openai=openai_chat,
            observability=None,
            generated_image_repo=generated_image_repo,
        )

        logger.info(
            "Dream Lite подключён (mongo=%s, content=%s)",
            settings.mongodb_uri.split("@")[-1] if "@" in settings.mongodb_uri else settings.mongodb_uri,
            content_root,
        )
        return DreamLiteContext(
            dream_lite_run_repo=dream_lite_run_repo,
            dream_lite_summary_repo=dream_lite_summary_repo,
            dream_lite_asset_repo=dream_lite_asset_repo,
            dream_pipeline_service=dream_pipeline,
            openai=openai_chat,
            reply_keyboard=main_reply_keyboard,
        )
    except Exception:
        logger.exception("Dream Lite: ошибка инициализации")
        return None
