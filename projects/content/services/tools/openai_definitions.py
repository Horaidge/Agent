"""
JSON-схемы инструментов для OpenAI Chat Completions (function calling).

Реализации Python лежат рядом: `image_tools.py`, `video_tools.py`.
Добавляя новый tool — описание здесь, обработку — в оркестраторе чата / отдельном handler.
"""
from __future__ import annotations

from typing import Any

# Схема для модели — сервер вызывает Python `tool_generate_image` по имени `generate_image`
GENERATE_IMAGE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "generate_image",
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

# Список tools, передаваемых в chat по умолчанию (расширяйте по мере добавления схем выше)
OPENAI_TOOLS_DEFAULT: list[dict[str, Any]] = [
    GENERATE_IMAGE_TOOL,
]
