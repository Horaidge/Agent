#!/usr/bin/env python3
"""Импорт чанков из JSON (Mongo-экспорт) в Supabase telegram_rag_chunks + эмбеддинги OpenAI."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
_CONTENT = ROOT.parent / "content" / ".env"

from dotenv import load_dotenv, dotenv_values


def load_env() -> None:
    load_dotenv(ROOT / ".env", override=True)
    if _CONTENT.is_file():
        extras = dotenv_values(_CONTENT)
        for name in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_RAG_TABLE",
                     "OPENAI_API_KEY", "OPENAI_PROXY_URL", "OPENAI_EMBEDDING_MODEL"):
            if (os.environ.get(name) or "").strip():
                continue
            val = (extras.get(name) or "").strip()
            if val:
                os.environ[name] = val


def bson_norm(x: Any) -> Any:
    if isinstance(x, dict):
        if len(x) == 1 and "$oid" in x:
            return x["$oid"]
        if len(x) == 1 and "$date" in x:
            return x["$date"]
        return {str(k): bson_norm(v) for k, v in x.items()}
    if isinstance(x, list):
        return [bson_norm(i) for i in x]
    return x


def truncate_text(text: str, max_chars: int) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def delete_all_rows(client, table: str) -> None:
    """Удалить все строки (service_role обходит RLS)."""
    client.table(table).delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()


def embed_batches(texts: list[str], model: str, api_key: str, proxy: str | None) -> list[list[float]]:
    import httpx
    from openai import OpenAI

    http_client: httpx.Client | None = None
    if (proxy or "").strip():
        http_client = httpx.Client(proxy=proxy.strip(), timeout=120.0)
    cli = OpenAI(api_key=api_key, http_client=http_client)
    out: list[list[float]] = []
    bs = 48
    for i in range(0, len(texts), bs):
        chunk = texts[i : i + bs]
        r = cli.embeddings.create(model=model, input=chunk)
        # preserve order
        order = sorted(r.data, key=lambda d: d.index)
        out.extend([d.embedding for d in order])
        time.sleep(0.05)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("json_path", type=Path, help="Путь к JSON (массив объектов)")
    parser.add_argument("--truncate", action="store_true", help="Очистить таблицу перед импортом")
    parser.add_argument("--no-embed", action="store_true", help="Не считать эмбеддинги (embedding = null)")
    parser.add_argument("--max-chars", type=int, default=24000, help="Обрезка текста для API")
    parser.add_argument("--batch-insert", type=int, default=80)
    args = parser.parse_args()
    load_env()

    url = (os.environ.get("SUPABASE_URL") or "").strip()
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    table = (os.environ.get("SUPABASE_RAG_TABLE") or "telegram_rag_chunks").strip()
    if not url or not key:
        print("Нужны SUPABASE_URL и SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
        return 1

    if not args.json_path.is_file():
        print(f"Нет файла: {args.json_path}", file=sys.stderr)
        return 1

    raw = json.loads(args.json_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        print("Ожидается JSON-массив", file=sys.stderr)
        return 1

    rows_in: list[dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, dict) or "content" not in row:
            continue
        content = str(row.get("content") or "").strip()
        if not content:
            continue
        src = (row.get("source") or row.get("source_file") or "chunks_export").strip()
        meta = bson_norm(
            {
                "chunk_id": row.get("id"),
                "job_id": row.get("job_id"),
                "row_index": row.get("row_index"),
                "source_file": row.get("source_file"),
                "stage": row.get("stage"),
                "embedding_model": row.get("embedding_model"),
                **(row.get("metadata") if isinstance(row.get("metadata"), dict) else {}),
            }
        )
        rows_in.append({"source": src, "content": content, "metadata": meta})

    print(f"Записей к импорту: {len(rows_in)}")

    try:
        from supabase import create_client
    except ImportError:
        print("pip install supabase openai httpx", file=sys.stderr)
        return 1

    client = create_client(url, key)

    if args.truncate:
        print("Очистка таблицы...")
        delete_all_rows(client, table)

    texts = [truncate_text(r["content"], args.max_chars) for r in rows_in]
    truncated = sum(1 for t, r in zip(texts, rows_in) if len(t) < len(r["content"]))
    if truncated:
        print(f"Обрезано по длине (--max-chars): {truncated} шт.")

    embeddings: list[list[float] | None]
    if args.no_embed:
        embeddings = [None] * len(texts)
    else:
        ak = (os.environ.get("OPENAI_API_KEY") or "").strip()
        if not ak:
            print("Нет OPENAI_API_KEY — используй --no-embed или задай ключ", file=sys.stderr)
            return 1
        model = (os.environ.get("OPENAI_EMBEDDING_MODEL") or "text-embedding-3-small").strip()
        proxy = (os.environ.get("OPENAI_PROXY_URL") or "").strip() or None
        print(f"Эмбеддинги OpenAI ({model}), {len(texts)} текстов...")
        embeddings = embed_batches(texts, model, ak, proxy)

    bi = max(1, args.batch_insert)
    total = 0
    for start in range(0, len(rows_in), bi):
        batch_meta = rows_in[start : start + bi]
        batch_texts = texts[start : start + bi]
        batch_emb = embeddings[start : start + bi]
        payload = []
        for rec, t, emb in zip(batch_meta, batch_texts, batch_emb):
            item: dict[str, Any] = {
                "source": rec["source"],
                "content": t,
                "metadata": rec["metadata"],
            }
            if emb is not None:
                # PostgREST / pgvector: передаём как строку литерала vector
                item["embedding"] = "[" + ",".join(str(x) for x in emb) + "]"
            payload.append(item)
        try:
            client.table(table).insert(payload).execute()
        except Exception as e:
            print(f"Ошибка вставки батча offset={start}: {e}", file=sys.stderr)
            return 2
        total += len(payload)
        print(f"  вставлено {total}/{len(rows_in)}")

    print(f"Готово. Строк: {total}, таблица {table!r}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
