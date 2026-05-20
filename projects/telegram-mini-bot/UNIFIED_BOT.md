# Единый Telegram-бот «Мини-бот»

Одна точка входа: **режимы** (кнопки) + **инструменты** (модель вызывает сама). Нет эвристик по длине текста или слову «сон».

## Режимы (состояния)

| Кнопка | Режим | Назначение |
|--------|-------|------------|
| 💬 Общение | `chat` | Обычный диалог |
| 🌙 Толкование снов | `dream_interpret` | Интерпретация сна текстом |
| 🎬 Визуализация сна | `dream_visualize` | Dream Lite → mp4 (`generate_dream_video`) |
| 📁 Внутренняя база (скоро) | `internal_kb` | Будущий RAG по файлам |

Режим хранится в `data/modes/<chat_id>.json`.

## System prompt (две части файлов + режим)

| Слой | Файл | Поведение |
|------|------|-----------|
| **База** | `prompts/system.txt` | Всегда; список инструментов и правил |
| **Override** | `data/system_override.txt` | Опционально; **дополняет** базу, не заменяет |
| **Режим** | код (`modes.py`) | Подсказка в конец system на каждый запрос |

Команды: `/show_prompt`, `/prompt <override>`, `/reset_prompt` (только override).

После смены override (инструмент или `/prompt`) бот **перезапускается** (`scripts/restart_bot.sh`).

## Инструменты

- `update_system_prompt_override`
- `search_public_knowledge` (Supabase RAG)
- `search_internal_documents` (заглушка «скоро»)
- `generate_dream_video` (если Dream Lite включён в `.env`)
