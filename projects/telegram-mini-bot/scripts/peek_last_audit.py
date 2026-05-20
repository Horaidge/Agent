#!/usr/bin/env python3
"""Печатает последнюю запись аудита: что ушло в OpenAI (system + RAG) и ответ."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from audit_log import iter_turns  # noqa: E402


def main() -> int:
    turns = iter_turns(ROOT / "data", max_lines=8000)
    if not turns:
        print("Журнал пуст: data/audit/turns.jsonl. Напиши боту в Telegram.")
        return 1
    t = turns[-1]
    print("=== chat_id", t.get("chat_id"), "ts", t.get("ts"), "===")
    print("\n--- ПОЛНЫЙ ПЕРВЫЙ SYSTEM (META + prompt + RAG) ---\n")
    print((t.get("full_system_message") or "(нет в записи — старый лог)").strip())
    print("\n--- ИСТОРИЯ (усечённо) ---\n")
    print((t.get("history_summary") or "(пусто)").strip())
    print("\n--- ТОЛЬКО RAG-ЧАНКИ ---\n")
    print((t.get("rag_context") or "(пусто)").strip())
    print("\n--- USER ---\n")
    print((t.get("user") or "").strip())
    print("\n--- ASSISTANT ---\n")
    print((t.get("assistant") or "").strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
