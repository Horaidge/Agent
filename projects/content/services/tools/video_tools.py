"""
Tool: image-to-video (Wan) без привязки к Telegram/LLM.

Создаёт запись в Mongo и сразу возвращает job_id; завершение — в фоновом polling.
"""
from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
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
    last_frame_url: str | None = None,
    job_extra: dict[str, Any] | None = None,
    video_backend: str | None = None,
    openrouter_model: str | None = None,
    openrouter_provider: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Запускает асинхронную генерацию видео. Не ждёт готовности видео.

    Возвращает job_id и текущий статус (обычно running после успешного create).
    """
    logger.info(
        "tool_image_to_video: owner=%s model=%s duration=%s backend=%s",
        owner_user_id,
        model,
        duration,
        video_backend or "(settings)",
    )
    svc = _video_service()
    try:
        job_id = svc.create_video_job(
            owner_user_id=owner_user_id,
            prompt=prompt,
            image_url=image_url,
            last_frame_url=last_frame_url,
            model=model,
            duration=duration,
            resolution=resolution,
            extra=job_extra,
            video_backend=video_backend,
            openrouter_model=openrouter_model,
            openrouter_provider=openrouter_provider,
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


def _chat_concat_static_dir() -> Path:
    root = Path(__file__).resolve().parent.parent.parent / "ui" / "dev" / "static" / "chat_concat"
    root.mkdir(parents=True, exist_ok=True)
    return root


def tool_concat_remote_video_urls(
    video_urls: list[str],
    *,
    owner_user_id: str = "manual",
    label: str | None = None,
) -> dict[str, Any]:
    """
    Скачивает mp4 по URL и склеивает через ffmpeg (как dream final assembler).
    Пишет файл под ui/dev/static/chat_concat/ и возвращает публичный путь /dev/static/...
    """
    from services.video.final_video_assembler import FinalVideoAssemblerError, assemble_remote_mp4s

    cleaned: list[str] = []
    for u in video_urls or []:
        s = str(u or "").strip()
        if not s:
            continue
        if not s.lower().startswith(("http://", "https://")):
            return {
                "ok": False,
                "error": f"Каждый URL должен быть http(s): пропуск или неверный формат: {s[:80]}",
                "final_video_url": None,
                "local_path": None,
            }
        cleaned.append(s)

    if len(cleaned) < 1:
        return {
            "ok": False,
            "error": "Нужен хотя бы один video_url",
            "final_video_url": None,
            "local_path": None,
        }

    safe_label = re.sub(r"[^a-zA-Z0-9._-]+", "_", (label or "").strip())[:40]
    part = safe_label or uuid.uuid4().hex[:10]
    owner = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(owner_user_id or "u").strip())[:24] or "u"
    fname = f"concat_{owner}_{part}.mp4"
    out_path = _chat_concat_static_dir() / fname

    try:
        assemble_remote_mp4s(cleaned, out_path)
    except FinalVideoAssemblerError as e:
        logger.warning("tool_concat_remote_video_urls: %s", e)
        return {
            "ok": False,
            "error": str(e),
            "final_video_url": None,
            "local_path": None,
        }
    except Exception as e:  # noqa: BLE001
        logger.exception("tool_concat_remote_video_urls")
        return {
            "ok": False,
            "error": str(e),
            "final_video_url": None,
            "local_path": None,
        }

    public = f"/dev/static/chat_concat/{fname}"
    return {
        "ok": True,
        "error": None,
        "final_video_url": public,
        "local_path": str(out_path.resolve()),
        "clips_merged": len(cleaned),
    }
