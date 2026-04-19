"""Обработчики входящих обновлений Telegram."""
from aiogram import F, Router
from aiogram.types import Message

from services.message_service import MessageService

router = Router(name="inbound_messages")


@router.message(F.text)
async def on_text_message(message: Message, message_service: MessageService) -> None:
    await message_service.handle_inbound_message(message)
