"""
Инструмент модели `last_frame_as_reference`.

Служебный tool для continuity: взять последний кадр предыдущего видео как референс.
"""
from __future__ import annotations

from typing import Any

TOOL_NAME = "last_frame_as_reference"

TOOL_DESCRIPTION = (
    "Извлекает последний кадр видео и возвращает его как reference image "
    "для следующей генерации/сцены."
)

OPENAI_TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": (
            "Взять последний кадр видео для использования как референс "
            "в следующем image/video шаге."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "video_url": {
                    "type": "string",
                    "description": "URL видео-источника, из которого берётся последний кадр",
                },
                "scene_index": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Опциональный индекс сцены для трассировки контекста",
                },
            },
            "required": ["video_url"],
        },
    },
}

