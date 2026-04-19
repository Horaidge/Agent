from __future__ import annotations

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession

from core.config.settings import Settings


def create_telegram_bot(settings: Settings) -> Bot:
    proxy = (settings.telegram_proxy_url or "").strip()
    if proxy:
        session = AiohttpSession(proxy=proxy)
        return Bot(token=settings.telegram_bot_token, session=session)
    return Bot(token=settings.telegram_bot_token)
