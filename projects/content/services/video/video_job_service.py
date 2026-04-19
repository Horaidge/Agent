"""
Оркестрация задач image-to-video: Mongo `video_jobs` + polling DashScope в фоновом потоке.

Поток не блокирует вызывающий код; используется sync httpx + sync PyMongo.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

from core.config.settings import Settings
from services.video.wan_i2v_client import (
    WanI2vClientError,
    create_video_task,
    get_video_task_status,
)
from storage.video_job_repository import VideoJobRepository

logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 5.0


def compact_image_url_for_storage(api_image_ref: str) -> str:
    """
    Не кладём в Mongo огромный data URI (лимит документа ~16MB).
    Для https оставляем URL; для data: — только длина.
    """
    s = api_image_ref or ""
    if s.startswith("data:"):
        return f"<data URI, {len(s)} chars>"
    if len(s) > 4000:
        return s[:4000] + "…"
    return s


def _synthesis_url(settings: Settings) -> str | None:
    u = (settings.dashscope_video_endpoint or "").strip()
    return u or None


class VideoJobService:
    def __init__(self, repository: VideoJobRepository, settings: Settings) -> None:
        self._repo = repository
        self._settings = settings

    def create_video_job(
        self,
        *,
        owner_user_id: str,
        prompt: str,
        image_url: str,
        model: str = "wan2.7-i2v",
        duration: int = 4,
        resolution: str = "720p",
        extra: dict[str, Any] | None = None,
    ) -> str:
        """
        Создаёт документ job, вызывает DashScope, сохраняет provider_task_id,
        запускает фоновый polling (daemon thread). Возвращает Mongo job_id.

        `image_url` — строка для API (URL или data URI). В Mongo сохраняется
        компактное представление через `compact_image_url_for_storage`.
        `extra` — доп. поля (source_type, dream_asset_id, …).
        """
        doc: dict[str, Any] = {
            "owner_user_id": owner_user_id,
            "prompt": prompt,
            "image_url": compact_image_url_for_storage(image_url),
            "model": model,
            "duration": duration,
            "resolution": resolution,
            "provider_task_id": None,
            "status": "created",
            "video_url": None,
            "error": None,
        }
        if extra:
            doc.update(extra)
        job_id = self._repo.insert_job_sync(doc)
        logger.info("video job создан job_id=%s owner=%s", job_id, owner_user_id)
        syn = _synthesis_url(self._settings)
        try:
            task_id, raw = create_video_task(
                prompt=prompt,
                image_url=image_url,
                model=model,
                duration=duration,
                resolution=resolution,
                synthesis_url=syn,
            )
        except WanI2vClientError as e:
            logger.warning("video job: ошибка создания задачи job_id=%s: %s", job_id, e)
            self._repo.update_job_sync(
                job_id,
                {
                    "status": "failed",
                    "error": str(e),
                },
            )
            return job_id
        except Exception as e:
            logger.exception("video job: неожиданная ошибка create task job_id=%s", job_id)
            self._repo.update_job_sync(job_id, {"status": "failed", "error": str(e)})
            return job_id

        self._repo.update_job_sync(
            job_id,
            {
                "provider_task_id": task_id,
                "status": "running",
                "raw_create_response": raw,
            },
        )
        logger.info(
            "video job: provider task_id=%s job_id=%s — запуск polling",
            task_id,
            job_id,
        )
        t = threading.Thread(
            target=self._poll_loop,
            args=(job_id, task_id, syn),
            name=f"wan-i2v-poll-{job_id[:8]}",
            daemon=True,
        )
        t.start()
        return job_id

    def _poll_loop(
        self,
        job_id: str,
        provider_task_id: str,
        synthesis_url: str | None,
    ) -> None:
        try:
            while True:
                try:
                    st = get_video_task_status(
                        provider_task_id,
                        synthesis_url=synthesis_url,
                    )
                except WanI2vClientError as e:
                    logger.warning(
                        "video job: ошибка опроса job_id=%s: %s",
                        job_id,
                        e,
                    )
                    self._repo.update_job_sync(
                        job_id,
                        {"status": "failed", "error": f"poll: {e}"},
                    )
                    return

                patch: dict[str, Any] = {"status": "running"}
                if st.progress is not None:
                    patch["progress"] = st.progress

                if st.status == "SUCCEEDED":
                    patch["status"] = "succeeded"
                    patch["video_url"] = st.video_url
                    patch["error"] = None
                    self._repo.update_job_sync(job_id, patch)
                    logger.info(
                        "video job успех job_id=%s video_url присутствует=%s",
                        job_id,
                        bool(st.video_url),
                    )
                    return

                if st.status in ("FAILED", "CANCELED"):
                    patch["status"] = "failed"
                    patch["error"] = st.error or st.status
                    self._repo.update_job_sync(job_id, patch)
                    logger.warning(
                        "video job провайдер завершил с ошибкой job_id=%s detail=%s",
                        job_id,
                        patch.get("error"),
                    )
                    return

                if st.status == "UNKNOWN":
                    patch["status"] = "failed"
                    patch["error"] = "UNKNOWN (истёк срок task_id или задача не найдена)"
                    self._repo.update_job_sync(job_id, patch)
                    return

                # PENDING / RUNNING
                self._repo.update_job_sync(job_id, patch)
                logger.info(
                    "video job polling job_id=%s provider_status=%s",
                    job_id,
                    st.status,
                )
                time.sleep(POLL_INTERVAL_SEC)
        except Exception as e:
            logger.exception("video job: критическая ошибка polling job_id=%s", job_id)
            try:
                self._repo.update_job_sync(
                    job_id,
                    {"status": "failed", "error": str(e)},
                )
            except Exception:
                logger.exception("video job: не удалось записать ошибку job_id=%s", job_id)

    def update_job_status(self, job_id: str, patch: dict[str, Any]) -> None:
        """Ручное обновление полей job (например для админки)."""
        self._repo.update_job_sync(job_id, patch)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return self._repo.get_job_sync(job_id)

    def poll_job_until_done(
        self,
        job_id: str,
        *,
        timeout_sec: float = 1200.0,
        interval_sec: float = 2.0,
    ) -> dict[str, Any]:
        """
        Блокирует поток до terminal статуса в Mongo (polling обновляет документ в фоне).

        Не дублирует HTTP-опрос провайдера — только чтение коллекции.
        """
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout_sec:
            job = self._repo.get_job_sync(job_id)
            if not job:
                raise KeyError(f"job не найден: {job_id}")
            st = job.get("status")
            if st == "succeeded":
                return job
            if st == "failed":
                return job
            time.sleep(interval_sec)
        raise TimeoutError(f"Таймаут ожидания job {job_id} в Mongo ({timeout_sec}s)")
