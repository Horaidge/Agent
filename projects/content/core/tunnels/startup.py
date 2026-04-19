"""Запуск uvicorn + ngrok + автоматический setWebhook для быстрых локальных тестов."""
from __future__ import annotations

import asyncio
import logging
import threading
import time

import uvicorn

from bot.webhook_management import get_webhook_info, set_webhook_absolute_url
from core.config.settings import Settings
from core.integrations.telegram_client import create_telegram_bot
from core.tunnels.ngrok_runner import start_public_http_url, stop_all

logger = logging.getLogger(__name__)

_SERVER_READY_DELAY_SEC = 2.0


def run_dev_with_ngrok(settings: Settings) -> None:
    """
    Поднимает FastAPI в фоне, открывает ngrok на тот же порт, вызывает setWebhook на
    https://<ngrok-host><WEBHOOK_PATH> и остаётся работать, пока не остановите процесс (Ctrl+C).
    """
    if not settings.ngrok_auth_token:
        raise SystemExit(
            "Для START_NGROK_TUNNEL=true укажите NGROK_AUTH_TOKEN в ENV "
            "(https://dashboard.ngrok.com/get-started/your-authtoken)."
        )

    def _serve() -> None:
        uvicorn.run(
            "application:create_app",
            factory=True,
            host=settings.host,
            port=settings.port,
        )

    server = threading.Thread(target=_serve, name="uvicorn", daemon=True)
    server.start()
    time.sleep(_SERVER_READY_DELAY_SEC)

    public_base: str
    try:
        public_base = start_public_http_url(settings.port, settings.ngrok_auth_token)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Не удалось запустить ngrok")
        stop_all()
        raise SystemExit(1) from exc

    webhook_url = f"{public_base.rstrip('/')}{settings.webhook_path}"
    if not webhook_url.startswith("https://"):
        logger.warning(
            "Публичный URL туннеля без https — Telegram может отклонить webhook: %s",
            webhook_url,
        )

    async def _set_webhook() -> None:
        bot = create_telegram_bot(settings)
        try:
            ok = await set_webhook_absolute_url(
                bot,
                webhook_url,
                settings.telegram_webhook_secret,
            )
            info = await get_webhook_info(bot)
            print()
            print("--- Telegram webhook ---")
            print("setWebhook:", ok)
            print("URL в Telegram:", info.url or "(пусто)")
            print("Ожидаемый URL:", webhook_url)
            print("-------------------------")
            print()
        finally:
            await bot.session.close()

    asyncio.run(_set_webhook())

    # Локальный Gradio уже выведен / открыт в lifespan FastAPI (поток uvicorn)
    print(f"Публичный туннель (Telegram): {public_base}")
    print("Остановка: Ctrl+C (ngrok будет закрыт)")
    print()

    try:
        server.join()
    except KeyboardInterrupt:
        print("\nОстановка...")
    finally:
        stop_all()
