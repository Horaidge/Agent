"""
Низкоуровневый HTTP-клиент Qwen Image (Alibaba DashScope multimodal-generation).

Документация: synchronous POST .../aigc/multimodal-generation/generation
"""
from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx

from core.config.settings import get_settings

logger = logging.getLogger(__name__)

DEFAULT_DASHSCOPE_ENDPOINT = (
    "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
)

# Секреты в логах не печатаем; обрезка для диагностики
_MAX_BODY_LOG_LEN = 800


class QwenImageClientError(Exception):
    """Ошибка вызова Qwen Image API (HTTP, разбор ответа, параметры)."""


def _get_api_key() -> str:
    # Сначала переменная процесса (override), затем ENV/env/.env через Settings
    key = (os.environ.get("DASHSCOPE_API_KEY") or "").strip()
    if not key:
        key = (get_settings().dashscope_api_key or "").strip()
    if not key:
        raise QwenImageClientError(
            "Не задан DASHSCOPE_API_KEY: задайте в env-файле (корень проекта) или в переменной окружения."
        )
    return key


def _get_endpoint() -> str:
    ep = (os.environ.get("DASHSCOPE_ENDPOINT") or "").strip()
    if not ep:
        ep = (get_settings().dashscope_endpoint or "").strip()
    if not ep:
        ep = DEFAULT_DASHSCOPE_ENDPOINT
    return ep


def _mime_for_path(path: Path) -> str:
    ext = path.suffix.lower()
    mapping = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
    }
    return mapping.get(ext, "application/octet-stream")


def _file_to_data_uri(path: Path) -> str:
    raw = path.read_bytes()
    mime = _mime_for_path(path)
    b64 = base64.standard_b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _resolve_image_ref(image_source: str) -> str:
    """
    URL/https, data URI или путь к локальному файлу → строка для поля image в API.
    """
    s = image_source.strip()
    if s.startswith(("http://", "https://")):
        return s
    if s.startswith("data:image"):
        return s
    p = Path(s).expanduser()
    if not p.is_file():
        raise QwenImageClientError(
            f"image_source не URL/data URI и не найден файл: {p}"
        )
    return _file_to_data_uri(p)


def _build_generate_payload(
    prompt: str,
    size: str,
    model: str,
    n: int,
) -> dict[str, Any]:
    return {
        "model": model,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": prompt}],
                }
            ]
        },
        "parameters": {
            "size": size,
            "n": n,
            "watermark": False,
        },
    }


def _build_edit_payload(
    image_ref: str,
    instruction: str,
    size: str,
    model: str,
    n: int,
) -> dict[str, Any]:
    return {
        "model": model,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"image": image_ref},
                        {"text": instruction},
                    ],
                }
            ]
        },
        "parameters": {
            "size": size,
            "n": n,
            "watermark": False,
        },
    }


def _extract_image_urls(data: dict[str, Any]) -> list[str]:
    out = data.get("output")
    if not isinstance(out, dict):
        return []
    choices = out.get("choices")
    if not isinstance(choices, list):
        return []
    urls: list[str] = []
    for ch in choices:
        if not isinstance(ch, dict):
            continue
        msg = ch.get("message")
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if isinstance(item, dict) and "image" in item:
                u = item.get("image")
                if isinstance(u, str) and u.startswith("http"):
                    urls.append(u)
    return urls


def _api_error_from_body(data: dict[str, Any]) -> str | None:
    code = data.get("code")
    msg = data.get("message")
    if code or msg:
        return f"{code or 'Error'}: {msg or ''}".strip()
    return None


def _safe_body_snippet(text: str) -> str:
    if len(text) <= _MAX_BODY_LOG_LEN:
        return text
    return text[:_MAX_BODY_LOG_LEN] + "…"


def _post_json(url: str, api_key: str, payload: dict[str, Any], timeout_sec: float) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=timeout_sec) as client:
            r = client.post(url, headers=headers, json=payload)
    except httpx.TimeoutException as e:
        raise QwenImageClientError(
            f"Таймаут запроса к DashScope (>{timeout_sec}s): {e}"
        ) from e
    except httpx.RequestError as e:
        raise QwenImageClientError(f"Сетевая ошибка HTTP-клиента: {e}") from e

    text = (r.text or "").strip()
    if not text:
        raise QwenImageClientError(
            f"Пустой ответ HTTP {r.status_code}, URL={url!r}"
        )

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise QwenImageClientError(
            f"Ответ не JSON (HTTP {r.status_code}): {_safe_body_snippet(text)}"
        ) from e

    if not isinstance(data, dict):
        raise QwenImageClientError("Корень ответа JSON не объект (dict).")

    if r.status_code >= 400:
        err = _api_error_from_body(data) or text[:500]
        raise QwenImageClientError(f"HTTP {r.status_code}: {err}")

    # DashScope часто возвращает 200 с полями code/message при логической ошибке
    if data.get("code") and not data.get("output"):
        err = _api_error_from_body(data) or "Unknown API error"
        raise QwenImageClientError(err)

    return data


def generate_image_from_prompt(
    prompt: str,
    size: str = "1024*1536",
    model: str = "qwen-image-2.0",
    n: int = 1,
    *,
    timeout_sec: float = 180.0,
) -> list[str]:
    """
    Генерация изображений по текстовому промпту (синхронный multimodal-generation).

    Возвращает список URL изображений (временные ссылки, ~24 ч).
    """
    api_key = _get_api_key()
    url = _get_endpoint()
    payload = _build_generate_payload(prompt, size, model, n)
    logger.debug(
        "Qwen generate: model=%s size=%s n=%s endpoint=%s",
        model,
        size,
        n,
        url,
    )
    data = _post_json(url, api_key, payload, timeout_sec)
    urls = _extract_image_urls(data)
    if not urls:
        raise QwenImageClientError(
            "Не удалось извлечь URL из ответа (неожиданная структура output.choices)."
        )
    return urls


def edit_image_with_instruction(
    image_source: str,
    instruction: str,
    size: str = "1024*1536",
    model: str = "qwen-image-2.0",
    n: int = 1,
    *,
    timeout_sec: float = 180.0,
) -> list[str]:
    """
    Редактирование: изображение по URL, data URI или пути к файлу + текстовая инструкция.

    Возвращает список URL результата.
    """
    api_key = _get_api_key()
    url = _get_endpoint()
    image_ref = _resolve_image_ref(image_source)
    payload = _build_edit_payload(image_ref, instruction, size, model, n)
    logger.debug(
        "Qwen edit: model=%s size=%s n=%s endpoint=%s",
        model,
        size,
        n,
        url,
    )
    data = _post_json(url, api_key, payload, timeout_sec)
    urls = _extract_image_urls(data)
    if not urls:
        raise QwenImageClientError(
            "Не удалось извлечь URL из ответа (неожиданная структура output.choices)."
        )
    return urls
