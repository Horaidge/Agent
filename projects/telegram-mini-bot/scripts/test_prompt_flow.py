"""Интеграционные тесты без Telegram: prompt + OpenAI."""
from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import get_settings
from agent import ChatAgent
from modes import BotMode
from prompt_store import PromptStore


def _fake_message() -> MagicMock:
    m = MagicMock()
    m.chat.id = 999001
    m.from_user.id = 1
    return m


async def _run() -> None:
    settings = get_settings()
    tmp = Path(tempfile.mkdtemp(prefix="mini-bot-test-"))
    try:
        prompts = tmp / "prompts"
        data = tmp / "data"
        prompts.mkdir()
        data.mkdir()
        shutil.copy(ROOT / "prompts" / "system.txt", prompts / "system.txt")

        store = PromptStore(prompts, data)
        agent = ChatAgent(settings, store, dream_pipeline_available=False)
        chat_id = 999001
        msg = _fake_message()

        base = store.read_base_prompt()
        assert "Dzen" in base or "инструмент" in base.lower(), "base prompt missing"

        r1 = await agent.reply_async(msg, chat_id, "Привет! Ответь одним словом: ок.", BotMode.CHAT)
        assert r1.text.strip(), "empty reply 1"
        print("reply1:", r1.text[:80].replace("\n", " "))

        marker = "TEST_MARKER_XYZ_42"
        r2 = await agent.reply_async(
            msg,
            chat_id,
            f"Обнови override: всегда начинай каждый ответ со слова {marker}. "
            "Используй update_system_prompt_override.",
            BotMode.CHAT,
        )
        print("reply2:", r2.text[:120].replace("\n", " "))
        print("prompt_updated:", r2.prompt_updated, "needs_restart:", r2.needs_restart)

        override = store.read_override_prompt()
        assert marker in override or r2.prompt_updated, "override should contain marker"

        r3 = await agent.reply_async(msg, chat_id, "Скажи только своё имя роли одним словом.", BotMode.CHAT)
        print("reply3:", r3.text[:120].replace("\n", " "))
        assert r3.text.strip(), "empty reply after prompt change"

        store.reset_to_default()
        assert marker not in store.read_override_prompt(), "reset failed"
        r4 = await agent.reply_async(msg, chat_id, "Ответь: восстановлено", BotMode.CHAT)
        print("reply4 after reset:", r4.text[:80].replace("\n", " "))
        assert r4.text.strip(), "empty reply after reset"

        print("ALL_PROMPT_TESTS_OK")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
