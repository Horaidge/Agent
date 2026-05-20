#!/usr/bin/env python3
"""Тест RAG: эмбеддинг запроса + match_telegram_rag_chunks в Supabase."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_CONTENT = ROOT.parent / "content" / ".env"

from dotenv import load_dotenv, dotenv_values


def load_env() -> None:
    load_dotenv(ROOT / ".env", override=True)
    if _CONTENT.is_file():
        extras = dotenv_values(_CONTENT)
        for name in (
            "SUPABASE_URL",
            "SUPABASE_SERVICE_ROLE_KEY",
            "SUPABASE_RAG_TABLE",
            "OPENAI_API_KEY",
            "OPENAI_PROXY_URL",
            "OPENAI_EMBEDDING_MODEL",
        ):
            if (os.environ.get(name) or "").strip():
                continue
            val = (extras.get(name) or "").strip()
            if val:
                os.environ[name] = val


def embed_query(text: str, model: str, api_key: str, proxy: str | None) -> list[float]:
    import httpx
    from openai import OpenAI

    http_client: httpx.Client | None = None
    if (proxy or "").strip():
        http_client = httpx.Client(proxy=proxy.strip(), timeout=120.0)
    cli = OpenAI(api_key=api_key, http_client=http_client)
    r = cli.embeddings.create(model=model, input=[text])
    return r.data[0].embedding


def to_pg_vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(str(x) for x in vec) + "]"


def parse_embedding(val: object) -> list[float] | None:
    if val is None:
        return None
    if isinstance(val, list):
        try:
            return [float(x) for x in val]
        except (TypeError, ValueError):
            return None
    if isinstance(val, str):
        s = val.strip()
        if s.startswith("[") and s.endswith("]"):
            inner = s[1:-1].split(",")
            try:
                return [float(x) for x in inner]
            except ValueError:
                return None
    return None


def cosine_sim(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return float("-inf")
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na <= 0 or nb <= 0:
        return float("-inf")
    return dot / (na * nb)


def search_local_fallback(client, table: str, query_vec: list[float], k: int) -> list[dict]:
    """Если RPC ещё не заведён — вытаскиваем эмбеддинги и считаем top-k локально."""
    rows: list[dict] = []
    page = 1000
    start = 0
    while True:
        end = start + page - 1
        res = (
            client.table(table)
            .select("id,content,source,metadata,embedding")
            .range(start, end)
            .execute()
        )
        chunk = res.data or []
        rows.extend(chunk)
        if len(chunk) < page:
            break
        start += page

    scored: list[tuple[float, dict]] = []
    for row in rows:
        emb = parse_embedding(row.get("embedding"))
        if not emb or len(emb) != len(query_vec):
            continue
        sim = cosine_sim(query_vec, emb)
        scored.append((sim, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    out = []
    for sim, row in scored[:k]:
        out.append(
            {
                "id": row.get("id"),
                "content": row.get("content"),
                "source": row.get("source"),
                "metadata": row.get("metadata"),
                "similarity": float(sim),
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Тест поиска RAG в Supabase")
    parser.add_argument("query", nargs="?", help="Текст запроса")
    parser.add_argument("-k", "--top", type=int, default=10, help="Сколько чанков вернуть (1–50)")
    parser.add_argument("--stdin", action="store_true", help="Читать запрос из stdin")
    parser.add_argument(
        "--local",
        action="store_true",
        help="Не вызывать RPC, только локальный top-k (медленнее, но без match_rag_chunks.sql)",
    )
    args = parser.parse_args()
    load_env()

    if args.stdin:
        query = sys.stdin.read().strip()
    else:
        query = (args.query or "").strip()
    if not query:
        print("Укажи текст запроса или передай --stdin", file=sys.stderr)
        return 1

    k = max(1, min(args.top, 50))
    url = (os.environ.get("SUPABASE_URL") or "").strip()
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    ak = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not url or not key:
        print("Нужны SUPABASE_URL и SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
        return 1
    if not ak:
        print("Нужен OPENAI_API_KEY", file=sys.stderr)
        return 1

    model = (os.environ.get("OPENAI_EMBEDDING_MODEL") or "text-embedding-3-small").strip()
    proxy = (os.environ.get("OPENAI_PROXY_URL") or "").strip() or None

    print(f"Модель эмбеддинга: {model}, top_k={k}\n--- запрос (фрагмент) ---\n{query[:500]}{'…' if len(query) > 500 else ''}\n")

    vec = embed_query(query, model, ak, proxy)
    if len(vec) != 1536:
        print(f"Ожидалась размерность 1536, получено {len(vec)}", file=sys.stderr)
        return 1

    try:
        from supabase import create_client
    except ImportError:
        print("pip install supabase openai httpx", file=sys.stderr)
        return 1

    client = create_client(url, key)
    table = (os.environ.get("SUPABASE_RAG_TABLE") or "telegram_rag_chunks").strip()
    rows: list[dict] = []
    if args.local:
        print("(режим --local: без RPC, полный скан таблицы)\n")
        rows = search_local_fallback(client, table, vec, k)
    else:
        lit = to_pg_vector_literal(vec)
        try:
            res = client.rpc(
                "match_telegram_rag_chunks",
                {"query_embedding": lit, "match_count": k},
            ).execute()
            rows = res.data or []
        except Exception as e:
            err = str(e)
            if "PGRST202" in err or "match_telegram_rag_chunks" in err:
                print(
                    "RPC нет в проекте — переключаюсь на локальный top-k "
                    "(для скорости на сервере выполни sql/match_rag_chunks.sql).\n",
                    file=sys.stderr,
                )
                rows = search_local_fallback(client, table, vec, k)
            else:
                print(f"Ошибка RPC match_telegram_rag_chunks: {e}", file=sys.stderr)
                return 2
    print(f"--- результаты: {len(rows)} шт. ---\n")
    for i, row in enumerate(rows, 1):
        sim = row.get("similarity")
        content = (row.get("content") or "")[:1200]
        src = row.get("source")
        rid = row.get("id")
        meta = row.get("metadata")
        tail = " …" if len(row.get("content") or "") > len(content) else ""
        print(f"### {i}. similarity={sim!r} id={rid} source={src!r}")
        if meta:
            print(f"    metadata: {json.dumps(meta, ensure_ascii=False)[:200]}…")
        print(content + tail)
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
