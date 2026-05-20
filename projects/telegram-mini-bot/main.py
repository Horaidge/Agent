"""Мини Telegram-бот: режимы, tools, база+override промпта. Long polling."""
from __future__ import annotations

import asyncio
import fcntl
import logging
import os
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from agent import ChatAgent
from config import ROOT, get_settings
from dream_callbacks import router as dream_callbacks_router
from dream_integration import dream_lite_enabled, get_dream_context
from mode_store import ModeStore
from modes import (
    ALL_MODE_BUTTONS,
    BTN_CHAT,
    BTN_CLEAR_HISTORY,
    BTN_DREAM_INTERPRET,
    BTN_DREAM_VISUALIZE,
    BTN_INTERNAL_KB,
    BUTTON_TO_MODE,
    SERVICE_BUTTONS,
    BotMode,
    mode_title,
)
from prompt_store import PromptStore
from restart import spawn_bot_restart

_LOCK_FP = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

TELEGRAM_SAFE_CHUNK = 4000


def reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_DREAM_INTERPRET), KeyboardButton(text=BTN_DREAM_VISUALIZE)],
            [KeyboardButton(text=BTN_CHAT), KeyboardButton(text=BTN_INTERNAL_KB)],
            [KeyboardButton(text=BTN_CLEAR_HISTORY)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def _acquire_single_instance_lock(data_dir: Path) -> None:
    global _LOCK_FP
    path = data_dir / "bot_run.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    _LOCK_FP = open(path, "a+", encoding="utf-8")
    try:
        fcntl.flock(_LOCK_FP.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(
            "Другой экземпляр бота уже держит lock (data/bot_run.lock). "
            "Останови: pgrep -af telegram-mini-bot.*main.py",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    _LOCK_FP.seek(0)
    _LOCK_FP.truncate()
    _LOCK_FP.write(str(os.getpid()) + "\n")
    _LOCK_FP.flush()


def split_for_telegram(text: str, limit: int = TELEGRAM_SAFE_CHUNK) -> list[str]:
    text = text or ""
    if len(text) <= limit:
        return [text] if text else ["…"]
    parts: list[str] = []
    rest = text
    while rest:
        if len(rest) <= limit:
            parts.append(rest)
            break
        chunk = rest[:limit]
        cut = chunk.rfind("\n\n")
        if cut < limit // 2:
            cut = chunk.rfind("\n")
        if cut < limit // 2:
            cut = limit
        parts.append(rest[:cut])
        rest = rest[cut:].lstrip("\n")
    return parts or ["…"]


async def main() -> None:
    settings = get_settings()
    store = PromptStore(settings.prompts_dir, settings.data_dir)
    mode_store = ModeStore(settings.data_dir)
    dream_on = dream_lite_enabled(settings)
    if dream_on and get_dream_context() is None:
        logger.warning("DREAM_LITE_ENABLED=1, но Dream Lite не инициализировался")
        dream_on = False

    agent = ChatAgent(settings, store, dream_pipeline_available=dream_on)
    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher()
    if dream_on:
        dp.include_router(dream_callbacks_router)

    kb = reply_keyboard()

    @dp.message(CommandStart())
    async def cmd_start(message: Message) -> None:
        cid = message.chat.id if message.chat else 0
        mode = mode_store.get_mode(cid) if cid else BotMode.CHAT
        site = settings.public_site_url.rstrip("/")
        await message.answer(
            f"Мини-бот Dzen.AI — единая точка входа.\n"
            f"Сайт: {site}\n\n"
            f"Сейчас режим: **{mode_title(mode)}**.\n\n"
            "Переключай режим кнопками внизу:\n"
            "• 💬 Общение\n"
            "• 🌙 Толкование снов\n"
            "• 🎬 Визуализация сна (Dream Lite)\n"
            "• 📁 Внутренняя база (скоро)\n\n"
            "Модель сама выбирает инструменты.\n"
            "/show_prompt — база + override\n"
            "/reset_prompt — удалить только override\n"
            "/prompt <текст> — записать override\n"
            "/mode — текущий режим",
            reply_markup=kb,
            parse_mode="Markdown",
        )

    @dp.message(Command("mode"))
    async def cmd_mode(message: Message) -> None:
        cid = message.chat.id if message.chat else 0
        m = mode_store.get_mode(cid)
        await message.answer(f"Режим: **{mode_title(m)}** (`{m.value}`)", parse_mode="Markdown")

    @dp.message(Command("show_prompt"))
    async def cmd_show_prompt(message: Message) -> None:
        cid = message.chat.id if message.chat else 0
        text = store.format_prompt_overview(mode_store.get_mode(cid))
        if len(text) > 3500:
            text = text[:3500] + "\n… (обрезано)"
        await message.answer(text)

    @dp.message(Command("reset_prompt"))
    async def cmd_reset_prompt(message: Message) -> None:
        if not settings.may_edit_prompt(message.from_user.id if message.from_user else 0):
            await message.answer("Нет прав менять prompt.")
            return
        store.reset_to_default()
        await message.answer("Override удалён. База prompts/system.txt без изменений. Перезапускаю бота…")
        spawn_bot_restart(ROOT)

    @dp.message(Command("prompt"))
    async def cmd_prompt(message: Message) -> None:
        uid = message.from_user.id if message.from_user else 0
        if not settings.may_edit_prompt(uid):
            await message.answer("Нет прав менять prompt.")
            return
        raw = (message.text or "").strip()
        parts = raw.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            await message.answer("Использование: /prompt <текст override>")
            return
        store.update_system_prompt(parts[1].strip())
        await message.answer("Override сохранён. Перезапускаю бота…")
        spawn_bot_restart(ROOT)

    async def _clear_this_chat(message: Message) -> None:
        if message.chat:
            store.clear_history(message.chat.id)
        await message.answer("История диалога очищена.", reply_markup=kb)

    @dp.message(Command("clear"))
    async def cmd_clear(message: Message) -> None:
        await _clear_this_chat(message)

    @dp.message(F.text == BTN_CLEAR_HISTORY)
    async def on_clear_button(message: Message) -> None:
        await _clear_this_chat(message)

    @dp.message(F.text.in_(ALL_MODE_BUTTONS))
    async def on_mode_button(message: Message) -> None:
        if not message.text or not message.chat:
            return
        new_mode = BUTTON_TO_MODE[message.text]
        mode_store.set_mode(message.chat.id, new_mode)
        extra = ""
        if new_mode == BotMode.INTERNAL_KB:
            extra = "\n\nПоиск по внутренним файлам и отдельный RAG — в разработке."
        elif new_mode == BotMode.DREAM_VISUALIZE and not dream_on:
            extra = "\n\nDream Lite на сервере не подключён (проверьте .env)."
        await message.answer(
            f"Режим: **{mode_title(new_mode)}**.{extra}\n\nМожно писать в чат.",
            reply_markup=kb,
            parse_mode="Markdown",
        )

    @dp.message(F.text)
    async def on_text(message: Message) -> None:
        if not message.text or not message.chat:
            return
        if message.text in SERVICE_BUTTONS | ALL_MODE_BUTTONS:
            return

        cid = message.chat.id
        mode = mode_store.get_mode(cid)
        await bot.send_chat_action(cid, "typing")
        try:
            result = await agent.reply_async(message, cid, message.text, mode)
        except Exception:
            logger.exception("agent error")
            await message.answer("Ошибка при обращении к модели. Проверьте OPENAI_API_KEY и прокси.")
            return

        if result.needs_restart:
            await message.answer(
                (result.text or "Готово.") + "\n\n_(override обновлён — перезапуск бота…)_",
                parse_mode="Markdown",
                reply_markup=kb,
            )
            spawn_bot_restart(ROOT)
            return

        if result.dream_pipeline_started and not (result.text or "").strip():
            return

        combined = result.text or "…"
        chunks = split_for_telegram(combined)
        for i, part in enumerate(chunks):
            await message.answer(part, parse_mode=None)
            if i < len(chunks) - 1:
                await bot.send_chat_action(cid, "typing")

    logger.info("Starting long polling (dream_lite=%s)", dream_on)
    await dp.start_polling(bot)


if __name__ == "__main__":
    _acquire_single_instance_lock(get_settings().data_dir)
    asyncio.run(main())
