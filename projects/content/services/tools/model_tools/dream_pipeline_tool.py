"""
Композитный инструмент `generate_dream_pipeline`.

Важно:
- Это фасад для полного Dream Pipeline.
- Внутри он выполняет несколько внутренних этапов (а не один API-вызов):
  1) разметка/декомпозиция сна на сцены,
  2) генерация изображений по сценам,
  3) анимация изображений,
  4) финальная склейка видео.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

TOOL_NAME = "generate_dream_pipeline"

TOOL_DESCRIPTION = (
    "Запускает Dream Pipeline Lite end-to-end: текст сна -> кадры -> анимация -> итоговое видео для пользователя Telegram."
)

OPENAI_TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": (
            "Запусти Dream Pipeline Lite целиком и отправь пользователю итоговое видео в Telegram. "
            "Используй, когда нужно превратить описание сна в финальный mp4."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "dream_text": {
                    "type": "string",
                    "description": "Описание сна естественным языком",
                },
                "telegram_user_id": {
                    "type": "integer",
                    "description": "Опционально: id пользователя Telegram (если есть в контексте).",
                },
            },
            "required": ["dream_text"],
        },
    },
}

# machine-readable описание внутренних этапов для Dev UI / отладки
PIPELINE_INTERNAL_STAGES: list[dict[str, str]] = [
    {"id": "resolve_style", "title": "Resolve style", "status": "internal"},
    {"id": "load_user_context", "title": "Load user context", "status": "internal"},
    {"id": "resolve_avatar", "title": "Resolve user avatar", "status": "internal"},
    {"id": "resolve_actors", "title": "Resolve secondary actors", "status": "internal"},
    {"id": "decomposition", "title": "Dream decomposition", "status": "internal"},
    {"id": "scene_actor_mapping", "title": "Bind scene actors", "status": "internal"},
    {"id": "build_prompts", "title": "Build final prompts", "status": "internal"},
    {"id": "generate_images", "title": "Generate scene images", "status": "internal"},
    {"id": "animate", "title": "Animate scenes", "status": "internal"},
    {"id": "assemble", "title": "Assemble final video", "status": "internal"},
]


@dataclass(frozen=True)
class DreamPipelineArgs:
    dream_text: str
    telegram_user_id: int | None = None


def parse_dream_pipeline_args(raw: str | dict[str, Any]) -> DreamPipelineArgs:
    """Нормализует аргументы инструмента из JSON-строки или dict."""
    if isinstance(raw, str):
        try:
            data = json.loads(raw or "{}")
        except json.JSONDecodeError:
            data = {}
    elif isinstance(raw, dict):
        data = raw
    else:
        data = {}

    dream_text = str(data.get("dream_text") or "").strip()
    if not dream_text:
        raise ValueError("missing_dream_text")

    telegram_user_id_raw = data.get("telegram_user_id")
    telegram_user_id: int | None = None
    if telegram_user_id_raw is not None:
        try:
            telegram_user_id = int(telegram_user_id_raw)
        except (TypeError, ValueError):
            telegram_user_id = None

    return DreamPipelineArgs(
        dream_text=dream_text,
        telegram_user_id=telegram_user_id,
    )

