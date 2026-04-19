"""Операции Telegram Bot API: setWebhook, getWebhookInfo, deleteWebhook (без long polling)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import WebhookInfo

from bot.webhook_url import resolve_telegram_webhook_url
from core.config.settings import Settings

logger = logging.getLogger(__name__)

_SETWEBHOOK_TRIES = 10
_SETWEBHOOK_INITIAL_PAUSE_SEC = 2.0


async def get_webhook_info(bot: Bot) -> WebhookInfo:
    """Текущее состояние webhook у бота."""
    return await bot.get_webhook_info()


def _log_webhook_info_line(info: WebhookInfo, *, phase: str) -> None:
    """Снимок getWebhookInfo для логов (url, очередь, последняя ошибка доставки)."""
    logger.info(
        "getWebhookInfo [%s]: url=%r pending_update_count=%s last_error_message=%r",
        phase,
        info.url,
        info.pending_update_count,
        info.last_error_message,
    )


async def set_webhook_absolute_url(
    bot: Bot,
    url: str,
    secret: str | None = None,
) -> bool:
    """Установить webhook на явный HTTPS URL (например после запуска ngrok)."""
    kwargs: dict[str, Any] = {"url": url.rstrip("/")}
    if secret:
        kwargs["secret_token"] = secret
    logger.info("setWebhook (absolute): отправляю в Telegram url=%r", kwargs["url"])
    ok = await bot.set_webhook(**kwargs)
    logger.info("setWebhook (absolute): ответ Telegram ok=%s", ok)
    info = await get_webhook_info(bot)
    _log_webhook_info_line(info, phase="после setWebhook (absolute)")
    return ok


async def set_webhook_from_settings(bot: Bot, settings: Settings) -> bool:
    """
    Собирает итоговый URL (туннель + WEBHOOK_PATH или env), вызывает setWebhook, затем getWebhookInfo.

    Порядок относительно Cloudflare: resolve_telegram_webhook_url() уже должен видеть
    актуальный tunnel URL (память или current_tunnel.txt) — это обеспечивается в lifespan
    до вызова этой функции.

    Для *.trycloudflare.com: возможны повторы при «Failed to resolve host» у серверов Telegram.
    """
    try:
        url = resolve_telegram_webhook_url(settings)
    except ValueError as exc:
        logger.error("setWebhook: URL не собран — %s", exc)
        raise

    kwargs: dict[str, Any] = {"url": url.rstrip("/")}
    if settings.telegram_webhook_secret:
        kwargs["secret_token"] = settings.telegram_webhook_secret

    logger.info(
        "setWebhook: вызов Bot API | полный webhook URL (tunnel/base + WEBHOOK_PATH)=%r",
        kwargs["url"],
    )

    if "trycloudflare.com" in kwargs["url"]:
        logger.info(
            "setWebhook: пауза %.1f с перед запросом к Telegram (DNS для trycloudflare.com)",
            _SETWEBHOOK_INITIAL_PAUSE_SEC,
        )
        await asyncio.sleep(_SETWEBHOOK_INITIAL_PAUSE_SEC)

    delay = 2.0
    last_ok = False
    for attempt in range(1, _SETWEBHOOK_TRIES + 1):
        try:
            last_ok = await bot.set_webhook(**kwargs)
            logger.info(
                "setWebhook: успех на попытке %s/%s, Telegram вернул ok=%s",
                attempt,
                _SETWEBHOOK_TRIES,
                last_ok,
            )
            break
        except TelegramBadRequest as exc:
            msg = (exc.message or str(exc)).lower()
            retryable = (
                "resolve" in msg
                or "failed to resolve" in msg
                or ("bad webhook" in msg and "resolve" in msg)
            )
            logger.warning(
                "setWebhook: попытка %s/%s отклонена Telegram: %s",
                attempt,
                _SETWEBHOOK_TRIES,
                exc.message,
            )
            if attempt < _SETWEBHOOK_TRIES and retryable:
                logger.info(
                    "setWebhook: повтор через %.1f с (ожидание DNS для хоста из URL)",
                    delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 1.4, 12.0)
                continue
            logger.error(
                "setWebhook: окончательная ошибка Telegram (не повторяем): %s",
                exc.message,
            )
            raise

    info = await get_webhook_info(bot)
    _log_webhook_info_line(info, phase="после успешного setWebhook")
    return last_ok


async def delete_webhook(bot: Bot, drop_pending_updates: bool = False) -> bool:
    """Снимает webhook (бот перестанет получать обновления по HTTPS)."""
    return await bot.delete_webhook(drop_pending_updates=drop_pending_updates)


def webhook_info_to_dict(info: WebhookInfo) -> dict[str, Any]:
    """Удобный вывод для CLI / логов."""
    return info.model_dump(mode="json")
