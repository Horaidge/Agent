#!/usr/bin/env python3
"""Создать таблицу RAG в Supabase (прямое подключение к Postgres) и вставить тестовую строку."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parents[1]
_CONTENT = ROOT.parent / "content" / ".env"

from dotenv import load_dotenv


def load_env() -> None:
    load_dotenv(ROOT / ".env", override=True)
    if _CONTENT.is_file():
        load_dotenv(_CONTENT, override=False)


def parse_project_ref(url: str) -> str:
    m = re.match(r"https://([^.]+)\.supabase\.co/?", url.strip(), re.I)
    if not m:
        raise SystemExit("SUPABASE_URL должен быть вида https://<ref>.supabase.co")
    return m.group(1)


def pooler_regions_try() -> list[str]:
    raw = (os.environ.get("SUPABASE_POOLER_REGION") or "").strip()
    if raw:
        return [raw]
    return [
        "eu-central-1",
        "eu-west-1",
        "eu-west-2",
        "eu-north-1",
        "us-east-1",
        "us-west-1",
        "ap-south-1",
        "ap-southeast-1",
    ]


def build_conninfo_candidates(url: str, password: str) -> list[str]:
    safe = quote_plus(password, safe="")
    ref = parse_project_ref(url)
    db_url = (os.environ.get("DATABASE_URL") or "").strip()
    out: list[str] = []
    if db_url:
        out.append(db_url)
        return out

    direct = f"postgresql://postgres:{safe}@db.{ref}.supabase.co:5432/postgres?sslmode=require"
    out.append(direct)

    port = int((os.environ.get("SUPABASE_POOLER_PORT") or "5432").strip() or "5432")
    if (os.environ.get("SUPABASE_USE_POOLER") or "").strip().lower() in ("1", "true", "yes"):
        for region in pooler_regions_try():
            host = f"aws-0-{region}.pooler.supabase.com"
            user = f"postgres.{ref}"
            out.append(f"postgresql://{user}:{safe}@{host}:{port}/postgres?sslmode=require")
        return out

    for region in pooler_regions_try():
        host = f"aws-0-{region}.pooler.supabase.com"
        user = f"postgres.{ref}"
        out.append(f"postgresql://{user}:{safe}@{host}:{port}/postgres?sslmode=require")
    return out


def connect_psycopg(conninfo_candidates: list[str]):
    import psycopg

    last_err: Exception | None = None
    for conninfo in conninfo_candidates:
        try:
            return psycopg.connect(conninfo, connect_timeout=25)
        except Exception as e:
            last_err = e
    if last_err:
        raise last_err
    raise RuntimeError("Нет строк подключения")


def split_sql_statements(raw: str) -> list[str]:
    text = "\n".join(
        line for line in raw.splitlines() if not line.strip().startswith("--")
    )
    return [s.strip() for s in text.split(";") if s.strip()]


def main() -> int:
    load_env()
    url = (os.environ.get("SUPABASE_URL") or "").strip()
    password = (os.environ.get("SUPABASE_DB_PASSWORD") or "").strip()
    if not url:
        print("Нужен SUPABASE_URL", file=sys.stderr)
        return 1
    if not password:
        print(
            "Нужен SUPABASE_DB_PASSWORD (пароль пользователя postgres из Supabase → Database).",
            file=sys.stderr,
        )
        return 1

    sql_path = ROOT / "sql" / "rag_chunks.sql"
    if not sql_path.is_file():
        print(f"Нет файла {sql_path}", file=sys.stderr)
        return 1

    try:
        import psycopg
    except ImportError:
        print("pip install -r requirements.txt", file=sys.stderr)
        return 1

    raw_sql = sql_path.read_text(encoding="utf-8")
    statements = split_sql_statements(raw_sql)

    candidates = build_conninfo_candidates(url, password)
    try:
        with connect_psycopg(candidates) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                for stmt in statements:
                    cur.execute(stmt)
                cur.execute(
                    """
                    insert into public.telegram_rag_chunks (source, content, metadata)
                    values ('bootstrap', %s, %s::jsonb)
                    returning id::text
                    """,
                    (
                        "Тест RAG: короткий текст для проверки. Бот может искать по базе.",
                        '{"bootstrap": true, "note": "можно удалить"}',
                    ),
                )
                row = cur.fetchone()
            print("OK: таблица и индексы применены, тестовая строка вставлена.")
            if row:
                print("id новой строки:", row[0])
    except Exception as e:
        print(f"Ошибка Postgres: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
