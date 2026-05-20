"""
Генерация изображений через OpenRouter Chat Completions (modalities по возможностям модели).

Поле `modalities` в теле запроса задаёт **выходные** модальности ответа (картинка ± текст ассистента),
а не «принимает ли модель текст»: вход по-прежнему `messages` с частями `image_url` + текст.

Модели с выходом image+text (Gemini image, GPT image на OpenRouter): `["image", "text"]`.
Модели только с выходом image (Flux и др.): `["image"]` — иначе 404 от роутера.

Документация: https://openrouter.ai/docs/guides/overview/multimodal/image-generation
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from core.config.settings import get_settings
from services.images.openrouter_image_models_catalog import (
    openrouter_model_supports_image_and_text_output,
    resolve_openrouter_image_model_id,
)

logger = logging.getLogger(__name__)

_DEFAULT_BASE = "https://openrouter.ai/api/v1"
_DEFAULT_TIMEOUT_SEC = 180.0

_URL_IN_TEXT_RE = re.compile(
    r"(?:data:image/[^\s\"'<>]+)|(?:https?://[^\s\"'<>]+)",
    re.IGNORECASE,
)


class OpenRouterImageError(Exception):
    """Ошибка вызова OpenRouter для image generation."""


def _output_modalities_for_openrouter_image_model(model_id: str) -> list[str]:
    """
    Output modalities для Chat Completions. Совпадает с карточкой модели на OpenRouter
    (см. `openrouter_model_supports_image_and_text_output`).
    """
    if openrouter_model_supports_image_and_text_output(model_id):
        return ["image", "text"]
    return ["image"]


def _format_openrouter_http_error(data: Any, status_code: int, fallback_text: str) -> str:
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            msg = err.get("message")
            code = err.get("code")
            if msg is not None:
                bits = f"{msg!s}"
                if code is not None:
                    bits = f"{{'message': {msg!r}, 'code': {code}}}"
                return f"HTTP {status_code}: {bits}"
        if isinstance(err, str) and err.strip():
            return f"HTTP {status_code}: {err.strip()}"
        msg = data.get("message")
        if isinstance(msg, str) and msg.strip():
            code = data.get("code")
            if code is not None:
                return f"HTTP {status_code}: {{'message': {msg!r}, 'code': {code}}}"
            return f"HTTP {status_code}: {msg.strip()}"
    return f"HTTP {status_code}: {(fallback_text or '')[:500]}"


def _redact_for_log(obj: Any, *, max_len: int = 400, max_list: int = 40) -> Any:
    """Укорачивает длинные строки (data URI, base64), чтобы логировать структуру ответа."""
    if isinstance(obj, dict):
        return {str(k): _redact_for_log(v, max_len=max_len, max_list=max_list) for k, v in obj.items()}
    if isinstance(obj, list):
        head = [_redact_for_log(x, max_len=max_len, max_list=max_list) for x in obj[:max_list]]
        if len(obj) > max_list:
            head.append(f"… <ещё {len(obj) - max_list} элементов>")
        return head
    if isinstance(obj, str) and len(obj) > max_len:
        return f"{obj[:80]}…<truncated len={len(obj)}>"
    return obj


def _log_openrouter_image_response(data: dict[str, Any], reason: str) -> None:
    try:
        redacted = _redact_for_log(data)
        dumped = json.dumps(redacted, ensure_ascii=False, default=str)
    except Exception:
        dumped = repr(data)[:12000]
    logger.warning("OpenRouter image: %s — redacted response:\n%s", reason, dumped[:12000])


def _append_url(bucket: list[str], url: Any) -> None:
    if url is None:
        return
    s = str(url).strip()
    if s and s not in bucket:
        bucket.append(s)


def _url_from_image_url_field(iu: Any) -> str | None:
    if isinstance(iu, dict):
        u = iu.get("url")
        return str(u).strip() if u else None
    if isinstance(iu, str):
        s = iu.strip()
        return s or None
    return None


def _extract_from_images_array(images: Any, bucket: list[str]) -> None:
    if not isinstance(images, list):
        return
    for item in images:
        if isinstance(item, str):
            _append_url(bucket, item)
            continue
        if not isinstance(item, dict):
            continue
        iu = item.get("image_url") or item.get("imageUrl") or item.get("url")
        u = _url_from_image_url_field(iu)
        if u:
            _append_url(bucket, u)
        b64 = item.get("b64_json")
        if isinstance(b64, str) and b64.strip():
            _append_url(bucket, f"data:image/png;base64,{b64.strip()}")


def _extract_from_content_parts(parts: list[Any], bucket: list[str]) -> None:
    for part in parts:
        if not isinstance(part, dict):
            continue
        ptype = str(part.get("type") or "")
        if ptype == "image_url":
            u = _url_from_image_url_field(part.get("image_url"))
            if u:
                _append_url(bucket, u)
        elif ptype in ("image", "output_image", "image_file"):
            img = part.get("image") or part.get("image_url") or part.get("url")
            if isinstance(img, str) and img.strip():
                _append_url(bucket, img)
            elif isinstance(img, dict):
                u = img.get("url") or img.get("href")
                if u:
                    _append_url(bucket, u)
        elif ptype == "text":
            t = part.get("text")
            if isinstance(t, str):
                for m in _URL_IN_TEXT_RE.finditer(t):
                    _append_url(bucket, m.group(0))


def _extract_urls_from_plain_text(text: str, bucket: list[str]) -> None:
    for m in _URL_IN_TEXT_RE.finditer(text):
        _append_url(bucket, m.group(0))


def _extract_image_urls_from_message(message: dict[str, Any], bucket: list[str], depth: int = 0) -> None:
    """Собирает URL из message: images[], content (list/str), плоские поля, вложенные output/data/result."""
    if depth > 5 or not isinstance(message, dict):
        return

    _extract_from_images_array(message.get("images"), bucket)

    content = message.get("content")
    if isinstance(content, list):
        _extract_from_content_parts(content, bucket)
    elif isinstance(content, str) and content.strip():
        _extract_urls_from_plain_text(content, bucket)

    for key in ("image_url", "imageUrl", "url"):
        raw = message.get(key)
        if isinstance(raw, str) and raw.strip():
            _append_url(bucket, raw)
        elif isinstance(raw, dict):
            u = raw.get("url")
            if u:
                _append_url(bucket, u)

    for nest_key in ("output", "data", "result"):
        nested = message.get(nest_key)
        if isinstance(nested, dict):
            _extract_image_urls_from_message(nested, bucket, depth + 1)
        elif isinstance(nested, list):
            for el in nested:
                if isinstance(el, dict):
                    _extract_image_urls_from_message(el, bucket, depth + 1)


def _extract_image_urls_from_choice(choice: dict[str, Any]) -> list[str]:
    """Извлекает URL/data URI из choice: message + плоские поля провайдера."""
    bucket: list[str] = []
    if not isinstance(choice, dict):
        return bucket

    _extract_from_images_array(choice.get("images"), bucket)

    msg = choice.get("message")
    if isinstance(msg, dict):
        _extract_image_urls_from_message(msg, bucket, 0)

    for key in ("image_url", "imageUrl", "url"):
        raw = choice.get(key)
        if isinstance(raw, str) and raw.strip():
            _append_url(bucket, raw)

    return bucket


def _message_content_for_request(
    prompt: str,
    reference_image_urls: list[str] | None,
) -> str | list[dict[str, Any]]:
    """Текст или multimodal content (OpenAI-совместимый список частей)."""
    p = prompt.strip()
    refs = [u.strip() for u in (reference_image_urls or []) if (u or "").strip()]
    if not refs:
        return p
    parts: list[dict[str, Any]] = []
    # OpenRouter рекомендует передавать текстовую инструкцию раньше image_url-частей:
    # это повышает вероятность корректного парсинга мультимодального ввода.
    parts.append({"type": "text", "text": p})
    for u in refs:
        parts.append({"type": "image_url", "image_url": {"url": u}})
    return parts


def generate_image_urls_via_openrouter_with_usage(
    *,
    prompt: str,
    model: str | None = None,
    aspect_ratio: str | None = None,
    image_size: str | None = None,
    reference_image_urls: list[str] | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    http_referer: str | None = None,
) -> tuple[list[str], dict[str, Any] | None]:
    """
    Возвращает (urls, usage) — usage из корня ответа OpenRouter, если провайдер отдал.
    """
    settings = get_settings()
    key = (api_key or settings.openrouter_api_key or "").strip()
    if not key:
        raise OpenRouterImageError(
            "Не задан OPENROUTER_API_KEY (переменная окружения или Settings)."
        )
    model_id = resolve_openrouter_image_model_id(model or settings.openrouter_image_model or "")
    if not model_id:
        raise OpenRouterImageError("Не задана модель OpenRouter для изображений.")

    root = (base_url or settings.openrouter_base_url or _DEFAULT_BASE).rstrip("/")
    url = f"{root}/chat/completions"

    content = _message_content_for_request(prompt, reference_image_urls)
    modalities = _output_modalities_for_openrouter_image_model(model_id)
    modality_attempts: list[list[str]] = [modalities]
    if modalities == ["image", "text"]:
        # Иногда роутер Gemini отвечает 404 по связке image+text; вторая попытка только image.
        modality_attempts.append(["image"])

    body: dict[str, Any] = {
        "model": model_id,
        "messages": [{"role": "user", "content": content}],
        "modalities": modalities,
    }
    image_config: dict[str, Any] = {}
    if aspect_ratio and str(aspect_ratio).strip():
        image_config["aspect_ratio"] = str(aspect_ratio).strip()
    if image_size and str(image_size).strip():
        image_config["image_size"] = str(image_size).strip()
    if image_config:
        body["image_config"] = image_config

    headers: dict[str, str] = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    ref = (http_referer or settings.openrouter_http_referer or "").strip()
    if ref:
        headers["HTTP-Referer"] = ref

    logger.info("OpenRouter image: model=%s aspect=%s modalities=%s", model_id, aspect_ratio, modalities)
    data: Any = {}
    r: httpx.Response | None = None
    with httpx.Client(timeout=_DEFAULT_TIMEOUT_SEC) as client:
        for attempt_i, mods in enumerate(modality_attempts):
            body["modalities"] = mods
            if attempt_i:
                logger.info(
                    "OpenRouter image: model=%s повтор запроса modalities=%s",
                    model_id,
                    mods,
                )
            r = client.post(url, headers=headers, json=body)
            try:
                data = r.json()
            except Exception:
                data = {"_raw": (r.text or "")[:2000]}
            if r.status_code < 400:
                break
            err = _format_openrouter_http_error(data, r.status_code, r.text or "")
            modality_routing = r.status_code == 404 and "modality" in err.lower()
            if modality_routing and attempt_i + 1 < len(modality_attempts):
                logger.warning("OpenRouter image: %s — пробуем другие modalities", err)
                continue
            raise OpenRouterImageError(err)

    choices = data.get("choices") if isinstance(data, dict) else None
    if not isinstance(choices, list) or not choices:
        raise OpenRouterImageError(f"Нет choices в ответе: {data!r}")

    ch0 = choices[0] if isinstance(choices[0], dict) else {}
    urls = _extract_image_urls_from_choice(ch0)
    if not urls:
        if isinstance(data, dict):
            _log_openrouter_image_response(
                data,
                "нет извлечённых URL изображений (см. структуру ответа ниже)",
            )
        msg = ch0.get("message") if isinstance(ch0.get("message"), dict) else {}
        refusal = msg.get("refusal") if isinstance(msg, dict) else None
        hint_keys = []
        if isinstance(msg, dict):
            hint_keys = [k for k in msg.keys() if k in ("images", "content", "refusal", "role")]
        extra = ""
        if refusal:
            extra = f" Отказ модели (refusal): {refusal!s}"
        raise OpenRouterImageError(
            "Модель не вернула изображение в ожидаемом формате "
            "(ожидались message.images, content с image_url, или плоские url/image_url). "
            "Проверьте modalities, id модели с image output и endpoint. "
            f"Ключи message: {hint_keys}.{extra} "
            "Полный ответ с усечёнными строками записан в лог (warning)."
        )
    usage = data.get("usage") if isinstance(data, dict) else None
    return urls, usage if isinstance(usage, dict) else None


def generate_image_urls_via_openrouter(
    *,
    prompt: str,
    model: str | None = None,
    aspect_ratio: str | None = None,
    image_size: str | None = None,
    reference_image_urls: list[str] | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    http_referer: str | None = None,
) -> list[str]:
    """Только список URL/data URI изображений."""
    urls, _u = generate_image_urls_via_openrouter_with_usage(
        prompt=prompt,
        model=model,
        aspect_ratio=aspect_ratio,
        image_size=image_size,
        reference_image_urls=reference_image_urls,
        api_key=api_key,
        base_url=base_url,
        http_referer=http_referer,
    )
    return urls
