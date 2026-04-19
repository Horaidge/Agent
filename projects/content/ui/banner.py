"""Сообщения в консоль и автооткрытие локального Gradio в браузере."""
from __future__ import annotations

import threading
import webbrowser

from core.config.settings import Settings


def local_base_url(settings: Settings) -> str:
    """Адрес для браузера на этой машине (не 0.0.0.0)."""
    host = settings.local_ui_host.strip() if settings.local_ui_host else "127.0.0.1"
    return f"http://{host}:{settings.port}"


def gradio_url(settings: Settings) -> str:
    return f"{local_base_url(settings).rstrip('/')}{settings.gradio_mount_path}"


def link_root_for_ui(settings: Settings) -> str:
    """
    Корень для ссылок в Gradio и сообщениях бота.

    Если задан PUBLIC_BASE_URL — используем путь за nginx (`/content/...`).
    Иначе — прямой адрес uvicorn на этой машине.
    """
    pub = (settings.public_base_url or "").strip().rstrip("/")
    if pub:
        return f"{pub}/content"
    return local_base_url(settings).rstrip("/")


def gradio_link_for_users(settings: Settings) -> str:
    """Тот URL Gradio, который можно открыть с телефона / в Telegram (не localhost)."""
    return f"{link_root_for_ui(settings).rstrip('/')}{settings.gradio_mount_path}"


def print_local_app_banner(settings: Settings) -> None:
    """Одна готовая строка с URL — в терминале Cursor/VS Code по ней можно перейти по клику."""
    base = local_base_url(settings)
    ui = gradio_url(settings)
    print()
    print("  ─────────────────────────────────────────────")
    print("   Локальный интерфейс (Gradio):  " + ui)
    if (settings.public_base_url or "").strip():
        print("   Публичный URL (браузер/Telegram): " + gradio_link_for_users(settings))
    if settings.dev_debug_ui_enabled:
        print("   Dev console (localhost):       " + f"{base}/dev/")
    print("   Проверка API:                  " + f"{base}/health")
    print("  ─────────────────────────────────────────────")
    print()


def schedule_open_gradio_in_browser(settings: Settings) -> None:
    """Открыть вкладку браузера после того, как uvicorn начнёт слушать порт."""

    if not settings.open_browser_on_start:
        return

    url = gradio_url(settings)

    def _open() -> None:
        webbrowser.open(url)

    threading.Timer(settings.browser_open_delay_sec, _open).start()
