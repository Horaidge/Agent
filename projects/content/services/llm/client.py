"""Клиент LLM: заглушка под выбранный провайдер (OpenAI, локальная модель и т.д.)."""
from __future__ import annotations


class LlmClient:
    """Вызовы к LLM для анализа текста и подсказок к генерации изображений."""

    async def analyze_user_prompt(self, text: str) -> str:
        """Обработка текста пользователя; вернуть нормализованный промпт или план."""
        raise NotImplementedError
