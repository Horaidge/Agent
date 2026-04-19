"""Точка входа: HTTP-сервер (webhook Telegram + Gradio). Туннель Cloudflare — см. run_cloudflared_tunnel.py (по умолчанию отдельно)."""
import logging
import os

# До импорта приложения / gradio — отключаем телеметрию Gradio и лишние запросы наружу
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "false")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

import uvicorn

from core.config.settings import get_settings
from core.logging_dev_filter import install_dev_access_log_filter
from core.tunnels.startup import run_dev_with_ngrok

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
install_dev_access_log_filter()


def main() -> None:
    settings = get_settings()
    if settings.start_ngrok_tunnel:
        run_dev_with_ngrok(settings)
        return

    uvicorn.run(
        "application:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
    )


if __name__ == "__main__":
    main()
