"""Журнал диалогов для мониторинга (одна строка JSON на ход)."""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _audit_path(data_dir: Path) -> Path:
    d = data_dir / "audit"
    d.mkdir(parents=True, exist_ok=True)
    return d / "turns.jsonl"


# Макс. размер полного system при записи в jsonl (символы)
AUDIT_FULL_SYSTEM_MAX_CHARS = 200_000


def append_turn(
    data_dir: Path,
    *,
    chat_id: int,
    user_text: str,
    assistant_text: str,
    rag_context: str,
    system_prompt: str,
    full_system_message: str,
    history_summary: str,
    model: str,
    override_prompt: str = "",
    mode: str = "",
) -> None:
    path = _audit_path(data_dir)
    fs = full_system_message or ""
    if len(fs) > AUDIT_FULL_SYSTEM_MAX_CHARS:
        fs = fs[: AUDIT_FULL_SYSTEM_MAX_CHARS - 30] + "\n… [обрезано в журнале]"
    rec: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "ts": datetime.now(UTC).isoformat(),
        "chat_id": chat_id,
        "user": user_text,
        "assistant": assistant_text,
        "rag_context": rag_context or "",
        "system_prompt": system_prompt or "",
        "override_prompt": override_prompt or "",
        "mode": mode or "",
        "full_system_message": fs,
        "history_summary": (history_summary or "")[:50_000],
        "model": model,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def iter_turns(data_dir: Path, *, max_lines: int = 5000) -> list[dict[str, Any]]:
    path = _audit_path(data_dir)
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    out: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def get_turn_by_id(data_dir: Path, turn_id: str) -> dict[str, Any] | None:
    for t in reversed(iter_turns(data_dir, max_lines=20000)):
        if t.get("id") == turn_id:
            return t
    return None
