from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from modes import BotMode, mode_system_hint


class PromptStore:
    def __init__(self, prompts_dir: Path, data_dir: Path) -> None:
        self._base_path = prompts_dir / "system.txt"
        self._override_path = data_dir / "system_override.txt"
        self._backup_dir = data_dir / "backups"
        self._history_dir = data_dir / "chat_history"
        for p in (data_dir, self._backup_dir, self._history_dir):
            p.mkdir(parents=True, exist_ok=True)

    def read_base_prompt(self) -> str:
        return self._base_path.read_text(encoding="utf-8").strip()

    def read_override_prompt(self) -> str:
        if not self._override_path.is_file():
            return ""
        return self._override_path.read_text(encoding="utf-8").strip()

    def compose_system_prompt(
        self,
        mode: BotMode,
        *,
        dream_pipeline_available: bool,
    ) -> str:
        """База + override (если есть) + подсказка режима. База и override не сливаются в один файл."""
        parts = [self.read_base_prompt()]
        override = self.read_override_prompt()
        if override:
            parts.append(
                "\n\n## Дополнительные инструкции (override)\n"
                "Следуй этому блоку вместе с базой; при конфликте по стилю приоритет у override, "
                "по инструментам и безопасности — у базы.\n\n"
                + override
            )
        parts.append(mode_system_hint(mode, dream_pipeline_available=dream_pipeline_available))
        return "\n".join(parts)

    def read_system_prompt(self) -> str:
        """Совместимость: только база+override без режима (для старых вызовов)."""
        parts = [self.read_base_prompt()]
        override = self.read_override_prompt()
        if override:
            parts.append("\n\n## Дополнительные инструкции (override)\n\n" + override)
        return "\n".join(parts)

    def format_prompt_overview(self, mode: BotMode) -> str:
        override = self.read_override_prompt()
        lines = [
            f"Режим: {mode.value}",
            "",
            "=== Базовый промпт (prompts/system.txt) ===",
            self.read_base_prompt(),
        ]
        if override:
            lines.extend(
                [
                    "",
                    "=== Override (data/system_override.txt) ===",
                    override,
                ]
            )
        else:
            lines.append("\n(override не задан)")
        return "\n".join(lines)

    def update_system_prompt(self, new_text: str) -> None:
        """Обновить только override."""
        new_text = new_text.strip()
        if not new_text:
            raise ValueError("Пустой override")
        if self._override_path.is_file():
            self._backup_override()
        self._override_path.write_text(new_text + "\n", encoding="utf-8")

    def reset_to_default(self) -> None:
        """Удалить override; база system.txt не трогается."""
        if self._override_path.is_file():
            self._backup_override()
            self._override_path.unlink()

    def _backup_override(self) -> None:
        current = self.read_override_prompt()
        if not current:
            return
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        path = self._backup_dir / f"override_{stamp}.txt"
        path.write_text(current + "\n", encoding="utf-8")

    def load_history(self, chat_id: int) -> list[dict[str, str]]:
        path = self._history_path(chat_id)
        if not path.is_file():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        return [m for m in data if isinstance(m, dict) and m.get("role") in ("user", "assistant")]

    def append_history(self, chat_id: int, role: str, content: str, *, max_turns: int = 20) -> None:
        history = self.load_history(chat_id)
        history.append({"role": role, "content": content})
        history = history[-(max_turns * 2) :]
        self._history_path(chat_id).write_text(
            json.dumps(history, ensure_ascii=False, indent=0),
            encoding="utf-8",
        )

    def clear_history(self, chat_id: int) -> None:
        path = self._history_path(chat_id)
        if path.is_file():
            path.unlink()

    def _history_path(self, chat_id: int) -> Path:
        return self._history_dir / f"{chat_id}.json"
