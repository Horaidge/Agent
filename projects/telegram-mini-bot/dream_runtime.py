"""Запуск Dream Lite из мини-бота (без эвристик по тексту)."""
from __future__ import annotations

import logging

from aiogram.types import Message

from dream_integration import get_dream_context

logger = logging.getLogger(__name__)


async def run_dream_video_pipeline(message: Message, dream_text: str) -> str:
    ctx = get_dream_context()
    if ctx is None:
        return (
            "Dream Lite не подключён на сервере "
            "(нужны DREAM_LITE_ENABLED=1 и MONGODB_URI)."
        )
    if not ctx.openai or not getattr(ctx.openai, "configured", False):
        return "LLM для Dream Lite не сконфигурирован (OPENAI_API_KEY)."

    text = (dream_text or "").strip()
    if not text:
        return "Пустой dream_text — передай полный текст сна."

    from services.dreams.dream_lite_telegram_runner import run_dream_lite_for_telegram_user

    try:
        lite_run_id = await run_dream_lite_for_telegram_user(
            message=message,
            dream_text=text,
            repo=ctx.dream_lite_run_repo,
            openai=ctx.openai,
            summary_repo=ctx.dream_lite_summary_repo,
            asset_repo=ctx.dream_lite_asset_repo,
        )
        if lite_run_id:
            return f"Пайплайн Dream Lite запущен (run_id={lite_run_id}). Статус — в чате."
        return "Пайплайн не запущен (ограничение частоты, активный run или ошибка — см. сообщения выше)."
    except Exception as exc:
        logger.exception("generate_dream_video failed")
        return f"Ошибка запуска Dream Lite: {type(exc).__name__}"
