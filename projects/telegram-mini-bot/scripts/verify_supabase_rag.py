#!/usr/bin/env python3
"""Проверка Supabase + таблицы RAG: подключение, чтение, опционально вставка тестового чанка."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv, dotenv_values


def load_env() -> None:
    load_dotenv(ROOT / ".env", override=True)
    content_env = ROOT.parent / "content" / ".env"
    if not content_env.is_file():
        return
    extras = dotenv_values(content_env)
    for name in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_RAG_TABLE"):
        if (os.environ.get(name) or "").strip():
            continue
        val = (extras.get(name) or "").strip()
        if val:
            os.environ[name] = val


def main() -> int:
    parser = argparse.ArgumentParser(description="Проверка Supabase RAG таблицы")
    parser.add_argument(
        "--insert-test",
        action="store_true",
        help="Вставить тестовую строку без эмбеддинга и удалить её",
    )
    args = parser.parse_args()
    load_env()

    url = (os.environ.get("SUPABASE_URL") or "").strip()
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    table = (os.environ.get("SUPABASE_RAG_TABLE") or "telegram_rag_chunks").strip()

    if not url or not key:
        print(
            "Задайте SUPABASE_URL и SUPABASE_SERVICE_ROLE_KEY "
            "(в telegram-mini-bot/.env или projects/content/.env).",
            file=sys.stderr,
        )
        return 1

    try:
        from supabase import create_client
    except ImportError:
        print("Установите зависимости: pip install -r requirements.txt", file=sys.stderr)
        return 1

    client = create_client(url, key)
    try:
        res = (
            client.table(table)
            .select("id", count="exact")
            .limit(1)
            .execute()
        )
    except Exception as e:
        print(f"Ошибка запроса к {table!r}: {e}", file=sys.stderr)
        print(
            "Убедись, что sql/rag_chunks.sql выполнен в SQL Editor проекта Supabase.",
            file=sys.stderr,
        )
        return 2

    cnt = getattr(res, "count", None)
    print(f"OK: таблица {table!r} доступна, всего строк (count): {cnt}")

    if args.insert_test:
        ins = (
            client.table(table)
            .insert(
                {
                    "source": "verify_supabase_rag.py",
                    "content": "Тестовый чанк для проверки RAG. Можно удалить.",
                    "metadata": {"test": True},
                }
            )
            .execute()
        )
        rows = ins.data or []
        if not rows:
            print("Вставка не вернула строку", file=sys.stderr)
            return 3
        rid = rows[0].get("id")
        print(f"Вставлена тестовая строка id={rid!r}")
        if rid:
            client.table(table).delete().eq("id", rid).execute()
            print("Тестовая строка удалена.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
