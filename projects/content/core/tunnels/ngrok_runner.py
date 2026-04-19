"""Запуск ngrok через pyngrok: один процесс — один HTTP-туннель на порт приложения."""
from __future__ import annotations

from pyngrok import conf, ngrok


def start_public_http_url(port: int, auth_token: str | None) -> str:
    """
    Поднимает ngrok на указанный порт, возвращает публичный URL (обычно https://....).

    Требуется NGROK_AUTH_TOKEN из личного кабинета ngrok (бесплатный аккаунт подходит).
    """
    if auth_token:
        conf.get_default().auth_token = auth_token.strip()

    # bind_tls=True — внешний URL с HTTPS (нужно для Telegram)
    tunnel = ngrok.connect(addr=port, proto="http", bind_tls=True)
    return tunnel.public_url


def stop_all() -> None:
    """Остановить все туннели текущего процесса."""
    ngrok.kill()
