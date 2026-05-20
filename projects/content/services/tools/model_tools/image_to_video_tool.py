"""
Инструмент модели `image_to_video`.

Пока не подключён в OPENAI_TOOLS_DEFAULT, но готов к добавлению в реестр.
"""
from __future__ import annotations

from typing import Any

TOOL_NAME = "image_to_video"

TOOL_DESCRIPTION = (
    "Создаёт видео из изображения и текстового промпта (Wan i2v, по умолчанию wan2.7). "
    "Опционально принимает last_frame_url для связки first/last frame. "
    "Возвращает job_id и статус задачи."
)

OPENAI_TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": (
            "Создать видео по изображению и описанию движения. "
            "Вызывай, когда пользователь просит анимировать картинку."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Описание желаемого движения/сюжета видео",
                },
                "image_url": {
                    "type": "string",
                    "description": "URL или data URI первого (стартового) кадра",
                },
                "last_frame_url": {
                    "type": "string",
                    "description": (
                        "Опционально: конечный ключевой кадр (wan2.7-i2v → input.media last_frame). "
                        "Сборщик: сначала сгенерировать оба кадра через generate_image_openrouter, затем вызвать i2v."
                    ),
                },
                "duration": {
                    "type": "integer",
                    "minimum": 2,
                    "maximum": 10,
                    "description": "Длительность ролика в секундах (диапазон Wan 2.7 в проекте: 2–10)",
                },
                "resolution": {
                    "type": "string",
                    "enum": ["480p", "720p", "1080p"],
                    "description": "Разрешение результата",
                },
            },
            "required": ["prompt", "image_url"],
        },
    },
}

