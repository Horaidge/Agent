"""Сборка полного HTTPS URL webhook из настроек (env)."""
from __future__ import annotations

from core.config.settings import Settings
from core.tunnels.cloudflare_tunnel import get_current_tunnel_url, read_persisted_tunnel_base_url


def resolve_telegram_webhook_url(settings: Settings) -> str:
    """
    Возвращает URL, который нужно передать в setWebhook.

    Приоритет (важно при смене trycloudflare на каждом запуске):
    1. Актуальный базовый URL из процесса main (get_current_tunnel_url).
    2. Или из data/runtime/current_tunnel.txt (отдельный run_cloudflared_tunnel.py).
    3. TELEGRAM_WEBHOOK_URL — только если туннель не дал URL (иначе возможен «старый» адрес в Telegram).
    4. PUBLIC_BASE_URL + WEBHOOK_PATH — то же условие.

    Итог для setWebhook: ``{база trycloudflare или env}{WEBHOOK_PATH}``.
    """
    tunnel = (get_current_tunnel_url() or "").strip()
    if not tunnel:
        tunnel = read_persisted_tunnel_base_url(
            settings.data_dir / "runtime" / "current_tunnel.txt",
        ).strip()
    if tunnel:
        path = settings.webhook_path or "/webhook"
        if not path.startswith("/"):
            path = "/" + path
        return f"{tunnel.rstrip('/')}{path}"

    direct = (settings.telegram_webhook_url or "").strip()
    if direct:
        return direct.rstrip("/")

    base = (settings.public_base_url or "").strip()
    if not base:
        msg = (
            "Задайте TELEGRAM_WEBHOOK_URL (полный HTTPS URL до webhook) "
            "или PUBLIC_BASE_URL вместе с WEBHOOK_PATH."
        )
        raise ValueError(msg)

    path = settings.webhook_path or "/webhook"
    if not path.startswith("/"):
        path = "/" + path
    return f"{base.rstrip('/')}{path}"
