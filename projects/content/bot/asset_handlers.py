"""Приём фото и классификация dream_assets через inline-кнопки."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from services.telegram_reply_keyboards import main_reply_keyboard
from services.assets.dream_asset_service import (
    ASSET_TYPE_CHARACTER,
    ASSET_TYPE_DREAM_OBJECT,
    ASSET_TYPE_ENVIRONMENT,
    ASSET_TYPE_FACE,
    ASSET_TYPE_LABELS,
    ASSET_TYPE_OTHER,
    DreamAssetService,
)

logger = logging.getLogger(__name__)

CALLBACK_PREFIX = "asset:set_type:"


def _callback_data(asset_id: str, asset_type: str) -> str:
    return f"{CALLBACK_PREFIX}{asset_id}:{asset_type}"


def _parse_callback(data: str) -> tuple[str, str] | None:
    if not data.startswith(CALLBACK_PREFIX):
        return None
    rest = data[len(CALLBACK_PREFIX) :]
    parts = rest.split(":", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return parts[0], parts[1]


def _classification_keyboard(asset_id: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=ASSET_TYPE_LABELS[ASSET_TYPE_FACE],
                callback_data=_callback_data(asset_id, ASSET_TYPE_FACE),
            )
        ],
        [
            InlineKeyboardButton(
                text=ASSET_TYPE_LABELS[ASSET_TYPE_ENVIRONMENT],
                callback_data=_callback_data(asset_id, ASSET_TYPE_ENVIRONMENT),
            )
        ],
        [
            InlineKeyboardButton(
                text=ASSET_TYPE_LABELS[ASSET_TYPE_DREAM_OBJECT],
                callback_data=_callback_data(asset_id, ASSET_TYPE_DREAM_OBJECT),
            )
        ],
        [
            InlineKeyboardButton(
                text=ASSET_TYPE_LABELS[ASSET_TYPE_CHARACTER],
                callback_data=_callback_data(asset_id, ASSET_TYPE_CHARACTER),
            )
        ],
        [
            InlineKeyboardButton(
                text=ASSET_TYPE_LABELS[ASSET_TYPE_OTHER],
                callback_data=_callback_data(asset_id, ASSET_TYPE_OTHER),
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def create_dream_asset_router(service: DreamAssetService) -> Router:
    r = Router(name="dream_assets")

    @r.message(F.photo)
    async def on_user_photo(message: Message) -> None:
        user = message.from_user
        if not user:
            return
        owner_uid = user.id
        photos = message.photo
        if not photos:
            return
        file_id = photos[-1].file_id
        chat_id = message.chat.id

        try:
            asset_id = await service.create_pending_asset(
                owner_user_id=owner_uid,
                telegram_user_id=owner_uid,
                chat_id=chat_id,
                telegram_file_id=file_id,
                source_message_id=message.message_id,
            )
        except Exception:
            logger.exception("create_pending_asset failed")
            await message.answer(
                "Не удалось сохранить изображение. Попробуйте ещё раз.",
                reply_markup=main_reply_keyboard(),
            )
            return

        await message.answer(
            "Что это за изображение?",
            reply_markup=_classification_keyboard(asset_id),
        )

    @r.callback_query(F.data.startswith(CALLBACK_PREFIX))
    async def on_asset_type_chosen(query: CallbackQuery) -> None:
        if not query.data or not query.from_user:
            await query.answer("Ошибка данных", show_alert=True)
            return

        parsed = _parse_callback(query.data)
        if not parsed:
            await query.answer("Некорректная кнопка", show_alert=True)
            return

        asset_id, type_key = parsed
        owner_id = query.from_user.id

        ok = await service.set_asset_type(
            asset_id,
            owner_user_id=owner_id,
            asset_type=type_key,
        )
        if not ok:
            await query.answer(
                "Нельзя обновить этот материал (чужой или устаревший).",
                show_alert=True,
            )
            return

        label = ASSET_TYPE_LABELS.get(type_key, type_key)
        await query.answer()
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:  # noqa: BLE001
            pass
        await query.message.answer(
            f"Изображение сохранено как: {label}",
            reply_markup=main_reply_keyboard(),
        )

    return r
