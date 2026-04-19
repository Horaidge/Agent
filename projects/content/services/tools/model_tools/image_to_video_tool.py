"""
Инструмент модели `image_to_video`.

Пока не подключён в OPENAI_TOOLS_DEFAULT, но готов к добавлению в реестр.
"""
from __future__ import annotations

from typing import Any

TOOL_NAME = "image_to_video"

TOOL_DESCRIPTION = (
    "Создаёт видео из изображения и текстового промпта (Wan i2v). "
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
                    "description": "URL исходного изображения",
                },
                "duration": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 8,
                    "description": "Длительность ролика в секундах",
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

