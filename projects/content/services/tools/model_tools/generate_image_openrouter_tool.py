"""
Инструмент `generate_image_openrouter`: картинки через OpenRouter (Gemini image и др.).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from services.tools.image_tools import ImageToolResult
from services.tools.openrouter_image_tools import tool_generate_image_openrouter

TOOL_NAME = "generate_image_openrouter"

TOOL_DESCRIPTION = (
    "Генерирует изображение по текстовому промпту через OpenRouter (модель с image output). "
    "Используется Сборщиком для ключевых кадров по плану Режиссёра."
)

_ASPECT_ENUM = [
    "1:1",
    "2:3",
    "3:2",
    "3:4",
    "4:3",
    "4:5",
    "5:4",
    "9:16",
    "16:9",
    "21:9",
]

OPENAI_TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": (
            "Сгенерировать изображение по описанию через OpenRouter. "
            "Вызывай для стартового/конечного кадра сцены, когда Режиссёр зафиксировал need для кадров."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Описание кадра (сцена, стиль, освещение, композиция)",
                },
                "aspect_ratio": {
                    "type": "string",
                    "enum": _ASPECT_ENUM,
                    "description": "Соотношение сторон (см. image_config OpenRouter)",
                },
                "image_size": {
                    "type": "string",
                    "enum": ["1K", "2K", "4K", "0.5K"],
                    "description": "Разрешение, если поддерживает модель",
                },
                "model": {
                    "type": "string",
                    "description": "Переопределение id модели OpenRouter (иначе из настроек)",
                },
            },
            "required": ["prompt"],
        },
    },
}


@dataclass(frozen=True)
class GenerateImageOpenRouterArgs:
    prompt: str
    aspect_ratio: str | None = None
    image_size: str | None = None
    model: str | None = None


def parse_generate_image_openrouter_args(
    raw: str | dict[str, Any],
) -> GenerateImageOpenRouterArgs:
    if isinstance(raw, str):
        try:
            data = json.loads(raw or "{}")
        except json.JSONDecodeError:
            data = {}
    elif isinstance(raw, dict):
        data = raw
    else:
        data = {}

    prompt = str(data.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("missing_prompt")

    ar = data.get("aspect_ratio")
    aspect_ratio = str(ar).strip() if ar else None
    if aspect_ratio and aspect_ratio not in _ASPECT_ENUM:
        aspect_ratio = None

    iz = data.get("image_size")
    image_size = str(iz).strip() if iz else None
    if image_size and image_size not in ("1K", "2K", "4K", "0.5K"):
        image_size = None

    mod = data.get("model")
    model = str(mod).strip() if mod else None

    return GenerateImageOpenRouterArgs(
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        image_size=image_size,
        model=model,
    )


def execute_generate_image_openrouter(
    args: GenerateImageOpenRouterArgs,
) -> ImageToolResult:
    return tool_generate_image_openrouter(
        args.prompt,
        aspect_ratio=args.aspect_ratio,
        image_size=args.image_size,
        model=args.model,
    )
