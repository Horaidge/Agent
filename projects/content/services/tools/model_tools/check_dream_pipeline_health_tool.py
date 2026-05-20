"""
Инструмент модели `check_dream_pipeline_health`.

Нужен для быстрой диагностики готовности Dream Pipeline Lite из Telegram
без запуска тяжёлой генерации изображений/видео.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

TOOL_NAME = "check_dream_pipeline_health"

TOOL_DESCRIPTION = (
    "Проверяет готовность Dream Pipeline Lite (конфиг, инструменты, репозитории, провайдеры) "
    "без запуска дорогой генерации."
)

OPENAI_TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": (
            "Запусти healthcheck Dream Pipeline Lite и верни статусы проверок. "
            "Используй, когда нужно проверить, что пайплайн готов к запуску."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "check_level": {
                    "type": "string",
                    "enum": ["quick", "full"],
                    "description": "quick=быстрые проверки; full=расширенные проверки доступности зависимостей.",
                }
            },
            "required": [],
        },
    },
}


@dataclass(frozen=True)
class DreamPipelineHealthArgs:
    check_level: str = "quick"


def parse_dream_pipeline_health_args(raw: str | dict[str, Any]) -> DreamPipelineHealthArgs:
    if isinstance(raw, str):
        try:
            data = json.loads(raw or "{}")
        except json.JSONDecodeError:
            data = {}
    elif isinstance(raw, dict):
        data = raw
    else:
        data = {}

    lvl = str(data.get("check_level") or "quick").strip().lower()
    if lvl not in ("quick", "full"):
        lvl = "quick"
    return DreamPipelineHealthArgs(check_level=lvl)
