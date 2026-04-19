"""
Низкоуровневый клиент Wan image-to-video (Alibaba DashScope, async API).

Документация: POST .../video-synthesis с заголовком X-DashScope-Async: enable,
GET .../api/v1/tasks/{task_id}.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from core.config.settings import get_settings

logger = logging.getLogger(__name__)

DEFAULT_VIDEO_SYNTHESIS_URL = (
    "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis"
)

_DEFAULT_POLL_INTERVAL_SEC = 5.0
_DEFAULT_HTTP_TIMEOUT_SEC = 120.0


class WanI2vClientError(Exception):
    """Ошибка вызова DashScope video-synthesis / tasks API."""


@dataclass(frozen=True)
class VideoTaskStatusResult:
    """Результат GET /api/v1/tasks/{task_id}."""

    status: str
    progress: float | None
    video_url: str | None
    error: str | None
    raw: dict[str, Any]


def _get_api_key() -> str:
    key = (os.environ.get("DASHSCOPE_API_KEY") or "").strip()
    if not key:
        key = (get_settings().dashscope_api_key or "").strip()
    if not key:
        raise WanI2vClientError(
            "Не задан DASHSCOPE_API_KEY (env или Settings.dashscope_api_key)."
        )
    return key


def _synthesis_url() -> str:
    u = (os.environ.get("DASHSCOPE_VIDEO_ENDPOINT") or "").strip()
    if not u:
        u = (get_settings().dashscope_video_endpoint or "").strip()
    if not u:
        u = DEFAULT_VIDEO_SYNTHESIS_URL
    return u


def tasks_base_url_from_synthesis(synthesis_url: str) -> str:
    """База для GET /api/v1/tasks/{task_id} (тот же хост, что и POST)."""
    parts = urlsplit(synthesis_url)
    path = "/api/v1/tasks"
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _normalize_resolution(resolution: str) -> str:
    r = (resolution or "720p").strip().upper()
    if r.endswith("P"):
        return r
    if r.isdigit():
        return f"{r}P"
    return r


def _model_uses_wan27_media_input(model: str) -> bool:
    """
    Wan 2.7 i2v требует input.media[] с type first_frame/url, а не input.img_url.
    См. Model Studio image-to-video (wan2.7-i2v).
    """
    m = (model or "").lower().replace("_", ".")
    return "wan2.7" in m


def _build_input_image_to_video(
    *,
    prompt: str,
    image_url: str,
    model: str,
) -> dict[str, Any]:
    if _model_uses_wan27_media_input(model):
        return {
            "prompt": prompt,
            "media": [
                {
                    "type": "first_frame",
                    "url": image_url,
                }
            ],
        }
    return {
        "prompt": prompt,
        "img_url": image_url,
    }


def _build_payload(
    *,
    prompt: str,
    image_url: str,
    model: str,
    duration: int,
    resolution: str,
) -> dict[str, Any]:
    return {
        "model": model,
        "input": _build_input_image_to_video(
            prompt=prompt,
            image_url=image_url,
            model=model,
        ),
        "parameters": {
            "resolution": _normalize_resolution(resolution),
            "duration": int(duration),
            "prompt_extend": True,
        },
    }


def _parse_task_response(data: dict[str, Any]) -> VideoTaskStatusResult:
    out = data.get("output") if isinstance(data.get("output"), dict) else {}
    status = str(out.get("task_status") or out.get("status") or "UNKNOWN").upper()
    video_url = out.get("video_url")
    if video_url is not None:
        video_url = str(video_url)
    err_parts: list[str] = []
    if data.get("message"):
        err_parts.append(str(data["message"]))
    if out.get("message"):
        err_parts.append(str(out["message"]))
    if out.get("code"):
        err_parts.append(str(out["code"]))
    error = "; ".join(err_parts) if err_parts else None
    progress = out.get("progress")
    if progress is not None:
        try:
            progress = float(progress)
        except (TypeError, ValueError):
            progress = None
    return VideoTaskStatusResult(
        status=status,
        progress=progress,
        video_url=video_url,
        error=error,
        raw=data,
    )


def create_video_task(
    *,
    prompt: str,
    image_url: str,
    model: str = "wan2.7-i2v",
    duration: int = 4,
    resolution: str = "720p",
    api_key: str | None = None,
    synthesis_url: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Создаёт асинхронную задачу image-to-video (first frame).

    Возвращает (task_id, raw_response_dict).
    """
    key = (api_key or "").strip() or _get_api_key()
    url = (synthesis_url or "").strip() or _synthesis_url()
    payload = _build_payload(
        prompt=prompt,
        image_url=image_url,
        model=model,
        duration=duration,
        resolution=resolution,
    )
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }
    logger.info(
        "Wan i2v: создание задачи model=%s resolution=%s duration=%s",
        model,
        payload["parameters"]["resolution"],
        duration,
    )
    with httpx.Client(timeout=_DEFAULT_HTTP_TIMEOUT_SEC) as client:
        r = client.post(url, headers=headers, json=payload)
    try:
        data = r.json()
    except Exception:
        data = {"_raw_text": r.text[:2000]}
    if r.status_code >= 400:
        logger.warning(
            "Wan i2v: ошибка HTTP %s code=%s",
            r.status_code,
            data.get("code") if isinstance(data, dict) else None,
        )
        raise WanI2vClientError(
            f"HTTP {r.status_code}: {data!r}" if isinstance(data, dict) else r.text[:500]
        )
    out = data.get("output") if isinstance(data, dict) else {}
    task_id = out.get("task_id") if isinstance(out, dict) else None
    if not task_id:
        logger.warning("Wan i2v: нет task_id в ответе")
        raise WanI2vClientError(f"Нет task_id в ответе: {data!r}")
    tid = str(task_id)
    logger.info("Wan i2v: задача создана task_id=%s", tid)
    return tid, data


def get_video_task_status(
    task_id: str,
    *,
    api_key: str | None = None,
    synthesis_url: str | None = None,
) -> VideoTaskStatusResult:
    """GET статуса задачи по task_id."""
    key = (api_key or "").strip() or _get_api_key()
    base = tasks_base_url_from_synthesis((synthesis_url or "").strip() or _synthesis_url())
    url = f"{base.rstrip('/')}/{task_id}"
    headers = {"Authorization": f"Bearer {key}"}
    with httpx.Client(timeout=_DEFAULT_HTTP_TIMEOUT_SEC) as client:
        r = client.get(url, headers=headers)
    try:
        data = r.json()
    except Exception:
        data = {"_raw_text": r.text[:2000]}
    if r.status_code >= 400:
        logger.warning(
            "Wan i2v: ошибка опроса HTTP %s task_id=%s",
            r.status_code,
            task_id,
        )
        raise WanI2vClientError(
            f"HTTP {r.status_code}: {data!r}" if isinstance(data, dict) else r.text[:500]
        )
    parsed = _parse_task_response(data if isinstance(data, dict) else {})
    logger.info(
        "Wan i2v: статус task_id=%s task_status=%s",
        task_id,
        parsed.status,
    )
    return parsed


def wait_for_video_result(
    task_id: str,
    *,
    timeout_sec: float = 900.0,
    interval_sec: float = _DEFAULT_POLL_INTERVAL_SEC,
    api_key: str | None = None,
    synthesis_url: str | None = None,
) -> VideoTaskStatusResult:
    """Синхронный polling до финального статуса или таймаута."""
    import time

    t0 = time.monotonic()
    while True:
        st = get_video_task_status(
            task_id, api_key=api_key, synthesis_url=synthesis_url
        )
        if st.status in ("SUCCEEDED", "FAILED", "CANCELED", "UNKNOWN"):
            if st.status == "SUCCEEDED":
                logger.info("Wan i2v: готово task_id=%s", task_id)
            else:
                logger.warning(
                    "Wan i2v: финальный статус %s task_id=%s",
                    st.status,
                    task_id,
                )
            return st
        if time.monotonic() - t0 > timeout_sec:
            logger.error("Wan i2v: таймаут ожидания task_id=%s", task_id)
            raise WanI2vClientError(f"Таймаут {timeout_sec}s для task_id={task_id}")
        time.sleep(interval_sec)


# --- Async API (не блокирует event loop при await sleep) ---


async def create_video_task_async(
    *,
    prompt: str,
    image_url: str,
    model: str = "wan2.7-i2v",
    duration: int = 4,
    resolution: str = "720p",
    api_key: str | None = None,
    synthesis_url: str | None = None,
) -> tuple[str, dict[str, Any]]:
    key = (api_key or "").strip() or _get_api_key()
    url = (synthesis_url or "").strip() or _synthesis_url()
    payload = _build_payload(
        prompt=prompt,
        image_url=image_url,
        model=model,
        duration=duration,
        resolution=resolution,
    )
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }
    logger.info(
        "Wan i2v async: создание задачи model=%s",
        model,
    )
    async with httpx.AsyncClient(timeout=_DEFAULT_HTTP_TIMEOUT_SEC) as client:
        r = await client.post(url, headers=headers, json=payload)
    try:
        data = r.json()
    except Exception:
        data = {"_raw_text": r.text[:2000]}
    if r.status_code >= 400:
        raise WanI2vClientError(
            f"HTTP {r.status_code}: {data!r}" if isinstance(data, dict) else r.text[:500]
        )
    out = data.get("output") if isinstance(data, dict) else {}
    task_id = out.get("task_id") if isinstance(out, dict) else None
    if not task_id:
        raise WanI2vClientError(f"Нет task_id в ответе: {data!r}")
    tid = str(task_id)
    logger.info("Wan i2v async: задача создана task_id=%s", tid)
    return tid, data


async def get_video_task_status_async(
    task_id: str,
    *,
    api_key: str | None = None,
    synthesis_url: str | None = None,
) -> VideoTaskStatusResult:
    key = (api_key or "").strip() or _get_api_key()
    base = tasks_base_url_from_synthesis((synthesis_url or "").strip() or _synthesis_url())
    url = f"{base.rstrip('/')}/{task_id}"
    headers = {"Authorization": f"Bearer {key}"}
    async with httpx.AsyncClient(timeout=_DEFAULT_HTTP_TIMEOUT_SEC) as client:
        r = await client.get(url, headers=headers)
    try:
        data = r.json()
    except Exception:
        data = {"_raw_text": r.text[:2000]}
    if r.status_code >= 400:
        raise WanI2vClientError(
            f"HTTP {r.status_code}: {data!r}" if isinstance(data, dict) else r.text[:500]
        )
    return _parse_task_response(data if isinstance(data, dict) else {})


async def wait_for_video_result_async(
    task_id: str,
    *,
    timeout_sec: float = 900.0,
    interval_sec: float = _DEFAULT_POLL_INTERVAL_SEC,
    api_key: str | None = None,
    synthesis_url: str | None = None,
) -> VideoTaskStatusResult:
    import time

    t0 = time.monotonic()
    while True:
        st = await get_video_task_status_async(
            task_id, api_key=api_key, synthesis_url=synthesis_url
        )
        if st.status in ("SUCCEEDED", "FAILED", "CANCELED", "UNKNOWN"):
            return st
        if time.monotonic() - t0 > timeout_sec:
            raise WanI2vClientError(f"Таймаут {timeout_sec}s для task_id={task_id}")
        await asyncio.sleep(interval_sec)
