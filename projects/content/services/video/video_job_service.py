"""
Оркестрация задач image-to-video: Mongo `video_jobs` + фоновый polling.

Бэкенды: DashScope (прямой Wan API) или OpenRouter (`POST /api/v1/videos`, напр. alibaba/wan-2.7).
"""
from __future__ import annotations

import base64
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from core.config.settings import Settings
from services.video.openrouter_video_client import (
    OpenRouterVideoError,
    normalize_openrouter_video_model_id,
    poll_openrouter_video_job,
    submit_openrouter_video_job,
)
from services.video.wan_i2v_client import (
    WanI2vClientError,
    create_video_task,
    get_video_task_status,
)
from storage.video_job_repository import VideoJobRepository

logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 5.0
# Макс. время опроса провайдера для одной задачи (после — failed в Mongo, чтобы не висеть running вечно)
_MAX_POLL_WALL_SEC = float(os.environ.get("VIDEO_JOB_MAX_POLL_SEC", "2700"))
_OPENROUTER_QUEUE_STALE_SEC = float(os.environ.get("OPENROUTER_QUEUE_STALE_SEC", "600"))
_REFERENCE_CHECK_TIMEOUT_SEC = float(os.environ.get("OPENROUTER_REFERENCE_CHECK_TIMEOUT_SEC", "12"))
_KLING_V3_STD_MODEL_ID = "kwaivgi/kling-v3.0-std"
_KLING_REFERENCE_PRESET = "kling_v3_reference_motion"
# Защита от двух потоков опроса на один job_id (рестарт сервера + новый poll)
_poll_lock = threading.Lock()
_active_poll_job_ids: set[str] = set()


def _try_begin_poll(job_id: str) -> bool:
    with _poll_lock:
        if job_id in _active_poll_job_ids:
            return False
        _active_poll_job_ids.add(job_id)
        return True


def _end_poll(job_id: str) -> None:
    with _poll_lock:
        _active_poll_job_ids.discard(job_id)


def _parse_job_dt(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        dt = val
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    s = str(val).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


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


def compact_provider_payload_for_storage(payload: Any, *, max_str: int = 4000) -> Any:
    """
    Сжимает сырой ответ провайдера перед записью в Mongo.
    Нужен, чтобы избежать DocumentTooLarge на больших вложенных полях.
    """
    if payload is None:
        return None
    if isinstance(payload, dict):
        return {str(k): compact_provider_payload_for_storage(v, max_str=max_str) for k, v in payload.items()}
    if isinstance(payload, list):
        return [compact_provider_payload_for_storage(v, max_str=max_str) for v in payload]
    s = str(payload)
    if len(s) <= max_str:
        return payload
    return s[:max_str] + f"…<truncated {len(s) - max_str} chars>"


def _synthesis_url(settings: Settings) -> str | None:
    u = (settings.dashscope_video_endpoint or "").strip()
    return u or None


def _dev_static_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "ui" / "dev" / "static"


def _resolve_image_url_for_provider(url: str | None, settings: Settings) -> str | None:
    u = str(url or "").strip()
    if not u:
        return None
    if u.startswith(("http://", "https://", "data:")):
        return u
    if not u.startswith("/dev/static/"):
        return u
    public_base = (settings.public_base_url or "").strip().rstrip("/")
    if public_base:
        return f"{public_base}{u}"
    rel = u[len("/dev/static/") :].lstrip("/")
    base = _dev_static_root().resolve()
    path = (base / rel).resolve()
    try:
        path.relative_to(base)
    except ValueError:
        return None
    if not path.is_file():
        return None
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    suffix = path.suffix.lower()
    mime = "image/png"
    if suffix in {".jpg", ".jpeg"}:
        mime = "image/jpeg"
    elif suffix == ".webp":
        mime = "image/webp"
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _is_strict_reference_validation_enabled(*, relaxed: bool) -> bool:
    if relaxed:
        return False
    raw = os.environ.get("OPENROUTER_STRICT_REFERENCE_VALIDATION", "1")
    return str(raw).strip().lower() not in {"0", "false", "off", "no"}


def _validate_reference_image_url(
    image_url: str,
    *,
    relaxed: bool,
) -> tuple[bool, str]:
    u = str(image_url or "").strip()
    if not u:
        return False, "missing_reference_image_url"
    if relaxed and u.startswith("data:"):
        return True, ""
    if not u.startswith("https://"):
        return False, "reference_image_must_be_public_https"
    if not _is_strict_reference_validation_enabled(relaxed=relaxed):
        return True, ""
    parsed = urlparse(u)
    if parsed.scheme != "https" or not parsed.netloc:
        return False, "reference_image_invalid_https_url"
    headers = {"User-Agent": "DreamPipelineLite/1.0"}
    try:
        with httpx.Client(timeout=_REFERENCE_CHECK_TIMEOUT_SEC, follow_redirects=True) as client:
            head = client.head(u, headers=headers)
            if head.status_code >= 400 or not head.headers:
                head = client.get(u, headers=headers)
    except Exception as exc:  # noqa: BLE001
        return False, f"reference_image_unreachable:{exc}"
    final_url = str(getattr(head, "url", "") or "")
    if final_url and not final_url.startswith("https://"):
        return False, "reference_image_redirected_to_non_https"
    content_type = str(head.headers.get("Content-Type") or "").lower()
    if not content_type.startswith("image/"):
        return False, "reference_image_content_type_not_image"
    cl = str(head.headers.get("Content-Length") or "").strip()
    if not cl:
        return False, "reference_image_missing_content_length"
    try:
        if int(cl) <= 0:
            return False, "reference_image_empty_content_length"
    except ValueError:
        return False, "reference_image_invalid_content_length"
    return True, ""


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
        last_frame_url: str | None = None,
        model: str = "wan2.7-i2v",
        duration: int = 4,
        resolution: str = "720p",
        extra: dict[str, Any] | None = None,
        video_backend: str | None = None,
        openrouter_model: str | None = None,
        openrouter_provider: dict[str, Any] | None = None,
    ) -> str:
        """
        Создаёт документ job и запускает генерацию (DashScope или OpenRouter Video API).

        `video_backend`: `dashscope` | `openrouter`; по умолчанию — Settings.video_generation_backend.
        Для OpenRouter модель — `openrouter_model` или Settings.openrouter_video_model
        (поле `model` в документе тогда соответствует id OpenRouter).
        """
        backend = (video_backend or self._settings.video_generation_backend or "dashscope").strip().lower()
        if backend not in ("dashscope", "openrouter"):
            backend = "dashscope"

        doc: dict[str, Any] = {
            "owner_user_id": owner_user_id,
            "video_backend": backend,
            "prompt": prompt,
            "image_url": compact_image_url_for_storage(image_url),
            "last_frame_url": compact_image_url_for_storage(last_frame_url)
            if (last_frame_url or "").strip()
            else None,
            "model": model,
            "duration": duration,
            "resolution": resolution,
            "provider_task_id": None,
            "openrouter_polling_url": None,
            "status": "created",
            "video_url": None,
            "error": None,
        }
        if extra:
            doc.update(extra)
        job_id = self._repo.insert_job_sync(doc)
        logger.info(
            "video job создан job_id=%s owner=%s backend=%s",
            job_id,
            owner_user_id,
            backend,
        )
        if backend == "openrouter":
            extra_obj = extra if isinstance(extra, dict) else {}
            return self._start_openrouter_job(
                job_id,
                prompt=prompt,
                image_url=image_url,
                last_frame_url=last_frame_url,
                duration=duration,
                resolution=resolution,
                openrouter_model=openrouter_model,
                openrouter_provider=openrouter_provider,
                montage_preset=str(extra_obj.get("montage_preset") or "").strip(),
                dev_relaxed_validation=bool(extra_obj.get("dev_relaxed_validation")),
            )
        return self._start_dashscope_job(
            job_id,
            prompt=prompt,
            image_url=image_url,
            last_frame_url=last_frame_url,
            model=model,
            duration=duration,
            resolution=resolution,
        )

    def _start_dashscope_job(
        self,
        job_id: str,
        *,
        prompt: str,
        image_url: str,
        last_frame_url: str | None,
        model: str,
        duration: int,
        resolution: str,
    ) -> str:
        syn = _synthesis_url(self._settings)
        lf = (last_frame_url or "").strip() or None
        try:
            task_id, raw = create_video_task(
                prompt=prompt,
                image_url=image_url,
                model=model,
                duration=duration,
                resolution=resolution,
                last_frame_url=lf,
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
                "raw_create_response": compact_provider_payload_for_storage(raw),
            },
        )
        logger.info(
            "video job: DashScope task_id=%s job_id=%s — запуск polling",
            task_id,
            job_id,
        )
        t = threading.Thread(
            target=self._run_poll_thread,
            args=(job_id, task_id, syn),
            name=f"wan-i2v-poll-{job_id[:8]}",
            daemon=True,
        )
        t.start()
        return job_id

    def _merge_openrouter_provider(
        self,
        override: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        raw = (self._settings.openrouter_video_provider_json or "").strip()
        base: dict[str, Any] | None = None
        if raw:
            try:
                import json

                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    base = dict(parsed)
            except Exception:
                logger.warning("openrouter_video_provider_json: невалидный JSON, игнор")
        if override:
            merged = dict(base or {})
            merged.update(override)
            return merged
        return base

    def _start_openrouter_job(
        self,
        job_id: str,
        *,
        prompt: str,
        image_url: str,
        last_frame_url: str | None,
        duration: int,
        resolution: str,
        openrouter_model: str | None,
        openrouter_provider: dict[str, Any] | None,
        montage_preset: str = "",
        dev_relaxed_validation: bool = False,
    ) -> str:
        or_model = normalize_openrouter_video_model_id(
            (openrouter_model or "").strip() or self._settings.openrouter_video_model
        )
        ff = _resolve_image_url_for_provider(image_url, self._settings)
        if not ff:
            self._repo.update_job_sync(job_id, {"status": "failed", "error": "unresolvable_image_url_for_openrouter"})
            return job_id
        provider = self._merge_openrouter_provider(openrouter_provider)
        duration_to_send = int(duration)
        preset = str(montage_preset or "").strip().lower()
        use_input_references = (
            or_model.strip().lower() == _KLING_V3_STD_MODEL_ID
            and preset == _KLING_REFERENCE_PRESET
        )
        size_to_send: str | None = None
        # Для WAN 2.6 на OpenRouter жёстко фиксируем duration=5
        # и блокируем fallback на другие провайдеры (в т.ч. atlascloud).
        if or_model.lower().startswith("alibaba/wan-2.6"):
            duration_to_send = 5
            forced = {
                "order": ["Alibaba"],
                "only": ["Alibaba"],
                "allow_fallbacks": False,
                "require_parameters": True,
            }
            merged = dict(provider or {})
            merged.update(forced)
            provider = merged
        if use_input_references:
            duration_to_send = 5
            size_to_send = "720x720"
        lf = _resolve_image_url_for_provider(last_frame_url, self._settings)
        if use_input_references:
            ok_ref, ref_error = _validate_reference_image_url(ff, relaxed=bool(dev_relaxed_validation))
            if not ok_ref:
                self._repo.update_job_sync(job_id, {"status": "failed", "error": ref_error})
                return job_id
            lf = None
        try:
            oid, poll_url, raw = submit_openrouter_video_job(
                prompt=prompt,
                model=or_model,
                duration=duration_to_send,
                resolution=str(resolution).strip(),
                size=size_to_send,
                first_frame_url=None if use_input_references else ff,
                last_frame_url=lf or None,
                input_references=[ff] if use_input_references else None,
                provider=provider,
            )
        except OpenRouterVideoError as e:
            msg = str(e)
            if use_input_references and msg.startswith("HTTP 4"):
                try:
                    oid, poll_url, raw = submit_openrouter_video_job(
                        prompt=prompt,
                        model=or_model,
                        duration=duration_to_send,
                        resolution=str(resolution).strip(),
                        size=size_to_send,
                        first_frame_url=ff,
                        last_frame_url=None,
                        input_references=None,
                        provider=provider,
                    )
                    raw = {
                        "fallback_mode": "frame_images_first_frame",
                        "primary_error": msg,
                        "fallback_response": raw,
                    }
                except OpenRouterVideoError as e2:
                    logger.warning("video job: OpenRouter submit job_id=%s: %s", job_id, e2)
                    self._repo.update_job_sync(job_id, {"status": "failed", "error": str(e2)})
                    return job_id
            logger.warning("video job: OpenRouter submit job_id=%s: %s", job_id, e)
            if not use_input_references or not msg.startswith("HTTP 4"):
                self._repo.update_job_sync(job_id, {"status": "failed", "error": str(e)})
                return job_id
        except Exception as e:
            logger.exception("video job: OpenRouter неожиданная ошибка job_id=%s", job_id)
            self._repo.update_job_sync(job_id, {"status": "failed", "error": str(e)})
            return job_id

        self._repo.update_job_sync(
            job_id,
            {
                "provider_task_id": oid,
                "openrouter_polling_url": poll_url,
                "status": "running",
                "raw_create_response": compact_provider_payload_for_storage(raw),
                "model": or_model,
                "duration": duration_to_send,
                "submitted_model": or_model,
                "provider_routing": compact_provider_payload_for_storage(provider),
                "submitted_size": size_to_send,
                "submitted_montage_preset": preset,
                "submitted_input_mode": "input_references" if use_input_references else "frame_images",
            },
        )
        logger.info(
            "video job: OpenRouter id=%s job_id=%s — запуск polling",
            oid,
            job_id,
        )
        t = threading.Thread(
            target=self._run_openrouter_poll_thread,
            args=(job_id, oid, poll_url),
            name=f"or-video-poll-{job_id[:8]}",
            daemon=True,
        )
        t.start()
        return job_id

    def _run_poll_thread(
        self,
        job_id: str,
        provider_task_id: str,
        synthesis_url: str | None,
    ) -> None:
        if not _try_begin_poll(job_id):
            logger.info(
                "video job: опрос уже выполняется для job_id=%s — дубликат не запускаем",
                job_id,
            )
            return
        try:
            self._poll_loop(job_id, provider_task_id, synthesis_url)
        finally:
            _end_poll(job_id)

    def resume_stale_pollers(self, *, max_jobs: int = 80) -> int:
        """
        После рестарта процесса (uvicorn --reload, деплой) фоновые потоки опроса мертвы,
        а записи в Mongo остаются в running. Поднимаем poll заново для каждой активной
        задачи с provider_task_id.
        """
        jobs = self._repo.list_active_sync(limit=max_jobs)
        started = 0
        for j in jobs:
            jid = j.get("_id")
            tid = j.get("provider_task_id")
            if not jid or not tid:
                logger.warning(
                    "resume_stale_pollers: job %s без provider_task_id — проверьте документ вручную",
                    jid,
                )
                continue
            backend = str(j.get("video_backend") or "dashscope").lower()
            if backend == "openrouter":
                poll_url = j.get("openrouter_polling_url")
                t = threading.Thread(
                    target=self._run_openrouter_poll_thread,
                    args=(str(jid), str(tid), poll_url),
                    name=f"or-video-poll-resume-{str(jid)[:8]}",
                    daemon=True,
                )
            else:
                syn = _synthesis_url(self._settings)
                t = threading.Thread(
                    target=self._run_poll_thread,
                    args=(str(jid), str(tid), syn),
                    name=f"wan-i2v-poll-resume-{str(jid)[:8]}",
                    daemon=True,
                )
            t.start()
            started += 1
        if started:
            logger.info("resume_stale_pollers: запущено потоков опроса: %s", started)
        return started

    def _poll_loop(
        self,
        job_id: str,
        provider_task_id: str,
        synthesis_url: str | None,
    ) -> None:
        try:
            while True:
                doc = self._repo.get_job_sync(job_id)
                if doc:
                    dt = _parse_job_dt(doc.get("created_at"))
                    if dt is not None:
                        age = (datetime.now(timezone.utc) - dt).total_seconds()
                        if age > _MAX_POLL_WALL_SEC:
                            self._repo.update_job_sync(
                                job_id,
                                {
                                    "status": "failed",
                                    "error": (
                                        f"Таймаут ожидания провайдера (~{int(age // 60)} мин). "
                                        "Задача могла зависнуть на стороне Wan, либо процесс сервера "
                                        "перезапускался (--reload) и опрос прерывался."
                                    ),
                                },
                            )
                            logger.warning(
                                "video job: таймаут wall-clock job_id=%s age_sec=%.0f",
                                job_id,
                                age,
                            )
                            return

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
                logger.debug(
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

    def _run_openrouter_poll_thread(
        self,
        job_id: str,
        openrouter_job_id: str,
        polling_url: str | None,
    ) -> None:
        if not _try_begin_poll(job_id):
            logger.info(
                "video job OpenRouter: опрос уже идёт job_id=%s — пропуск",
                job_id,
            )
            return
        try:
            self._poll_loop_openrouter(job_id, openrouter_job_id, polling_url)
        finally:
            _end_poll(job_id)

    def _poll_loop_openrouter(
        self,
        job_id: str,
        openrouter_job_id: str,
        polling_url: str | None,
    ) -> None:
        try:
            while True:
                age = 0.0
                doc = self._repo.get_job_sync(job_id)
                if doc:
                    dt = _parse_job_dt(doc.get("created_at"))
                    if dt is not None:
                        age = (datetime.now(timezone.utc) - dt).total_seconds()
                        if age > _MAX_POLL_WALL_SEC:
                            self._repo.update_job_sync(
                                job_id,
                                {
                                    "status": "failed",
                                    "error": (
                                        f"Таймаут ожидания провайдера (~{int(age // 60)} мин). "
                                        "OpenRouter / WAN — см. логи и статус задачи на openrouter.ai."
                                    ),
                                },
                            )
                            return

                try:
                    pr = poll_openrouter_video_job(
                        job_id=openrouter_job_id,
                        polling_url=polling_url,
                    )
                except OpenRouterVideoError as e:
                    logger.warning(
                        "video job OpenRouter: ошибка опроса job_id=%s: %s",
                        job_id,
                        e,
                    )
                    self._repo.update_job_sync(
                        job_id,
                        {"status": "failed", "error": f"poll: {e}"},
                    )
                    return

                patch: dict[str, Any] = {"status": "running"}
                raw_status = str(pr.raw.get("status") or pr.raw.get("task_status") or "").strip().lower()
                if raw_status in {"queued", "pending"} and age > _OPENROUTER_QUEUE_STALE_SEC:
                    self._repo.update_job_sync(
                        job_id,
                        {
                            "status": "stale_timeout",
                            "error": "Задача зависла в очереди провайдера (queued/pending > 10 мин).",
                        },
                    )
                    logger.warning(
                        "video job OpenRouter stale_timeout job_id=%s raw_status=%s age_sec=%.0f",
                        job_id,
                        raw_status,
                        age,
                    )
                    return
                if pr.status_normalized == "SUCCEEDED":
                    vurl = pr.video_urls[0] if pr.video_urls else None
                    patch["status"] = "succeeded"
                    patch["video_url"] = vurl
                    patch["error"] = None
                    self._repo.update_job_sync(job_id, patch)
                    logger.info(
                        "video job OpenRouter успех job_id=%s url=%s",
                        job_id,
                        bool(vurl),
                    )
                    return

                if pr.status_normalized == "FAILED":
                    patch["status"] = "failed"
                    patch["error"] = pr.error or "FAILED"
                    self._repo.update_job_sync(job_id, patch)
                    logger.warning(
                        "video job OpenRouter ошибка job_id=%s detail=%s",
                        job_id,
                        patch.get("error"),
                    )
                    return

                self._repo.update_job_sync(job_id, patch)
                logger.debug(
                    "video job OpenRouter poll job_id=%s raw_status=%s",
                    job_id,
                    pr.raw.get("status"),
                )
                time.sleep(POLL_INTERVAL_SEC)
        except Exception as e:
            logger.exception("video job OpenRouter: критическая ошибка job_id=%s", job_id)
            try:
                self._repo.update_job_sync(
                    job_id,
                    {"status": "failed", "error": str(e)},
                )
            except Exception:
                logger.exception(
                    "video job OpenRouter: не удалось записать ошибку job_id=%s",
                    job_id,
                )

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
            if st in {"failed", "stale_timeout"}:
                return job
            time.sleep(interval_sec)
        raise TimeoutError(f"Таймаут ожидания job {job_id} в Mongo ({timeout_sec}s)")
