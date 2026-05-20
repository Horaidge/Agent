"""Режимы работы мини-бота (состояния)."""
from __future__ import annotations

from enum import StrEnum


class BotMode(StrEnum):
    CHAT = "chat"
    DREAM_INTERPRET = "dream_interpret"
    DREAM_VISUALIZE = "dream_visualize"
    INTERNAL_KB = "internal_kb"


BTN_CHAT = "💬 Общение"
BTN_DREAM_INTERPRET = "🌙 Толкование снов"
BTN_DREAM_VISUALIZE = "🎬 Визуализация сна"
BTN_INTERNAL_KB = "📁 Внутренняя база (скоро)"
BTN_CLEAR_HISTORY = "🗑 Очистить историю"

BUTTON_TO_MODE: dict[str, BotMode] = {
    BTN_CHAT: BotMode.CHAT,
    BTN_DREAM_INTERPRET: BotMode.DREAM_INTERPRET,
    BTN_DREAM_VISUALIZE: BotMode.DREAM_VISUALIZE,
    BTN_INTERNAL_KB: BotMode.INTERNAL_KB,
}

ALL_MODE_BUTTONS = frozenset(BUTTON_TO_MODE)
SERVICE_BUTTONS = frozenset({BTN_CLEAR_HISTORY})


def mode_title(mode: BotMode) -> str:
    return {
        BotMode.CHAT: "Общение",
        BotMode.DREAM_INTERPRET: "Толкование снов",
        BotMode.DREAM_VISUALIZE: "Визуализация сна",
        BotMode.INTERNAL_KB: "Внутренняя база (скоро)",
    }[mode]


def mode_system_hint(mode: BotMode, *, dream_pipeline_available: bool) -> str:
    lines = [
        "\n\n## Текущий режим чата",
        f"Активный режим: **{mode_title(mode)}** (`{mode.value}`).",
        "Пользователь переключает режим кнопками внизу; учитывай режим, но сам выбирай инструменты по смыслу запроса.",
    ]
    if mode == BotMode.CHAT:
        lines.append(
            "Режим общения: диалог, вопросы о платформе, бытовые темы. "
            "Для фактов из публичной базы — `search_public_knowledge`. "
            "Для видео по сну — `generate_dream_video` (если пользователь явно просит ролик/визуализацию)."
        )
    elif mode == BotMode.DREAM_INTERPRET:
        lines.append(
            "Режим толкования снов: разворачивай сон цельным авторским текстом (см. override). "
            "Для стиля и опоры на тексты — `search_public_knowledge`. "
            "Не запускай видео без явной просьбы; для ролика — `generate_dream_video`."
        )
    elif mode == BotMode.DREAM_VISUALIZE:
        if dream_pipeline_available:
            lines.append(
                "Режим визуализации: когда пользователь описал сон и хочет ролик — "
                "вызови `generate_dream_video` с полным текстом сна. "
                "Можешь кратко уточнить деталь перед запуском, но не заменяй пайплайн длинным текстом."
            )
        else:
            lines.append(
                "Режим визуализации выбран, но пайплайн Dream Lite на сервере не подключён."
            )
    elif mode == BotMode.INTERNAL_KB:
        lines.append(
            "Режим внутренней базы в разработке. Используй `search_internal_documents` — "
            "инструмент пока сообщит о статусе. Не выдумывай содержимое файлов."
        )
    return "\n".join(lines)
