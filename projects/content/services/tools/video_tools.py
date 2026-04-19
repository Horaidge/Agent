"""
Tool: image-to-video (Wan) без привязки к Telegram/LLM.

Создаёт запись в Mongo и сразу возвращает job_id; завершение — в фоновом polling.
"""
from __future__ import annotations

import logging
from typing import Any

from pymongo import MongoClient

from core.config.settings import get_settings
from services.video.video_job_service import VideoJobService
from storage.video_job_repository import VideoJobRepository

logger = logging.getLogger(__name__)

_mongo_client: MongoClient | None = None


def _video_service() -> VideoJobService:
    """Один sync MongoClient на процесс — фоновый polling продолжает использовать коллекцию."""
    global _mongo_client
    settings = get_settings()
    if _mongo_client is None:
        _mongo_client = MongoClient(settings.mongodb_uri)
    coll = _mongo_client[settings.mongodb_db][settings.mongodb_collection_video_jobs]
    repo = VideoJobRepository(async_collection=None, sync_collection=coll)
    return VideoJobService(repo, settings)


def get_video_job_service() -> VideoJobService:
    """Тот же экземпляр сервиса, что использует tool_image_to_video (скрипты, тесты)."""
    return _video_service()


def tool_image_to_video(
    prompt: str,
    image_url: str,
    duration: int = 4,
    resolution: str = "720p",
    *,
    owner_user_id: str = "manual",
    model: str = "wan2.7-i2v",
    job_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Запускает асинхронную генерацию видео. Не ждёт готовности видео.

    Возвращает job_id и текущий статус (обычно running после успешного create).
    """
    logger.info(
        "tool_image_to_video: owner=%s model=%s duration=%s",
        owner_user_id,
        model,
        duration,
    )
    svc = _video_service()
    try:
        job_id = svc.create_video_job(
            owner_user_id=owner_user_id,
            prompt=prompt,
            image_url=image_url,
            model=model,
            duration=duration,
            resolution=resolution,
            extra=job_extra,
        )
    except Exception as e:
        logger.exception("tool_image_to_video: неожиданная ошибка")
        return {
            "ok": False,
            "job_id": None,
            "status": "failed",
            "video_url": None,
            "error": str(e),
        }

    doc = svc.get_job(job_id) or {}
    st = doc.get("status") or "unknown"
    err = doc.get("error")
    ok = st == "running" or st == "created"
    return {
        "ok": ok,
        "job_id": job_id,
        "status": st,
        "video_url": doc.get("video_url"),
        "error": err,
    }
