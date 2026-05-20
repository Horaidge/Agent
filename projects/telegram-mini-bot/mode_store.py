"""Режим чата на пользователя (файл в data/modes/)."""
from __future__ import annotations

import json
from pathlib import Path

from modes import BotMode


class ModeStore:
    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "modes"
        self._dir.mkdir(parents=True, exist_ok=True)

    def get_mode(self, chat_id: int) -> BotMode:
        path = self._path(chat_id)
        if not path.is_file():
            return BotMode.CHAT
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            value = str(raw.get("mode") or BotMode.CHAT.value)
            return BotMode(value)
        except (json.JSONDecodeError, ValueError):
            return BotMode.CHAT

    def set_mode(self, chat_id: int, mode: BotMode) -> None:
        self._path(chat_id).write_text(
            json.dumps({"mode": mode.value}, ensure_ascii=False),
            encoding="utf-8",
        )

    def _path(self, chat_id: int) -> Path:
        return self._dir / f"{chat_id}.json"
