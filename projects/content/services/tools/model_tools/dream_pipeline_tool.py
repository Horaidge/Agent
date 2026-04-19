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
    "Запускает полный pipeline визуализации сна: декомпозиция -> кадры -> анимация -> итоговое видео."
)

OPENAI_TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": (
            "Запусти полную визуализацию сна пользователя. "
            "Используй, когда нужно превратить описание сна в финальное видео."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "dream_text": {
                    "type": "string",
                    "description": "Описание сна естественным языком",
                },
                "style_hint": {
                    "type": "string",
                    "description": "Опциональная подсказка стиля/атмосферы",
                },
                "scene_count_hint": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 8,
                    "description": "Опционально: желаемое количество сцен",
                },
            },
            "required": ["dream_text"],
        },
    },
}

# machine-readable описание внутренних этапов для Dev UI / отладки
PIPELINE_INTERNAL_STAGES: list[dict[str, str]] = [
    {"id": "stage_1", "title": "Декомпозиция сна", "status": "internal"},
    {"id": "stage_2", "title": "Генерация изображений", "status": "internal"},
    {"id": "stage_3", "title": "Анимация сцен", "status": "internal"},
    {"id": "stage_4", "title": "Финальная сборка", "status": "internal"},
]


@dataclass(frozen=True)
class DreamPipelineArgs:
    dream_text: str
    style_hint: str | None = None
    scene_count_hint: int | None = None


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

    style_hint_raw = str(data.get("style_hint") or "").strip()
    style_hint = style_hint_raw or None

    scene_count_hint_raw = data.get("scene_count_hint")
    scene_count_hint: int | None = None
    if scene_count_hint_raw is not None:
        try:
            scene_count_hint = int(scene_count_hint_raw)
        except (TypeError, ValueError):
            scene_count_hint = None
        if scene_count_hint is not None:
            scene_count_hint = max(1, min(8, scene_count_hint))

    return DreamPipelineArgs(
        dream_text=dream_text,
        style_hint=style_hint,
        scene_count_hint=scene_count_hint,
    )

