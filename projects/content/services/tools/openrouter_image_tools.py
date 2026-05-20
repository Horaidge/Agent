"""
Tool-слой: генерация изображения через OpenRouter (Nano Banana / Gemini image на OpenRouter).
"""
from __future__ import annotations

import logging
from typing import Any

from core.config.settings import get_settings
from services.images.openrouter_image_models_catalog import (
    openrouter_model_supports_reference_images,
    openrouter_image_models_try_chain,
    resolve_openrouter_image_model_id,
)
from services.images.openrouter_image_client import (
    OpenRouterImageError,
    generate_image_urls_via_openrouter_with_usage,
)
from services.tools.image_tools import ImageToolResult

logger = logging.getLogger(__name__)


def tool_generate_image_openrouter(
    prompt: str,
    *,
    aspect_ratio: str | None = None,
    image_size: str | None = None,
    model: str | None = None,
    reference_image_urls: list[str] | None = None,
    strict_model: bool = False,
) -> ImageToolResult:
    """
    Синхронная генерация одного изображения; в `image_urls` — как минимум один URL/data URL.
    При ошибке перебирает цепочку: основная → OPENROUTER_IMAGE_MODEL_FALLBACK → модели с **выходом image+text**
    на OpenRouter (Gemini image, GPT image), без Flux/Seedream, чтобы везде один контракт modalities.
    """
    settings = get_settings()
    primary = resolve_openrouter_image_model_id(model or settings.openrouter_image_model or "")
    fb = resolve_openrouter_image_model_id(settings.openrouter_image_model_fallback or "")
    refs = [str(u).strip() for u in (reference_image_urls or []) if str(u).strip()]
    if refs and primary and not openrouter_model_supports_reference_images(primary):
        return ImageToolResult(
            ok=False,
            image_urls=[],
            error=(
                f"Выбранная image-модель {primary} не поддерживает reference images. "
                "Смените модель на refs-capable (например, Gemini/GPT/Seedream) "
                "или отключите обязательные refs для кадра."
            ),
            model=primary,
            size=None,
            usage=None,
            models_tried=[primary] if primary else None,
        )

    models = [primary] if (strict_model and primary) else openrouter_image_models_try_chain(
        primary_resolved=primary,
        settings_fallback_resolved=fb,
    )

    if not models:
        return ImageToolResult(
            ok=False,
            image_urls=[],
            error=(
                "Не задан валидный id модели OpenRouter (ожидается вид vendor/name). "
                "Проверьте выбор в списке, OPENROUTER_IMAGE_MODEL и FALLBACK в .env."
            ),
            model=model,
            size=None,
            usage=None,
        )

    last_err: str | None = None
    models_tried: list[str] = []
    for model_id in models:
        models_tried.append(model_id)
        try:
            urls, usage = generate_image_urls_via_openrouter_with_usage(
                prompt=prompt,
                model=model_id,
                aspect_ratio=aspect_ratio,
                image_size=image_size,
                reference_image_urls=refs,
            )
        except OpenRouterImageError as e:
            last_err = str(e)
            logger.warning(
                "tool_generate_image_openrouter: model=%s failed: %s — пробуем следующую",
                model_id,
                e,
            )
            continue
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
            logger.exception("tool_generate_image_openrouter: model=%s", model_id)
            continue

        return ImageToolResult(
            ok=True,
            image_urls=urls[:1],
            error=None,
            model=model_id,
            size=aspect_ratio,
            usage=usage,
            models_tried=list(models_tried),
        )

    tried_hint = ", ".join(models_tried) if models_tried else "—"
    final_err = last_err or "все модели изображений вернули ошибку"
    if models_tried:
        final_err = f"{final_err} (перепробованы: {tried_hint})"

    return ImageToolResult(
        ok=False,
        image_urls=[],
        error=final_err,
        model=models_tried[-1] if models_tried else model,
        size=None,
        usage=None,
        models_tried=list(models_tried) if models_tried else None,
    )


def tool_generate_image_openrouter_dict(
    prompt: str,
    *,
    aspect_ratio: str | None = None,
    image_size: str | None = None,
    model: str | None = None,
    reference_image_urls: list[str] | None = None,
    strict_model: bool = False,
) -> dict[str, Any]:
    """Обёртка с to_dict для логов и HTTP."""
    return tool_generate_image_openrouter(
        prompt,
        aspect_ratio=aspect_ratio,
        image_size=image_size,
        model=model,
        reference_image_urls=reference_image_urls,
        strict_model=strict_model,
    ).to_dict()
