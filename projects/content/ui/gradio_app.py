"""Gradio: таблица последних входящих сообщений из MongoDB."""
from __future__ import annotations

import gradio as gr

from core.config.settings import Settings
from storage.repository import MessageRepository
from ui.banner import link_root_for_ui


def build_gradio_app(repository: MessageRepository, settings: Settings) -> gr.Blocks:
    def load_rows() -> list[list[str | int | float]]:
        rows = repository.list_recent_sync(limit=200)
        out: list[list[str | int | float]] = []
        for r in rows:
            media_note = ""
            if r.media:
                fn = r.media.get("file_name") or r.media.get("kind") or ""
                media_note = str(fn)[:300]
            out.append(
                [
                    r.created_at.isoformat(),
                    r.telegram_user_id,
                    r.telegram_chat_id,
                    r.telegram_message_id,
                    r.username or "",
                    r.message_type or "text",
                    media_note,
                    (r.text or "")[:500],
                    r.trace_id or "",
                ]
            )
        return out

    link_root = link_root_for_ui(settings)
    has_public = bool((settings.public_base_url or "").strip())
    dev_block = ""
    if settings.dev_debug_ui_enabled:
        dev_hint = (
            "HTTPS за nginx; при basic-auth введите логин и пароль из `.htpasswd`."
            if has_public
            else "только с этой машины (`DEV_DEBUG_UI=true` в ENV)."
        )
        dev_block = (
            "\n\n### Dev-консоль (сообщения + генерация изображений)\n"
            f"Эта страница — только **краткая таблица**. Список сообщений, детали, Qwen Image — "
            f"[открыть dev-консоль]({link_root}/dev/) ({dev_hint})\n"
        )
    else:
        dev_block = (
            "\n\n*Чтобы включить dev-консоль с полным трейсом:* задайте в ENV **`DEV_DEBUG_UI=true`**, "
            "перезапустите сервер, затем откройте `/dev/`.\n"
        )

    with gr.Blocks(
        title="Входящие сообщения",
        analytics_enabled=False,
    ) as demo:
        gr.Markdown(
            "## Входящие сообщения Telegram (MongoDB)\n"
            "Ниже — последние записи из коллекции (упрощённый вид)."
            + dev_block
        )
        table = gr.Dataframe(
            headers=[
                "Время (UTC)",
                "User ID",
                "Chat ID",
                "Message ID",
                "Username",
                "Тип",
                "Медиа (имя / вид)",
                "Текст / подпись",
                "trace_id",
            ],
            label="Последние сообщения",
            interactive=False,
        )
        refresh = gr.Button("Обновить")
        refresh.click(fn=load_rows, outputs=table)
        demo.load(fn=load_rows, outputs=table)

    return demo
