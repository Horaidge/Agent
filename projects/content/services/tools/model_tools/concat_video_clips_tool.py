"""
Инструмент модели: склейка нескольких готовых mp4 (по URL) в один файл.
"""
from __future__ import annotations

from typing import Any

TOOL_NAME = "concat_video_clips"

TOOL_DESCRIPTION = (
    "Склеивает несколько видеороликов в один mp4 в порядке списка URL. "
    "Каждый URL должен указывать на уже готовый файл mp4 (например, результат завершённого video job). "
    "Используй после того, как получены прямые ссылки на видео."
)

OPENAI_TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": (
            "Объединить несколько mp4 в один финальный ролик. "
            "Передай video_urls в нужном порядке (сверху вниз = от начала к концу фильма)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "video_urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Прямые HTTP(S) URL готовых mp4, по одному на клип, порядок = монтаж",
                },
                "label": {
                    "type": "string",
                    "description": "Опционально: короткая метка для имени файла (латиница, без пробелов)",
                },
            },
            "required": ["video_urls"],
        },
    },
}
