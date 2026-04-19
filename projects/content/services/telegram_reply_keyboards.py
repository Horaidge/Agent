"""Общая reply keyboard для Telegram: главное меню данных пользователя."""
from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

MAIN_MENU_BUTTON_TEXT = "📋 Меню"


def main_reply_keyboard() -> ReplyKeyboardMarkup:
    """Постоянная клавиатура внизу чата (не inline). Повторно передаётся в ответах, чтобы кнопка всегда была доступна."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=MAIN_MENU_BUTTON_TEXT)]],
        resize_keyboard=True,
        is_persistent=True,
    )
