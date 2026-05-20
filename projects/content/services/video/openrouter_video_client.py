"""
Асинхронная генерация видео через OpenRouter (POST /api/v1/videos).

Документация: https://openrouter.ai/docs/guides/overview/multimodal/video-generation
Модель WAN 2.7: https://openrouter.ai/alibaba/wan-2.7/api
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from core.config.settings import get_settings

logger = logging.getLogger(__name__)

_DEFAULT_BASE = "https://openrouter.ai/api/v1"
_SUBMIT_TIMEOUT_SEC = 120.0
_POLL_TIMEOUT_SEC = 120.0


class OpenRouterVideoError(Exception):
    """Ошибка вызова OpenRouter Video API."""


@dataclass(frozen=True)
class OpenRouterVideoPollResult:
    """Сырой ответ опроса задачи видео."""

    status_normalized: str  # SUCCEEDED | FAILED | RUNNING
    video_urls: list[str]
    error: str | None
    raw: dict[str, Any]


def normalize_openrouter_video_model_id(model_id: str | None) -> str:
    mid = str(model_id or "").strip()
    if not mid:
        return ""
    if mid.lower().endswith("/image-to-video"):
        return mid[: -len("/image-to-video")]
    return mid


def _sanitize_openrouter_polling_url(polling_url: str | None, *, root: str) -> str | None:
    pu = str(polling_url or "").strip()
    if not pu:
        return None
    try:
        parsed = urlparse(pu)
    except Exception:
        return None
    if parsed.scheme not in {"http", "https"}:
        return None
    # Используем только OpenRouter polling endpoint.
    if parsed.netloc.lower() != "openrouter.ai":
        return None
    if not parsed.path.startswith("/api/v1/videos"):
        return None
    return pu


def _headers(*, api_key: str, http_referer: str | None) -> dict[str, str]:
    h: dict[str, str] = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if http_referer and http_referer.strip():
        h["HTTP-Referer"] = http_referer.strip()
    return h


def _extract_video_urls(data: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for k in ("unsigned_urls", "urls", "video_urls"):
        v = data.get(k)
        if isinstance(v, list):
            for x in v:
                if x and str(x).strip():
                    urls.append(str(x).strip())
    out = data.get("output")
    if isinstance(out, dict):
        u = out.get("video_url") or out.get("url")
        if u and str(u).strip():
            urls.append(str(u).strip())
    u2 = data.get("video_url") or data.get("url")
    if u2 and str(u2).strip() and str(u2) not in urls:
        urls.append(str(u2).strip())
    return urls


def _normalize_poll_status(data: dict[str, Any]) -> tuple[str, str | None]:
    st = str(data.get("status") or data.get("task_status") or "").lower()
    err = None
    if isinstance(data.get("error"), str):
        err = data["error"]
    elif isinstance(data.get("error"), dict):
        err = str(data["error"].get("message") or data["error"])
    if data.get("message") and not err:
        err = str(data["message"])

    if st in ("completed", "complete", "succeeded", "success"):
        return "SUCCEEDED", err
    if st in ("failed", "error", "cancelled", "canceled"):
        return "FAILED", err
    return "RUNNING", err


def submit_openrouter_video_job(
    *,
    prompt: str,
    model: str,
    duration: int | None = None,
    resolution: str | None = None,
    size: str | None = None,
    first_frame_url: str | None = None,
    last_frame_url: str | None = None,
    input_references: list[str] | None = None,
    provider: dict[str, Any] | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    http_referer: str | None = None,
) -> tuple[str, str | None, dict[str, Any]]:
    """
    POST /videos. Возвращает (job_id, polling_url или None, raw_json).
    """
    settings = get_settings()
    key = (api_key or settings.openrouter_api_key or "").strip()
    if not key:
        raise OpenRouterVideoError(
            "Не задан OPENROUTER_API_KEY (переменная окружения или Settings)."
        )
    root = (base_url or settings.openrouter_base_url or _DEFAULT_BASE).rstrip("/")
    url = f"{root}/videos"
    mid = normalize_openrouter_video_model_id(model or settings.openrouter_video_model)
    if not mid:
        raise OpenRouterVideoError("Не задана модель OpenRouter для видео.")

    body: dict[str, Any] = {"model": mid, "prompt": prompt.strip()}
    if duration is not None:
        body["duration"] = int(duration)
    if size and str(size).strip():
        body["size"] = str(size).strip().lower()
    elif resolution and str(resolution).strip():
        body["resolution"] = str(resolution).strip().lower()
    frame_images: list[dict[str, Any]] = []
    ff = (first_frame_url or "").strip()
    if ff:
        frame_images.append(
            {
                "type": "image_url",
                "image_url": {"url": ff},
                "frame_type": "first_frame",
            }
        )
    lf = (last_frame_url or "").strip()
    if lf:
        frame_images.append(
            {
                "type": "image_url",
                "image_url": {"url": lf},
                "frame_type": "last_frame",
            }
        )
    if frame_images:
        body["frame_images"] = frame_images
    refs: list[dict[str, Any]] = []
    for ref in list(input_references or []):
        rr = str(ref or "").strip()
        if not rr:
            continue
        refs.append({"type": "image_url", "image_url": rr})
    if refs:
        body["input_references"] = refs
    if provider:
        body["provider"] = provider

    headers = _headers(api_key=key, http_referer=http_referer or settings.openrouter_http_referer)
    logger.info("OpenRouter video: submit model=%s duration=%s", mid, duration)
    with httpx.Client(timeout=_SUBMIT_TIMEOUT_SEC) as client:
        r = client.post(url, headers=headers, json=body)
    try:
        data = r.json()
    except Exception:
        data = {"_raw": (r.text or "")[:2000]}

    if r.status_code >= 400:
        msg = ""
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict):
                msg = str(err.get("message") or err)
            else:
                msg = str(err or data.get("message") or data)
        raise OpenRouterVideoError(f"HTTP {r.status_code}: {msg or r.text[:500]}")

    if not isinstance(data, dict):
        raise OpenRouterVideoError(f"Неожиданный ответ: {data!r}")

    job_id = data.get("id") or data.get("job_id") or data.get("task_id")
    if not job_id:
        raise OpenRouterVideoError(f"Нет id в ответе OpenRouter: {data!r}")
    polling_url = _sanitize_openrouter_polling_url(data.get("polling_url"), root=root)
    if data.get("polling_url") and not polling_url:
        logger.warning("OpenRouter video: ignored non-OpenRouter polling_url")
    return str(job_id), polling_url, data


def poll_openrouter_video_job(
    *,
    job_id: str,
    polling_url: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    http_referer: str | None = None,
) -> OpenRouterVideoPollResult:
    """GET polling_url или GET /videos/{id}."""
    settings = get_settings()
    key = (api_key or settings.openrouter_api_key or "").strip()
    if not key:
        raise OpenRouterVideoError("Не задан OPENROUTER_API_KEY.")
    root = (base_url or settings.openrouter_base_url or _DEFAULT_BASE).rstrip("/")
    url = (polling_url or "").strip() or f"{root}/videos/{job_id}"
    headers = _headers(api_key=key, http_referer=http_referer or settings.openrouter_http_referer)
    with httpx.Client(timeout=_POLL_TIMEOUT_SEC) as client:
        r = client.get(url, headers=headers)
    try:
        data = r.json()
    except Exception:
        data = {"_raw": (r.text or "")[:2000]}

    if r.status_code >= 400:
        msg = str(data) if isinstance(data, dict) else r.text[:500]
        raise OpenRouterVideoError(f"HTTP {r.status_code}: {msg}")

    if not isinstance(data, dict):
        raise OpenRouterVideoError(f"Неожиданный ответ опроса: {data!r}")

    norm, err = _normalize_poll_status(data)
    urls = _extract_video_urls(data)
    if norm == "SUCCEEDED" and not urls:
        logger.warning("OpenRouter video: статус completed без URL в теле: keys=%s", list(data.keys()))
    return OpenRouterVideoPollResult(
        status_normalized=norm,
        video_urls=urls,
        error=err,
        raw=data,
    )
