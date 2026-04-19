"""Регистрация HTTP-маршрута webhook для Telegram (FastAPI + aiogram)."""
from __future__ import annotations

import uuid

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from fastapi import FastAPI, HTTPException, Request

from core.observability.context import current_trace_id
from core.observability.service import ObservabilityService
from core.observability.telegram_payload import (
    classify_update_type,
    extract_user_chat_ids,
)
from core.config.settings import Settings


def register_telegram_webhook(
    app: FastAPI,
    bot: Bot,
    dp: Dispatcher,
    settings: Settings,
    observability: ObservabilityService | None = None,
) -> None:
    """POST {webhook_path}: принимает Update от Telegram и отдаёт в Dispatcher."""

    secret = settings.telegram_webhook_secret

    @app.post(settings.webhook_path)
    async def telegram_webhook(request: Request) -> dict[str, bool]:
        if secret:
            token_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
            if token_header != secret:
                raise HTTPException(status_code=403, detail="Invalid webhook secret")

        try:
            body = await request.json()
        except Exception as exc:  # noqa: BLE001 — отдаём 400 клиенту Telegram
            raise HTTPException(status_code=400, detail="Invalid JSON") from exc

        trace_id = str(uuid.uuid4())
        current_trace_id.set(trace_id)
        try:
            if observability:
                uid, cid = extract_user_chat_ids(body)
                await observability.record_telegram_update(
                    trace_id=trace_id,
                    raw_body=body,
                    update_id=body.get("update_id"),
                    telegram_user_id=uid,
                    telegram_chat_id=cid,
                    update_type=classify_update_type(body),
                )
            update = Update.model_validate(body)
            await dp.feed_update(bot, update)
        finally:
            current_trace_id.set(None)

        return {"ok": True}
