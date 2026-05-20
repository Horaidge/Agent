"""
Инструмент модели `video_trim_start`.

Служебный tool для постобработки видео: убрать инерционный «разгон» в начале.
"""
from __future__ import annotations

from typing import Any

TOOL_NAME = "video_trim_start"

TOOL_DESCRIPTION = (
    "Обрезает начало видео на небольшую длительность (обычно 0.3..1.0 сек), "
    "чтобы убрать фазу разгона движения."
)

OPENAI_TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": (
            "Обрезать начало видео на trim_start_sec секунд. "
            "Вызывай, когда в начале ролика есть статичный разгон перед движением."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "video_url": {
                    "type": "string",
                    "description": "URL исходного видео для обрезки",
                },
                "trim_start_sec": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 2.0,
                    "description": "Сколько секунд обрезать с начала (рекомендуемо 0.3..1.0)",
                },
            },
            "required": ["video_url", "trim_start_sec"],
        },
    },
}

