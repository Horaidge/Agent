"""
Инструмент модели `generate_image`.

Содержит в одном месте:
- OpenAI function schema (что видит модель),
- правила аргументов,
- описание назначения,
- Python-исполнитель.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from services.tools.image_tools import ImageToolResult, tool_generate_image

TOOL_NAME = "generate_image"

TOOL_DESCRIPTION = (
    "Генерирует изображение по текстовому описанию. "
    "Используется для иллюстраций, визуализации сцен и dream-контента."
)

OPENAI_TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": (
            "Сгенерировать изображение по текстовому описанию (Qwen Image / DashScope). "
            "Вызывай, когда пользователь просит картинку, иллюстрацию, визуализацию сцены."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Описание изображения (сцена, стиль, детали)",
                },
                "size": {
                    "type": "string",
                    "enum": ["1024*1024", "1024*1536", "1536*1024"],
                    "description": "Размер в формате width*height",
                },
                "model": {
                    "type": "string",
                    "description": "Модель Qwen Image, например qwen-image-2.0",
                },
                "n": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 6,
                    "description": "Сколько вариантов сгенерировать",
                },
            },
            "required": ["prompt"],
        },
    },
}


@dataclass(frozen=True)
class GenerateImageArgs:
    prompt: str
    size: str = "1024*1536"
    model: str = "qwen-image-2.0"
    n: int = 1


def parse_generate_image_args(raw: str | dict[str, Any]) -> GenerateImageArgs:
    """Нормализует tool arguments из JSON-строки или dict."""
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

    size = str(data.get("size") or "1024*1536")
    model = str(data.get("model") or "qwen-image-2.0")
    n_raw = data.get("n", 1)
    try:
        n = int(n_raw)
    except (TypeError, ValueError):
        n = 1
    n = max(1, min(6, n))

    return GenerateImageArgs(prompt=prompt, size=size, model=model, n=n)


def execute_generate_image(args: GenerateImageArgs) -> ImageToolResult:
    """Синхронный вызов image tool с уже нормализованными аргументами."""
    return tool_generate_image(
        prompt=args.prompt,
        size=args.size,
        model=args.model,
        n=args.n,
    )

