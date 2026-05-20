"""Схемы OpenAI tools для мини-бота."""
from __future__ import annotations

from typing import Any


def build_openai_tools(*, dream_pipeline_available: bool) -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = [
        {
            "type": "function",
            "function": {
                "name": "update_system_prompt_override",
                "description": (
                    "Сохранить или заменить блок ДОПОЛНИТЕЛЬНЫХ инструкций (override) поверх базового "
                    "промпта. Базовый промпт с перечнем инструментов не меняется. Вызывай, когда "
                    "пользователь явно просит изменить стиль, роль или постоянные правила поведения."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "new_override": {
                            "type": "string",
                            "description": "Полный текст override (русский или как просит пользователь).",
                        }
                    },
                    "required": ["new_override"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_public_knowledge",
                "description": (
                    "Семантический поиск по публичной базе знаний (Supabase RAG, фрагменты статей/постов). "
                    "Используй для фактов, цитат и образца манеры речи — не выдумывай то, чего нет в результатах."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Поисковый запрос на русском или английском.",
                        }
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_internal_documents",
                "description": (
                    "Поиск по внутренней базе файлов организации (отдельный RAG, в разработке). "
                    "Вызывай в режиме internal_kb или когда нужны внутренние документы."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Что искать во внутренних файлах.",
                        }
                    },
                    "required": ["query"],
                },
            },
        },
    ]
    if dream_pipeline_available:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "generate_dream_video",
                    "description": (
                        "Запустить Dream Lite: полный пайплайн визуализации сна до mp4 "
                        "(персонажи, кадры, план монтажа, подтверждение, i2v, склейка). "
                        "Передавай полный текст сна. Не вызывай для простого толкования без просьбы о видео."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "dream_text": {
                                "type": "string",
                                "description": "Текст сна пользователя целиком.",
                            }
                        },
                        "required": ["dream_text"],
                    },
                },
            }
        )
    return tools
