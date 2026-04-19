"""
Обёртки для Qwen Image: вызываются вручную, из тестов или как tools у языковой модели.

Не содержат логики Telegram и не импортируют LLM-клиенты.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from services.images.qwen_image_client import (
    QwenImageClientError,
    edit_image_with_instruction,
    generate_image_from_prompt,
)

logger = logging.getLogger(__name__)


@dataclass
class ImageToolResult:
    """Унифицированный результат tool для логов и агента."""

    ok: bool
    image_urls: list[str]
    error: str | None = None
    model: str | None = None
    size: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "image_urls": self.image_urls,
            "error": self.error,
            "model": self.model,
            "size": self.size,
            "count": len(self.image_urls),
        }


_DEFAULT_BASE_CHARACTER_PROMPT = (
    "realistic portrait of a neutral human, studio lighting, consistent identity"
)


@dataclass
class BaseCharacterToolResult:
    """Результат generate_base_character (Qwen Image)."""

    ok: bool
    image_url: str | None
    prompt_used: str
    character_id: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "image_url": self.image_url,
            "prompt_used": self.prompt_used,
            "character_id": self.character_id,
            "error": self.error,
        }


def tool_generate_base_character(appearance: str | None = None) -> BaseCharacterToolResult:
    """
    Сгенерировать базового персонажа по тексту внешности (или дефолтный нейтральный портрет).
    """
    if appearance and str(appearance).strip():
        prompt_used = str(appearance).strip()
    else:
        prompt_used = _DEFAULT_BASE_CHARACTER_PROMPT

    character_id = str(uuid.uuid4())
    logger.info("tool_generate_base_character: character_id=%s", character_id)

    try:
        urls = generate_image_from_prompt(
            prompt=prompt_used,
            size="1024*1536",
            model="qwen-image-2.0",
            n=1,
        )
        if not urls:
            return BaseCharacterToolResult(
                ok=False,
                image_url=None,
                prompt_used=prompt_used,
                character_id=character_id,
                error="Пустой ответ генератора изображений",
            )
        return BaseCharacterToolResult(
            ok=True,
            image_url=urls[0],
            prompt_used=prompt_used,
            character_id=character_id,
        )
    except QwenImageClientError as e:
        logger.warning("tool_generate_base_character: %s", e)
        return BaseCharacterToolResult(
            ok=False,
            image_url=None,
            prompt_used=prompt_used,
            character_id=character_id,
            error=str(e),
        )


def tool_generate_image(
    prompt: str,
    size: str = "1024*1536",
    model: str = "qwen-image-2.0",
    n: int = 1,
) -> ImageToolResult:
    """
    Tool: сгенерировать изображение по промпту (Qwen Image / DashScope).
    """
    logger.info(
        "tool_generate_image: model=%s size=%s n=%s",
        model,
        size,
        n,
    )
    try:
        urls = generate_image_from_prompt(
            prompt=prompt,
            size=size,
            model=model,
            n=n,
        )
        logger.info(
            "tool_generate_image: success count=%s model=%s size=%s",
            len(urls),
            model,
            size,
        )
        return ImageToolResult(
            ok=True,
            image_urls=urls,
            model=model,
            size=size,
        )
    except QwenImageClientError as e:
        logger.warning(
            "tool_generate_image: error model=%s size=%s: %s",
            model,
            size,
            e,
        )
        return ImageToolResult(
            ok=False,
            image_urls=[],
            error=str(e),
            model=model,
            size=size,
        )


def tool_edit_image(
    image_source: str,
    instruction: str,
    size: str = "1024*1536",
    model: str = "qwen-image-2.0",
    n: int = 1,
) -> ImageToolResult:
    """
    Tool: отредактировать изображение (URL, data URI или путь к файлу) по инструкции.
    """
    logger.info(
        "tool_edit_image: model=%s size=%s n=%s",
        model,
        size,
        n,
    )
    try:
        urls = edit_image_with_instruction(
            image_source=image_source,
            instruction=instruction,
            size=size,
            model=model,
            n=n,
        )
        logger.info(
            "tool_edit_image: success count=%s model=%s size=%s",
            len(urls),
            model,
            size,
        )
        return ImageToolResult(
            ok=True,
            image_urls=urls,
            model=model,
            size=size,
        )
    except QwenImageClientError as e:
        logger.warning(
            "tool_edit_image: error model=%s size=%s: %s",
            model,
            size,
            e,
        )
        return ImageToolResult(
            ok=False,
            image_urls=[],
            error=str(e),
            model=model,
            size=size,
        )
